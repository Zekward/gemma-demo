"""Cerebras gemma-4-31b client: UA-fixed, rate-limited (req/min + tok/min), concurrent, JSON-robust."""
from __future__ import annotations
import json, re, time, threading, urllib.request, urllib.error, pathlib
from concurrent.futures import ThreadPoolExecutor

_ENV = pathlib.Path(__file__).resolve().parent.parent / ".cerebras.env"
_kv = dict(l.strip().split("=", 1) for l in _ENV.read_text().splitlines() if "=" in l)
KEY, MODEL = _kv["CEREBRAS_API_KEY"], _kv["CEREBRAS_MODEL"]
URL = "https://api.cerebras.ai/v1/chat/completions"
UA = "bondsec/0.1"

# stay safely under the published caps (100 req/min, 100k tok/min)
REQ_PER_MIN, TOK_PER_MIN, MAX_WORKERS = 85, 90_000, 8

class _Limiter:
    def __init__(self):
        self.lock = threading.Lock(); self.reqs = []; self.toks = []
    def acquire(self, est_tokens):
        while True:
            with self.lock:
                now = time.time(); cut = now - 60
                self.reqs = [t for t in self.reqs if t > cut]
                self.toks = [(t, n) for t, n in self.toks if t > cut]
                tok_sum = sum(n for _, n in self.toks)
                if len(self.reqs) < REQ_PER_MIN and tok_sum + est_tokens < TOK_PER_MIN:
                    self.reqs.append(now); self.toks.append((now, est_tokens)); return
                wait = 0.3
                if self.reqs: wait = max(wait, 60 - (now - min(self.reqs)) + 0.05)
            time.sleep(min(wait, 2))
    def record(self, actual):
        with self.lock:
            if self.toks: self.toks[-1] = (self.toks[-1][0], actual)

_lim = _Limiter()
_stats = {"calls": 0, "tokens": 0, "errors": 0}
_metrics = []                 # per-call metric dicts
_mlock = threading.Lock()
_t_first = [None]             # wall clock of first completed call (for elapsed/throughput)
METRICS_PATH = None           # set by caller -> stream per-call metrics as JSONL

def _record(wall, u, ti, headers):
    ct = ti.get("completion_time") or 0.0
    comp = u.get("completion_tokens", 0)
    m = {"wall_s": round(wall, 4),
         "server_total_s": round(ti.get("total_time", 0.0), 4),
         "queue_s": round(ti.get("queue_time", 0.0), 5),
         "prompt_s": round(ti.get("prompt_time", 0.0), 5),
         "completion_s": round(ct, 4),
         "ttft_server_s": round(ti.get("queue_time", 0.0) + ti.get("prompt_time", 0.0), 5),  # server time-to-first-token
         "ttft_wall_s": round(max(wall - ct, 0.0), 4),          # client-observed TTFT (incl. network RTT)
         "net_overhead_s": round(max(wall - ti.get("total_time", 0.0), 0.0), 4),
         "prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": comp,
         "total_tokens": u.get("total_tokens", 0),
         "out_tps_server": round(comp / ct, 1) if ct else None,    # tokens/sec, server generation
         "out_tps_wall": round(comp / wall, 1) if wall else None,  # tokens/sec, end-to-end
         "rl_tokens_min_left": int(headers.get("x-ratelimit-remaining-tokens-minute", 0) or 0)}
    with _mlock:
        if _t_first[0] is None: _t_first[0] = time.time()
        _stats["calls"] += 1; _stats["tokens"] += m["total_tokens"]
        _metrics.append(m)
        if METRICS_PATH:
            with open(METRICS_PATH, "a") as f: f.write(json.dumps(m) + "\n")

def chat(messages, max_tokens=900, temperature=0.2, est_tokens=None, tries=5) -> tuple[str, dict]:
    if est_tokens is None:
        est_tokens = sum(len(m["content"]) for m in messages) // 4 + max_tokens
    body = json.dumps({"model": MODEL, "messages": messages, "max_completion_tokens": max_tokens,
                       "temperature": temperature}).encode()
    for attempt in range(tries):
        _lim.acquire(est_tokens)
        req = urllib.request.Request(URL, data=body, headers={
            "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "User-Agent": UA})
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=90)
            r = json.load(resp); wall = time.time() - t0
            u = r.get("usage", {}) or {}
            _lim.record(u.get("total_tokens", est_tokens))
            _record(wall, u, r.get("time_info", {}) or {}, resp.headers)
            return r["choices"][0]["message"]["content"], u
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (429, 503, 500, 502, 403) and attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            _stats["errors"] += 1; raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < tries - 1: time.sleep(1.5 * (attempt + 1)); continue
            _stats["errors"] += 1; raise
    raise RuntimeError("chat failed")

_JSON = re.compile(r"\{.*\}", re.S)
def chat_json(messages, max_tokens=900, temperature=0.1, est_tokens=None) -> dict | None:
    """Force-parse a JSON object from the reply (gemma sometimes wraps in prose/fences)."""
    txt, _ = chat(messages, max_tokens=max_tokens, temperature=temperature, est_tokens=est_tokens)
    txt = txt.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(txt)
    except Exception:
        m = _JSON.search(txt)
        if m:
            try: return json.loads(m.group(0))
            except Exception: return None
        return None

def pmap(fn, items, workers=MAX_WORKERS):
    out = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in futs:
            i = futs[f]
            try: out[i] = f.result()
            except Exception as e: out[i] = {"_error": str(e)[:200]}
    return out

def stats(): return dict(_stats)

def _pct(xs, p):
    if not xs: return None
    xs = sorted(xs); k = (len(xs) - 1) * p / 100.0; f = int(k); c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 4)

def summary():
    """Aggregate latency / TTFT / throughput metrics across all calls so far."""
    with _mlock:
        ms = list(_metrics); elapsed = (time.time() - _t_first[0]) if _t_first[0] else 0.0
    if not ms: return {"calls": 0, "errors": _stats["errors"]}
    col = lambda k: [m[k] for m in ms if m.get(k) is not None]
    wall, ttftw, stps = col("wall_s"), col("ttft_wall_s"), col("out_tps_server")
    tot, comp = sum(m["total_tokens"] for m in ms), sum(m["completion_tokens"] for m in ms)
    band = lambda xs: {"mean": round(sum(xs) / len(xs), 3), "p50": _pct(xs, 50), "p95": _pct(xs, 95), "max": round(max(xs), 3)} if xs else None
    return {
        "calls": len(ms), "errors": _stats["errors"], "elapsed_s": round(elapsed, 1),
        "total_tokens": tot, "completion_tokens": comp,
        "latency_wall_s": band(wall),
        "ttft_wall_s": band(ttftw),
        "ttft_server_s_mean": round(sum(col("ttft_server_s")) / len(ms), 5),
        "out_tps_server": {"mean": round(sum(stps) / len(stps), 1), "p50": _pct(stps, 50)} if stps else None,
        "net_overhead_s_mean": round(sum(col("net_overhead_s")) / len(ms), 3),
        "throughput": {"tokens_per_min": round(tot / elapsed * 60) if elapsed else None,
                       "calls_per_min": round(len(ms) / elapsed * 60, 1) if elapsed else None,
                       "effective_completion_tps": round(comp / elapsed, 1) if elapsed else None},
    }

def write_summary(path, extra=None):
    s = summary()
    if extra: s.update(extra)
    open(path, "w").write(json.dumps(s, indent=1))
    return s
