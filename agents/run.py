"""Autodata-style Gemma pipeline over SEC bonds.

Roles (Autodata decomposition):
  extract  : one SEC doc  -> grounded structured node       (the "source of law")
  compare  : two near-dup extracts -> the contrastive delta edge
  verify   : drop any difference not supported by the extracts (grounding gate)

Candidate pairs are NOT all-N^2: we bucket by sector (SIC) and take top-k nearest
neighbours by cheap bag-of-words similarity over the symbolic extract — sparse, "linear".

Works most-recent-first; checkpoints nodes_<prefix>.jsonl / edges_<prefix>.jsonl per day.
"""
from __future__ import annotations
import argparse, json, math, sys, time, pathlib
import concurrent.futures as cf
from collections import defaultdict
from datetime import date, timedelta

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # import bondsec.py (SEC fetch/discovery)
sys.path.insert(0, str(HERE))                 # import gemma.py
import bondsec as B
import gemma as G

# --- compact doctrine (token-frugal version of fi_agent_doctrine.md) ----------
DOCTRINE = (
 "You are a fixed-income extraction agent reading U.S. SEC bond filings. Rules that OVERRIDE helpfulness: "
 "1) GROUNDING: never output a value not literally in the text; if absent use null. Admitting a gap is correct; inventing is not. "
 "2) EXTRACT, don't compute: report only stated figures; never derive yields/prices/totals. "
 "3) Don't infer classification; surface nuance (flag subordinated/144A/callable); never silently reclassify. "
 "4) Output ONLY JSON. No prose, no fences. "
 "FI facts LLMs get wrong: price=points(%par); callable->relevant yield is YTW not YTM; Moody's reversed (Aaa best); "
 "IG/HY not derivable from price; subordinated notes of high-grade issuers carry a HY instrument rating but trade high-grade; "
 "144A CUSIPs often not in the filing; offering amount(static) != outstanding(dynamic).")

EXTRACT_SCHEMA = ('{"is_bond":bool,"doc_type":str,"lifecycle_stage":"intent|priced|closed|registered|other",'
 '"issuer":str,"tranches":[{"series":str,"coupon_pct":num|null,"coupon_type":str|null,"maturity_year":int|null,'
 '"principal_usd":int|null,"seniority":str|null,"secured":bool|null,"callable":bool|null,"cusip":str|null}],'
 '"guarantees":str|null,"key_covenants":[str],"salient_features":[str],"is_144a":bool|null}')

COMPARE_SCHEMA = ('{"relationship":"supersedes|sibling_tranche|shelf_variant|reopening|same_issuer_comparable|'
 'cross_issuer_comparable|unrelated","identical_fields":[str],'
 '"differences":[{"field":str,"a":str,"b":str,"why_it_matters":str}],"materiality":num,"summary":str}')


def extract(doc_text: str, meta: dict) -> dict | None:
    excerpt = doc_text[:4500]
    user = (f"Filing form={meta['form']} issuer={meta['issuer']} date={meta['date']}.\n"
            f"Extract this bond filing into the schema. Use null for anything not in the text.\n"
            f"SCHEMA: {EXTRACT_SCHEMA}\n\nFILING TEXT:\n{excerpt}")
    out = G.chat_json([{"role": "system", "content": DOCTRINE}, {"role": "user", "content": user}], max_tokens=850)
    if isinstance(out, dict):
        out["_meta"] = meta
    return out


def compare(a: dict, b: dict) -> dict | None:
    def slim(n):
        return {k: n.get(k) for k in ("issuer", "doc_type", "lifecycle_stage", "tranches",
                                      "seniority", "is_144a", "guarantees", "salient_features")}
    user = (f"Two SEC bond extracts an automated step flagged as near-identical (A,B). "
            f"Find the EXACT material differences; only report a difference present in the extracts. "
            f"Classify the relationship. Output ONLY JSON.\nSCHEMA: {COMPARE_SCHEMA}\n\n"
            f"A({a['_meta']['id']}): {json.dumps(slim(a))}\n\nB({b['_meta']['id']}): {json.dumps(slim(b))}")
    return G.chat_json([{"role": "system", "content": DOCTRINE}, {"role": "user", "content": user}], max_tokens=700)


