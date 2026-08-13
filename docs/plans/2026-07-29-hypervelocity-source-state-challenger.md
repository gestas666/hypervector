# Hypervelocity causal source-state challenger

Date: 2026-07-29
Status: predeclared, report-only

## Motivation

The first frozen bar/L2 model family lost to base rate in five purged folds and
again on the December 15-January 9 holdout. It is retired from tuning. The
strict source gate used source direction but omitted source subtype,
confidence, volume ratio, raw/stabilized disagreement, and state duration from
the model rows.

Subtype outcome summaries have already been inspected through January 9.
Therefore all data through that boundary is development evidence. No metric on
that interval can validate this new feature family.

## Frozen feature set

All source values must satisfy `available_at <= signal_time`. The fixed numeric
features are:

- confidence and volume ratio;
- minutes since the current primary/secondary source state became available;
- breakout, strong, weak/choppy, exhaustion, high-volatility, low-volatility,
  and normal-volatility flags;
- raw-versus-stabilized primary and secondary agreement flags.

No future label, outcome, post-entry price, or manually supplied trade result
may contribute to these features.

## Frozen candidate set

1. Fold-local base rate.
2. Logistic regression on bar/regime plus source-state features.
3. Shallow LightGBM on the existing bar/regime features.
4. Shallow LightGBM on bar/regime plus source-state features.
5. Shallow LightGBM on bar/regime, source-state, static L2, and causal 15s/60s
   L2 sequence features.

The existing regularization, LightGBM depth/leaf limits, 60-minute embargo, and
five expanding purged folds remain fixed. Training uses corrected runtime60
strict-source replay outcomes through January 9. No candidate is installed.

## Forward validation contract

January 9 onward is untouched for this candidate. Scoring begins only after a
gap-free block contains at least 50 resolved trades and 10 liquidations. A
source-state model must satisfy all of the following on that block:

- lower log loss than both base rate and bar/regime LightGBM;
- ROC AUC above 0.60;
- liquidation-risk top-quintile lift above 1.5;
- exact frozen model hashes and no retraining during holdout scoring.

Passing these statistical checks is not execution promotion. A separate
report-only replay must translate a predeclared annotation policy into positive
net expectancy after fees, funding, fills, and liquidation handling. Runtime
authority remains `observe`, `may_filter=false`, and `may_scale=false` unless
the user explicitly changes it after forward evidence.

## Failure interpretation

Failure would reject this source-state feature family, not prove that no
Hypervelocity strategy can work. The next branch would move to observed creator
loss/exit mechanics or a materially different entry lifecycle rather than tune
more thresholds on the same failed target-only stream.
