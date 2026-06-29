"""Local UI backend: serves the static app + /api/query (NL -> filter via Gemma-4 on Cerebras).
The API key is read server-side from ../.cerebras.env and never reaches the browser."""
import json, sys, pathlib, subprocess, base64, os, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "agents")); sys.path.insert(0, str(ROOT.parent))
import gemma as G   # UA-fixed Cerebras client + .cerebras.env
import bondsec as B  # SEC fetch + html_to_text (for full-filing research / vision)

GRAPH = json.load(open(ROOT / "data/graph.json"))
NODES = GRAPH["nodes"]

SYS = ("You are search_db, translating a natural-language query about US bond filings into a JSON filter. "
       "Settable fields (include ONLY those implied): issuer (case-insensitive substring of issuer name), "
       "form (424B2|424B3|424B5|FWP), sector (substring), coupon_min (number, percent), coupon_max (number), "
       "maturity (int year), keyword (matched against the note's structure/features/series text), cusip. "
       "Also always include 'answer': one sentence describing what you searched for. Output ONLY JSON.")

import re as _re
def _norm(s): return _re.sub(r"[^a-z0-9]", "", s.lower())

# --- /parallel agents effort tiers --------------------------------------------
CAP = {"small": 3, "mid": 6, "high": 10, "nuclear": 16}
EFFORT = {
  "small":   {"tok": 320,  "doc": 0,     "vision": False, "depth": "a tight 3-4 sentence brief: what it is, its structure, the single biggest risk, and what makes it distinct"},
  "mid":     {"tok": 700,  "doc": 4000,  "vision": False, "depth": "a 5-7 sentence analysis of structure, economics, the main risks, and peer comparison, using the filing text"},
  "high":    {"tok": 1300, "doc": 13000, "vision": False, "depth": "a thorough multi-paragraph analysis: structure & economics, ALL material risks, redemption/call mechanics, covenants & ranking, and relative value vs peers — read the full filing text closely"},
  "nuclear": {"tok": 2200, "doc": 16000, "vision": True,  "depth": "an exhaustive deep-dive grounded in BOTH the full filing text AND the rendered filing image: structure, economics, every risk, redemption/call mechanics, covenants, ranking/subordination, and the subtle intricacies a human analyst would miss. Use the image to catch tables/footnotes/cover-page terms not in the extracted facts"},
}
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_DOC, _IMG = {}, {}
def doc_text(url):
    if url not in _DOC:
        try: _DOC[url] = B.html_to_text(B.fetch(url))
        except Exception: _DOC[url] = ""
    return _DOC[url]
def render_filing(url):
    if url not in _IMG:
        b = None
        try:
            h = hashlib.md5(url.encode()).hexdigest(); hp, pp = f"/tmp/bsx_{h}.html", f"/tmp/bsx_{h}.png"
            open(hp, "wb").write(B.fetch(url))
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--screenshot={pp}",
                            "--window-size=1280,2200", "--hide-scrollbars", f"file://{hp}"], capture_output=True, timeout=45)
            if os.path.exists(pp): b = base64.b64encode(open(pp, "rb").read()).decode()
        except Exception: b = None
        _IMG[url] = b
    return _IMG[url]

def research_one(n, effort="small"):
    cfg = EFFORT.get(effort, EFFORT["small"])
    facts = {k: n.get(k) for k in ("issuer", "form", "sector", "coupon", "maturity", "principal", "seniority", "cusip", "is_144a", "features")}
    content = [{"type": "text", "text": "Bond facts: " + json.dumps(facts)}]
    used_vision = False
    if cfg["doc"]:
        t = doc_text(n["sec_url"])[:cfg["doc"]]
        if t: content.append({"type": "text", "text": "Original filing text:\n" + t})
    if cfg["vision"]:
        img = render_filing(n["sec_url"])
        if img:
            content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + img}}); used_vision = True
    sysmsg = "You are a fixed-income research agent. Produce " + cfg["depth"] + ". Ground strictly in the facts/filing; never invent numbers. Plain prose, no markdown headers."
    est = sum(len(c.get("text", "")) for c in content) // 4 + (300 if used_vision else 0) + cfg["tok"]
    try:
        txt, _ = G.chat([{"role": "system", "content": sysmsg}, {"role": "user", "content": content}], max_tokens=cfg["tok"], est_tokens=est)
    except Exception as e:
        txt = f"(agent error: {str(e)[:80]})"
    return {"id": n["id"], "issuer": n["issuer"], "form": n["form"], "coupon": n.get("coupon"),
            "maturity": n.get("maturity"), "research": txt.strip(), "vision": used_vision}

