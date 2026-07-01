"""Local UI backend: serves the static app + /api/query (NL -> filter via Gemma-4 on Cerebras).
The API key is read server-side from ../.cerebras.env and never reaches the browser."""
import json, sys, pathlib, subprocess, base64, os, hashlib, time, threading, queue, urllib.request
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

# --- Cerebras vs GPU race (ported from the Next.js lib/providers.ts) ----------
def _envkv():
    kv = {}
    for fn in (".env.local", ".cerebras.env"):
        p = ROOT.parent / fn
        if p.exists():
            for l in p.read_text().splitlines():
                l = l.strip()
                if l and not l.startswith("#") and "=" in l:
                    k, v = l.split("=", 1); kv.setdefault(k.strip(), v.strip())
    for k in ("CEREBRAS_API_KEY", "CEREBRAS_BASE_URL", "CEREBRAS_MODEL",
              "GPU_API_KEY", "GPU_BASE_URL", "GPU_MODEL", "GPU_LABEL"):
        if not kv.get(k) and os.environ.get(k):   # Render / prod: keys come from env vars
            kv[k] = os.environ[k]
    return kv
_ENV = _envkv()
PROV = {
    "cerebras": {"label": "Cerebras", "base": _ENV.get("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"),
                 "key": _ENV.get("CEREBRAS_API_KEY"), "model": _ENV.get("CEREBRAS_MODEL", "gemma-4-31b")},
    "gpu": {"label": _ENV.get("GPU_LABEL", "Together AI"), "base": _ENV.get("GPU_BASE_URL", "https://api.together.xyz/v1"),
            "key": _ENV.get("GPU_API_KEY"), "model": _ENV.get("GPU_MODEL", "google/gemma-4-31B-it")},
}
def _bond_facts(n):
    pr = n.get("principal")
    return (f"{n['issuer']} {n.get('maturity') or ''} ({n['id']})\n"
            f"  form: {n['form']}  coupon: {n.get('coupon')}%  maturity: {n.get('maturity')}  "
            f"principal: ${(pr // 1000000) if pr else '—'}mm  seniority: {n.get('seniority')}  144A: {n.get('is_144a')}\n"
            f"  features: {'; '.join((n.get('features') or [])[:3])}")
def _compare_messages(a, b):
    return [{"role": "system", "content": "You are a fixed-income research assistant for institutional credit analysts. "
             "Answer only from the figures provided. Be concise and decisive, use exact numbers, never invent data. "
             "Structure: a one-line verdict, then the carry/duration/credit trade-off, then who each suits."},
            {"role": "user", "content": f"Compare these two bonds and tell me which is the better buy.\n\n{_bond_facts(a)}\n\n{_bond_facts(b)}\n\nKeep it under 160 words."}]

def _stream_provider(pid, messages, q):
    cfg = PROV[pid]; start = time.time(); ttft = None; tokens = 0; text = ""
    def emit(t, **kw): q.put({"provider": pid, "model": cfg["model"], "t": t, **kw})
    if not cfg.get("key"):
        emit("error", message=f"{cfg['label']}: no API key"); emit("done", ttftMs=None, tokens=0, elapsedMs=0, tps=0); return
    try:
        body = json.dumps({"model": cfg["model"], "messages": messages, "stream": True,
                           "temperature": 0.3, "max_tokens": 700}).encode()
        req = urllib.request.Request(cfg["base"] + "/chat/completions", data=body,
              headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json",
                       "User-Agent": "exabond/0.1", "Accept": "text/event-stream"})
        resp = urllib.request.urlopen(req, timeout=180)
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"): continue
            payload = line[5:].strip()
            if payload == "[DONE]": break
            try:
                j = json.loads(payload); delta = (j.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
            except Exception: continue
            if delta:
                if ttft is None: ttft = int((time.time() - start) * 1000)
                text += delta; tokens = max(1, len(text) // 4); el = int((time.time() - start) * 1000)
                emit("token", v=delta)
                emit("metrics", ttftMs=ttft, tokens=tokens, elapsedMs=el, tps=round(tokens / (el / 1000), 1) if el > 0 else 0)
        el = int((time.time() - start) * 1000)
        emit("done", ttftMs=ttft, tokens=tokens, elapsedMs=el, tps=round(tokens / (el / 1000), 1) if el > 0 else 0)
    except Exception as e:
        emit("error", message=f"{cfg['label']}: {str(e)[:140]}")
        emit("done", ttftMs=ttft, tokens=tokens, elapsedMs=int((time.time() - start) * 1000), tps=0)


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
        if self.path == "/api/compare": return self._compare(body)
        return self._send(404, b"no", "text/plain")

    def _compare(self, body):
        a = next((x for x in NODES if x["id"] == body.get("aId")), None)
        b = next((x for x in NODES if x["id"] == body.get("bId")), None)
        if not a or not b: return self._send(400, json.dumps({"error": "unknown bond"}))
        msgs = _compare_messages(a, b)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        # meta event so the UI can label panels before tokens arrive
        meta = {"t": "start", "a": {"id": a["id"], "issuer": a["issuer"]}, "b": {"id": b["id"], "issuer": b["issuer"]},
                "models": {"cerebras": PROV["cerebras"]["model"], "gpu": PROV["gpu"]["model"]}}
        self.wfile.write(f"data: {json.dumps(meta)}\n\n".encode()); self.wfile.flush()
        q = queue.Queue()
        for p in ("cerebras", "gpu"):
            threading.Thread(target=_stream_provider, args=(p, msgs, q), daemon=True).start()
        done = 0
        try:
            while done < 2:
                ev = q.get()
                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode()); self.wfile.flush()
                if ev["t"] == "done": done += 1
        except Exception:
            pass

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
    env_port = os.environ.get("PORT")                       # Render sets PORT
    port = int(env_port) if env_port else (int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    host = "0.0.0.0" if env_port else "127.0.0.1"           # bind public only in prod
    print(f"exabond UI on {host}:{port}  (model={G.MODEL}, {len(NODES)} nodes)", flush=True)
    ThreadingHTTPServer((host, port), H).serve_forever()
