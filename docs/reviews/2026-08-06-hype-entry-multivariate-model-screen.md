# HYPE entry multivariate model screen

**Observed:** 2026-08-06 UTC  
**Mode:** report-only development measurement  
**Execution authority:** none

## Problem restatement

The prior HYPE entry audit tested 21 causal bar/regime features mostly one at a
time. This experiment tested whether a fixed multivariate model could combine
those same measurements into a stable ranking of the deployed HYPE breakout
lifecycles. The prespecified search contained exactly two candidates: Ridge
regression with fold-local scaling and one shallow deterministic LightGBM
regressor. No hyperparameter sweep or runtime model installation was allowed.

## Validation contract

The immutable input contains 1,011 unique control-admitted lifecycles from
2025-07-29 through 2026-05-28. These admitted lifecycles are serialized: zero
next signals occurred before the preceding exit. Five expanding walk-forward
folds purged training labels by actual exit timestamp and applied a 60-minute
embargo for the longest feature lookback.

Models predicted gross return so fixed costs did not become an artificial
feature target. Economic scoring used each selected trade's actual net return,
including the artifact's modeled fees, slippage, and funding. A candidate
needed all of the following:

- at least 4/5 positive rank-IC folds;
- worst-fold rank IC above `-0.05`;
- median top-minus-bottom gross spread of at least `26 bps`;
- at least 3/5 folds clearing that spread;
- at least 3/5 top-quintile folds with positive mean net return.

## Results

| Candidate | Median IC | Positive IC folds | Worst IC | Median gross spread | Spread-clearing folds | Median top net | Positive top-net folds |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ridge | +0.0273 | 3/5 | -0.1899 | +16.38 bps | 2/5 | -1.36 bps | 2/5 |
| LightGBM | +0.0980 | 3/5 | -0.2364 | -13.47 bps | 2/5 | -0.90 bps | 2/5 |

Neither candidate passed any complete acceptance set. Both changed rank sign
across folds, failed the 26-bps median-spread hurdle, and selected a negative
median after-cost top tail. LightGBM's higher median IC did not translate into
stable economic ordering.

## Decision

Reject runtime installation of both candidates. Keep the live metalabel/model
authority unchanged. Do not tune more thresholds or LightGBM parameters on this
same development artifact; doing so would expand the post-hoc search without
new independent evidence.

**Confidence: high for this exact development experiment; low for claims about
all possible future feature sets.** The input, fold metrics, and predictions are
immutable and hash-linked, but they remain bar-derived development evidence.
They do not prove that causal event-level L2 features, a materially different
entry definition, or a fresh regime-specific sample cannot work.

## Failure modes and falsifier

- Bar features do not reproduce event-level queue position or exact IOC fill
  conditions.
- Market episodes remain serially dependent even though admitted positions do
  not overlap.
- The already-opened final block was deliberately not read or rescored.
- Fresh, independently observed and venue-matched lifecycles would update this
  decision if a frozen candidate produced at least 4/5 positive rank folds,
  cleared the 26-bps spread hurdle in at least 3/5 folds, and retained positive
  after-cost selected-tail returns.

## Evidence

- Input features: `data/logs/research/hype_breakout_entry_attribution_development_v2_20260804.features.parquet`
  (`SHA-256 0088305b8348ca8e624433c7699a28521583923c2e80b24f5bdc1dbbb2afaf89`)
- Summary: `data/logs/research/hype_entry_model_development_v1_20260806.json`
  (`SHA-256 4d118f6301278cdf4c39459e7d447c8fb5c8752f62e5db1d278c8f02c83fb88e`)
- Fold metrics: `data/logs/research/hype_entry_model_development_v1_20260806.folds.parquet`
  (`SHA-256 960288a4eac86a9fed5cb5d77954023c174db0b295941910d1cf84be9c02e983`)
- OOS predictions: `data/logs/research/hype_entry_model_development_v1_20260806.predictions.parquet`
  (`SHA-256 fc75cdac3c2278aa66b6054963be0e9f7a0c36a87feda0e6a503edd177892e49`)
