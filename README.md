# AIQ — Real-time, formally-verified bond intelligence

**Cerebras + Gemma. Fast enough for mobile, trustworthy enough for the trading desk.**

A credit analyst asks "compare these two bonds — which is the better buy?" and gets a
complete, knowledge-graphed, **Lean-formally-verified** answer in the time a GPU provider
takes to finish its first paragraph. The verification is the enterprise unlock: in fixed
income a hallucinated coupon or maturity is a fireable mistake, so *every numeric claim is
proved by Lean's kernel before it reaches the screen*. Verify-as-you-go is only interactive
because Cerebras is fast enough to run generation **and** verification inside a human
attention span.

## What's in the demo

- **Live side-by-side** — the same Gemma model streamed from Cerebras vs a conventional GPU
  host, with live TTFT / tokens-per-second / end-to-end latency counters on each side. Both
  engines are **warmed on page load** so the first measured run reflects steady-state speed,
  not cold-start latency.
- **The race, made visceral** — a shared-axis chart overlays both engines' cumulative tokens
  over time (Cerebras spikes near-vertical; the GPU curve crawls), next to a single
  **`N×` throughput readout** and a live "Cerebras done · GPU still generating" status.
- **Formally-verified-answer headline** — when the proof completes, one line fuses both
  differentiators: *"Formally-verified answer in N s — M/M facts proved by Lean · GPU host
  answered unverified in X s."*
- **Formally verified facts** — each quantitative claim (yield differential, spread, coupon
  ordering, maturity ordering, duration gap) is compiled into a real Lean `theorem` proved by
  `decide` over integer basis-points, run through the actual `lean` binary. ✓/✗ is the
  kernel's verdict, not a model's opinion.
- **Bond knowledge graph** — issuer / sector / similarity edges over the bond universe;
  "find the 6 nearest bonds by yield · spread · duration · rating".
- **Built like a product, not a demo** — responsive down to phone widths (metrics reflow to a
  2×2 grid), with `prefers-reduced-motion` support, visible focus rings, and a polite
  `aria-live` region that narrates milestones to screen readers.

## Run it

```bash
pnpm install
pnpm dev        # http://localhost:3000
```

The app runs immediately in **simulated mode** (clearly flagged in the UI) so you can see the
full workflow with no keys. To make the side-by-side fully live, copy `.env.example` to
`.env.local` and add keys:

```bash
cp .env.example .env.local
# CEREBRAS_API_KEY=...   CEREBRAS_MODEL=<your Gemma model id>
# GPU_API_KEY=...        GPU_BASE_URL=...   GPU_MODEL=<same Gemma model>
```

Both backends are OpenAI-compatible (`/chat/completions`, `stream:true`), so any GPU host of
the same Gemma works for an honest A/B (Together / Fireworks / etc.).

### Lean (formal verification)

Installed via [`elan`](https://lean-lang.org):

```bash
curl https://elan.lean-lang.org/elan-init.sh -sSf | sh -s -- -y --default-toolchain stable
```

Proofs are pure integer arithmetic (basis points / tenths) checked with `decide`, so **no
mathlib** is needed — verification is a sub-second, dependency-free `lean` invocation. The app
finds the binary at `~/.elan/bin/lean` (override with `LEAN_BIN`). If Lean is absent the UI
says so honestly instead of faking a ✓.

## Architecture

```
app/
  page.tsx              orchestrator: race chart, split-screen stream, metrics, verified-answer
                        banner, verified facts, graph, aria-live narration
  api/compare/route.ts  SSE stream from one provider, server-measured TTFT / tok-s / latency
  api/verify/route.ts   build claims from source data -> run Lean -> per-claim verdicts
  api/warmup/route.ts   1-token ping to both engines on load -> steady-state first run
lib/
  providers.ts          Cerebras + GPU (OpenAI-compatible) streaming + simulated fallback
  bonds.ts              data load, knowledge graph, cosine similarity
  claims.ts             numeric claims -> Lean theorem strings (integer basis points)
  lean.ts               write .lean, spawn `lean`, parse verdicts
components/
  KnowledgeGraph.tsx    deterministic clustered SVG graph
data/bonds.json         pre-baked bond universe (SpaceX pair + curated peers)
```

> Figures in `data/bonds.json` are plausible but synthetic. The *pipeline* — streaming
> inference, Lean verification, and the graph — is real.
