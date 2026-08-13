# HIP-3 route-authority pruning comparison

Date: 2026-08-09
Status: fixed descriptive comparison after exploratory inspection
Execution authority: none

## Objective

Determine whether v25's HIP-3 route breadth is adding robust after-cost value
or merely increasing turnover and stress losses. The result may prepare a
reversible flat-boundary authority diff, but cannot change the running profile.

## Epistemic status

The development and validation data were already inspected during prior v29,
v30, exit-policy, and live reconciliation work. This is therefore a transparent
descriptive consolidation, not a new sealed confirmation. The final
chronological holdout remains unavailable to this comparison.

## Fixed variants

All variants preserve both long and short sides, the exact production recipes,
$75 route notional, 5x leverage, provider priority, modeled fees/funding, and
nominal/stress friction.

1. `full_v25_hip3`: all ten v25 HIP-3 provider-symbol routes.
2. `weak_swing_pruned`: remove SNDK and BRENTOIL Swing; retain GOLD Swing and
   all commodity Breakout routes.
3. `weak_swing_sndk_breakout_pruned`: additionally remove SNDK commodity
   Breakout while retaining GOLD and BRENTOIL commodity Breakout.
4. `v29_hip3`: existing v29 HIP-3 subset—SPCX Swing, SP500 Breakout, GOLD
   Swing.
5. `v30_spcx_core`: existing v30 HIP-3 subset—SPCX Swing only.

No parameter surface or route subset may be added after artifact generation.

## Required evidence

- family-native development/validation boundaries must remain visible, while
  shared-account arbitration uses only their common wall-clock intersection;
- nominal and stress friction must both be retained;
- net PnL, PF, realized drawdown, turnover, route/side coverage, and net after
  removing the largest winner must remain visible;
- current immutable v25 live closes must be reconciled by exact
  provider-symbol identity;
- absent routes and zero-trade cells must not become positive evidence; and
- all inputs and implementation sources must be content-addressed.

## Interpretation

A narrower route set is strengthened by positive net and PF above one across
development/validation and nominal/stress, lower drawdown, both sides, and a
non-negative result after removing the largest winner. It is weakened by
window reversal, stress failure, concentration, or a material loss of live
opportunity cadence.

Because these windows are already opened and live samples are sparse, even a
strong result qualifies only as a forward candidate. It does not automatically
pause, promote, resize, reroute, restart, or execute anything.

## Source-window correction

The immutable source cases use different family-local phase boundaries. Index
development begins later and ends after commodity development. Combining rows
by their native `development` or `validation` labels would create artificial
cross-family capital contention between different wall-clock intervals.

The shared comparison therefore uses:

- `common_early`: latest family start through earliest development end;
- `common_later_descriptive`: earliest development end through earliest
  validation end; and
- `common_full`: the union of those two common intervals.

The later interval is explicitly descriptive because the family-native phase
labels differ. This correction was made before any immutable result was
published; the failed attempt wrote no artifact.
