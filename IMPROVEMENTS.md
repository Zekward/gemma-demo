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
- [ ] Cumulative tokens-over-time sparkline per provider
- [ ] Typography & spacing polish pass (less generic dark-theme)
- [ ] Number formatting (thousands separators, monospaced tabular figures)
- [ ] Accessibility: focus states, aria-live for streaming regions (reduced-motion done in cycle 3)
- [ ] Empty/loading states refinement
- [ ] Mobile/responsive tightening
- [ ] Header: tighten the value prop, add a subtle AIQ/Cerebras lockup

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

## Cycle notes
- Baseline captured: app runs, Cerebras streams ~real, Lean proves 5/5, graph renders.
- Tooling note: browser-preview MCP is bound to this repo dir + port 3000; run the dev server here.
</content>
