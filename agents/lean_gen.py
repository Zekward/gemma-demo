"""Gemma-generated Lean (parallel + BATCHED on Cerebras) with a real compile gate + fallback.

Speed: we are request-bound on Cerebras (~85 req/min), so we BATCH ~15 bonds per call
(7,626 calls -> ~500). Reliability: each batch is compile-gated by the real Lean 4 toolchain;
anything that doesn't compile falls back to the deterministic template (always compiles).
Safety: results are written INCREMENTALLY (append + flush) and the run is RESUMABLE — a
teardown loses at most one in-flight batch.
"""
from __future__ import annotations
import json, sys, time, threading, pathlib
import concurrent.futures as cf
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gemma as G
import lean as L

NODE_BATCH = 15
EDGE_BATCH = 15

NODE_SYS = (
"You are a Lean 4 code generator. Output ONLY valid Lean 4 source — no markdown/fences/prose/imports/Mathlib/comments.\n"
"A structure is ALREADY defined (do NOT redefine): structure Bond where couponBp:Nat; maturityYear:Nat; principalMM:Nat; senior:Bool\n"
"You are given MULTIPLE bonds (one per line). For EACH bond emit, using its EXACT NAME:\n"
"  def <NAME> : Bond := { couponBp := <Nat>, maturityYear := <Nat>, principalMM := <Nat>, senior := <Bool> }\n"
"  then 2-4 lines `theorem <NAME>_pK : <prop> := by decide` — each a TRUE statement about <NAME>'s fields.\n"
"Use ONLY Nat/Bool, equalities and Nat <,>,≤,≥. Every theorem MUST be true for the given values. "
"Concatenate all bonds' code, nothing else.")

EDGE_SYS = (
"You are a Lean 4 code generator. Output ONLY valid Lean 4 source — no markdown/fences/prose/imports/comments.\n"
"Bonds are ALREADY defined as values of `structure Bond where couponBp:Nat; maturityYear:Nat; principalMM:Nat; senior:Bool`.\n"
"You are given MULTIPLE edges (one per line), each with an EDGENAME and two bonds A,B with their field values.\n"
"For EACH edge emit 2-3 lines `theorem <EDGENAME>_rK : <prop> := by decide` comparing A and B's fields "
"(e.g. A.couponBp < B.couponBp, A.maturityYear ≤ B.maturityYear, (A.senior = B.senior) = <Bool>). "
"Use ONLY the two given def names and Nat/Bool. Every theorem MUST be true for the given values. Concatenate all, nothing else.")


def _clean(s: str) -> str:
    s = s.strip()
    for f in ("```lean", "```"): s = s.removeprefix(f).strip()
    return s.removesuffix("```").strip()

def _chunks(xs, n):
    for i in range(0, len(xs), n): yield xs[i:i + n]

def _parse_node_blocks(src: str) -> dict:
    blocks, cur, buf = {}, None, []
    for ln in src.splitlines():
        if ln.strip().startswith("def ") and " : Bond" in ln:
            if cur: blocks[cur] = "\n".join(buf)
            cur = ln.strip().split()[1]; buf = [ln]
        elif cur is not None:
            buf.append(ln)
    if cur: blocks[cur] = "\n".join(buf)
    return blocks

def _node_template(nid, b):
    det = L.node_lean(nid, b)
    return {"id": nid, "name": L._name(nid), "lean": det["lean"], "lean_by": "template",
            "lean_verified": True, "verified_facts": det["verified_facts"],
            "def_line": det["lean"].splitlines()[0]}

def do_node_batch(batch):
    items = []
    for n in batch:
        b = L.bond_facts(n)
        if not b: continue
        nid = n.get("_meta", {}).get("id") or n.get("id")
        items.append((nid, L._name(nid), b))
    if not items: return []
    user = "\n".join(f"NAME={nm} couponBp={b['couponBp']} maturityYear={b['maturityYear']} "
                     f"principalMM={b['principalMM']} senior={str(b['senior']).lower()}" for _, nm, b in items)
    try: raw = _clean(G.chat([{"role": "system", "content": NODE_SYS}, {"role": "user", "content": user}], max_tokens=2400)[0])
    except Exception: raw = ""
    blk = _parse_node_blocks(raw)
    present = [(nid, nm, b, blk[nm]) for nid, nm, b in items if blk.get(nm)]
    out = []
    if present and L.compile_lean(L.PREAMBLE + "\n" + "\n".join(x[3] for x in present))[0]:
        for nid, nm, b, code in present:
            out.append({"id": nid, "name": nm, "lean": code, "lean_by": "gemma", "lean_verified": True,
                        "def_line": next((l for l in code.splitlines() if l.strip().startswith("def ")), "")})
        done = {x[0] for x in present}
        out += [_node_template(nid, b) for nid, nm, b in items if nid not in done]
    else:                                   # salvage per-item
        for nid, nm, b in items:
            code = blk.get(nm)
            if code and L.compile_lean(L.PREAMBLE + "\n" + code)[0]:
                out.append({"id": nid, "name": nm, "lean": code, "lean_by": "gemma", "lean_verified": True,
                            "def_line": next((l for l in code.splitlines() if l.strip().startswith("def ")), "")})
            else:
                out.append(_node_template(nid, b))
    return out


