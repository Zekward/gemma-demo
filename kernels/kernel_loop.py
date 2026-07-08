#!/usr/bin/env python3
"""Autoresearch loop: gemma-4-31b on Cerebras evolves the ARMv8-A (Apple A9 / iPhone 6s)
Q4_0 x Q8_0 vec_dot kernel that powers on-device Gemma 3 1B decode.

Each round:
  1) ask Cerebras for B candidate kernels (diverse strategy hints) given the current champion
     source + its measured speed + the last attempt's outcome,
  2) compile each candidate for -mcpu=apple-a9 (the 6s ISA) and benchmark it (correctness vs a
     trusted scalar reference, then ns/dot on this host),
  3) promote the fastest correct candidate that beats the champion; log everything.

Host timings (M3) are a PROXY: candidates are ISA-restricted to A9 (no sdot/udot/i8mm), so the
generated assembly is valid for the 6s, but absolute ns are this Mac's. For real A9 numbers set
BENCH backend to the device (see --device, not yet wired) — relative ranking transfers well for
this memory-bound matvec.

Usage:
  python3 kernel_loop.py --iters 40 --batch 4
  python3 kernel_loop.py --forever --batch 6 --explore-every 6
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time, pathlib, shutil

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "agents"))
import gemma as G  # Cerebras client (reads ../.cerebras.env -> gemma-4-31b)

RUNS = HERE / "runs"; CHAMPS = HERE / "champions"
LEADER = HERE / "leaderboard.jsonl"; BEST = HERE / "BEST_KERNEL.c"
CFLAGS_DEFAULT = "-O3 -arch arm64 -mcpu=apple-a9 -std=c11"

# ---- the contract handed to the model every round --------------------------------------------
ABI = r"""
You are optimizing ONE function for the Apple A9 CPU (iPhone 6s, ARMv8-A BASELINE, ARM NEON).

HARD ISA RULES (the A9 predates these — using them is an automatic FAIL):
  - NO dot-product: no sdot/udot, no vdotq_*; NO i8mm (vmmla); NO SVE/SVE2.
  - fp16 ARITHMETIC is not available (only fp16<->fp32 CONVERT). Do per-block scaling in fp32.
  - You MUST beat the current champion on speed while staying numerically correct.

Speedups must come from: loop unrolling, multiple independent accumulators (break dep chains for
dual-issue), software prefetch (__builtin_prefetch), fewer NEON ops on the critical path, and the
identity  sum((x-8)*y) = sum(x*y) - 8*sum(y)  to drop the per-element subtract.

EXACT ABI (do not change the signature or the block layout):
  #define QK 32
  typedef _Float16 half;
  typedef struct { half d; uint8_t qs[16]; } block_q4_0; // d = fp16 scale; 16 bytes hold 32 nibbles
  typedef struct { half d; int8_t  qs[32]; } block_q8_0; // d = fp16 scale; 32 int8 quants
  void vec_dot_candidate(int n, float * restrict s, const void * restrict vx, const void * restrict vy);

SEMANTICS (must match exactly): nb = n/32 blocks. For block i, with x=block_q4_0*, y=block_q8_0*:
  low nibble  xl_j = (qs[j] & 0x0F) - 8   pairs with y.qs[j]       for j in 0..15
  high nibble xh_j = (qs[j] >> 4)   - 8   pairs with y.qs[j+16]    for j in 0..15
  block_sum (int) = sum over j of xl_j*y.qs[j] + xh_j*y.qs[j+16]
  *s = sum over blocks of (float)x.d * (float)y.d * (float)block_sum