def relationship_synthesis(nodes, agents, effort):
    cfg = EFFORT.get(effort, EFFORT["high"])
    briefs = "\n".join(f"- {a['issuer']} ({a.get('maturity')}, {a.get('coupon')}%): {a['research'][:400]}" for a in agents)
    content = [{"type": "text", "text":
        "You are a senior credit strategist. Surface the INTRICATE relationships BETWEEN these researched bonds — relative value, "
        "shared vs divergent structure, curve/maturity positioning, cross-issuer comparisons, and subtle distinctions a junior analyst "
        "would miss. Be specific and grounded.\n\nResearched bonds:\n" + briefs}]
    if cfg["vision"]:
        for n in nodes[:3]:
            img = render_filing(n["sec_url"])
            if img: content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + img}})
    est = len(briefs) // 4 + 900 + cfg["tok"]
    try:
        txt, _ = G.chat([{"role": "user", "content": content}], max_tokens=cfg["tok"] + 400, est_tokens=est)
        return txt.strip()
    except Exception as e:
        return f"(synthesis error: {str(e)[:80]})"

def apply_filter(f):
    out = []
    for n in NODES:
        if f.get("issuer") and f["issuer"].lower() not in n["issuer"].lower(): continue
        if f.get("form") and n["form"] != f["form"]: continue
        if f.get("sector") and f["sector"].lower() not in n["sector"].lower(): continue
        c = n.get("coupon")
        if f.get("coupon_min") is not None and (c is None or c < f["coupon_min"]): continue
        if f.get("coupon_max") is not None and (c is None or c > f["coupon_max"]): continue
        if f.get("maturity") and n.get("maturity") != f["maturity"]: continue
        if f.get("cusip") and (not n.get("cusip") or f["cusip"].lower() not in str(n["cusip"]).lower()): continue
        if f.get("keyword"):
            hay = _norm(n["issuer"] + " " + " ".join(n.get("features") or []) + " " + str(n.get("cusip") or "")
                        + " " + str(n.get("seniority") or "") + " notes bond debt " + str(n.get("form") or ""))
            toks = [t for t in (_norm(w) for w in str(f["keyword"]).split()) if len(t) > 1]
            if not all(t in hay for t in toks): continue
        out.append(n["id"])
    return out

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/": path = "/index.html"
        f = (ROOT / path.lstrip("/"))
        if f.exists() and f.is_file():
            ct = {"html": "text/html", "json": "application/json", "js": "text/javascript",
                  "css": "text/css"}.get(f.suffix.lstrip("."), "application/octet-stream")
            self._send(200, f.read_bytes(), ct)
        else:
            self._send(404, b"not found", "text/plain")
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/query": return self._query(body)
        if self.path == "/api/parallel": return self._parallel(body)
        return self._send(404, b"no", "text/plain")

    def _query(self, body):
        q = body.get("q", "").strip()
        if not q: return self._send(400, json.dumps({"error": "empty"}))
        try:
            f = G.chat_json([{"role": "system", "content": SYS}, {"role": "user", "content": q}], max_tokens=300) or {}
        except Exception as e:
            return self._send(500, json.dumps({"error": str(e)[:200]}))
        ids = apply_filter(f)
        answer = f.pop("answer", None) or f"Found {len(ids)} matching filings."
        sample = [{"issuer": x["issuer"], "form": x["form"], "coupon": x.get("coupon"), "maturity": x.get("maturity")}
                  for x in (next(y for y in NODES if y["id"] == i) for i in ids[:6])]
        self._send(200, json.dumps({"query": q,
            "tool_calls": [{"name": "search_db", "args": f, "result": {"count": len(ids), "sample": sample}}],
            "matched_ids": ids, "count": len(ids), "answer": answer}))

    def _parallel(self, body):
        effort = body.get("effort", "small")
        ids = (body.get("ids") or [])[:CAP.get(effort, 3)]
        nodes = [n for n in (next((x for x in NODES if x["id"] == i), None) for i in ids) if n]
        if not nodes: return self._send(400, json.dumps({"error": "no bonds"}))
        agents = [a for a in G.pmap(lambda n: research_one(n, effort), nodes, workers=8) if a]
        out = {"agents": agents, "model": G.MODEL, "effort": effort}
        if effort in ("high", "nuclear") and len(agents) >= 2:
            out["synthesis"] = relationship_synthesis(nodes, agents, effort)
        self._send(200, json.dumps(out))

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"bondsec UI on http://localhost:{port}  (model={G.MODEL}, {len(NODES)} nodes)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
