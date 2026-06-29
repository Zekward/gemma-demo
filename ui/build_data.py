"""Build ui/data/graph.json from the week-1 graph DB + Lean, with a precomputed
issuer-cluster layout so the browser can render all ~2500 nodes without doing layout."""
import json, math, re, pathlib
from collections import defaultdict
ROOT = pathlib.Path(__file__).resolve().parent.parent
G = ROOT / "graph"
def load(p):
    f = G / p; return [json.loads(l) for l in open(f)] if f.exists() else []

PREFIX = "week1"
nodes = load(f"nodes_{PREFIX}.jsonl"); edges = load(f"edges_{PREFIX}.jsonl")
nlean = {r["id"]: r for r in load(f"nodes_lean_{PREFIX}.jsonl")}
elean = {(r["src"], r["dst"]): r for r in load(f"edges_lean_{PREFIX}.jsonl")}
def short(s):
    if "Space Exploration" in s: return "SpaceX"     # alias the IPO'd issuer to its common name
    return re.split(r"\s*\(", s)[0].strip()[:34]

out_nodes = []
for n in nodes:
    m = n["_meta"]; t = (n.get("tranches") or [{}])[0]; lid = nlean.get(m["id"], {})
    out_nodes.append({"id": m["id"], "issuer": short(m["issuer"]), "form": m["form"], "sector": m.get("sector", "?"),
        "date": m["date"], "sec_url": m["doc_url"], "stage": n.get("lifecycle_stage"), "is_144a": n.get("is_144a"),
        "coupon": t.get("coupon_pct"), "maturity": t.get("maturity_year"), "principal": t.get("principal_usd"),
        "cusip": t.get("cusip"), "seniority": t.get("seniority"), "features": (n.get("salient_features") or [])[:4],
        "lean": lid.get("lean"), "lean_by": lid.get("lean_by"), "facts": lid.get("verified_facts")})
nid = {n["id"] for n in out_nodes}
out_edges = []
for e in edges:
    if e["src"] not in nid or e["dst"] not in nid: continue
    el = elean.get((e["src"], e["dst"]), {})
    out_edges.append({"src": e["src"], "dst": e["dst"], "rel": e.get("relationship"), "sim": e.get("candidate_sim"),
        "mat": e.get("materiality"), "summary": e.get("summary"),
        "diffs": [{"f": d.get("field"), "a": d.get("a"), "b": d.get("b"), "why": d.get("why_it_matters")}
                  for d in (e.get("differences") or [])][:5], "lean": el.get("lean"), "lean_by": el.get("lean_by")})

# degree
deg = defaultdict(int)
for e in out_edges: deg[e["src"]] += 1; deg[e["dst"]] += 1
for n in out_nodes: n["deg"] = deg.get(n["id"], 0)

# layout: issuer clusters on a golden-angle spiral; members in a small disk per cluster
groups = defaultdict(list)
for n in out_nodes: groups[n["issuer"]].append(n)
order = sorted(groups, key=lambda k: -len(groups[k]))
GA = 2.399963229728653
for gi, iss in enumerate(order):
    ang = gi * GA; rad = 230 * math.sqrt(gi + 1)
    gx, gy = 5000 + rad * math.cos(ang), 5000 + rad * math.sin(ang)
    for j, n in enumerate(groups[iss]):
        a = j * GA; r = 16 * math.sqrt(j + 1)
        n["x"] = round(gx + r * math.cos(a), 1); n["y"] = round(gy + r * math.sin(a), 1)

stats = {"nodes": len(out_nodes), "edges": len(out_edges), "issuers": len(groups),
         "lean_nodes": len(nlean), "lean_edges": len(elean)}
(ROOT / "ui/data").mkdir(parents=True, exist_ok=True)
json.dump({"nodes": out_nodes, "edges": out_edges, "stats": stats}, open(ROOT / "ui/data/graph.json", "w"))
print(f"graph.json: {stats}  ({(ROOT/'ui/data/graph.json').stat().st_size//1024} KB)")
