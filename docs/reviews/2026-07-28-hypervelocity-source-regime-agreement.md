# Hypervelocity source-regime agreement review

Date: 2026-07-28

## Problem restatement

The backend and pinned Hypertrader classifiers agree on trend direction but use
different trend-versus-range boundaries. This experiment tested whether current
Hypervelocity entries improve when they are retained only if the causally
available Hypertrader label agrees. It was report-only and did not change the
runtime strategy, TUI, or observe-only metalabel authority.

## Known facts and assumptions

- Window: 2026-04-28 00:00 UTC through 2026-07-27 00:00 UTC.
- Tape: 12,013,541 canonical L2 snapshots, 36,591,762 deduplicated public
  trades, 127,814 authentic price updates, and 2,160 funding rows.
- Execution contract: $10,000 initial equity, 70% isolated margin allocation,
  40x leverage, 8% gross margin target, maker trade-through fills, five-minute
  entry TTL and cooldown, and same-direction re-entry after regime reset.
- Strict source revision: `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Legacy source revision: `96014462c8f3911abff1babc925448893d65676d`.
- Each 5m source label became usable only at its recorded `available_at` time.
- Public evidence cannot reconstruct private queue rank, cancellations, hidden
  depth, or partial maker fills.

## Results

| Candidate | Directional bars | Fills | Targets | Liquidations | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Canonical control | 113,927 | 277 | 241 | 36 | $27.04 | -99.85% |
| Strict source agreement | 43,639 | 176 | 149 | 27 | $15.74 | -99.90% |
| Legacy source agreement | 47,099 | 214 | 178 | 36 | $1.03 | -99.99% |

The control exactly reproduced the frozen entry-filter control on directional
bars, lifecycle counts, final equity, drawdown, funding, and status counts. The
strict gate removed 70,288 otherwise-directional bars as non-tradable and
reduced liquidations by nine, but reduced final equity and worsened maximum
drawdown. It retained 14 of 35 creator-entry direction matches versus 24 for
the control. The legacy gate also introduced 2,450 direction mismatches.

## Assessment

High confidence for this implementation and evidence window: a blanket source
regime agreement gate is inferior to the unchanged control. Exact control
parity, pinned metadata, causal availability, and identical execution settings
support that conclusion.

Low confidence that this rules out all uses of source taxonomy. Sequence effects
can differ when source agreement is combined with another entry-boundary rule,
and all 90 days remain development evidence rather than a sealed holdout.

The conclusion would be falsified by a code or evidence audit finding look-ahead,
candidate-specific execution settings, broken control parity, or a repeat on an
independent venue-matched window showing materially better equity and drawdown.

## Decision and next validation

- Reject strict and legacy blanket gates for runtime use.
- Keep the deployed runtime configuration unchanged.
- The bounded strict-source plus hard-BBWP/recovery interaction was also
  rejected. Its control reproduced $2,466.13, 39 liquidations, and -97.83%
  drawdown; the interaction ended at $36.70, with 31 liquidations and -99.86%
  drawdown. All three 30-day segments lost.
- Stop exploring blanket source-taxonomy gates. The result does not justify a
  regime-detector runtime change.
- On the hard-BBWP/recovery lifecycles, a fixed-lifecycle consolidation-wick
  screen improved additive PnL by $3,526.75 and intercepted 28 liquidations at
  the cost of stopping 73 eventual targets. The confirmed 2-left/2-right pivot
  worsened additive PnL by $10,230.23 and is rejected.
- Run the consolidation wick in a full stateful event replay with authentic
  mark, funding, BBO stop execution, taker fees, compounding, and re-entry.

The stateful replay falsified that screen. The hard/recovery control again
ended at $2,466.13 with 39 liquidations and -97.83% drawdown. The wick candidate
reduced liquidations to 15, but generated 155 stop exits and 524 completed
trades, increased total fees from $13,847.07 to $19,701.99, and ended at $20.33
with -99.86% drawdown. All three 30-day segments lost. The fixed-lifecycle
improvement did not survive compounding, re-entry, or execution friction.

The next evidence-backed direction is the legacy trend-down short-follow
candidate. It is not literal source Recipe C: it preserves Recipe C onset times
but changes the side from countertrend long to trend-following short. That
matches the observed strategy rule of shorting `TREND_DOWN`, while remaining a
report-only challenger. Its development replay produced 29 targets and one
liquidation from 30 fills, grew $10,000 to $25,219.35, and had positive
closed-trade growth in all three 30-day slices (1.75x, 1.09x, and 1.33x). One
subsequent Jul 27 event filled and targeted for +$476.87. Thirty-plus-one fills
remain insufficient for live promotion.

## First independent forward window

The canonical DuckDB evidence was extended through 2026-07-28 22:00 UTC with
120,593 L2 snapshots, 290,737 deduplicated public trades, 1,307 causal price
updates, and 22 official funding observations. Both source revisions were
rebuilt across the full 26,472-bar history. Every classification and causal
availability field matched the prior 26,208-bar prefix exactly; the largest
`volume_ratio` difference was `3.01e-13`, attributable to floating-point
aggregation order and below the new `1e-12` annotation identity tolerance.

Both revisions emitted one fresh trend-down follow event. The current
`ad15f2bd` classifier decided at 14:05 UTC, filled a short at $63,182.00, and
targeted at $63,055.636 after 10 minutes 52 seconds. Net PnL was +$476.08 after
$83.92 fees on a fresh $10,000 portfolio, with -3.58% maximum marked-equity
drawdown, no liquidation, and no funding settlement. The legacy classifier
decided five minutes later; its 60-second maker order did not fill and was
canceled.

Across development plus the two later windows, the current revision has 28
fills, 27 targets, and one liquidation; the legacy revision has 31 fills, 30
targets, and one liquidation, plus the unfilled Jul 28 order. Legacy remains
the higher-equity development result, while current has the better Jul 28
timing. That split is why neither revision is promoted.

This is encouraging but remains low-confidence (`n=1` independent event). It
does not promote either classifier or change runtime execution. Multiple later
current-only losses or liquidations while legacy avoids them would falsify the
observed timing advantage. The next step is continued immutable forward-window
collection and the same predeclared replay, without retuning against July 28.

## Short-arm isolation

A final causal comparison removed the unsupported Recipe-B long arm and kept
only the current-revision `TREND_DOWN` onset short during 07:00-16:00 UTC. The
candidate retained the frozen 100-bps completed-5m range annotation, 60-second
maker TTL, 70% isolated margin, 40x leverage, 8% gross-margin target, authentic
fees and funding, and no stop. It remains research-only.

The 90-day development replay ended at $23,366.73 under touch, $35,678.79 under
one-tick book-through, and $25,600.17 under public trade-through. The strict
path resolved 20 fills as 20 targets with zero liquidations and -32.50% maximum
marked-equity drawdown; all three fixed 30-day slices were profitable. The
frozen candidate then resolved the Jul 27 and Jul 28 forward events as two more
targets. The full legacy fade-long population, by contrast, ended at $133.39
under public trade-through with 12 liquidations and -99.46% drawdown.

This raises confidence in a narrow short-side edge to medium, but confidence in
a complete Hypervelocity strategy remains low. The result is sparse,
session-constrained, short-only, and selected on development evidence. It is
frozen in `configs/research/hypervelocity_source_follow_short.toml`; it is not
loaded by the runtime and does not change the faithful configuration, TUI, or
observe-only ML authority. See
`docs/reviews/2026-07-28-source-follow-short-candidate.md`.

Evidence:
`data/logs/research/hypervelocity_source_regime_gate_20260728.json`,
`data/logs/research/hypervelocity_hard_recovery_source_regime_interaction_20260728.json`,
`data/logs/research/hypervelocity_hard_recovery_consolidation_wick_stop_20260728.json`,
and
`data/logs/research/hypervelocity_hard_recovery_confirmed_pivot_stop_20260728.json`,
`data/logs/research/hypervelocity_hard_recovery_wick_stop_stateful_20260728.json`,
and
`data/logs/research/hypertrader_legacy_96014462_source_follow_only_ttl60_trade_through_duckdb_20260728.json`.
Forward artifacts:
`data/logs/research/hypertrader_current_ad15_source_follow_only_ttl60_trade_through_forward_20260728T2200.json`
and
`data/logs/research/hypertrader_legacy_96014462_source_follow_only_ttl60_trade_through_forward_20260728T2200.json`.
