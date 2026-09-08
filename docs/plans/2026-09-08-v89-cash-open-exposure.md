# Historical noncrypto cash-open exposure attribution

Hypothesis `v89_noncrypto_cash_open_exposure_attribution_20260908_v1`.
Research authority only. No live rules, execution, deployment or prospective
collector changes. Do not inspect the sealed September 8–22 experiment.

## Question fixed before window outcomes

Do the registered SNDK/SPCX shared-account lifecycles lose disproportionately
during the first half-hour of the US equity cash session, relative to their
other exposure on the same session dates? The two latest live stop-outs motivate
this exploratory question; they are excluded from the historical calculation.
Existing historical data and whole-trade results have already been explored.

Use July 21 00:00 UTC through September 7 00:00 UTC, with the original August 18
00:00 UTC split. Analyze archive/first-recorded/latest-recorded source variants,
nominal/adverse/full-HIP3-fee costs, and recorded/late-intrabar exit clocks: all
18 inherited cases. Primary readout: first-recorded, adverse, recorded clock.
Cases are sensitivity checks, not independent samples. Preserve original accepted
trades, quantities and prices; do not simulate changed policies or account resets.

Session dates use America/New_York and the verified 2026 NYSE/Nasdaq cash calendar.
Their scheduled cash open is 09:30 and close 16:00. Calendar references:
https://www.nyse.com/trade/hours-calendars and
https://www.nasdaq.com/market-activity/stock-market-holiday-schedule .
No exchange holidays fall between July 21 and September 6; weekends are not cash
session dates. September 7 Labor Day is outside the historical end bound.
This calendar is an explanatory reference, not Hyperliquid's trading schedule.

The initially discussed 09:25–10:00 window is discarded before computing outcomes:
the registered noncrypto source uses 15-minute candles. Carrying the 09:15 mark
into 09:25 would obscure the intended boundary. Freeze these aligned windows:

- Pre-open: (09:15, 09:30] New York, a separate diagnostic control.
- Cash opening: (09:30, 10:00] New York, the primary window.
- Other time on the same full local session date: midnight→09:15 and
  10:00→next midnight, retaining pre-open separately.
- Non-session or partial local dates: residual, not discarded.

## Accounting, exposure and controls

Use original filled entry/exit prices, fees and hourly funding settlements. Make
each candle close available at its completion (source timestamp +15 minutes).
At boundaries use the latest completed mark after entry, or the entry price if
none has completed. Preserve the original cumulative post-event convention:
events at the left boundary belong to the preceding interval; events at the
right boundary belong to the interval ending there. Report boundary events and
mark age. Opening PnL is marked movement, not whole-trade PnL assigned by exit hour.

Measure interval gross PnL, entry/exit fees, funding, net PnL, intersecting trades,
position-hours, entry-notional dollar-hours, exposed dates, positive/negative
dates and paired opening/other-date totals. Split by asset and direction and by
the original chronological partitions. Exposure duration is exact intersection
of entry→exit with each interval. Normalize only when exposure is positive;
event costs can occur at boundaries with zero duration and must remain visible.
Aggregate groups with their full denominators, not means of ratios.

Reconcile every trade across all partitioned intervals to its saved net result,
every UTC day by symbol to the saved daily attribution, and terminal SNDK/SPCX
totals to the original report. Report the remaining portfolio assets separately
through the already registered full-account totals. Do not claim removing an
opening loss would retain the same entries, exits, margins or outside profits.

Freeze all day-level rows. Report paired same-asset/side dates having opening
exposure; disclose the selection and any missing outside exposure. Use raw counts
and first/second-partition signs, not significance claims from overlapping trades.
No threshold sweep, new filter, stop optimization, leverage or sizing search.

## Validation and disposition

Require source hashes and original journal registration; exact timezone/boundary
tests including weekends, holiday exclusion, DST conversion, crossing midnight,
entry/exit boundary fees, long/short signs and zero exposure. Test that future
marks cannot change earlier attribution and missing/stale source is explicit.
Independent arithmetic and frozen-source replay must reproduce totals.

Retain a descriptive finding only if reconciliation passes. A negative opening
contribution alone does not justify a live filter. A useful next experiment must
show repeated, direction-consistent concentration across chronological partitions
and adequate independent session observations; otherwise defer it and record
the minimum missing evidence. Changed input hashes or failed accounting falsify
the technical conclusion. Causal claims remain unproven without independent
prospective evidence and a full chronological policy/occupancy simulation.
