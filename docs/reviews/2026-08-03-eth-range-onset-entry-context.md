# ETH range-onset entry-context challenger

Date: 2026-08-03 EDT

## Problem and evidence boundary

The first resolved live ETH range-onset trade looked directionally arbitrary:
the strategy bought while the completed 1-minute trend and most observe-only
components pointed down. The question was whether this was a software defect or
an intended but weak part of the frozen entry contract.

The live decision was correct under the implemented rule. The rule requires a
completed hourly SMA10/30 cross while the completed 5-minute canonical state is
`RANGE` or `BREAKOUT`. It does not require agreement from the completed 1-minute
state, completed 5/15-minute candle bias, EMA/SMA direction, Cipher A, HARSI, or
trend slope.

At the live long entry:

- hourly SMA gap was only `+1.77 bps`;
- canonical state was 1m `TREND_DOWN`, 5m `RANGE`, 15m `TREND_UP`;
- completed candle biases were 5m `-3` and 15m `-3`;
- the weighted component-alignment score was `-0.7778`;
- the trade stopped after about 155 minutes for `-$0.17438` net.

This audit was specified after observing that live loss. It is therefore an
exploratory challenger, not an independent confirmation test. The audit itself
has no execution, sizing, model, routing, promotion, or balance-gating
authority. A later explicit profile decision can use the measured condition;
that configured policy is separate from the report-only research artifact.

## Fixed hypotheses

The existing signal and its fixed 60-bps stop, 48-hour maximum hold, 5x
leverage, modeled fees, funding, and slippage were held constant. Four entry
variants were measured on the same venue-native ETH one-minute data:

1. current contract;
2. current contract with weighted component alignment at least `-0.5`;
3. current contract unless completed 5m and 15m candle biases both oppose;
4. current contract unless the completed 1m trend opposes.

This is a bounded four-candidate comparison, not an optimizer or threshold
sweep. The `$500` approximate live research bankroll is not used anywhere in
candidate admission or evaluation.

## Results

| Segment | Candidate | Trades | W/L | Net PnL | PF | Max DD |
|---|---|---:|---:|---:|---:|---:|
| Development | Current | 53 | 5/48 | -$481.68 | 0.788 | -8.93% |
| Development | Component ≥ -0.5 | 37 | 4/33 | -$110.83 | 0.928 | -7.74% |
| Development | Dual-MTF not opposed | 43 | 5/38 | +$40.97 | 1.023 | -7.18% |
| Development | 1m not opposed | 43 | 5/38 | +$22.55 | 1.013 | -7.96% |
| Validation | Current | 22 | 8/14 | +$1,756.35 | 3.258 | -6.74% |
| Validation | Component ≥ -0.5 | 18 | 7/11 | +$1,822.10 | 4.045 | -6.74% |
| Validation | Dual-MTF not opposed | 18 | 6/12 | +$1,591.11 | 3.421 | -6.74% |
| Validation | 1m not opposed | 20 | 7/13 | +$1,535.49 | 3.140 | -6.74% |
| Pseudo-holdout | Current | 11 | 4/7 | +$494.73 | 2.347 | -4.32% |
| Pseudo-holdout | Component ≥ -0.5 | 9 | 4/5 | +$604.65 | 3.297 | -4.32% |
| Pseudo-holdout | Dual-MTF not opposed | 9 | 4/5 | +$604.65 | 3.297 | -4.32% |
| Pseudo-holdout | 1m not opposed | 10 | 4/6 | +$549.19 | 2.740 | -4.32% |
| Continuous | Current | 86 | 17/69 | +$1,753.18 | 1.513 | -8.93% |
| Continuous | Component ≥ -0.5 | 64 | 15/49 | +$2,370.90 | 1.979 | -7.74% |
| Continuous | Dual-MTF not opposed | 70 | 15/55 | +$2,307.04 | 1.841 | -7.18% |
| Continuous | 1m not opposed | 73 | 16/57 | +$2,166.66 | 1.755 | -7.96% |

The new baseline reproduces the prior shape-surface metrics, directional
summaries, and exit counts exactly in all four segments. This proves the
comparison did not silently change the old simulator contract.

## Rare-winner retention

The dual-MTF challenger is the cleanest mechanism result:

- development retained all 5 winners and removed 10 of 48 losses;
- validation retained 6 of 8 winners and removed 2 of 14 losses;
- pseudo-holdout retained all 4 winners and removed 2 of 7 losses;
- continuous history retained 15 of 17 winners and 94.7% of baseline gross
  profit while removing 14 of 69 losses and 21.6% of baseline gross loss.

The component-threshold challenger produced the largest aggregate improvement,
but its threshold is less interpretable and development PF remained below one.
The 1m-only challenger retained one more continuous winner but removed less
gross loss. None of these comparisons estimates private queue position or
future live expectancy.

## Recommendation and trade-off

