# HIP-3 early-adverse HA-flip exit review

Date: 2026-08-09
Execution authority: none
Runtime changed: no
Decision: reject the fixed early-adverse rule

## Problem restatement

The deployed commodity Swing/HA lifecycle ignores provider HA-flip exits and
instead closes on its 80-bps stop, 24-hour timer, or opposite entry intent. A
recent SNDK loss suggested that a narrow early HA-flip might remove failed
onsets without the churn already observed when every HA flip is honored.

The preregistered challenger admitted a side-specific HA-flip only when the
signal was known at a completed 15-minute close, the position was at most eight
completed bars old, MFE was below 20 bps, and directional close return was at
or below -13 bps. An admitted exit executed at the next modeled open.

## Fixed inputs and validation method

The `ignore`, `honor`, and `early_adverse` arms used the same content-verified
source report, pre-holdout midpoint/BBO bars, production recipe, $75 notional,
asset leverage, 80-bps stop, 24-hour maximum hold, fees, official funding, and
nominal/stress slippage. Only signal-exit handling changed. The experiment
retained development and validation failures and did not read the final
chronological holdout.

Windows:

- development: 2026-03-04 22:30 UTC through 2026-06-05 18:00 UTC;
- validation: 2026-06-05 18:00 UTC through 2026-07-06 16:30 UTC; and
- sealed holdout: 2026-07-06 16:30 UTC through 2026-08-06 15:00 UTC.

The simulator was regression-tested for causal close-to-next-open execution,
age/MFE/adverse-return conditions, invalid parameter rejection, and unchanged
default behavior when conditional fields are absent. Forty focused tests
passed before the immutable experiment was run.

## Results

Aggregate independent-asset results for SNDK, GOLD, and BRENTOIL:

| Window | Friction | Policy | Trades | Net USD | PF | Net ex-largest USD | Worst asset DD | Signal exits |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Development | Nominal | Ignore | 193 | +12.41 | 1.132 | -2.28 | -4.75% | 0 |
| Development | Nominal | Honor all | 399 | -7.68 | 0.922 | -16.59 | -3.35% | 320 |
| Development | Nominal | Early adverse | 219 | +3.77 | 1.039 | -10.78 | -4.70% | 53 |
| Development | Stress | Ignore | 198 | -18.09 | 0.838 | -31.83 | -5.53% | 0 |
| Development | Stress | Honor all | 401 | -58.07 | 0.560 | -66.77 | -6.94% | 310 |
| Development | Stress | Early adverse | 235 | -35.23 | 0.705 | -48.37 | -5.84% | 66 |
| Validation | Nominal | Ignore | 78 | -3.96 | 0.894 | -11.46 | -2.64% | 0 |
| Validation | Nominal | Honor all | 191 | -13.86 | 0.681 | -18.52 | -1.89% | 161 |
| Validation | Nominal | Early adverse | 95 | -7.15 | 0.812 | -14.67 | -2.60% | 30 |
| Validation | Stress | Ignore | 80 | -12.67 | 0.710 | -19.90 | -3.00% | 0 |
| Validation | Stress | Honor all | 192 | -39.34 | 0.350 | -43.60 | -3.54% | 154 |
| Validation | Stress | Early adverse | 98 | -17.89 | 0.615 | -25.12 | -3.06% | 31 |

Relative to ignore, early adverse reduced validation net by $3.20 nominal and
$5.22 stress. It added 17/18 completed trades and $1.26/$1.27 in fees. Its
validation PF, after-largest-winner result, and stress drawdown were all worse.

## Asset and side attribution

GOLD falsified the universal rule most clearly. Validation nominal changed from
+$0.76, PF 1.106 under ignore to -$5.58, PF 0.457 under early adverse. Stress
changed from +$0.39 to -$6.16. The challenger also remained negative on both
validation directions: long -$6.40 nominal and short -$0.76 nominal.

SNDK provided a weak, non-repeatable lead rather than promotion evidence.
Early adverse changed validation nominal from -$1.14 to +$0.71, but validation
stress remained negative at -$6.53 and development stress deteriorated from
-$0.95 to -$9.19. The SNDK validation result remained negative after removing
its largest winner. BRENTOIL improved modestly in validation but remained
negative and worsened in development.

## Decision and confidence

Reject `early_adverse_8bar_mfe20_adverse13` for the commodity route and for
SNDK-specific promotion. Preserve the current live exit policy. Do not spend
the sealed holdout to rescue or retune this post-SNDK hypothesis.

Confidence: high for rejecting this exact fixed rule under the tested bar-level
contract. It loses to ignore in development and validation, nominal and stress,
after costs and after removing the largest winner. Confidence is medium that
the exact live counterfactual has the same magnitude because midpoint/BBO bars
cannot reproduce venue trigger order, queueing, quantity rounding, or combined
portfolio capital contention.

This conclusion would be falsified by a reproducible implementation or input
identity defect, or by separately preregistered forward/live evidence showing
the same rule improves after-cost outcomes across assets, both directions, and
stress friction without excess turnover. One favorable SNDK slice is not such
evidence.

## Evidence and limitations

- Immutable report:
  `data/logs/research/hip3_early_adverse_ha_flip_20260809.json`, SHA-256
  `3a5c924ca9f32116f4a1f084dadd715a7a8d3ac0b70e304a6e7052ba8099897c`.
- Immutable trade sidecar:
  `data/logs/research/hip3_early_adverse_ha_flip_20260809.trades.parquet`,
  2,379 rows, SHA-256
  `4d500ad2834ccc3642140d50c0a3176a5cfbaf3a4c20cbaaaca4a9f4ab6a2fa4`.
- The comparison is an independent-asset 15-minute approximation, not exact
  combined-account, wall-clock, or historical venue execution parity.
- GOLD historical fee uncertainty remains inherited from the source evidence.
- The sealed holdout was not evaluated.
- No position, order, route, size, leverage, exit policy, backend process, or
  TUI state changed.