OUTPUT FORMAT: first a single line "IDEA: <one sentence>", then ONE ```c code block containing the
COMPLETE self-contained candidate.c (may #include only <arm_neon.h> and <stdint.h>; redefine the
typedefs). No prose outside the code block. No file I/O, no syscalls, no other includes.
"""

HINTS = [
    "Unroll the block loop by 2 and interleave both blocks' loads to hide L1 load latency.",
    "Unroll by 4 with FOUR independent int32 accumulators to break the dependency chain for dual-issue.",
    "Use the sum((x-8)*y)=sum(x*y)-8*sum(y) identity so the low/high nibbles need no vsubq_s8.",
    "Accumulate widened products with vpadalq_s16 straight into an int32x4 accumulator each block.",
    "Software-prefetch x[i+2].qs and y[i+2].qs with __builtin_prefetch ahead of the compute.",
    "Keep low-nibble and high-nibble products in SEPARATE int16x8 accumulators; combine once at the end.",
    "Minimize fp work: keep an int32 running sum per block, convert+scale by d only once per block.",
    "Restructure the nibble unpack to cut vand/vshr count; fold the -8 bias into the horizontal sum.",
]

FORBIDDEN = ("system(", "exec", "popen", "fopen", "open(", "socket", "remove(", "unlink",
             "fork(", "getenv", "fprintf", "printf", "stdio.h", "stdlib.h", "unistd.h", "fwrite")
ALLOWED_INCLUDES = ("arm_neon.h", "stdint.h", "stddef.h")


def guard(code: str) -> str | None:
    """Return reason string if the candidate looks unsafe/invalid, else None."""
    if "vec_dot_candidate" not in code:
        return "missing vec_dot_candidate"
    low = code.lower()
    for tok in FORBIDDEN:
        if tok in low:
            return f"forbidden token: {tok}"
    for inc in re.findall(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", code):
        if inc not in ALLOWED_INCLUDES:
            return f"disallowed include: {inc}"
    for bad in ("sdot", "udot", "vdotq", "vmmla", "i8mm", "svld", "svdot"):
        if bad in low:
            return f"used A9-illegal instruction: {bad}"
    return None


def extract_code(reply: str) -> str | None:
    m = re.search(r"```(?:c|cpp|c\+\+)?\s*\n(.*?)```", reply, re.S)
    if m:
        return m.group(1).strip()
    i = reply.find("#include")
    if i == -1:
        i = reply.find("void vec_dot_candidate")
    return reply[i:].strip() if i != -1 else None


def compile_cand(cand_path: pathlib.Path, bin_path: pathlib.Path, cflags: str) -> tuple[bool, str]:
    cmd = ["clang", *cflags.split(), str(HERE / "bench.c"), str(cand_path), "-o", str(bin_path)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return p.returncode == 0, p.stderr.strip()[:1500]


def run_bench(bin_path: pathlib.Path, env: dict) -> dict:
    e = {**os.environ, **env}
    p = subprocess.run([str(bin_path)], capture_output=True, text=True, timeout=120, env=e)
    for l in p.stdout.splitlines():
        i = l.find("{")
        if i != -1 and l.rstrip().endswith("}"):
            try:
                return json.loads(l[i:])
            except Exception:
                continue
    return {"ok": False, "error": f"no json (rc={p.returncode}): {p.stdout[-200:]} {p.stderr[-200:]}"}


def build_messages(champ_src: str, champ_m: dict, last: dict | None, hint: str, explore: bool):
    ctx = (f"CURRENT CHAMPION — {champ_m['ns_per_dot']:.3f} ns/dot, "
           f"{champ_m['gflops']:.1f} GFLOP/s, {champ_m['gbps']:.1f} GB/s "
           f"(d_in={champ_m['d_in']}, rows={champ_m['rows']}):\n```c\n{champ_src}\n```\n")
    if last:
        if last.get("status") == "compile_error":
            ctx += f"\nYOUR LAST ATTEMPT FAILED TO COMPILE:\n{last.get('err','')[:600]}\nFix it.\n"
        elif last.get("status") == "wrong":
            ctx += f"\nYOUR LAST ATTEMPT WAS NUMERICALLY WRONG (max_rel_err={last.get('max_rel_err')}). Re-check the nibble/half pairing.\n"
        elif last.get("status") == "slower":
            ctx += f"\nYour last attempt was correct but SLOWER ({last.get('ns'):.3f} ns/dot). Try a different angle.\n"
    if explore:
        ctx += "\nEXPLORE MODE: propose a STRUCTURALLY DIFFERENT approach, not a tweak of the champion.\n"
    ctx += f"\nSTRATEGY TO TRY THIS TIME: {hint}\nReturn a faster, correct candidate.c."
    return [{"role": "system", "content": ABI}, {"role": "user", "content": ctx}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--forever", action="store_true")
    ap.add_argument("--batch", type=int, default=4, help="candidates generated per round")
    ap.add_argument("--explore-every", type=int, default=6)
    ap.add_argument("--d-in", type=int, default=1152, help="Gemma 3 1B hidden=1152, ffn=6912")
    ap.add_argument("--rows", type=int, default=4096)
    ap.add_argument("--cflags", default=CFLAGS_DEFAULT)
    ap.add_argument("--seed-from", default=str(HERE / "candidate_seed.c"))
    ap.add_argument("--temperature", type=float, default=0.5)
    args = ap.parse_args()

    RUNS.mkdir(exist_ok=True); CHAMPS.mkdir(exist_ok=True)
    bench_env = {"D_IN": str(args.d_in), "ROWS": str(args.rows), "MIN_SECS": "0.4", "SEED": "1234"}
    G.METRICS_PATH = str(HERE / "cerebras_calls.jsonl")

    # ---- establish the champion from the seed ----
    champ_src = pathlib.Path(args.seed_from).read_text()
    seed_cand = RUNS / "champion.c"; seed_cand.write_text(champ_src)
    ok, err = compile_cand(seed_cand, RUNS / "bench_champ", args.cflags)
    if not ok:
        print(f"FATAL: seed kernel does not compile:\n{err}"); sys.exit(1)
    champ_m = run_bench(RUNS / "bench_champ", bench_env)
    if not champ_m.get("ok"):
        print(f"FATAL: seed kernel is incorrect/failed: {champ_m}"); sys.exit(1)
    print(f"[seed] {champ_m['ns_per_dot']:.3f} ns/dot  {champ_m['gflops']:.1f} GFLOP/s  "
          f"{champ_m['gbps']:.1f} GB/s  (d_in={args.d_in}, target={args.cflags})")
    shutil.copy(seed_cand, BEST)

    last = None
    rnd = 0
    t_start = time.time()
    total_iters = float("inf") if args.forever else args.iters
    done = 0
    while done < total_iters:
        rnd += 1
        explore = (rnd % args.explore_every == 0)
        b = args.batch
        hints = [HINTS[(rnd * b + k) % len(HINTS)] for k in range(b)]
        msgs = [build_messages(champ_src, champ_m, last, hints[k], explore) for k in range(b)]
        temp = 0.85 if explore else args.temperature

        def gen(m):
            try:
                txt, _ = G.chat(m, max_tokens=2200, temperature=temp)
                return txt
            except Exception as ex:
                return f"__CHAT_ERROR__ {ex}"
        replies = G.pmap(gen, msgs, workers=min(b, 8))

        results = []
        for k, reply in enumerate(replies):
            done += 1
            tag = f"r{rnd:03d}c{k}"
            rec = {"iter": done, "round": rnd, "tag": tag, "explore": explore, "hint": hints[k]}
            if isinstance(reply, dict) or str(reply).startswith("__CHAT_ERROR__"):
                rec["status"] = "chat_error"; rec["err"] = str(reply)[:200]; _log(rec); continue
            code = extract_code(reply)
            if not code:
                rec["status"] = "no_code"; _log(rec); continue
            why = guard(code)
            if why:
                rec["status"] = "rejected"; rec["err"] = why; _log(rec); continue
            cand = RUNS / f"{tag}.c"; cand.write_text(code)
            ok, err = compile_cand(cand, RUNS / f"{tag}.bin", args.cflags)
            if not ok:
                rec["status"] = "compile_error"; rec["err"] = err; _log(rec); results.append(rec); continue
            m = run_bench(RUNS / f"{tag}.bin", bench_env)
            if not m.get("ok"):
                rec["status"] = "wrong"; rec["max_rel_err"] = m.get("max_rel_err"); rec["err"] = m.get("error")
                _log(rec); results.append(rec); continue
            rec["status"] = "ok"; rec["ns"] = m["ns_per_dot"]; rec["gflops"] = m["gflops"]; rec["gbps"] = m["gbps"]
            rec["code"] = code; rec["metrics"] = m; _log(rec); results.append(rec)

        # ---- pick the fastest correct candidate and maybe promote ----
        good = [r for r in results if r.get("status") == "ok"]
        improved = False
        if good:
            best = min(good, key=lambda r: r["ns"])
            speedup = champ_m["ns_per_dot"] / best["ns"]
            if best["ns"] < champ_m["ns_per_dot"] * 0.997:
                champ_src = best["code"]; champ_m = best["metrics"]
                (RUNS / "champion.c").write_text(champ_src)
                shutil.copy(RUNS / "champion.c", BEST)
                stamp = CHAMPS / f"champ_{best['ns']:.2f}ns_iter{best['iter']}.c"
                stamp.write_text(champ_src)
                improved = True
                print(f"  round {rnd:>3} NEW BEST ▲ {best['ns']:.3f} ns/dot  "
                      f"({speedup:.3f}x vs prev)  {best['gflops']:.1f} GFLOP/s  [{best['hint'][:40]}]")
                last = None
            else:
                last = {"status": "slower", "ns": best["ns"]}
        if not improved:
            # carry the most informative failure back to the model
            ce = next((r for r in results if r.get("status") == "compile_error"), None)
            wr = next((r for r in results if r.get("status") == "wrong"), None)
            last = ({"status": "compile_error", "err": ce["err"]} if ce else
                    {"status": "wrong", "max_rel_err": wr.get("max_rel_err")} if wr else last)
            cur_best = min((r["ns"] for r in good), default=None)
            tail = f"best {cur_best:.3f}" if cur_best else "no valid candidate"
            print(f"  round {rnd:>3} no improvement (champ {champ_m['ns_per_dot']:.3f} ns/dot; {tail})")

    el = time.time() - t_start
    print(f"\nDONE {done} candidates in {el:.0f}s. Champion: {champ_m['ns_per_dot']:.3f} ns/dot "
          f"({champ_m['gflops']:.1f} GFLOP/s). Best kernel -> {BEST}")
    print(f"Cerebras: {json.dumps(G.summary())}")


def _log(rec: dict):
    slim = {k: v for k, v in rec.items() if k != "code"}
    with open(LEADER, "a") as f:
        f.write(json.dumps(slim) + "\n")


if __name__ == "__main__":
    main()
