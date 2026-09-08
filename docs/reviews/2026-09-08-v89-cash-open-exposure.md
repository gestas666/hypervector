# Noncrypto cash-open exposure attribution

**The historical opening-window result is too sensitive to the assumed exit
clock to support a cash-open filter.** In the primary adverse-cost case,
SNDK/SPCX opening contribution changes from **−$3.887588** to **−$83.505224**
when modeled intrabar exits move from their recorded bar timestamp to one
millisecond before that bar completes. Whole-lifecycle net remains **+$164.643539**.
High confidence in the reconciled accounting; low confidence in a causal session
effect or any resulting trading improvement. Retain the descriptive result and
qualify the two largest SNDK clock drivers next.

## Scope and fixed accounting

Hypothesis `v89_noncrypto_cash_open_exposure_attribution_20260908_v1`.
Protocol commit `d267512` predates calculation of these window outcomes. The
registered history runs July 21 00:00 through September 7 00:00 UTC, with the
original August 18 split. These dates and whole-trade results were already
explored; this is not an untouched holdout. The two September 8 actual stop-outs
motivate the question but are excluded from this historical sample.

All **18** inherited source/cost/clock combinations retain **99** accepted
SNDK/SPCX lifecycles each. Archive, first-recorded and last-recorded variants
produce exactly equal noncrypto segment tables at each cost and clock. They
are sensitivity cases, not independent replications. Initial shared-account
equity and the other five assets remain inherited; +$164.64 is the two-asset
contribution, distinct from the primary seven-asset +$96.12 total.

