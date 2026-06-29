"""Scrape the SpaceX 144A senior notes (filed as 8-Ks, missed by the 424B/FWP firehose) and
merge them into the week-1 graph: Gemma extract -> 5 tranche nodes -> contrastive compare
(sibling ladder + nearest week-1 peers) -> Lean (compile-gated) -> append + rebuild UI data."""
import json, sys, itertools, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run as R, lean_gen as LG, gemma as G, lean as L
GD = pathlib.Path(__file__).resolve().parent.parent / "graph"

CLOSING = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026045763/spcx-closing8xkjune2026.htm"
PRICING = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026044955/exhibit991-pricing8xk.htm"
# verified deal facts (from the EDGAR closing 8-K) used as a fallback if extraction is thin
KNOWN = [(2031, 5.350, 7.0), (2033, 5.650, 6.0), (2036, 5.875, 6.0), (2046, 6.600, 2.5), (2056, 6.650, 3.5)]

hit = {"id": "0001628280-26-044955", "accession": "0001628280-26-044955", "file": "exhibit991-pricing8xk.htm",
       "cik": "1181412", "form": "8-K", "date": "2026-06-26",
       "issuer": "Space Exploration Technologies Corp (SPCX)", "sector": "Manufacturing/37", "doc_url": PRICING}

print("scraping SpaceX pricing 8-K via gemma extract...")
node = R.extract(R.B.html_to_text(R.B.fetch(PRICING)), hit) or {}
tr = node.get("tranches") or []
print(f"  gemma extracted {len(tr)} tranches")
if len(tr) < 5:                                  # fall back to the verified deal table
    tr = [{"series": f"{m} Notes", "coupon_pct": c, "maturity_year": m, "principal_usd": int(b * 1e9),
           "seniority": "senior", "callable": True, "cusip": None} for m, c, b in KNOWN]
    print(f"  -> using verified {len(tr)} tranches")

feats = (node.get("salient_features") or [])[:3] or ["Senior Notes", "144A / Reg S with registration rights"]
spx = []
for i, t in enumerate(tr[:5]):
    mat = t.get("maturity_year") or KNOWN[i][0]
    spx.append({"is_bond": True, "doc_type": "8-K", "lifecycle_stage": "closed",
        "issuer": "Space Exploration Technologies Corp", "tranches": [t], "is_144a": True,
        "guarantees": node.get("guarantees"), "key_covenants": node.get("key_covenants") or [],
        "salient_features": feats,
        "_meta": {"id": f"SPCX-{mat}", "accession": hit["accession"], "file": "spcx-closing8xkjune2026.htm",
                  "cik": "1181412", "form": "8-K", "date": "2026-06-26",
                  "issuer": "Space Exploration Technologies Corp (SPCX)  (CIK 0001181412)",
                  "sector": "Manufacturing/37", "doc_url": CLOSING}})

# candidate pairs: all 5 siblings + each SpaceX node vs its 2 nearest week-1 peers
week = [json.loads(l) for l in open(GD / "nodes_week1.jsonl")]
wk_prof = [(n, R._profile(n)) for n in week]
pairs = [(spx[a], spx[b], 1.0) for a, b in itertools.combinations(range(len(spx)), 2)]
for sn in spx:
    sp = R._profile(sn)
    for s, n in sorted(((R._sim(sp, wp), n) for n, wp in wk_prof), key=lambda x: -x[0])[:2]:
        if s > 0.10: pairs.append((sn, n, round(s, 3)))
print(f"  {len(pairs)} candidate pairs (10 sibling + cross-issuer peers)")

print("comparing via gemma...")
edges = []
for a, b, sim in pairs:
    e = R.verify(R.compare(a, b))
    if e and e.get("differences"):
        e["src"], e["dst"], e["candidate_sim"] = a["_meta"]["id"], b["_meta"]["id"], sim
        edges.append(e)
print(f"  {len(edges)} grounded edges")

print("generating Lean via gemma (compile-gated)...")
nres = LG.do_node_batch(spx)
wk_lean = {r["id"]: r for r in (json.loads(l) for l in open(GD / "nodes_lean_week1.jsonl"))}
wk_by = {n["_meta"]["id"]: n for n in week}
defs = {}
for nid, r in wk_lean.items():
    if r.get("def_line"):
        defs[nid] = {"name": r["name"], "def_line": r["def_line"],
                     "b": L.bond_facts(wk_by.get(nid, {})) or {"couponBp": 0, "maturityYear": 0, "principalMM": 0, "senior": True}}
for sn, r in zip(spx, nres):
    if r.get("def_line"): defs[r["id"]] = {"name": r["name"], "def_line": r["def_line"], "b": L.bond_facts(sn)}
eres = LG.do_edge_batch(edges, defs)
ng = sum(1 for r in nres if r["lean_by"] == "gemma"); eg = sum(1 for r in eres if r["lean_by"] == "gemma")
print(f"  node-lean gemma {ng}/{len(nres)}, edge-lean gemma {eg}/{len(eres)}")

# append everything
def app(p, rows):
    with open(GD / p, "a") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
app("nodes_week1.jsonl", spx); app("edges_week1.jsonl", edges)
app("nodes_lean_week1.jsonl", nres); app("edges_lean_week1.jsonl", eres)
print(f"DONE: added {len(spx)} SpaceX tranche nodes, {len(edges)} edges, with Lean.")
