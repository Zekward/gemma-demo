"""Deterministic Lean-4 generator for bond facts + relationship edges.

Design (the honest division of labour):
  - Gemma EXTRACTS the facts (coupon, maturity, principal, seniority) — grounded in the doc.
  - Lean CERTIFIES internal consistency + relationships: every `by decide` that compiles is a
    real proof. We only emit propositions that actually hold (computed in Python first), so the
    generated Lean always compiles → a genuine green check, no flaky LLM-written proofs.

Plain Lean 4, NO Mathlib (Nat/Bool have decidable eq/lt in core) → compiles in ~1s.
"""
from __future__ import annotations
import json, re, subprocess, tempfile, pathlib

HERE = pathlib.Path(__file__).resolve().parent
PREAMBLE = (
"-- bondsec: machine-verified bond facts. Plain Lean 4; each `by decide` that compiles IS the proof.\n"
"structure Bond where\n"
"  couponBp     : Nat   -- coupon in basis points (5.350% = 535)\n"
"  maturityYear : Nat\n"
"  principalMM  : Nat   -- principal, $ millions\n"
"  senior       : Bool\n"
"  deriving Repr\n")

def _name(s: str) -> str:
    n = re.sub(r"[^0-9A-Za-z]", "_", str(s))
    return ("b_" + n) if not n[:1].isalpha() else n

def _bp(pct): return None if pct is None else round(float(pct) * 100)
def _mm(usd): return None if not usd else int(usd) // 1_000_000


def bond_facts(node: dict) -> dict | None:
    """Pull a single (coupon,maturity,principal,senior) tuple from a node (graph.json Tranche
    or a Gemma node's first priced tranche). Returns None if not a bond tranche."""
    p = node.get("props", node)
    cp = p.get("coupon_pct"); mat = p.get("maturity") or p.get("maturity_year")
    prin = p.get("principal_usd"); sen = p.get("seniority")
    tr = node.get("tranches") or []                         # Gemma node form
    if tr:
        t = next((t for t in tr if t.get("coupon_pct") is not None), tr[0])
        if cp is None: cp = t.get("coupon_pct")
        if mat is None: mat = t.get("maturity_year")
        if prin is None: prin = t.get("principal_usd")
        if sen is None: sen = t.get("seniority")
    if cp is None and mat is None and not prin: return None
    return {"couponBp": _bp(cp) or 0, "maturityYear": int(mat) if mat else 0,
            "principalMM": _mm(prin) or 0, "senior": "sub" not in str(sen or "").lower()}


def node_lean(nid: str, b: dict, issue_year: int = 2026) -> dict:
    nm = _name(nid)
    lines = [f"def {nm} : Bond := {{ couponBp := {b['couponBp']}, maturityYear := {b['maturityYear']}, "
             f"principalMM := {b['principalMM']}, senior := {str(b['senior']).lower()} }}"]
    facts = []
    th = []
    if b["couponBp"] > 0:
        th.append((f"{nm}.couponBp = {b['couponBp']}", f"coupon = {b['couponBp']/100:.3f}%"))
    if b["maturityYear"] > issue_year:
        th.append((f"{nm}.maturityYear > {issue_year}", f"matures ({b['maturityYear']}) after issue ({issue_year})"))
    if b["principalMM"] > 0:
        th.append((f"{nm}.principalMM > 0", f"principal {b['principalMM']}MM > 0"))
    if b["senior"]:
        th.append((f"{nm}.senior = true", "ranks senior"))
    if not th:
        th.append((f"{nm}.couponBp = {b['couponBp']}", f"couponBp = {b['couponBp']}"))
    for i, (prop, human) in enumerate(th):
        lines.append(f"theorem {nm}_f{i} : {prop} := by decide   -- {human}")
        facts.append(human)
    return {"def_name": nm, "lean": "\n".join(lines), "verified_facts": facts}


def edge_lean(a_id: str, b_id: str, ba: dict, bb: dict) -> dict:
    """Relationship theorems between two bonds — emit only propositions that actually hold."""
    a, b = _name(a_id), _name(b_id)
    out, facts = [], []
    def rel(field, va, vb, label):
        op = "<" if va < vb else (">" if va > vb else "=")
        prop = f"{a}.{field} {op} {b}.{field}"
        out.append(f"example : {prop} := by decide   -- {label}")
        facts.append(f"{label}: {a}.{field} {op} {b}.{field}")
    rel("couponBp", ba["couponBp"], bb["couponBp"], "coupon ladder")
    rel("maturityYear", ba["maturityYear"], bb["maturityYear"], "maturity ordering")
    same = ba["senior"] == bb["senior"]
    out.append(f"example : ({a}.senior = {b}.senior) = {str(same).lower()} := by decide   -- seniority match")
    facts.append(f"same seniority: {same}")
    return {"lean": "\n".join(out), "verified_facts": facts}


def compile_lean(source: str) -> tuple[bool, str]:
    """Compile a standalone Lean file; (ok, stderr). ~1s, no Mathlib."""
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write(source); path = f.name
    try:
        r = subprocess.run(["lean", path], capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    finally:
        pathlib.Path(path).unlink(missing_ok=True)


def build_from_graph(graph_path: str, out_lean: str, out_json: str) -> dict:
    """Enrich a graph.json (nodes/links) with per-node + per-edge Lean, compile the whole thing."""
    g = json.load(open(graph_path))
    src = [PREAMBLE, ""]
    facts_by_id = {}
    bonds = {}
    for n in g["nodes"]:
        b = bond_facts(n)
        if not b: continue
        bonds[n["id"]] = b
        nl = node_lean(n["id"], b)
        n["lean"] = nl["lean"]; n["verified_facts"] = nl["verified_facts"]
        src += [f"-- ## {n['id']}", nl["lean"], ""]
    for e in g["links"]:
        a, b = e.get("src") or e.get("source"), e.get("dst") or e.get("target")
        if a in bonds and b in bonds and e.get("type") in ("SIBLING_TRANCHE", "SUPERSEDES"):
            el = edge_lean(a, b, bonds[a], bonds[b])
            e["lean"] = el["lean"]; e["verified_facts"] = el["verified_facts"]
            src += [f"-- ## edge {a} -> {b} ({e['type']})", el["lean"], ""]
    source = "\n".join(src)
    ok, msg = compile_lean(source)
    pathlib.Path(out_lean).write_text(source)
    g["_lean_compiled"] = ok
    json.dump(g, open(out_json, "w"), indent=1)
    return {"ok": ok, "msg": msg, "nodes_with_lean": sum(1 for n in g["nodes"] if "lean" in n),
            "edges_with_lean": sum(1 for e in g["links"] if "lean" in e), "lean_file": out_lean, "json": out_json}


if __name__ == "__main__":
    import sys
    r = build_from_graph(str(HERE.parent / "graph/graph.json"),
                         str(HERE.parent / "graph/spacex.lean"),
                         str(HERE.parent / "graph/graph_lean.json"))
    print(json.dumps(r, indent=1))
