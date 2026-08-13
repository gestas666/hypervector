# Source-follow decision-clock session validation

Date: 2026-07-30

## Correction: later replay used the wrong range timeframe

The original `v1` 2026-04-28 through 2026-07-28 row and its all-day comparison
are superseded. The report-only runner passed one-minute candles to a selector
whose 12-100 bps gate is defined on completed five-minute candles. The runtime
was not affected: it assembles five completed one-minute bars before computing
range.

After a failing regression test, all affected report callers now resample to
five minutes and the shared selector rejects misaligned inputs. The corrected
session replay contains 51 signals, 26 public-trade-through fills, 26 targets,
zero liquidations, $28,511.41 final equity from $15,000, and -12.22% maximum
drawdown. Its immutable artifact is
`data/logs/research/hypervelocity_source_session_strict_tuned_20260428_20260728_trade_through_hv35x30_v2.json`
with SHA-256
`c7f115e22f7fb5ef837f5922726aba4d90eee7edeb32cca204501c89d177c6c2`.

The corrected 24/7 control contains 102 signals, 55 fills, 50 targets, one
24-hour exit, four full and four partial liquidations, $10,824.37 final equity,
0.800 PF, and -59.43% maximum drawdown. Its immutable artifact is
`data/logs/research/hypervelocity_source_all_day_strict_tuned_20260428_20260728_trade_through_hv35x30_v2.json`
with SHA-256
`9c6f769f178cbbabf425ee9fc5ff429e67107e0e533636ae9821a410aacd15d8`.

The older segmented and holdout rows below used recorded five-minute ranges
from source artifacts and remain mechanically valid. The corrected later
result remains limited by public queue uncertainty and 26 fills.

## 1. Problem restatement

The 24/7, source-follow BTC short lost money in the corrected later 91-day
venue replay because one 24-hour exit and four full liquidations occurred
outside the previously frozen 06:00-15:00 UTC development session. This
experiment asks
whether limiting only new entries to the half-open UTC session improves the
35%-isolated, 30x, 8%-target strategy while preserving source labels, execution
friction, funding, liquidation accounting, and open-position exit rules.

Success requires positive after-cost results in older, intermediate holdout,
and later chronological windows, exact runtime/replay clock parity, and a
material improvement over the later 24/7 control. The model remains
observe-only and the candidate remains shadow/no-submit.

## 2. Clock correction

The first older and holdout replays selected session membership by source
`label_time_utc`; decisions become available five minutes later. The later
replay and runtime use `decision_time_utc`. This admitted a 15:00 decision in
the older artifact and made the initial cross-window comparison non-identical.

A failing regression test reproduced the mismatch. The corrected continuous
runner now requires unfiltered all-day source artifacts and filters the causal
decision timestamp with `06:00 <= hour < 15:00`. Runtime uses the same half-open
boundary. The original immutable artifacts remain audit records but are not
promotion evidence.

## 3. Runtime-aligned results

| Window | Completed trades | Outcomes | Final equity | Net PnL | PF | Max DD | Liquidations |
|---|---:|---|---:|---:|---:|---:|---:|
| 2025-07-28 to 2026-04-18 | 42 | 40 target statuses, 2 full liquidations | $24,300.69 | +$9,300.69 | 2.372 | -31.80% | 2 full, 7 partial |
| 2026-04-18 to 2026-04-28 | 1 | 1 target from 2 entries | $15,221.67 | +$221.67 | no realized loss | -2.27% | 0 |
| 2026-04-28 to 2026-07-28 | 26 | 26 targets from 51 signals | $28,511.41 | +$13,511.41 | no realized loss | -12.22% | 0 |
| Later 24/7 control | 55 | 50 targets, 1 time exit, 4 liquidations | $10,824.37 | -$4,175.63 | 0.800 | -59.43% | 4 full, 4 partial |
| 2025-07-30 to 2026-07-28 direct supplement | 66 | 65 targets, 1 liquidation | $58,105.59 | +$43,105.59 | 9.311 | -26.31% | 1 full, 1 partial |