Medium confidence: the dual-MTF condition is the strongest next forward
challenger because it directly addresses the observed contradiction, is
symmetric for longs and shorts, and does not require a broad indicator
conjunction. Confidence is not high because the rule was chosen after a live
loss and the original signal itself was post-hoc.

The next-run profile now explicitly configures
`entry_context_overrides = { ETH = "dual_mtf_not_opposed" }` for the
bidirectional range-onset provider. Under that profile, an ETH long is withheld
only when both completed 5m and 15m candle biases are bearish; an ETH short is
withheld only when both are bullish. Clear long and short entries remain
eligible. Missing context is exposed as unavailable and withheld under this
explicit rule rather than silently treated as agreement.

The current armed process remains on the prior profile. It still labels the
condition `DUAL-MTF CHALLENGER CLEAR`, `OPPOSED`, or `N/A` with `[REPORT ONLY]`
authority and does not change readiness, blockers, entry, sizing, or exit. The
new backend will add `ENTRY CONTEXT DUAL-MTF ... [ACTIVE]` and one readiness
condition after a safe restart. The open protected HYPE lifecycle is not being
restarted merely to activate the new ETH rule.

Evidence that would strengthen the challenger is repeated forward ETH events
where opposed entries underperform clear entries after exact live fees,
slippage, funding, and stop/hold behavior. Evidence that would weaken it is an
opposed entry becoming one of the rare large winners, clear entries producing
similar or worse stop rates, or replay/live decision disagreement. These are
falsifiers for keeping the explicitly configured rule; they are not balance,
promotion, or trial-abort gates.

## Live 48-hour follow-through journal

The rolling read-only checkpoint now tracks every resolved trade from its
authoritative entry fill for 4, 12, 24, and 48 hours. It reports completed-bar
coverage, close return in the original trade direction, MFE, MAE, and whether
ordinary trade candles crossed the configured protective-stop price. The
report continues after the real exit, so it is a path diagnostic rather than
counterfactual trade PnL or execution advice.

At `2026-08-04T03:19:49Z`, the ETH long had these measurements:

| Horizon | Coverage | Directional close | MFE | MAE | Status |
|---|---:|---:|---:|---:|---|
| 4h | 240/240 | +19.32 bps | +32.21 bps | -83.20 bps | resolved |
| 12h | 318/720 | -23.62 bps | +42.41 bps | -83.20 bps | censored |
| 24h | 318/1440 | -23.62 bps | +42.41 bps | -83.20 bps | censored |
| 48h | 318/2880 | -23.62 bps | +42.41 bps | -83.20 bps | censored |

The resolved four-hour result updates the causal diagnosis. The final
four-hour direction was not simply wrong, but the path first moved far enough
against the entry to exceed the fixed 60-bps stop. That supports weak timing or
path-risk as a plausible mechanism. It does not establish that widening or
removing the stop would improve expectancy because the later 12-hour prefix
had already reversed again and exact alternative fills were not simulated.

Ordinary ETH trade candles first crossed the stop price at
`2026-08-03T22:06:00Z`; the authoritative venue stop fill occurred at
`2026-08-04T00:35:05.222Z`. The candle cross is deliberately labeled
`protective_stop_price_crossed`, not `protective_stop_hit`. Hyperliquid trigger
price mechanics are not proven by trade OHLC, and the venue fill remains the
only authoritative execution evidence.

The TUI closed-trade inspector renders the resolved 4-hour and current 48-hour
rows. A censored path that has not crossed the stop says `STOP PX CLEAR SO FAR`
rather than claiming a completed-horizon result. This telemetry is report-only
and has no execution, routing, sizing, balance-gating, or strategy-mutation
authority.

Additional verification on the current worktree:

- 3,187 non-network Python tests passed with four intentional deselections;
- the complete Rust/TUI suite passed;
- strict Clippy, Rustfmt, targeted Ruff, and whitespace checks passed;
- the read-only checkpoint reports runtime profile `8dfeee41...` and staged
  profile `128da53b...`, with `wait_for_flat_and_no_orders` blocked only by the
  existing HYPE lifecycle;
- the checkpoint exports the current disk profile's exact non-secret override,
  `range_onset_bidirectional_v1|ETH = dual_mtf_not_opposed`;
- an actual 165x50 TUI monitor showed `SOURCE CONTRACT` as the effective ETH
  rule and `DUAL-MTF NOT OPPOSED` as the next-run rule, along with the stale
  runtime warning and exact protected HYPE state. Quitting left the backend
  and stop OID `509351056418` unchanged.

## Validation and identity

- Focused Python tests: 15 passed across causal variants, immutable command,
  live telemetry, configuration evidence, and scorecard projection.
- Baseline parity: exact metrics, side summaries, and exit counts in all four
  chronological scopes.
- Immutable artifact:
  `data/logs/research/range_onset_context_challenger_ETH_20250728_20260728_v2.json`
- SHA-256:
  `0f09a44db3a027678710a46056edaf17b8ac5a325ad8ac72e99a2703a75e0a93`