def verify(edge: dict) -> dict:
    """Grounding gate: keep only differences with non-empty, actually-differing values."""
    if not isinstance(edge, dict):
        return {}
    diffs = [d for d in edge.get("differences", []) if isinstance(d, dict)
             and str(d.get("a", "")).strip() and str(d.get("a")) != str(d.get("b"))]
    edge["differences"] = diffs
    m = edge.get("materiality")
    if isinstance(m, (int, float)) and m > 1:            # gemma sometimes uses a 0-10 scale
        edge["materiality"] = round(min(m / 10.0, 1.0), 2)
    edge["_verified"] = True
    return edge


# --- candidate pairs: sector bucket + bag-of-words kNN (sparse, not all-pairs) ---
def _profile(node: dict) -> set:
    toks = set()
    toks.update(str(node.get("issuer", "")).lower().split())
    for f in node.get("salient_features", []) or []:
        toks.update(str(f).lower().split())
    for t in node.get("tranches", []) or []:
        toks.add(f"mat{t.get('maturity_year')}"); toks.add(str(t.get("seniority", "")).lower())
    return {x for x in toks if len(x) > 2}

def _sim(a: set, b: set) -> float:
    if not a or not b: return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))

def candidate_pairs(nodes: list[dict], k: int = 3, min_sim: float = 0.18) -> list[tuple]:
    by_sector = defaultdict(list)
    for i, n in enumerate(nodes):
        by_sector[n["_meta"].get("sector", "?")].append(i)
    profs = [_profile(n) for n in nodes]
    pairs, seen = [], set()
    for sector, idxs in by_sector.items():
        for ii in idxs:
            sims = sorted(((_sim(profs[ii], profs[jj]), jj) for jj in idxs if jj != ii), reverse=True)[:k]
            for s, jj in sims:
                if s < min_sim: continue
                key = (min(ii, jj), max(ii, jj))
                if key in seen: continue
                seen.add(key); pairs.append((ii, jj, round(s, 3)))
    return pairs


# --- SEC discovery (most-recent-first) with sector ----------------------------
_SIC_SECTOR = {  # coarse SIC division -> sector label
    "0": "Agriculture", "1": "Mining/Energy", "2": "Manufacturing", "3": "Manufacturing",
    "4": "Transport/Utilities", "5": "Trade", "6": "Finance/RealEstate", "7": "Services",
    "8": "Services", "9": "Public"}
def _sector(sics):
    s = str((sics or ["0"])[0]).zfill(4)
    return _SIC_SECTOR.get(s[0], "Other") + f"/{s[:2]}"

def discover_window(startdt: str, enddt: str, forms: str) -> list[dict]:
    """Return bond-form filing hits in [startdt,enddt], most-recent-first, with sector."""
    resp = B.efts(forms=forms, startdt=startdt, enddt=enddt)
    total = resp.get("hits", {}).get("total", {}).get("value", 0)
    raw = list(resp.get("hits", {}).get("hits", []))
    frm = 100
    while len(raw) < total and frm < 10000:
        raw += B.efts(forms=forms, startdt=startdt, enddt=enddt, frm=frm).get("hits", {}).get("hits", [])
        frm += 100
    out = []
    for h in raw:
        _id = h.get("_id", ""); s = h.get("_source", {})
        if ":" not in _id: continue
        acc, fname = _id.split(":", 1)
        cik = str(int((s.get("ciks") or ["0"])[0]))
        out.append({"id": acc, "accession": acc, "file": fname, "cik": cik, "form": s.get("form", ""),
                    "date": s.get("file_date", ""), "issuer": (s.get("display_names") or [""])[0],
                    "sector": _sector(s.get("sics")),
                    "doc_url": f"{B.ARCHIVES}/{cik}/{acc.replace('-','')}/{fname}"})
    out.sort(key=lambda d: d["date"], reverse=True)   # most-recent-first
    return out


def fetch_and_extract(hit: dict) -> dict | None:
    try:
        text = B.html_to_text(B.fetch(hit["doc_url"]))
    except Exception as e:
        return {"_error": f"fetch:{e}", "_meta": hit}
    node = extract(text, hit)
    if isinstance(node, dict) and "_error" not in node:
        node["_meta"] = hit
    return node


