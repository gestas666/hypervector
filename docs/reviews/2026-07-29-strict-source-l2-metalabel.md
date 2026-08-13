# Strict-source runtime60 and causal L2 metalabel review

Date: 2026-07-29

## Problem and acceptance criteria

This review asks two separate questions:

1. Does the corrected target-only strict-source replay have positive economics
   across multiple gap-free Hyperliquid periods?
2. Can point-in-time regime and L2 features identify liquidation risk better
   than a fold-local base-rate prediction?

The replay must use the faithful 60-second cooldown, 40x leverage, 70% margin
allocation, 8% gross margin target, authentic mark/funding context, and public
trade-through maker fills. Model eligibility requires at least 200 resolved
trades, 25 liquidation labels, and five purged walk-forward folds containing
both classes. Models remain annotation-only.

## Replay result

Four non-overlapping blocks contain 213 resolved trades: 174 targets and 39
liquidations, an 81.69% target rate. Every block lost most of the portfolio.

| Window UTC | Targets | Liquidations | Target rate | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Aug 1-Sep 9 20:00 | 61 | 12 | 83.56% | $502.48 | -98.52% |
| Sep 10-Oct 16 11:00 | 43 | 13 | 76.79% | $153.57 | -98.90% |
| Oct 23-Nov 15 | 38 | 7 | 84.44% | $2,239.51 | -89.71% |
| Nov 26-Dec 15 | 32 | 7 | 82.05% | $1,299.75 | -89.77% |

Execution economics are conclusive for the observed public tape: all blocks
have verified checksums, zero active book-gap windows, and authentic
Hyperliquid liquidation boundaries. Private queue rank and hidden liquidity
remain unobservable.

High confidence under the tested execution model: the reconstructed target-only
baseline is not economically viable on these periods. This would be falsified
by an identified error in entry identity, fee/funding accounting, liquidation
math, or public trade-through fill handling that materially changes all four
blocks.

## Model result

The v2 dataset has complete bar and sequence-count coverage for all 213 rows;
203 rows have fresh numeric L2 values. Five purged folds score 107 OOS rows and
21 OOS liquidations. No model is installed.

| Candidate | Mean log loss | Worst fold | Mean ROC AUC | Mean AP |
|---|---:|---:|---:|---:|
| Base rate | **0.5009** | **0.7151** | 0.5000 | 0.1970 |
| LightGBM bar/regime | 0.5088 | 0.7350 | 0.5577 | 0.3074 |
| LightGBM static L2 | 0.5294 | 0.8391 | 0.5486 | 0.2629 |
| LightGBM 15s/60s L2 sequence | 0.5253 | 0.7634 | 0.5731 | 0.3094 |
| Logistic bar/regime | 0.5403 | 0.7671 | 0.3846 | 0.2441 |
| Logistic static L2 | 0.5508 | 0.8300 | 0.4327 | 0.2659 |
| Logistic 15s/60s L2 sequence | 0.6582 | 1.0510 | 0.4358 | 0.2505 |
| Logistic prior-signal lags | 0.8505 | 1.3171 | 0.4081 | 0.2420 |

LightGBM sequence features modestly improved static-L2 LightGBM log loss in
three of five folds, but both variants remained worse than base rate. Weak AUC
above 0.5 is insufficient because calibration and worst-fold stability failed.
The causal L2 challenger is therefore rejected for promotion.

Medium confidence that the tested entry-time L2 families lack a deployable
liquidation-risk edge on this population. That assessment would change if a
new, untouched period beats base-rate log loss in every predeclared comparison
and converts the ranking into positive replay expectancy.

## Source-fidelity implication and next experiment

The observed creator CSV provides no realized losing lifecycle; thirteen early
positions are closed without an exit fill/PnL row, while the later reconciled
rows are targets or near breakeven. The separate creator scorecard reports four
losses but does not provide their size or exit reason. Therefore target-only
holding through liquidation is not empirically established as the creator's
loss behavior.

The next experiment should not threshold-tune this failed model. Finish the
one-year archive, reserve later gap-free blocks as untouched validation, and
predeclare source-state subtype features already available at decision time.
In parallel, reconcile the four creator losses. A stop/exit candidate should
only be tested against those observed loss mechanics, or explicitly labeled as
a robustness deviation from the source.

## Immutable v2 evidence

- Report SHA-256:
  `e764e9a1fea1378c2c27a306d16e0da5c433aad7fcbf4d76f77c48c353d3459e`.
- Dataset SHA-256:
  `d37754a1b06f6fb4a7a84de8f23ca464b053496e4e7876866fc8dc448e23db37`.
- Fold metrics SHA-256:
  `d3880fc2c68c80f93a376c91c835c0c6dd97d42e63ca44de4a9426071794952e`.
- Predictions SHA-256:
  `120b9748b2aa378f8c614d4dbb0f230770cf7f0904d5f1e953dc8793bb43b5ba`.
