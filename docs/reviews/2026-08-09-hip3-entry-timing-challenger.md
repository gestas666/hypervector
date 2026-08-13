# HIP-3 entry-timing challenger review

## Problem restatement

The v25 live prefix raised a testable timing hypothesis: GOLD and SNDK entries
were directionally aligned across their native EMA, Heikin-Ashi, order-block,
and pivot components, yet initially experienced adverse paths. This experiment
asks whether changing only the causal entry clock improves after-cost outcomes.
It does not test new direction gates, leverage, sizing, stops, or exits.

## Fixed protocol and assumptions

- Signal identity: exact production HIP-3 Swing recipes.
- Timing arms: provider exact, alignment-episode onset, one-bar confirmation,
  and first later completed-bar touch of the fast EMA.
- Fill clock: signal on completed 15-minute bar, entry at next bar open.
- Lifecycle: fixed 80-bps price stop, 24-hour maximum hold, provider exits
  ignored, matching the deployed v25 bar approximation.
- Economics: archived visible-book friction, nominal and stress latency,
  official funding, venue leverage, and `$75` notional.
- Evidence boundary: development and validation only. The sealed holdout was
  not read.
- Search accounting: four timing arms across five symbols, two phases, and two
  friction classes. No result has automatic promotion or execution authority.

Index coverage was 2026-05-17 through 2026-07-21 before the sealed window.
Commodity coverage was 2026-03-04 through 2026-07-06 before the sealed window.

## Results

### Index recipe aggregate: SP500 and SPCX

| Arm | Development nominal | Validation nominal | Validation stress |
|---|---:|---:|---:|
| Provider exact | 52 trades, +$10.20, PF 1.44 | 29, +$1.75, PF 1.16 | 30, -$0.00, PF 1.00 |
| Alignment onset | 48, +$12.72, PF 1.61 | 29, +$1.75, PF 1.16 | 30, -$0.00, PF 1.00 |
| Next-bar confirmation | 40, +$13.49, PF 1.80 | 29, -$4.97, PF 0.59 | 29, -$6.02, PF 0.54 |
| Fast-EMA pullback | 0 trades | 1, -$0.05, PF 0.00 | 1, -$0.08, PF 0.00 |

The next-bar confirmation failed out of sample. The fast-EMA pullback removed
essentially the entire opportunity set. Alignment onset removed four nominal
and five stress SPCX development re-entries; every removed lifecycle was a
protective-stop loss. Validation economics were effectively unchanged because
the validation state path did not contain the same repeated-entry pattern.

SPCX alone was positive in validation: +$2.77, PF 1.30 nominal and +$1.19,
PF 1.11 stress. SP500 was negative. SPCX still failed the concentration test:
net PnL excluding its largest winner was -$0.80 nominal and -$2.30 stress.

### Commodity recipe aggregate: SNDK, GOLD, and BRENTOIL

| Arm | Development nominal | Validation nominal | Validation stress |
|---|---:|---:|---:|
| Provider exact/onset | 193 trades, +$12.41, PF 1.13 | 78, -$3.96, PF 0.89 | 80, -$12.67, PF 0.71 |
| Next-bar confirmation | 184, -$3.04, PF 0.97 | 68, -$4.37, PF 0.86 | 73, -$14.75, PF 0.62 |
| Fast-EMA pullback | 4, +$0.91, PF 1.49 | 0 trades | 0 trades |

The exact commodity recipe and alignment-onset arms are identical because the
production recipe already uses onset entries. Delaying one bar worsened every
aggregate validation result. The EMA pullback is operationally non-trading.

GOLD was slightly positive in validation: +$0.76, PF 1.11 nominal and +$0.39,
PF 1.05 stress, but became negative after removing its largest winner. SNDK and
BRENTOIL were negative under both validation friction classes.

## Direction and stability findings

Static side gating is not supported:

- SPCX development was carried by longs (+$14.85, PF 3.36), while validation
  longs lost -$1.87 and validation shorts earned +$4.64, PF 1.62.
- GOLD development longs and shorts were both negative, while validation
  shorts earned +$2.05, PF 1.81 and longs lost -$1.29.
- SNDK development longs earned +$28.54, PF 1.98, but validation longs lost
  -$1.05 nominal and -$4.11 under stress.

This rotation is contradictory evidence against choosing a permanent long-only
or short-only rule from these windows.

## Decision

1. Reject the fast-EMA pullback and one-bar confirmation arms.
2. Retain the exact v25 entry clock for current live execution.
3. Retain alignment-episode onset as an annotation-only SPCX challenger. It is
   a re-entry/cooldown mechanism, not a market-regime gate.
4. Do not add static side gates for SPCX, GOLD, or SNDK.
5. Before any future flat-boundary profile change, measure provider-state
   episode identity and re-entry ordinal in the routed live ledger. Promote
   onset only if repeated same-episode entries remain after-cost losers without
   being required to capture later winners.

## Uncertainty, risks, and falsifiers

Confidence is medium for rejecting the two global delays and low-to-medium for
the SPCX onset challenger. The simulator is an independent-asset bar
approximation rather than the shared live router. Positive SPCX and GOLD
results depend on their largest winners, and the validation windows are not a
new sealed confirmation set.

The onset recommendation is falsified if routed wall-clock replay or forward
live annotation shows same-episode re-entries contributing positive after-cost
PnL, capturing winners that onset would miss, or arising from a different
provider episode than the bar reconstruction reports. The rejection of the
two delays should be revisited only with a materially different, pre-registered
pullback definition or independent forward evidence; retuning these results
post hoc would be a new hypothesis.

The first v1 artifact is superseded because its aggregate drawdown reducer
selected the least-negative asset rather than the worst asset. The v3 artifact
corrects that reporting defect; trade rows and economic outcomes are otherwise
unchanged.