def do_edge_batch(batch, defs):
    items = []
    for e in batch:
        a, d = e.get("src"), e.get("dst")
        if a in defs and d in defs:
            en = L._name(a) + "_" + L._name(d)
            items.append((a, d, en, defs[a], defs[d]))
    if not items: return []
    user = "\n".join(f"EDGENAME={en} A={da['name']}(couponBp={da['b']['couponBp']},maturityYear={da['b']['maturityYear']},senior={str(da['b']['senior']).lower()}) "
                     f"B={db['name']}(couponBp={db['b']['couponBp']},maturityYear={db['b']['maturityYear']},senior={str(db['b']['senior']).lower()})"
                     for a, d, en, da, db in items)
    try: raw = _clean(G.chat([{"role": "system", "content": EDGE_SYS}, {"role": "user", "content": user}], max_tokens=2000)[0])
    except Exception: raw = ""
    lines = raw.splitlines()
    head = L.PREAMBLE + "\n" + "\n".join(sorted({da["def_line"] for *_, da, _ in items} | {db["def_line"] for *_, db in items})) + "\n"
    out = []
    for a, d, en, da, db in items:
        th = [l for l in lines if en in l and ("theorem" in l or "example" in l)]
        if th and L.compile_lean(head + "\n".join(th))[0]:
            out.append({"src": a, "dst": d, "lean": "\n".join(th), "lean_by": "gemma", "lean_verified": True})
        else:
            det = L.edge_lean(a, d, da["b"], db["b"])
            out.append({"src": a, "dst": d, "lean": det["lean"], "lean_by": "template",
                        "lean_verified": True, "verified_facts": det["verified_facts"]})
    return out


def run(prefix="week1"):
    log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    nodes = [json.loads(l) for l in open(HERE.parent / f"graph/nodes_{prefix}.jsonl")]
    edges = [json.loads(l) for l in open(HERE.parent / f"graph/edges_{prefix}.jsonl")]
    npath = HERE.parent / f"graph/nodes_lean_{prefix}.jsonl"
    epath = HERE.parent / f"graph/edges_lean_{prefix}.jsonl"
    G.METRICS_PATH = str(HERE.parent / f"graph/metrics_lean_{prefix}.jsonl"); open(G.METRICS_PATH, "w").close()
    lock = threading.Lock(); t0 = time.time()

    # resume: skip nodes already written
    done_ids = set()
    if npath.exists():
        for l in open(npath):
            try: done_ids.add(json.loads(l)["id"])
            except Exception: pass
    todo = [n for n in nodes if (n.get("_meta", {}).get("id") or n.get("id")) not in done_ids]
    log(f"NODES: {len(todo)} to do ({len(done_ids)} already done), batches of {NODE_BATCH} via gemma-4-31b parallel...")
    nf = open(npath, "a")
    nb_done = [0]
    with cf.ThreadPoolExecutor(max_workers=G.MAX_WORKERS) as ex:
        futs = [ex.submit(do_node_batch, c) for c in _chunks(todo, NODE_BATCH)]
        for fut in cf.as_completed(futs):
            res = fut.result()
            with lock:
                for r in res: nf.write(json.dumps(r) + "\n")
                nf.flush(); nb_done[0] += 1
                if nb_done[0] % 10 == 0: log(f"  node-batches {nb_done[0]}/{len(futs)} | {G.stats()}")
    nf.close()
    nres = [json.loads(l) for l in open(npath)]
    defs = {r["id"]: {"name": r["name"], "def_line": r["def_line"], "b": L.bond_facts(_byid(nodes, r["id"]))} for r in nres if r.get("def_line")}
    gpass = sum(1 for r in nres if r["lean_by"] == "gemma")
    log(f"NODES done: {len(nres)} | gemma-compiled {gpass} ({100*gpass//max(len(nres),1)}%), template {len(nres)-gpass}")

    edone = set()
    if epath.exists():
        for l in open(epath):
            try: r = json.loads(l); edone.add((r["src"], r["dst"]))
            except Exception: pass
    etodo = [e for e in edges if (e.get("src"), e.get("dst")) not in edone]
    log(f"EDGES: {len(etodo)} to do, batches of {EDGE_BATCH} via gemma parallel...")
    ef = open(epath, "a"); eb_done = [0]
    with cf.ThreadPoolExecutor(max_workers=G.MAX_WORKERS) as ex:
        futs = [ex.submit(do_edge_batch, c, defs) for c in _chunks(etodo, EDGE_BATCH)]
        for fut in cf.as_completed(futs):
            res = fut.result()
            with lock:
                for r in res: ef.write(json.dumps(r) + "\n")
                ef.flush(); eb_done[0] += 1
                if eb_done[0] % 20 == 0: log(f"  edge-batches {eb_done[0]}/{len(futs)} | {G.stats()}")
    ef.close()
    eres = [json.loads(l) for l in open(epath)]
    egpass = sum(1 for r in eres if r["lean_by"] == "gemma")
    summ = {"nodes": len(nres), "node_lean_gemma": gpass, "node_lean_template": len(nres) - gpass,
            "edges": len(eres), "edge_lean_gemma": egpass, "edge_lean_template": len(eres) - egpass,
            "seconds": round(time.time() - t0, 1), "gemma": G.summary()}
    (HERE.parent / f"graph/LEAN_{prefix}.json").write_text(json.dumps(summ, indent=1))
    log(f"DONE: {len(nres)} node-proofs ({gpass} gemma), {len(eres)} edge-proofs ({egpass} gemma) in {round(time.time()-t0)}s")
    log(f"METRICS: {json.dumps(G.summary())}")

def _byid(nodes, nid):
    for n in nodes:
        if (n.get("_meta", {}).get("id") or n.get("id")) == nid: return n
    return {}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--prefix", default="week1"); a = ap.parse_args()
    run(a.prefix)
