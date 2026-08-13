# Venue-native 1m order-flow impulse development review

Date: 2026-08-09 EDT  
Status: reject exact deterministic and ML family  
Execution authority: none  
Runtime strategy changed: false

## Systems decision

Do not add this one-minute BTC/SOL order-flow impulse family to v30 or another
live profile. Completed one-minute price shocks with aligned public-trade flow
had approximately zero gross edge before the registered 13-bps round-trip
friction. Neither terminal L2 agreement, reversal, Ridge, nor shallow LightGBM
produced a stable after-cost exception.

This rejects the frozen event, barrier, and feature/model family. It does not
establish that all one-minute order-flow research is futile. No nearby threshold
or barrier sweep should be run on this development interval; that would convert
a predeclared rejection into post-hoc selection.

Confidence is high for rejecting the exact family on the measured development
data. Confidence is low about all possible event-driven order-flow mechanisms.

## Frozen contract

- Symbols: BTC and SOL, both long and short.
- Development: `2025-07-28T00:00:00Z` through
  `2026-01-28T00:00:00Z`.
- Causal warmup: 10,080 completed consecutive one-minute bars, re-earned after
  every gap.
- Base event: prior-seven-day 90th-percentile absolute body move,
  prior-seven-day 75th-percentile public-trade volume, and signed aggressive
  flow aligned with the move.
- Arms: continuation, continuation with two-of-three L2 agreement, reversal,
  and reversal with two-of-three opposing L2 components.
- Entry: next-minute open.
- Exit: 30-bps target, 20-bps stop, or 15-minute timeout with pessimistic
  stop-first handling.
- Nominal cost: 13 bps; stress cost: 20 bps; official funding included.
- One position per symbol within each arm.
- Ridge and shallow LightGBM: three outcome-time-purged expanding folds,
  annotation-only, with selection thresholds learned from each training fold.

## Data coverage and gaps

The archive contains substantial raw source history:

| Symbol | Raw L2 rows | Raw trade rows | Development base events |
|---|---:|---:|---:|
| BTC | 57,353,560 | 163,051,872 | 2,765 |
| SOL | 75,220,850 | 63,652,648 | 877 |
| ETH | 0 | 0 | unavailable |
| HYPE | 0 | 0 | unavailable |

Within the warmup-plus-scoring query, BTC contained 25 discontinuities and SOL
59. The largest gaps were 11 minutes and one day plus one minute,
respectively. The longest complete segment was 21,512 minutes for both assets.
After resetting rolling history at every discontinuity, 43,120 BTC and 15,110
SOL scored feature minutes remained. This explains the sparse first
chronological fold and is preserved as evidence rather than filled or ignored.

The gap handling is conservative. It reduces representativeness, but it does
not rescue an event family that was strongly negative in every sufficiently
populated fold and every asset-side cell.

## Deterministic economics

### Aggregate nominal result

| Arm | Trades | Mean | Net | PF | Net excluding largest winner |
|---|---:|---:|---:|---:|---:|
| Continuation | 2,234 | -12.59 bps | -28,137 bps | 0.30 | -28,157 bps |
| Continuation + L2 aligned | 1,275 | -11.65 bps | -14,854 bps | 0.33 | -14,874 bps |
| Reversion | 2,337 | -12.91 bps | -30,176 bps | 0.27 | -30,198 bps |
| Reversion + L2 opposed | 1,449 | -12.27 bps | -17,781 bps | 0.29 | -17,803 bps |

The continuation mean of -12.59 bps after a 13-bps nominal cost implies only
about +0.41 bps before the registered round-trip friction. The raw event
therefore contains no material economic margin for execution error.

Stress-cost results were worse: means ranged from -18.65 to -19.91 bps. Every
BTC/SOL long/short cell was negative nominally. The least-negative cell was SOL
short reversion with opposing L2 at -10.48 bps per trade and PF 0.41, which is
not a viable exception.

## Annotation-model result

| Model | Mean daily rank IC | Positive-mean folds | Selected trades | Selected net | PF |
|---|---:|---:|---:|---:|---:|
| Ridge | -0.0337 | 2/3 | 488 | -6,008 bps | 0.27 |
| LightGBM | -0.0427 | 1/3 | 385 | -4,179 bps | 0.35 |

Both training-fold 80th-percentile prediction thresholds were negative in
every fold. That is direct evidence that the fitted models did not expect even
their preferred event tail to clear costs. Selected economics remained deeply
negative and became worse after removing the largest winner. Keep both models
out of routing, sizing, entry, and exit authority.

## Validation and failure modes

Focused tests cover:

- feature prefix invariance;
- rejection of future L2 observations;
- symmetric long/short event construction;
- next-bar entry;
- pessimistic simultaneous-barrier ordering;
- exact 13/20-bps friction reconciliation;
- funding direction;
- one-position-per-symbol serialization;
- archive coverage without fabricated ETH/HYPE rows; and
- outcome-time-purged OOS model predictions.

The result would be invalidated by changed artifact bytes, an observation after
decision time, a signal-bar entry, an unreported gap fill, inverted funding,
incorrect side pairing, or an overlap counted as an independent accepted
lifecycle. Private queue position, cancel dynamics, and sub-minute path order
remain unmodeled; those limitations would normally weaken a positive result,
not explain an approximately zero pre-cost mean.

## Portfolio recommendation

1. Preserve v25 while its protected positions remain open.
2. Keep the inactive lean v30 candidate unchanged: SOL Range Onset, ETH
   dual-MTF Range Onset, and SPCX Swing/HA, both sides.
3. Do not add this impulse family to v30 and do not increase leverage to offset
   its negative expectancy.
4. Do not purchase or backfill ETH/HYPE L2 solely to repeat this rejected
   contract. Acquire their history only for a causally distinct registered
   hypothesis.
5. Continue the live-transition and prospective v30 evidence lane, and derive
   any next cadence mechanism from reconciled missed-opportunity and execution
   journals rather than nearby impulse thresholds.

## Immutable evidence

- Deterministic report:
  `data/logs/research/orderflow_impulse_development_20260809T163500Z.json`
  (`2098f749aa95c9416f9a35c135c3d597cb2e9e24ac961bea7a9cc847cb975608`).
- Deterministic sidecar:
  `data/logs/research/orderflow_impulse_development_20260809T163500Z.parquet`
  (`b4f50769c20a19e4d5bc61158dc50c1a6159751632bc4f52a03147ef7cc78757`).
- ML report:
  `data/logs/research/orderflow_impulse_ml_challenger_20260809T164500Z.json`
  (`d1a553a83b131d4edd04f082ea10f31fc4763857ff7a15eef536519a6ac2fb44`).
- OOS predictions:
  `data/logs/research/orderflow_impulse_ml_challenger_20260809T164500Z.predictions.parquet`
  (`84e0391120e11723d1377b62361d65199663571860f0c5e0c637e6180d17d86b`).
- Selected annotations:
  `data/logs/research/orderflow_impulse_ml_challenger_20260809T164500Z.selected.parquet`
  (`524b606c8f269eb9ac348e9a6a44af848d3dd80cccb0cbd51c47efb62c02def7`).

No live process, profile, route, signal, order, position, stop, target, size,
leverage, transition drain, or protection changed.
