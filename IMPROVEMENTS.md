# gemma-demo — continuous improvement log

Tracks an autonomous improvement loop on the `improvements` branch (the literal sibling
clone lives at `../gemma-demo-lab` as a backup; iteration happens here so the browser
preview tooling — bound to this repo — can verify each change). `main` preserves the
hackathon submission untouched. Each cycle: pick the highest-value item, investigate,
execute, verify in the browser, commit.

Two north stars:
1. **Demonstrate fast inference for Cerebras** — make the speed contrast visceral and undeniable.
2. **Reduce the "vibecoded" feel** — intentional, dense, terminal-grade UI; not generic AI dark theme.

## Backlog (unordered ideas)
- [ ] Typography & spacing polish pass (less generic dark-theme; subjective — only if clearly better)
- [ ] Number formatting (thousands separators, monospaced tabular figures)
- [ ] (a11y largely covered: reduced-motion in cycle 3, focus-visible in cycle 5, aria-live in cycle 8)
- [ ] Empty/loading states refinement

## Done
- [x] **Cycle 1 — Live race strip + speedup multiplier.** Two lanes fill in real time above the
      panels; Cerebras saturates + shows "✓ done · proving…" while "GPU still generating…". Center
      shows live `N×` throughput ratio. Verified in browser end-to-end.
- [x] **Cycle 2 — Warm-up ping (fixes cold-start credibility).** New `/api/warmup` fires a 1-token
      request to both engines on page load (`lib/providers.ts:warmupProvider`); a green "engines
      warm · steady-state speed" badge appears under Run. Measured impact: Cerebras TTFT 4071ms→712ms,
      36→151 t/s, headline 3.6×→**11×** on a warm run. No-op + "simulated" label without keys.
- [x] **Cycle 3 — Designed states (de-vibecode).** Replaced the `🧠 reasoning…` emoji with a
      designed three-dot "Reasoning" indicator (`dotPulse` keyframe, staggered delays); added
      `prefers-reduced-motion` support that holds pulse/dots/pop-in/caret still. Verified the
      indicator renders (injected-markup screenshot) since the thinking state rarely triggers live.
- [x] **Cycle 4 — Shared throughput chart.** Upgraded the race strip: replaced the two lane bars
      with a single SVG chart overlaying both providers' cumulative-token curves on a shared time
      axis. Cerebras spikes near-vertical at the left; the GPU curve crawls across the bottom — the
      speed gap is legible at a glance. Live time-series collected from the metric stream
      (`appendSample`). Verified in browser mid-race (23× run, Cerebras 312 t/s).
- [x] **Cycle 5 — Product masthead (de-vibecode header).** Replaced the inline "AIQ Bond
      Intelligence" text with a monogram lockup (rounded "AIQ" mark + wordmark + refined tagline),
      a structured "Analyst query" chip with divider, a cleaner CTA (dropped the ▶ glyph) with a
      `focus-visible` ring, and a header bottom-border for structure. Verified in browser.
- [x] **Cycle 6 — "Formally-verified answer in Ns" banner.** The climax that fuses both
      differentiators: a green ✓ banner (appears on verify-done) showing Cerebras answer-time +
      Lean proof-time as one number, with "N/N facts proved by Lean's kernel" and either "GPU still
      generating its first draft" or "GPU answered unverified in Xs". Verified in browser
      (e.g. verified in 3.2s vs GPU unverified in 6.6s).
- [x] **Cycle 7 — Mobile QA pass + metric-row fix.** Audited 360/390px: masthead, controls,
      race strip, banner all wrap cleanly with no page overflow. Found + fixed a real bug — the
      provider panels' 4-up metric row clipped at 360px (308px in 294px); now a responsive
      2×2 grid on mobile, 4-up (`sm:grid-cols-4`) on larger. Verified both breakpoints.
- [x] **Cycle 8 — Screen-reader accessibility (aria-live).** Added a visually-hidden polite live
      region that narrates milestones (not every token): "Formally verified answer in N seconds.
      M of M facts proved by Lean." Gave the verified-answer banner `role="status"` and the
      throughput chart `role="img"` with a dynamic `aria-label` describing the speed gap. Verified
      the live region updates and is correctly sr-only.
