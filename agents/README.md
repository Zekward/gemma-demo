# How the Gemma-4 agents should operate

Two inputs shaped this: (1) the **AIQ Markets system prompt** — distilled into
[fi_agent_doctrine.md](fi_agent_doctrine.md), the stable fixed-income + integrity prefix every
agent carries; (2) **Autodata** (Weston et al., Meta, arXiv:2606.25996) — a blueprint for how to
*structure* and *improve* data-creating agents. Autodata's lesson: don't write one big agent —
decompose into narrow single-job subagents, ground everything in a structured extract, iterate
with a judge, and meta-optimize the prompts.

## The agent roles (Autodata decomposition → bond pipeline)

| Autodata role | Our agent | Job |
|---|---|---|
| **Extractor** | `extract` | Read ONE SEC doc → structured, grounded node (the P0 prompt). Output becomes the **"source of law."** |
| **Challenger / Writer** | `compare` | Given two near-dup extracts → the delta + a rubric for *why it matters* (the P1 contrastive diff). |
| **Verifier / Judge** | `verify` | Reject any value/diff not grounded in a cited span; emit structured feedback. |
| **Main agent** | orchestrator | The Workflow/pipeline; reuses the extract across rounds, passes judge feedback verbatim. |

**The load-bearing idea — "extract as source of law":** downstream agents reason ONLY over the
grounded extract + cited spans, never over raw parametric knowledge. This is the same discipline
as the AIQ "never fabricate a field that isn't in the source" rule, and it's what keeps a small
model honest. Small models do markedly better with **narrow jobs + hard grounding constraints**
than with one broad "analyze this bond" prompt.

## The inner loop (per example)

```
extract(doc) → compare(a,b) → verify → accept?
                    ▲                     │ no: structured feedback
                    └─────────────────────┘  ("diff X not grounded in B")
                       regenerate from a DIFFERENT angle, not a tweak
```

Autodata's finding: on rejection, ask for "an entirely new question from a different reasoning
angle" rather than nudging the old one. Apply the same to a rejected diff/extract.

## The outer loop (meta-optimization) — also the benchmark + the iPhone demo

Autodata's second contribution: **evolve the agents' PROMPTS**. Run → an analyzer reads the
trajectories and finds systematic failures (e.g. "hallucinates coupon when only an ISIN is
present") → a code-editor patches the prompt as a diff → accept only if a held-out validation set
improves (Boltzmann-sampled parents, T=0.1; 62%→80% in the paper). This is **GEPA-style** (you
already have `cutedsl/gepa-src`) and it is *literally* the autoresearch-loop-on-iPhone story —
just optimizing an agent prompt instead of a CUDA kernel. Same loop shape, runnable on Cerebras.

Note: the AIQ codebase already has this TODO — auto-update its market-knowledge block via
`product_engineering_review.py` with "expert-in-the-loop." Autodata is the generalization.

## This also answers "how do I build the benchmark"

Autodata's **weak/strong gap** is the recipe. Generate a bond question grounded in a real
indenture/prospectus, run a **weak solver (small Gemma)** and a **strong solver (Opus)**; keep the
example only if strong succeeds, weak struggles, and the gap clears a threshold — *calibrated for
learnability* (don't keep all-zero-weak items; the paper raised weak-rollout variance to get a
usable training signal). That discriminative, rubric-scored set is simultaneously:
- your **fixed-income benchmark** (verifiable, span-grounded rubrics), and
- your **GRPO training data** for the small Gemma (ties to `cutedsl/aiq/evals` + the Conductor work).

So the same agent machinery that builds the RAG graph also mints the benchmark and the RL data —
one pipeline, three outputs.
