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
- [ ] Typography & spacing polish pass (less generic dark-theme)
- [ ] Number formatting (thousands separators, monospaced tabular figures)
- [ ] Accessibility: focus states, aria-live for streaming regions (reduced-motion done in cycle 3)
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

## Cycle notes
- Baseline captured: app runs, Cerebras streams ~real, Lean proves 5/5, graph renders.
- Tooling note: browser-preview MCP is bound to this repo dir + port 3000; run the dev server here.
