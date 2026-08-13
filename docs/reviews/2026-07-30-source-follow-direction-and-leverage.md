# Source-follow direction and leverage controls

Date: 2026-07-30

## Problem and experiment contract

This checkpoint asks two bounded questions about the pinned source-follow
minimum-range-12 lead without changing the active backend:

1. Does the same source event stream work because of its short direction, or
   would the identical events also work long?
2. Does 25x leverage improve the 30x lead by moving liquidation farther away
   while preserving the 8% gross-margin target?

All accepted comparisons use the same 285 selected decisions from 421 source
events, twelve ordered gap-free Hyperliquid segments, one continuously carried
$15,000 portfolio, 50% isolated margin, displayed queue ahead, public
trade-through fills, partial fills, latency, maker/taker fees, authentic
mark/oracle liquidation, official funding, one BTC position, and a 24-hour
maximum hold. ML remains observe-only and every replay has zero execution
authority.

## Exact direction control

| Metric | Short lead | Exact long mirror |
|---|---:|---:|
| Selected signals | 285 | 285 |
| Completed trades | 114 | 128 |
| Targets | 100 | 106 |
| Time exits | 2 | 2 |
| Full liquidations | 12 | 20 |
| Partial liquidations | 43 | 24 |
| Final equity | $36,408.76 | $619.02 |
| Profit factor | 1.428 | 0.581 |
| Maximum drawdown | -51.14% | -97.78% |
| Maker / taker fees | $9,844.58 / $1,326.85 | $2,867.88 / $951.07 |
| Funding cashflow | +$737.16 | -$352.17 |

Direction is economically material. The profitable result is not reproduced
by mechanically mirroring the same completed-5m source events long. The long
mirror reached 106 targets, but twenty liquidation losses dominated those
wins. This also demonstrates why target hit rate is insufficient as a strategy
quality metric.

An earlier run in this checkpoint accidentally used the older 06:00-15:00
confidence-70 artifact family. It selected 109 rather than 285 signals and is
not treated as the exact direction control. That separate long run also failed:
$15,000 to $4,794.38, PF 0.564, seven liquidations, and -82.92% drawdown. The
artifact mismatch was corrected explicitly by resolving the twelve source
artifacts against the SHA-256 identities embedded in the accepted short replay.

## Exact leverage control

| Metric | 30x lead | 25x challenger |
|---|---:|---:|
| Selected signals | 285 | 285 |
| Completed trades | 114 | 113 |
| Targets | 100 | 100 |
| Time exits | 2 | 4 |
| Full liquidations | 12 | 9 |
| Partial liquidations | 43 | 33 |
| Final equity | $36,408.76 | $35,442.43 |
| Profit factor | 1.428 | 1.456 |
| Maximum drawdown | -51.14% | -57.97% |
| Maker / taker fees | $9,844.58 / $1,326.85 | $7,173.69 / $1,180.24 |
| Funding cashflow | +$737.16 | +$745.87 |

The 25x challenger reduced liquidation counts and slightly improved profit
factor, but the wider 0.32% price target kept adverse positions open longer.
It produced two additional maximum-hold exits, a worse marked drawdown, and
$966.34 less final equity. The 30x lead therefore dominates 25x on both ending
equity and maximum drawdown in this path.

## Fresh source annotations and telemetry correction

Pinned source labels were extended through 2026-07-30 05:30 UTC. The 18 new
bars were TRANSITION or RANGE and created no additional qualified source-follow
entry. All 26,832 overlapping prior rows matched exactly for labels and
confidence; volume-ratio differences were floating-point noise no larger than
9.6e-14.

The annotation database previously called bars without both strict and legacy
labels `unlabeled`. That was misleading after the shorter legacy series ended.
Telemetry now reports strict, legacy, and dual coverage separately. On the
current ledger, 391/392 completed bars have causal strict labels, 59/392 have
both strict and legacy labels, and the only strict-unlabeled bar is the newest
bar beyond the artifact's causal availability boundary. This is an
observability correction; it changes no regime or execution decision.

## Decision and remaining risk

The 30x short-only minimum-range-12 profile remains the research lead. The long
mirror and 25x challenger are rejected. Previously tested consolidation-wick
and confirmed-pivot stops remain rejected because they removed more eventual
target expectancy than liquidation losses.

The lead is not ready for live capital. Its continuous historical PF is above
one and its first fresh live-tape replay completed 2/2 targets, but -51.14%
historical drawdown and only two fresh completed trades leave live/income
confidence low. The active faithful shadow backend remains unchanged and is
still holding its older canonical short; no restart, reset, or source-follow
cutover occurred.

The lowest-risk next validation remains an explicit flat-only shadow cutover
to `configs/hypervelocity_source_follow_minrange12_shadow.toml`, followed by an
unchanged forward sample. Repeated fresh PF at or below one, liquidation
frequency outside the historical envelope, materially worse real queue
conversion, or source-label drift would falsify the lead.

## Immutable evidence

- Exact short lead, corrected 6-second freshness:
  `data/logs/research/hypervelocity_source_production_minrange12_continuous_runtime6s_20250728_20260418_20260730.json`
  (`db223085f8c0ff747373376b2a3d40869d56a2a1dd7cfa7a9ade426041d436e9`).
- Exact long mirror:
  `data/logs/research/hypervelocity_source_production_all_day_minrange12_long_continuous_runtime6s_20250728_20260418_20260730.json`
  (`b0a1977bb98abe23f462875a526d28232a8348137d32e8403bba2a961dedee7f`).
- 25x short challenger:
  `data/logs/research/hypervelocity_source_production_all_day_minrange12_short_alloc50_lev25_continuous_runtime6s_20250728_20260418_20260730.json`
  (`d3b30e39bb7f0d7aebc6a96fbda762d08b6ffba6717a673f374ac607b44ef581`).
- Extended strict labels:
  `data/logs/research/hypertrader_current_ad15_btc_5m_labels_through_20260730T0530.parquet`
  (`f5b8186d450afbd689364905c5630cfeb601ab8384bedd2e129bd3e0dc75ead8`).

## Confidence and falsification

- High confidence that the local direction and leverage comparisons are
  mechanically matched; signal counts, source identities, risk fields, and
  production execution paths are explicit and tested.
- Medium confidence that the short stream has historical edge; the continuous
  path, reset-block comparison, exact long control, and first fresh tape all
  agree, but the 12-bps threshold was selected on development evidence.
- Low confidence that the result will meet a live annual-income objective; the
  fresh sample is two trades, private queue cancellations remain unknowable,
  and historical drawdown is severe.

Verification after the implementation changes passed 1,454 non-network Python
tests with four deselected, all 34 Rust/TUI integration tests, focused Ruff,
changed-file whitespace validation, and the 500-line source limit. The new long
queue path and 25x profile were introduced test-first.
