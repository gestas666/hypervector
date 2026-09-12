# SNDK August 19 source and exit reconciliation

The selected SNDK hour fell **6.7453%** in all four reconstructed price series.
Small native/vendor opening and closing differences remain, but the measured
one-hour endpoints agree exactly. The original **−$13.6563** modeled net loss
reconciles. Its recorded **13:30 UTC** exit is a modeled bar-opening clock;
the associated candle completes at **13:45**, with source knowledge recorded
at **13:45:10**. It is not evidence of a physical fill at 13:30:00.

Confidence is **high for these scoped measurements and original-record
semantics**, supported by authenticated source bytes, independent SQL,
decimal cash checks and archive reproduction. Confidence in causal explanations
or future profitability remains **low**. A changed source hash, failed
reproduction, contradictory trade/mark records or an incorrect source-clock
binding would update this assessment.

## Scope and provenance

This date was selected after the completed day-influence analysis. It is an
explored diagnostic, not an out-of-sample strategy test. The original 47 SNDK
entries, account outcomes and prior studies remain intact. The selected original
case is `first_full_prefix_hip3_full_fee_recorded_bar_clock_control`, and its
trade identity ends in `xyz:SNDK:1787144400000:long`.

The [frozen protocol](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/analysis_source_archive_v2/docs/plans/2026-09-12-v89-sndk-source-reconciliation.md)
fixed August 19 00:00 through August 20 00:00 UTC, half-open, before the archive
prices were compared. Historical model source commit is
`69dd84a990836c30cd56b1effa524b0e20f88acd`; six inspected clock/price modules
match its implementation manifest. New offline analysis source commit is
`b4aaf94a56f77556497fe2f0da1490fbb3f7e4a6` in the isolated SNDK source worktree.

