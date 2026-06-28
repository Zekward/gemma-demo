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
- [ ] **Cerebras speed variance** — saw 446 t/s (TTFT 191ms) one run, 36 t/s (TTFT 4071ms) another.
      Investigate model id `gemma-4-31b` correctness, throttling, warm-up; the "fast inference"
      story collapses if Cerebras lands at 36 t/s on camera. Consider a warm-up ping before the race.
- [ ] Cumulative tokens-over-time sparkline per provider
- [ ] Typography & spacing polish pass (less generic dark-theme)
- [ ] Number formatting (thousands separators, monospaced tabular figures)
- [ ] Accessibility: focus states, aria-live for streaming regions, reduced-motion
- [ ] Empty/loading states refinement
- [ ] Mobile/responsive tightening
- [ ] Header: tighten the value prop, add a subtle AIQ/Cerebras lockup

## Done
- [x] **Cycle 1 — Live race strip + speedup multiplier.** Two lanes fill in real time above the
      panels; Cerebras saturates + shows "✓ done · proving…" while "GPU still generating…". Center
      shows live `N×` throughput ratio. Verified in browser end-to-end.

## Cycle notes
- Baseline captured: app runs, Cerebras streams ~real, Lean proves 5/5, graph renders.
- Tooling note: browser-preview MCP is bound to this repo dir + port 3000; run the dev server here.
</content>
