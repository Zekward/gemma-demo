"""Local UI backend: serves the static app + /api/query (NL -> filter via Gemma-4 on Cerebras).
The API key is read server-side from ../.cerebras.env and never reaches the browser."""
import json, sys, pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "agents"))
import gemma as G   # UA-fixed Cerebras client + .cerebras.env

GRAPH = json.load(open(ROOT / "data/graph.json"))
NODES = GRAPH["nodes"]

SYS = ("You are search_db, translating a natural-language query about US bond filings into a JSON filter. "
       "Settable fields (include ONLY those implied): issuer (case-insensitive substring of issuer name), "
       "form (424B2|424B3|424B5|FWP), sector (substring), coupon_min (number, percent), coupon_max (number), "
       "maturity (int year), keyword (matched against the note's structure/features/series text), cusip. "
       "Also always include 'answer': one sentence describing what you searched for. Output ONLY JSON.")

import re as _re
def _norm(s): return _re.sub(r"[^a-z0-9]", "", s.lower())

RESEARCH_SYS = ("You are a fixed-income research agent. Given ONE bond's extracted facts, write a tight 3-4 sentence brief: "
                "what the instrument is, its structure/economics, the single most important risk, and what makes it distinct vs "
                "typical peers. Ground strictly in the facts; never invent numbers. Plain prose, no preamble, no markdown.")

def research_one(n):
    facts = {k: n.get(k) for k in ("issuer", "form", "sector", "coupon", "maturity", "principal",
                                   "seniority", "cusip", "is_144a", "features")}
    try:
        txt, _ = G.chat([{"role": "system", "content": RESEARCH_SYS}, {"role": "user", "content": json.dumps(facts)}], max_tokens=320)
    except Exception as e:
        txt = f"(agent error: {str(e)[:80]})"
    return {"id": n["id"], "issuer": n["issuer"], "form": n["form"], "coupon": n.get("coupon"),
            "maturity": n.get("maturity"), "research": txt.strip()}

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
        ids = (body.get("ids") or [])[:8]
        nodes = [n for n in (next((x for x in NODES if x["id"] == i), None) for i in ids) if n]
        if not nodes: return self._send(400, json.dumps({"error": "no bonds"}))
        agents = G.pmap(research_one, nodes, workers=8)
        self._send(200, json.dumps({"agents": agents, "model": G.MODEL}))

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"bondsec UI on http://localhost:{port}  (model={G.MODEL}, {len(NODES)} nodes)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