The native source is the retained official Hyperliquid raw response and its
Parquet normalization from `frequency_repair_native_inputs_20260907_v1`.
The vendor responses use the exact HIP-3 `xyz:SNDK` candle route. The
[vendor documentation](https://docs.0xarchive.io/rest-api/candles) describes
candle-start timestamps and separate base volume, quote volume and trade counts.
These are separately captured sources; their agreement does not establish
independent underlying economic feeds or a historical mark-price series.

## Data qualification and numerical results

All **4,801 native raw candles** pass the OHLC, quantity, instrument, cadence
and clock checks. That response contains the original 4,800 source-window
candles plus one exactly at its excluded end. The selected day contains 96.
The vendor returns 1,441 minute rows and 97 quarter-hour rows, each including
one exact-end row. The selected day has **1,440 minutes and 96 quarters**, with
no missing, duplicate or disordered slots. No gaps were filled.

| Comparison | Price results | Quantity results |
|---|---|---|
| Native raw → native Parquet | All 384 OHLC cells agree exactly | All 96 base-volume cells agree |
| Native → vendor 15-minute | 11 opening and 5 closing cells differ; all highs/lows agree | All 96 volumes and 96 trade counts agree |
| Vendor 15-minute → complete minute aggregates | All 384 OHLC cells agree exactly | All trade counts agree; tiny volume differences retained |

Native/vendor maximum opening difference is **0.4 price units / 2.5180988354
bps**; maximum closing difference is **0.2 / 1.2793449754 bps**. Price basis
points use `(vendor − native) / native × 10,000`. Volume/count differences
remain in their own units. Minute aggregation has maximum base-volume
difference **3.493×10⁻¹⁰** and quote-volume difference **1.23×10⁻⁸**; all 96
base-volume and 95 quote-volume comparisons are nonzero. Their size is consistent
with numerical accumulation differences, but the vendor implementation is unverified.

All four series—native raw, native Parquet, vendor quarters and aggregated
vendor minutes—give the following completed closes:

| Completion boundary, August 19 UTC | Completed source interval | Close |
|---|---|---:|
| 13:00 entry measurement anchor | 12:45–13:00 | 1704.9 |
| 13:30 recorded exit boundary | 13:15–13:30 | 1681.9 |
| 13:45 exit-bar completion | 13:30–13:45 | 1647.7 |
| 14:00 fixed one-hour target | 13:45–14:00 | 1589.9 |

The fixed-hour return is **−674.5263651827 bps**. These completed-close
measurements do not substitute hypothetical post-exit PnL for the original trade.
See the [full cell comparison](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/price_final/comparisons.json),
[source profiles](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/price_final/profiles.json)
and [price report](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/price_final/price_report.json).

## Original execution model and cash

The native entry-bar open is **1705.5**. Applying the recorded 5.5 bps entry
slippage reconstructs **1706.438025**, within 2×10⁻¹³ of the stored entry.
The original resolved stop reference is **1663.7770743750002**. Applying the
recorded 5.5 bps exit slippage reconstructs the stored **1662.8619969840938**
exit within 1.5×10⁻¹³ price units.

At quantity **0.293**, the original gross is **−$12.7677762087**, entry fee
**$0.4499877072**, exit fee **$0.4384967086**, funding cash **$0**, and net
**−$13.6562606245**. Decimal recomputation differs from stored cash by at most
2.079×10⁻¹⁴ USD. Seven numeric fields also agree with the prior trade-driver
diagnostic. See the [quote checks](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/quote_reconciliation_verified.json)
and [original account reconciliation](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/exit_final/exit_report.json).

All **61 original minute events** from 13:00 through 14:00 are retained as
byte-identical JSONL. The selected risk evaluation consumes the native
13:30–13:45 bar: open **1682.1**, high **1699.8**, low **1620.4**. Its stop
decision is unambiguous in that model. The record explicitly retains the
modeled opening clock separately from completion and knowledge clocks.
The existing registered late-intrabar timing variant is preserved; no new
exit policy was simulated here.

The vendor minute series first crosses the modeled stop reference during
**13:30–13:31**: its low is **1662.2**. This supplies a trade-price interval,
not a precise trigger time, mark-price crossing, executable quote or actual fill.
Price movement through later completed boundaries therefore remains labeled
by source clocks rather than assigned to a physical stop execution.

## Verification, limitations and decision

The independent DuckDB implementation verifies **1,728 comparison cells**,
**1,440 individual minute rows**, **18 displayed field summaries**, all source
grids and all four endpoint/return series. Maximum independent decimal return
residual is **4.8852×10⁻²⁴ bps**. It rejects altered operands, duplicate cells,
missing anchors, changed minute paths and incorrect report projections.

**78 offline tests pass**. New analysis code has 92% combined statement/branch
coverage; the candle arithmetic has **100 statements and 50 branches covered
at 100%**. The corrected 142-file source archive passes the same 78 tests and
all three standalone commands. All **10 final output files reproduce
byte-for-byte**. The [reproduction receipt](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/analysis_reproduction_verified.json)
and [independent result](../../data/logs/research/bidirectional_cohort/v89_sndk_source_reconciliation_20260912_v1/sql_final/independent.json)
state the exact verification scope.
The primary price report preserves its pre-verification
`independent_checks_complete=false` stage marker; the separate completed SQL
and reproduction receipts establish the final independent verification.

The first 20-file archive passed tests but failed standalone imports; those
failures are retained, and only `analysis_source_v2.tar.gz` is the complete
runtime package. The original strict native-boundary failure and SQL parser
failure are also retained. No failed attempt is relabeled as a successful run.

Remaining limitations:

- Vendor status was degraded overall but HIP-3 operational. Exact-symbol
  quality metadata omitted candles; coarse completeness is not selected-day
  accuracy proof. The incident query cannot rule out earlier-starting incidents.
- One selected day does not validate every historical day, the full 47-entry
  cohort or future profitability. Endpoint disagreements remain reported.
- Candles cannot establish historical venue mark triggers, book liquidity,
  slippage realization, queue order or actual intraminute fills.
- This is a conditional historical account reconstruction; it adds no
  prospective evidence and opens neither sealed outcome window.

Decision: **accept the scoped source/clock reconstruction**. The hypothesis
that a large native-price error explains the selected one-hour decline is
**rejected for the measured endpoints**. Broader data fidelity and strategy
causality remain open. No live strategy, risk, sizing, leverage, universe,
execution or deployment change is proposed from this one-day result.

The single next investigation is **propagation of the 16 observed endpoint
differences into the already-published SNDK entry-quality and matched-background
measurements that touch August 19**. Preserve the original roster, use both
sources symmetrically, quantify the affected cells and aggregate shifts, and
do not choose a source or filter based on PnL. This bounds the impact of the
remaining source disagreement before drawing a new strategy conclusion.

At **09:37:22 UTC September 12**, the fresh unsigned account capture still
shows SNDK short **−0.306**, entry **1629.2**, **10x isolated**, unrealized
**−$0.0612**, and full-size buy reduce-only stop **1669.9** (OID 542326955281).
There are 19 captured funding cash rows totaling **+$0.081031** and only the
original entry in the bounded fill query. Core positions/orders are empty.
The original trading PIDs are absent in the observed process scope; permission
limits preclude an unrestricted machine-wide assertion. Installed profile,
TUI, ledgers and pending installation candidates are unchanged.

The standing installation questions remain pending. This research result does
not authorize installation or rearming under the objective's Human control
clause, and broad live readiness remains unproven.
