# v25 profit-lock robustness audit

**Observed through:** 2026-08-08 20:03:44 UTC  
**Run:** `bidirectional-live-1786182011216`  
**Profile:** `multi_asset_bidirectional_complete_portfolio_canary_v25`  
**Fingerprint:** `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`

## Problem restatement

The all-live profit-lock challengers contain several positive strategy-policy
means even though every portfolio-wide policy trails actual exits. The missing
validation was whether a positive subset survives its most favorable path,
whether the policy actually triggered more than once, and whether the evidence
spans distinct live runs and profile contracts.

The added diagnostic is report-only. It must normalize every lifecycle by its
own entry notional, separate eligible from withheld paths, separate triggered
from non-triggered zero-delta paths, and expose sign and outlier sensitivity.

## Evidence and reasoning

The ML4T evidence-boundary and effective-sample principles were applied here:
raw lifecycle count is not treated as policy activation count, mixed sizing is
normalized to basis points, and a favorable mean is tested after removing its
largest contributor.

For the support-decay mechanism across 29 eligible all-live lifecycles:

| Policy | Mean delta | Triggered | Triggered mean | Leave worst | Leave best |
|---|---:|---:|---:|---:|---:|
| `a25_floor15_trail10` | -21.84 bps | 13 | -48.72 bps | -11.28 bps | -26.36 bps |
| `a40_floor15_trail20` | -18.82 bps | 13 | -41.98 bps | -8.13 bps | -23.21 bps |
| `a60_floor15_trail30` | -19.26 bps | 9 | -62.07 bps | -8.23 bps | -21.30 bps |

All three remain negative after removing their single most adverse path. The
mechanism therefore does not become attractive merely by excluding one bad
outlier.

The strongest apparent provider subset was HYPE-breakout SOL with support-decay
`a40`:

- three eligible lifecycles across two runs and two profile fingerprints;
- mean delta `+13.5621 bps`;
- median `0.0 bps`;
- only one lifecycle triggered;
- that trigger contributed `+40.6864 bps`;
- removing the most favorable lifecycle leaves `0.0 bps`.

This is one successful mechanism event rather than repeatable policy evidence.
It remains valuable as a frozen challenger, but it does not support live
promotion.

The 9.09-minute live-prefix delta adds no fills, closes, fees, funding, wins,
losses, or resolved net PnL. Its journal recommendation remains false.

## Implementation and validation

- Added
  `src/hypervector/research/cohort_profit_lock_robustness.py`.
- Every normalized all-live profit-lock mechanism now publishes
  `robustness_by_policy` at portfolio and provider-symbol levels.
- Diagnostics include eligible/withheld/triggered counts, distinct run/profile
  counts, positive/negative/zero counts, positive fraction, mean, median,
  minimum, maximum, leave-most-favorable mean, and leave-most-adverse mean.
- Test-first validation proved that a synthetic `+100/-10/-10 bps` sample has
  a positive mean but a `-10 bps` leave-most-favorable mean. The initial test
  failed before the module and integration existed.
- Focused profit-lock/audit/checkpoint suite: `49 passed`.
- Full non-network suite: `4,125 passed`, four deselected, 27 known warnings.
- Ruff lint and formatting passed for the changed files.

Immutable audit:

`data/logs/research/bidirectional_cohort/v25_live_prefix_profit_lock_robustness_20260808T200356Z.json`

SHA-256:

`a0be77cf562636614273a67ddfb73def5036ef87930bf7f84dbc72e10a0d1c34`

Immutable delta:

`data/logs/research/bidirectional_cohort/v25_live_prefix_delta_20260808T195443Z_20260808T200356Z.json`

SHA-256:

`948c254d564ff90c19e4eb04d8cc2599545c36c88308e03cc1b6fff38fcff039`

## Recommendation and trade-offs

| Option | Evidence | Trade-off | Recommendation |
|---|---|---|---|
| Promote a portfolio-wide profit lock | Negative with and without worst outlier | Earlier protection but materially lower historical capture | Do not promote |
| Promote SOL support-decay `a40` | One beneficial trigger, two zero-delta lifecycles | Mechanistically promising but entirely one-event dependent | Keep frozen/report-only |
| Keep measuring exact triggered outcomes | Preserves causal live evidence | Requires more lifecycle time | Continue |
| Remove the challengers | Simplifies reports | Discards a plausible conditional mechanism | Do not remove |

No live strategy, exit, order, stop, target, position, allocation, profile, or
runtime process changed.

## Uncertainty and falsifiers

Confidence is high for the normalized arithmetic, outlier sensitivity, source
counts, and execution isolation. Confidence is medium that the current
portfolio-wide profit-lock candidates are harmful under the measured live
history because source profiles differ. Confidence is low for the SOL-specific
mechanism because it has one trigger.

Repeated independent SOL triggers with positive venue-costed deltas and a
positive leave-most-favorable result would update the SOL conclusion. A
positive portfolio-wide result that survives source-profile splits, costs, and
both outlier removals would update the general conclusion. Incorrect notional
normalization, a withheld lifecycle included as eligible, truncated history,
an immutable hash mismatch, a report-only execution side effect, profile drift,
a missing stop, or a runtime fault would falsify the corresponding claim.