- [x] **Cycle 9 — Docs capstone + wind-down.** Updated README.md, SUBMISSION.md, and
      VIDEO_SCRIPT.md to accurately describe the improved demo (race chart + `N×` readout,
      warm-up for steady-state speed, the formally-verified-answer banner, accessibility), with
      no overclaiming. Ran a full end-to-end check at 1280px (32× run, 5/5 proved, no console
      errors). **Loop wound down here** — remaining backlog is low-value/subjective.
- [x] **Cycle 10 — Throughput-chart rendering polish (loop restarted).** The chart stretches
      its SVG (`preserveAspectRatio="none"`) to span the full time axis, which was also squashing
      the idle placeholder text and warping the end-point dots into ellipses. Moved the placeholder
      and the latest-value dots to crisp HTML overlays positioned by percentage; the SVG now carries
      only the (intentionally stretched) curves. Verified: idle text crisp, dots round (9×9),
      curves intact, "GPU still generating" banner variant captured.
- [x] **Cycle 11 — Knowledge-graph legibility pass.** The graph was the least-polished surface:
      node labels collided with edges (no halo) and top-row labels clipped off-canvas (y≈-4).
      Added a panel-colored text halo (`paintOrder: stroke`) so labels read cleanly over edges,
      and flip labels below their node when an above-position would clip the top edge. Verified.
- [x] **Cycle 12 — Don't let the slow GPU lock the UI.** `run()` awaited the GPU stream before
      `setRunning(false)`, so the Run button + selectors stayed disabled for the GPU's full
      duration — and server logs showed real GPU `/api/compare` calls taking 18s–2.1min while
      Cerebras finishes in ~300ms. Now the UI unlocks the instant the verified answer is ready
      (~3.8s), and the GPU keeps streaming in the background (panel/chart/banner still update).
      Added an `AbortController` so a fresh run cancels the prior in-flight GPU request, and
      guarded the verify reveal timeouts against a superseded run. Verified: button re-enables
      while GPU still streaming; typecheck + console clean.
- [x] **Cycle 13 — "Controlled A/B" bar (honest, demonstrable comparison).** Audited what's held
      constant: prompt (`buildMessages`), sampling (temp 0.3 / max 1500 / stream — same code path),
      server-side timing, warm-up, input bonds — all identical for both engines. Surfaced it as a
      bar between the chart and panels: "only the inference engine differs: ✓ same Gemma model ✓
      same prompt ✓ temperature 0.3 ✓ max 1,500 tokens ✓ both pre-warmed ✓ identical server-side
      timing." Sampling values come from a new shared `lib/sampling.ts` (`SAMPLING`) that the API
      also sends, so the displayed params can't drift from reality. Caveats to confirm out-of-band:
      genuine model-checkpoint parity (`gemma-4-31b` vs `google/gemma-4-31B-it`) and serving
      precision are provider-controlled. Verified in browser.
- [x] **Cycle 14 — GPU pending/elapsed indicator.** After cycle 12 the UI unlocks early, leaving
      the GPU panel sitting on a bare "…" during its (real) 18s–2min wait. Replaced it with a live
      "waiting for first token · N.Ns" counter; past 5s the GPU adds an honest note: "conventional
      GPU hosts queue & cold-start — Cerebras already answered." Turns the dead wait into part of
      the speed story. Verified: at 24s the GPU still had no first token while Cerebras was done
      and 5/5 proved.
- [x] **Cycle 15 — End-to-end verification + wind-down (no feature).** Backlog exhausted of
      genuinely valuable items, so rather than pad, ran a full E2E check at 1280px: all 14 cycles
      render and work together — warm badge, Controlled A/B bar, throughput chart (round dot),
      "Formally-verified answer in 2.9s · GPU still generating" banner, 5/5 proved, Cerebras
      138ms / 475.6 t/s, GPU pending indicator counting (24s→83s, no first token). Console clean,
      typecheck green. **Loop wound down again** — remaining backlog (number formatting, subjective
      typography, empty-state tweaks) isn't worth shipping. Open follow-up: confirm model-checkpoint
      parity + unify the displayed model name once the user provides the two provider model IDs.

## Cycle notes
- Baseline captured: app runs, Cerebras streams ~real, Lean proves 5/5, graph renders.
- Tooling note: browser-preview MCP is bound to this repo dir + port 3000; run the dev server here.