One older trade marked `target_completed` had negative net PnL after a partial
liquidation, so target status is not treated as a win-rate substitute. The
later session arm beat the 24/7 control by $17,687.05 and improved maximum
drawdown by 47.22 percentage points on that path. The 24/7 path is a portfolio
control rather than an additive attribution: out-of-session positions can
block otherwise eligible session entries and change later compounded size.

The direct continuous-year row is supplementary rather than promotion-grade.
Its causal replay encountered 3,881 stale mark observations, one stale oracle
observation, and source-label intervals outside the older segmented artifact's
gap-safe windows. It is directionally consistent with the segmented evidence,
but it does not replace the older segmented and holdout rows.

## 4. Runtime implementation and forward state

The distinct candidate profile is
`configs/hypervelocity_source_follow_session_06_15_minrange12_alloc35_shadow.toml`.
It changes only entry-session authority relative to the prior 35% profile.
Positions opened during the session continue toward the 8% gross-margin target
or 24-hour maximum hold after 15:00; the boundary does not force an exit.

The flat 24/7 control stopped cleanly with no fills or pending order. The new
shadow run `12e013351489` started at $15,000. Its first live observation was
outside the session and correctly reported no entry direction,
`source_follow_outside_entry_session`, `submitted=false`, and
`place_attempted=false`. L2, public trades, and asset context continue to be
archived.

## 5. Uncertainties, failure modes, and falsifiers

- Public trade-through cannot identify private queue rank or cancellations.
- The UTC window was originally selected on older development data and may be
  confounded with the creator's waking schedule rather than a stable market
  mechanism.
- The April holdout has only one completed trade. A no-loss PF in one or 26
  trades is sparse tail evidence, not a guarantee.
- The older path still had two full and seven partial liquidations. The session
  improves rather than eliminates tail risk.
- Missing older archive intervals were crossed only while flat and idle, but
  receipt timestamps remain approximated by exchange timestamps.
- Both recent paths crossed 21 global empty-book hours, although no pending
  entry or open position overlapped them. The reports therefore conservatively
  mark execution economics non-conclusive.

Confidence is high in mechanical replay/runtime clock parity, medium in the
historical session edge, and low in live-income repeatability. Forward PF at or
below one after costs, materially worse fill conversion, renewed liquidation
clustering, or disagreement between source labels and backend telemetry would
falsify promotion.

## 6. Recommendation

Use the session-limited profile as the active shadow candidate and preserve the
24/7 result as a control artifact. Do not arm live execution. Accumulate fresh
venue-matched session entries, compare every decision and fill against offline
replay, and reassess after enough losses and non-losses exist to estimate tail
behavior rather than relying on target rate alone.

## 7. Evidence identity

- Older decision-clock artifact:
  `data/logs/research/hypervelocity_source_session_decision_06_15_minrange12_alloc35_lev30_continuous_20250728_20260418_v1.json`
- Older SHA-256:
  `30ba449e7e0587d139c89620fa9ad22a14a060c4b4c86ff3b5debe55921ef9e7`
- Holdout decision-clock artifact:
  `data/logs/research/hypervelocity_source_session_decision_06_15_minrange12_alloc35_lev30_holdout_20260418_20260428_v1.json`
- Holdout SHA-256:
  `ea68dc3c7c42bd1f1e93e64955bc9dda98c2466295746625719887c39a88e156`
- Later corrected session replay:
  `data/logs/research/hypervelocity_source_session_strict_tuned_20260428_20260728_trade_through_hv35x30_v2.json`
- Later corrected session SHA-256:
  `c7f115e22f7fb5ef837f5922726aba4d90eee7edeb32cca204501c89d177c6c2`
- Later corrected 24/7 replay:
  `data/logs/research/hypervelocity_source_all_day_strict_tuned_20260428_20260728_trade_through_hv35x30_v2.json`
- Later corrected 24/7 SHA-256:
  `9c6f769f178cbbabf425ee9fc5ff429e67107e0e533636ae9821a410aacd15d8`
- Direct continuous-year supplementary replay:
  `data/logs/research/hypervelocity_source_session_strict_tuned_continuous_20250730_20260728_trade_through_hv35x30_v2.json`
- Direct continuous-year supplementary SHA-256:
  `af0a5e995b3f8cd1b083d3be66a946460427e4d7d7a4ee054889b08c3643784f`