def run(days: int, forms: str, max_docs: int | None, prefix: str, end: str | None):
    enddt = date.fromisoformat(end) if end else date.today()
    startdt = enddt - timedelta(days=days - 1)
    log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    log(f"discover {startdt}..{enddt} forms={forms}")
    hits = discover_window(startdt.isoformat(), enddt.isoformat(), forms)
    log(f"discovered {len(hits)} bond-form filings (most-recent-first)")
    if max_docs: hits = hits[:max_docs]

    npath = HERE.parent / f"graph/nodes_{prefix}.jsonl"
    epath = HERE.parent / f"graph/edges_{prefix}.jsonl"
    spath = HERE.parent / f"graph/STATUS_{prefix}.json"
    def status(**kw):
        spath.write_text(json.dumps({"window": f"{startdt}..{enddt}", "discovered": len(hits),
                                     "gemma": G.stats(), **kw}))
    G.METRICS_PATH = str(HERE.parent / f"graph/metrics_{prefix}.jsonl"); open(G.METRICS_PATH, "w").close()
    t_start = time.time()

    log(f"EXTRACT: {len(hits)} docs via gemma-4-31b (workers={G.MAX_WORKERS})...")
    nodes, done = [], 0
    with open(npath, "w") as nf, cf.ThreadPoolExecutor(max_workers=G.MAX_WORKERS) as ex:
        futs = [ex.submit(fetch_and_extract, h) for h in hits]
        for fut in cf.as_completed(futs):
            done += 1
            try: n = fut.result()
            except Exception: n = None
            if isinstance(n, dict) and n.get("is_bond") and "_error" not in n:
                nodes.append(n); nf.write(json.dumps(n) + "\n"); nf.flush()
            if done % 100 == 0 or done == len(hits):
                log(f"  extract {done}/{len(hits)} | bonds={len(nodes)} | {G.stats()}")
                status(phase="extract", extracted=done, bonds=len(nodes))
    t_ex = time.time()
    log(f"EXTRACT done: {len(nodes)} bond nodes (of {len(hits)}) in {round(t_ex-t_start)}s")

    pairs = candidate_pairs(nodes, k=3)
    log(f"CANDIDATE PAIRS: {len(pairs)} (sector-bucketed kNN, not {len(nodes)*(len(nodes)-1)//2} all-pairs)")
    status(phase="compare", bonds=len(nodes), pairs=len(pairs), edges=0)

    def cmp_pair(p):
        i, j, sim = p
        edge = verify(compare(nodes[i], nodes[j]))
        if edge:
            edge["src"] = nodes[i]["_meta"]["id"]; edge["dst"] = nodes[j]["_meta"]["id"]
            edge["candidate_sim"] = sim
        return edge
    log(f"COMPARE: {len(pairs)} pairs via gemma-4-31b...")
    nedges, cdone = 0, 0
    with open(epath, "w") as ef, cf.ThreadPoolExecutor(max_workers=G.MAX_WORKERS) as ex:
        futs = [ex.submit(cmp_pair, p) for p in pairs]
        for fut in cf.as_completed(futs):
            cdone += 1
            try: e = fut.result()
            except Exception: e = None
            if isinstance(e, dict) and e.get("differences"):
                ef.write(json.dumps(e) + "\n"); ef.flush(); nedges += 1
            if cdone % 100 == 0 or cdone == len(pairs):
                log(f"  compare {cdone}/{len(pairs)} | edges={nedges} | {G.stats()}")
                status(phase="compare", bonds=len(nodes), pairs=len(pairs), compared=cdone, edges=nedges)
    t_cmp = time.time()
    status(phase="done", bonds=len(nodes), pairs=len(pairs), edges=nedges)
    mpath = HERE.parent / f"graph/METRICS_{prefix}.json"
    G.write_summary(str(mpath), {"phase_seconds": {"extract": round(t_ex - t_start, 1),
        "compare": round(t_cmp - t_ex, 1), "total": round(t_cmp - t_start, 1)},
        "docs_discovered": len(hits), "bond_nodes": len(nodes), "edges": nedges})
    log(f"DONE: {len(nodes)} nodes, {nedges} grounded edges in {round(t_cmp-t_start)}s")
    log("METRICS: " + json.dumps(G.summary()))
    log(f"-> {npath.name}, {epath.name}, {mpath.name}, metrics_{prefix}.jsonl")
    return len(nodes), nedges


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--forms", default="424B5,FWP")
    ap.add_argument("--max-docs", type=int, default=None)
    ap.add_argument("--prefix", default="run")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    run(a.days, a.forms, a.max_docs, a.prefix, a.end)
