# AIQ — Project Description (Cerebras × Gemma Hackathon · Track 3: Enterprise Impact)

> Paste-ready for the Discord submission. Trim to the channel's length limit if needed.

## One-liner

**AIQ: real-time, formally-verified bond intelligence. Powered by Cerebras + Gemma — fast
enough to run on your phone, trustworthy enough for a trading desk.**

## The problem

Comparing two corporate bonds today means a credit analyst reading hundreds of pages of
prospectuses and SEC filings, by hand, to reconcile coupons, maturities, spreads and
duration. It is slow, and it is error-prone in a domain where a single wrong number — a
misread coupon or maturity — is a fireable, P&L-moving mistake. LLMs can read the filings,
but on a trading desk "the model said so" is not good enough: you cannot put an
unverifiable number into a trade ticket.

## What we built

A credit analyst asks *"compare SpaceX's two bonds — which is the better buy?"* and AIQ
returns a complete, decision-ready answer:

1. **A streamed analysis** of the carry-vs-duration trade-off from **Gemma on Cerebras**, shown
   side-by-side against a GPU host of the same model. A live chart races both engines' token
   curves on a shared axis and distills the gap into a single **`N×` throughput** number
   (engines are pre-warmed so the figure reflects steady-state, not cold-start, speed).
2. **A bond knowledge graph** placing both notes in their sector/issuer neighborhood and
   surfacing the nearest comparable bonds by yield, spread, duration and rating.
3. **Formally verified facts** — every quantitative claim (the 55 bps yield pickup, the
   50 bps wider spread, the coupon and maturity ordering, the 2.2y duration gap) is compiled
   to a **Lean theorem and proved by Lean's kernel** before it is shown. The green ✓ is a
   formal proof, not a model's self-assessment.

The unlock is speed: **verify-as-you-go is only interactive because Cerebras runs generation
*and* formal verification inside a human attention span** — the Cerebras side finishes a
graphed, proven answer before the GPU side finishes its first paragraph. The app says this in
one line: *"Formally-verified answer in N s — M/M facts proved by Lean · GPU host answered
unverified in X s."*

## How it maps to the judging criteria

- **Business Impact** — collapses hours of manual fixed-income research (enterprise search +
  knowledge management over filings and the bond universe) into seconds, with a correctness
  guarantee a bank can actually underwrite.
- **Production Readiness** — AIQ is a real, deployed credit-intelligence platform (FINRA /
  MarketAxess ETL, neo4j graph, Phoenix observability, ECS). This demo swaps a Cerebras
  inference + Lean verification layer into that production stack; it is not a throwaway toy.
- **Technical Excellence** — a formal-verification layer (Lean 4) gating model output is the
  standout: numeric claims become integer-arithmetic theorems checked by the kernel via
  `decide`, sub-second and dependency-free. Almost no one ships verified LLM output.
- **AI Differentiation** — **Cerebras speed = the interactivity** (live TTFT / tok-s /
  latency shown side-by-side against a GPU host of the *same* Gemma model); **Gemma's
  multimodal capability = reading the actual filing** (vision extraction of bond terms
  straight from a prospectus page).

## Stack

Next.js + TypeScript · Gemma via Cerebras (OpenAI-compatible streaming) · GPU comparison via
any OpenAI-compatible host · Lean 4 formal verification · responsive, accessible UI (mobile
reflow, reduced-motion, focus-visible, aria-live screen-reader narration).

## Honesty notes

The bond figures in the demo dataset are plausible but synthetic; the pipeline — streaming
inference, the side-by-side latency measurement, the Lean proofs, and the graph — is real and
runs live. Lean verdicts are produced by invoking the actual `lean` binary at request time.
