# BTC 5m L2 expected-return challenger — 2026-08-02

## Problem and frozen boundary

The prior BTC five-minute L2 LightGBM classifier ranked 60-minute target hits
better than the base rate, but its serialized 25/18-bps barrier strategy lost
after the original optimistic six-bps cost. This bounded development-only test
asked whether the same feature pipeline and chronological window, rebuilt from
the current research database, could predict a gross-return tail large enough
to pay current IOC-style friction.

- Input: the same causal Hyperliquid BTC 5m price, public-trade, and L2 feature
  rows used by the existing challenger.
- Window: `2025-04-25T03:00:00Z` through `2026-01-25T23:20:00Z`.
- Labels: next-bar entry, 25-bps target, 18-bps stop, 60-minute horizon, and
  pessimistic stop-first ordering when both barriers touch in one bar.
- Validation: three expanding walk-forward folds with a 60-minute purge and
  embargo; 56,130 out-of-sample directional rows.
- Models: Ridge and shallow LightGBM conditional-mean regression.
- Economic screen: choose the higher predicted side only when predicted gross
  return clears 13-bps nominal or 20-bps stress round-trip cost; one open BTC
  position at a time.
- Authority: report-only. Validation, pseudo-holdout, runtime, and live orders
  were untouched.

The current build has the same 56,130 OOS signal/side identities as the July 31
classifier artifact. Entry, exit, outcome timestamp, status, and gross return
match on every row. The source-frame book hash also matches, while bars and
trades hashes differ. Therefore this is outcome-comparable but not a claim of
byte-identical feature input. A dtype/schema normalization or later database
source revision could explain the changed hashes; the old artifact does not
retain enough feature columns to distinguish those causes.

## Results

| Model | Mean rank IC | Worst-fold rank IC | Mean RMSE | Maximum predicted gross | Trades at 13/20 bps |
|---|---:|---:|---:|---:|---:|
| Ridge | 0.0355 | 0.0168 | 19.17 bps | 5.92 bps | 0 / 0 |
| LightGBM | 0.0227 | 0.0060 | 19.18 bps | 3.56 bps | 0 / 0 |

The largest fold-level top-minus-bottom gross quintile spread was 3.25 bps.
The ML4T feasibility screen requires at least twice expected round-trip cost,
or 26 bps at the nominal 13-bps assumption. The observed spread is therefore
about one eighth of the minimum screen and does not support a tradable signal.

V1 used an L1 LightGBM objective. That estimates a conditional median and was
not aligned with an expected-return hurdle. The immutable V1 artifact remains
as failed methodological evidence; V2 corrected the objective to conditional
mean and is the decision artifact.

## Decision

Stop this model branch before chronological validation or holdout. The data
contains weak ranking association, but not enough gross separation to justify
execution research at current costs. Lowering the hurdle, increasing leverage,
or selecting post-hoc percentile cutoffs would change the loss rate or overfit
the development window rather than create edge.

Confidence is high for rejecting the V2 feature/label/model contract on its
recorded current input because both model families and every fold show
economically tiny spread. Confidence is not a claim that all L2 models are
futile or that V2 is byte-identical to the July 31 classifier input. A
materially different, predeclared feature/label mechanism that produces at
least 26 bps fold-level gross spread and then survives untouched chronological
validation would falsify this decision.

## Evidence

- `data/logs/research/low_tf_l2_expected_return_btc_development_v1.json`
- `data/logs/research/low_tf_l2_expected_return_btc_development_v2.json`
- `data/logs/research/low_tf_l2_expected_return_btc_development_v2.parquet`
- `data/logs/research/low_tf_l2_expected_return_btc_development_v2_trades.parquet`