There are 34 full local cash-session dates. The scheduled 09:30 New York open
and 2026 holidays were verified against the
[NYSE calendar](https://www.nyse.com/trade/hours-calendars) and
[Nasdaq schedule](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule).
The NYSE HTML is retained. Nasdaq was verified through the web tool; a separate
archival GET timed out and no Nasdaq HTML capture is claimed. This reference
calendar is not Hyperliquid's trading schedule.

The preregistered windows are pre-open **(09:15,09:30]**, cash opening
**(09:30,10:00]**, other time on the same full local session date, and residual
weekend/partial dates. The preliminary 09:25 boundary was discarded before
window calculations because the registered noncrypto candles have 15-minute
resolution. Completed candle closes become available at timestamp +15 minutes.
They are historical price proxies, not native venue mark prices.

Post-event cumulative accounting assigns events at a right boundary to the
interval ending there. Exact position duration is reported separately; an entry
fee or same-timestamp modeled exit may therefore contribute with zero duration.
All gross price changes, fees and hourly funding remain conserved. This is not
a counterfactual in which opening trades are removed while outside profits survive.

## Results

First-recorded source, opening contribution in USD:

| Inherited cost case | Recorded: first 28 days | Recorded: later 20 days | Recorded: full | Late intrabar: full |
|---|---:|---:|---:|---:|
| Nominal | −15.536144 | +12.958382 | −2.577763 | −82.170803 |
| Adverse, primary | −16.400039 | +12.512451 | −3.887588 | −83.505224 |
| Full HIP-3 fee | −22.827569 | +9.686982 | −13.140587 | −93.958452 |

For the primary recorded clock, opening exposure covers **17 dates and 9.5
position-hours**. The raw −$3.887588 covers 24 dates with events or exposure:
**−$13.261976** comes from zero-duration segments and **+$9.374388** from
positive-duration segments. It must not be described as a loss solely on those
17 exposed dates. Recorded-clock same-timestamp exits number three across the
full sample; one contributes to this opening accounting.

The paired comparison selects 20 asset/side/date groups on those 17 dates with
positive opening exposure. Opening +$9.374388 over 9.5 position-hours compares
with +$245.628667 over 244 hours elsewhere on the same selected dates, including
pre-open. Full-denominator rates are 19.7356 versus 20.1335 net basis points per
entry-notional dollar-hour. No pair lacks outside exposure. This selected subset
does not establish a causal opening penalty or represent the raw all-date total.

Under the late clock, primary opening contribution is −$71.193863 in the first
partition and −$12.311361 in the second. Exposure rises to 24 dates and
11.749998 position-hours; only −$0.45 is zero-duration accounting. Pre-open
contribution simultaneously changes from −$47.086937 to +$48.214000. These
clock-dependent reassignments conserve whole-trade net and do not measure a
changed executable policy.

Ten trades change opening contribution between clocks. The two largest are
SNDK short `xyz:SNDK|19`, August 6 13:30 UTC (−$28.334555 shift), and SNDK long
`xyz:SNDK|20`, August 7 13:30 UTC (−$23.191473 shift). Together they explain
$51.526027 of the $79.617635 net clock difference. Those shifts are interval
attribution changes, not their whole-trade losses.

The August 7 original engine row is labeled **modeled liquidation** and
`same_bar_ambiguous=true`: stop 1285.269009375, adverse liquidation/exit
1248.9692660171054. The full-fee case inherits a different liquidation/exit
1250.0932259605263 despite identical entry, quantity and recorded times.
The registered liquidation helper includes entry fees in isolated-margin equity.
Consequently this sensitivity is not a pure fee-only comparison. It is not
evidence of an actual venue liquidation or a newly observed live-system defect.

## Validation and limits

Research-only source **`e01ca6840326fa9cba6ccf1b9f19ba9e35255b39`** is frozen in
an archive. All **5,099** Git members match their blob identities, and its replay
reproduces all **55** report/parquet files byte-for-byte. The three reused
attribution, portfolio and settlement modules are exact copies of their already
registered contemporary source. The older worktree validator rejected valid
same-timestamp modeled exits; its prior version and initial failing test log
remain preserved. No research Python source was deployed into the main workspace.

**33 offline tests passed**, covering boundary costs, direction, timezone,
weekends/holidays, future-mark isolation and lifecycle conservation. The two new
pure calculation modules cover 125/125 statements and 42/42 branches. This is
not whole-project or I/O coverage. Ruff and the new-file/function limits pass.
All 1,728 original symbol/UTC-day values reconcile; maximum absolute error is
2.4869e−14 USD. Completed-price boundary age is zero at the aligned sample
boundaries, which does not resolve intrabar event order.

A separate DuckDB calculation importing no research implementation reconstructs
**21,132** interval component values from original trades, candles and funding,
with maximum error 1.7764e−15 USD, plus **10,566** exposure comparisons. An
additional check verifies exact source equality and every saved clock-driver
delta. Revised input hashes, failed conservation or independent replay, or
finer venue evidence contradicting event timing would update these conclusions.

## Decision and next investigation

| Option | Value and confidence | Trade-off / evidence still needed | Disposition |
|---|---|---|---|
| Keep present rules while researching | Avoids fitting already explored clocks; return improvement unverified | Does not resolve strategy weakness | Current research baseline |
| Add a cash-open or pre-open filter | Expected return effect unverified; low confidence | Boundary conventions, occupancy changes and winner selection can reverse interpretation | Defer; no live proposal |
| Qualify August 6–7 SNDK exit clocks | High diagnostic priority given their $51.53 contribution to timing sensitivity | Need finer historical price/mark coverage and stop-versus-liquidation sequence | Next investigation |

Next hypothesis: `v89_sndk_opening_exit_clock_qualification_20260908_v1`.
First inventory registered historical sources and existing archive coverage for
these two exact bars. If insufficient, preregister a bounded public historical
acquisition. Qualify timestamps, gaps, trade prices versus native marks and
whether event order can distinguish stop from liquidation. Do not infer fills
from candle extrema. An eventual filter would still require a full chronological
policy/occupancy simulation and independent prospective evidence. Prior SNDK
onset/durable-correction studies do not answer this V89 exit-clock question.
The sealed September 8–22 experiment remains unopened.

At September 8 **15:51:59 UTC**, tracked backend, supervisor, reporter and TUI
PIDs were absent. This is process evidence, not a fresh venue account snapshot;
the latest retained flat/no-orders read remains 14:11 UTC. The approved TUI
binary remains installed. This study took no process lifecycle action and
changed no live strategy, configuration or deployment.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_noncrypto_cash_open_exposure_attribution_20260908_v1/`.
