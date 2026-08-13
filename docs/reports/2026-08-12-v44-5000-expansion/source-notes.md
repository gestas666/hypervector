# Hypervector v44 and $5,000 Portfolio Expansion Review — source notes

## Evidence boundary

- Live metrics are frozen from the v39 checkpoint generated at `2026-08-12T04:31:23.907479+00:00`.
- v44 configuration and stress metrics are bound to profile fingerprint `a947c234d900f01ba993358e75ef44589a3262e000d0a67070c94c353dc1249a`.
- MU, SKHX, and CL results are development-only and do not imply validation or holdout performance.
- All PnL is after modeled or realized fees and funding as declared by each source artifact.

## Chart map

1. `v39-route-pnl-chart`: signed horizontal comparison of the six provider-symbol routes contributing to the seven current-run closes.
2. `regime-accuracy-chart`: grouped primary-regime directional accuracy by forward horizon with a 50% reference line.
3. `candidate-pf-chart`: nominal versus stressed development profit factor for MU, SKHX, and CL; unresolved lifecycle counts remain visible in tooltips and narrative.

## Deliberately omitted views

- No equity curve: seven v39 closes are too few for a useful path graphic; route contribution is the actionable question.
- No correlation heatmap: the exact eight-asset return panel has zero shared timestamps, so a covariance matrix would be fabricated.
- No projected monthly income: the current evidence does not support a stable frequency or expectancy forecast.
- No ten-slot allocation chart: v44 has three actual asset slots; seven additional allocations do not exist yet.

## Interpretation rules

- Capacity is not a target. An empty slot is preferable to a route that failed later chronological partitions.
- The p99 stop wave is a deterministic stacked sensitivity, not a joint-probability estimate or a guaranteed loss ceiling.
- Pooled regime observations overlap. Episode-onset samples are smaller but closer to the intended independent-event question.
- Positive development economics with unresolved execution paths remain research evidence, not live authority.
