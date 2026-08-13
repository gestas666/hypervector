# Hypervelocity Source-Follow Session Confidence Robustness

Date: 2026-07-29

## Problem restatement

The strongest report-only source-follow candidate selects current-revision
Hypertrader `TREND_DOWN` onsets, aligns them short, requires source confidence
of at least 0.70, and admits signals from 06:00 through 14:59 UTC. The question
is whether its positive development result survives neighboring nine-hour UTC
windows or is an exact clock-boundary artifact.

This experiment does not change the running Hypervelocity strategy, canonical
regime detector, model authority, target, allocation, leverage, order model, or
exit policy.

## Fixed comparison

The four equal-width, half-open windows are:

- 05:00-14:00 UTC;
- 06:00-15:00 UTC, the existing development leader;
- 07:00-16:00 UTC; and
- 08:00-17:00 UTC.

Every arm uses the same pinned source revision, source confidence threshold,
60-second maker-entry eligibility, 100-bps completed-5m signal range ceiling,
trade-through fill rule, 70% isolated allocation, 40x leverage, +8% gross-margin
target, authentic Hyperliquid mark and funding context, adverse-BBO liquidation,
and venue fee assumptions. All arms are report-only with
`runtime_strategy_changed=false`, `selection_is_promotion=false`, and
`model_authority=observe`.

The twelve development blocks are independently reset because the canonical
archive contains declared book gaps. Aggregate PnL therefore sums twelve
separate $10,000 portfolios; it is not a continuous compounded forecast.

## Development result

| UTC window | Fills | Completed | Targets | Liquidations | Open | Positive blocks | Aggregate PnL | Worst block drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 05-14 | 56 | 55 | 52 | 3 | 1 | 9/12 | +$13,088.65 | -54.66% |
| **06-15** | **59** | **58** | **55** | **3** | **1** | **10/12** | **+$17,577.90** | **-74.53%** |
| 07-16 | 69 | 68 | 61 | 6 | 1 | 7/12 | +$2,745.53 | -74.53% |
| 08-17 | 72 | 71 | 63 | 7 | 1 | 7/12 | +$438.64 | -74.53% |

The 06-15 arm retains the highest aggregate PnL, most positive blocks, and
highest median final block equity. The 05-14 arm is a legitimate risk-return
alternative: it loses $4,489.25 of aggregate PnL and one positive block but
improves worst block drawdown by 19.88 percentage points.

The 06-15 target share is 55/58, or 94.83%, among resolved positions. This is
descriptive development evidence, not an estimate of live win probability.

## Boundary attribution

The stateful 06-15 event stream resolved hour-06 entries as eight targets and
zero liquidations for +$4,341.38 of lifecycle net PnL. The 05-14 stream's added
hour-05 entries resolved as four targets and one liquidation for -$2,634.36.
The 07-16 stream's added hour-15 entries resolved as fourteen targets and three
liquidations for -$5,588.57.

These lifecycle sums do not exactly equal portfolio deltas because the replay
also carries open-position mark-to-market, funding, and path-dependent sizing.
They nevertheless identify the boundary failures directly: removing hour 06
discards an 8/8 target population, while adding hour 15 admits three full
liquidations.

The result is consistent with an early-UTC session effect rather than arbitrary
performance from every nine-hour window. It does not prove the clock is the
causal variable. The creator's waking schedule is not itself a market rule, and
the candidate hours were evaluated after inspecting earlier results.

## Late April comparison

The April 18-28 block remained positive for every arm:

| UTC window | Fills | Targets | Liquidations | Net PnL |
|---|---:|---:|---:|---:|
| 05-14 | 1 | 1 | 0 | +$471.90 |
| 06-15 | 1 | 1 | 0 | +$471.90 |
| 07-16 | 2 | 2 | 0 | +$970.45 |
| 08-17 | 3 | 3 | 0 | +$1,492.73 |

This window was reserved before the peak-observer experiment, but it is not a
strict untouched holdout for the later post-hoc clock sensitivity. It is a
non-inferiority comparison only.

## Decision

Retain 06-15 confidence-70 short-follow as the development return leader. Do
not alter the runtime strategy or promote the clock filter from these results.
Retain 05-14 as the explicit lower-return/lower-worst-drawdown challenger; do
not silently replace the leader based on risk preference.

Freeze the session boundaries now. Further hour tuning on the same archive
would increase selection bias. The next evidence must come from newly recorded
Hyperliquid data or a predeclared later archive window. The +7% peak observer
continues separately in report-only mode because its development improvement
was sparse and concentrated in one reversal.

## Uncertainty and falsification

Confidence is high that the replay comparison changes only session membership
and preserves the declared execution economics. Confidence is medium that the
06-15 short-side effect is strong enough for forward validation. Confidence in
a complete two-sided profitable strategy remains low because no long arm has
survived equivalent validation.

Reject the session hypothesis if new forward data is net negative after fees
and funding, if liquidation frequency rises enough to dominate targets, or if
neighboring performance no longer shows an early-to-late degradation. Update
the causal interpretation if a point-in-time market feature explains the same
entries out of sample without relying on fixed UTC hours.
