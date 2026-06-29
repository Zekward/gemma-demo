# 60-Second Demo Video — Shot List & Script

Goal the judges are scoring: **Cerebras speed unlocks a capability that's impossible at GPU
latency** — interactive, formally-verified bond research. Not "it's faster." "Speed makes a
new enterprise workflow possible."

**Before recording**
- Run live if at all possible: put real keys in `.env.local` (Cerebras + a GPU host of the
  *same* Gemma model) so the counters are real. Simulated mode is the fallback.
- Browser at ≥1280px wide so the split-screen is side-by-side. Zoom so both metric strips are
  legible. Hide bookmarks bar.
- Have the SpaceX pair pre-selected (it's the default). Mouse near the **Run comparison**
  button. The engines auto-warm on load — wait for the green "engines warm · steady-state
  speed" chip under the button before recording, so the first run shows true Cerebras speed.

| Time | On screen | Voiceover |
|------|-----------|-----------|
| **0–8s** | Slow scroll over a stack of SEC filings / a 200-page prospectus PDF (b-roll or a filing open in a tab). Cut to the AIQ app, idle, query visible in the header. | "Comparing two corporate bonds means hours reading prospectuses and filings — and on a trading desk, one wrong number is a fireable mistake." |
| **8–20s** | Click **Run comparison**. The **race chart** fills live — the Cerebras curve spikes near-vertical while the GPU curve barely lifts — and the **`N×` throughput** number lands beside it. Cerebras TTFT sub-second, tok/s into the hundreds; GPU still on its first tokens. | "Same question, same Gemma model, two engines. Watch the throughput: Cerebras streams the full analysis while the GPU is still on its first paragraph." |
| **20–35s** | Cerebras completes; the green **"Formally-verified answer in N s"** banner pops in ("M/M facts proved by Lean · GPU host still generating"). Pan down: the **bond knowledge graph** lights up — SpaceX '27 and '30 highlighted, similarity edges fanning to comparable bonds. GPU side still streaming. | "Cerebras finishes a complete, graphed, *formally-verified* answer — before the GPU finishes a sentence." |
| **35–48s** | The **Formally Verified Facts** cards pop in one by one, each flipping to a green ✓ **Verified in Lean**. Hover one card → the Lean `theorem … := by decide` source appears. Linger on "✓ 5/5 proved · Lean v4.31". | "And every number is formally verified — compiled to a Lean theorem and proved by the kernel. No hallucinated coupons or maturities reach the desk." |
| **48–56s** | Pick up an iPhone showing the same URL; tap **Run**; the verified answer streams on the phone, snappy. | "Fast enough to run on a phone in the field." |
| **56–60s** | Pull to AIQ logo + tagline card. | "Trustworthy enough for the desk. That's AIQ, on Cerebras." |

## The three things that make or break it

1. **Lean must be visibly real.** Hover a card so the actual `theorem … := by decide` shows,
   and let the "✓ 5/5 proved · Lean version 4.31.0" line be readable. That on-screen proof
   source is the moat — judges have seen faked ✓ badges.
2. **The side-by-side must be honest and live.** Real Cerebras key + real GPU host of the
   *same* Gemma. If you must use simulated mode, the UI already labels it `SIMULATED` — don't
   hide that; instead, narrate "characteristic speeds" and show one live run if you can.
3. **Show Gemma doing something multimodal.** One shot of Gemma reading the filing *page
   image* and extracting the bond terms (the ingestion strip) — otherwise the "Gemma
   multimodal" criterion scores zero. See `docs/MULTIMODAL.md`.

## Capture tips

- macOS screen record: `⇧⌘5`, record the browser window only, 60fps if available.
- Record the desktop run and the phone run separately, then cut together — don't try to do
  both in one take.
- If a live run is too fast to read the GPU lag, that's a *good* problem: slow the clip to
  0.5× for the 8–20s segment and speak over it.
```
