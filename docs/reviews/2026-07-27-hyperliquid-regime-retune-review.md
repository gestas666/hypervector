# Hyperliquid-Native Regime Retune Review

## Decision

Apply trial 60, the secondary train-only stability Pareto candidate, to both
`faithful_regime_config()` and `configs/hypervelocity_faithful.toml`.

Confidence is medium. The evidence is point-in-time and venue-native, and the
candidate is non-inferior on the chronological entry holdout, but only 35
unique positive entry decisions exist and there are no independently labeled
negative or range intervals. The tuner computed holdout metrics for every trial
but excluded them from all selection scores; fresh shadow is therefore the
stronger confirmation boundary.

## Frozen evidence

- Strict cache: 129,600 BTC 1m bars; 129,532 `hl`, 68 explicit
  `hl_gap_fill`, zero cadence gaps.
- Recorded positions: 37 rows, 35 unique entry decisions.
- Chronological split: 24 train entries and 11 holdout entries at
  `2026-07-22T12:24:23.415474Z`.
- Tuning: 100 deterministic trials, seed 42, all retained. The tuner's raw
  `train_only` score selected trial 42; the secondary stability Pareto screen,
  also using only training-slice diagnostics rather than holdout outcomes,
  selected trial 60. Full-window diagnostics were computed after selection.
- Artifacts:
  - `data/logs/research/hypervelocity_regime_eval_hl90d_baseline_20260727.json`
  - `data/logs/research/hypervelocity_regime_tuning_hl90d_20260727.json`
  - `data/logs/research/hypervelocity_regime_eval_hl90d_applied_20260727.json`
  - `data/logs/research/hypervelocity_regime_comparison_hl90d_20260727.json`

## Baseline versus applied candidate

| Diagnostic | Baseline | Trial 60 | Change |
|---|---:|---:|---:|
| Exact direction matches | 24/35 | 25/35 | +1 |
| Exact direction recall | 68.57% | 71.43% | +2.86 pp |
| False RANGE at real entries | 3 | 1 | -2 |
| Any no-entry state at real entries | 6 | 4 | -2 |
| Breakout miss diagnostic | 97.02% | 96.53% | -0.48 pp |
| One-sided expansion labeled RANGE | 43.70% | 42.40% | -1.30 pp |
| Label churn | 4,054 | 1,811 | -2,243 (-55.3%) |
| Mean transition latency | 4.38 bars | 7.54 bars | +3.16 bars |

The scoring-excluded holdout remains 8/11 exact direction matches and zero false-RANGE
entries for both baseline and trial 60. Trial 60 also retains two no-entry
states, improves the breakout miss diagnostic from 98.33% to 96.47%, and
worsens the one-sided RANGE diagnostic from 21.12% to 24.70%.

## Why trial 42 was not applied

The raw train-score winner, trial 42, reaches 19/24 train direction matches and
zero train false-RANGE entries. It keeps 8/11 holdout direction matches and
zero holdout false-RANGE entries, but full-window churn rises from 4,054 to
6,988 and holdout one-sided RANGE errors rise to 26.41%. Because regime reset
re-arms same-direction entries, that churn could create repeated entry episodes.
Trial 42 remains a recorded result, not a discarded trial.

## Applied parameters

| Parameter | Previous | Applied |
|---|---:|---:|
| EMA fast / slow | 5 / 13 | 20 / 50 |
| Structure lookback | 120 | 240 |
| Trend strength percentile | 70 | 50 |
| Minimum trend gap | 0.5 bps | 1.0 bps |
| Choppiness RANGE threshold | 75 | 85 |
| Coiling width | 1.0 bps | 3.0 bps |
| Breakout clearance | 8 bps | 5 bps |
| Breakout volume multiple | 2.5x | 2.0x |

The range-strength percentile remains 40, breakout lookback remains 90, and
all architecture remains unchanged: 5m is authoritative, 1m only confirms
breakout direction, 15m is non-veto context, and confidence remains report-only.

## Failure modes and falsifiers

- The slower 7.54-bar transition response may miss profitable early trend
  entries. Same-window real logs showing systematic late entries would falsify
  the applied candidate.
- The holdout RANGE expansion diagnostic worsened. Independently labeled range
  intervals showing more false RANGE classifications would require retuning or
  rollback to the prior parameters.
- Breakout misses remain above 96%; the breakout label is not evidence of
  predictive edge. It remains a deterministic state, not an ML/confidence gate.
- Positive entry logs cannot measure false trend signals during periods when
  the real strategy stayed flat. Fresh paired shadow and real-strategy windows
  remain necessary for negative-class validation.

Rollback is one parameter-only revert in `faithful_regime_config()` and the
faithful TOML; no ledger schema or stored market evidence changed.
