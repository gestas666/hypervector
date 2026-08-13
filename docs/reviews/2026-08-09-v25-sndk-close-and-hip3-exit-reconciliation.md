# V25 SNDK close and HIP-3 exit reconciliation

Date: 2026-08-09

## 1. Problem restatement

A new SNDK Swing/HA stop close materially changed the v25 live prefix and
must be reconciled with the previously rejected direct provider-exit policy.
The question is whether this live loss overturns the broader exit evidence or
identifies a narrower mechanism worth testing.

## 2. Verified live change

The same-run immutable delta spans 14:32:55Z through 18:04:29Z and added:

- 1,229 ledger rows;
- one closed SNDK short lifecycle;
- three fill rows;
- $0.012918 fees and +$0.005540 funding;
- a net loss of $1.093178; and
- no disappearing open lifecycle without a corresponding close.

The complete v25 prefix now contains 12 closes, 6 wins and 6 losses, after-cost
net +$1.970335, PF 1.808777, fees $0.469156, and funding -$0.077289.
Coverage remains incomplete only under the already-known
provider_metric_telemetry_missing identity; no new technical-gap identity
appeared.

## 3. SNDK exit attribution

The SNDK short entered through the fully attributed HIP-3 Swing/HA onset
mechanism and ultimately hit its 80-bps protective stop after 31,600,520 ms.
Its first ignored native exit was a short HA flip at reference price 1219.4.
From that signal to the actual stop, directional continuation was -124.651468
bps. This specific lifecycle therefore supports an earlier exit, although the
counterfactual venue fill, exit fee, and slippage were not recorded and cannot
be presented as realized savings.

The live ignored-exit scorecard now has only three resolved lifecycles:

| Exit mode | N | Mean continuation after first ignored signal |
|---|---:|---:|
| Commodity HA flip | 2 | -58.297838 bps |
| Index alignment loss | 1 | +224.541904 bps |
| Combined | 3 | +35.982076 bps |
| Combined excluding largest continuation | 2 | -58.297838 bps |

The result is mode-conflicted and below the predeclared five-lifecycle policy
analysis threshold.

## 4. Reconciliation with historical evidence

The frozen 2,252-row validation challenger tested unconditional provider-exit
honoring with the deployed stop and maximum-hold shape. Under stress friction:

| Route family | Ignore PF / net | Honor PF / net |
|---|---:|---:|
| Commodity Swing | 0.7098 / -$12.67 | 0.3498 / -$39.34 |
| Index Swing | 0.9998 / approximately $0.00 | 0.2197 / -$11.28 |

One live SNDK avoided-loss counterfactual does not overturn those broader
negative results. It instead suggests that unconditional honoring pooled
useful and harmful exit states.

## 5. Decision and next experiment

Retain rejection of unconditional provider-recipe exits and leave v25
unchanged. Do not alter the currently open GOLD or SPCX lifecycle from this
analysis.

The next distinct hypothesis is an early-adverse HA-flip exit for commodity
Swing only. It must be frozen under a new strategy identity and distinguish:

- a flip before meaningful favorable excursion from a flip after a profitable
  excursion;
- current adverse state from profitable continuation;
- GOLD, SNDK, and BRENTOIL separately;
- long and short results;
- development and untouched forward windows; and
- nominal and stress fees, slippage, funding, turnover, drawdown, and
  largest-winner sensitivity.

This is not permission to optimize thresholds on the SNDK loss or activate the
dormant honor controller.

## 6. Confidence, risks, and falsifiers

Confidence is high in the same-run lifecycle identity, actual venue close,
after-cost arithmetic, first recorded provider signal, and source hashes.
Confidence remains medium-high that unconditional provider-exit honoring
should stay rejected because the broad validation result is strongly negative.
Confidence is low that the narrower early-adverse rule has edge before it is
tested.

The decision changes if a combined-priority, after-cost shared-account replay
and independent forward evidence show a new mode-specific rule improving PF
and drawdown across both sides without excessive churn. A source hash mismatch,
noncausal path field, incorrect first-signal identity, missing fill, or
counterfactual result presented as actual would invalidate this review.
