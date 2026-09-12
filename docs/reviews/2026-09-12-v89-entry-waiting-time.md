# Historical inactivity windows and the next entry's outcome

The completed 48-day shared-account history often contained several hours without
a new entry. **51.44% of complete four-hour windows, 24.80% of eight-hour windows
and 11.74% of twelve-hour windows had no portfolio entry.** High confidence applies
to these authenticated historical counts; future waiting times remain unproven.
This does not describe an actively running backend today.

The original complete matrix and portable report finished on September 10. They
were found through their actual completion artifacts and the later current-index
entry; the earlier preparation reviews remain dated history. Neither pipeline
was restarted. This study extends their gap summary with fixed window counts and
preceding-wait outcome bins. It introduces no strategy or parameter trial.

## What the history says

The window is July 21–September 7 UTC: 48 previously examined calendar days.
All 48 original source/cost/clock/allocation cases have the same **177 ordered
trade identities**, representing **167 distinct entry timestamps**. They are one
historical schedule, not 8,496 independent trades. Simultaneous entries are grouped
only for episode analysis; each original trade and its costs remain retained.

| Complete window length | Hourly-start windows with no entry | Fraction | Separate non-overlapping windows with no entry |
| --- | ---: | ---: | ---: |
| 4 hours | 591 / 1,149 | 51.44% | 150 / 288 |
| 8 hours | 284 / 1,145 | 24.80% | 33 / 144 |
| 12 hours | 134 / 1,141 | 11.74% | 11 / 96 |
| 24 hours | 3 / 1,129 | 0.27% | 0 / 48 |

Hourly observations overlap. The separate grid starts at the original period
boundary; its observations may still be serially dependent. These fractions are
descriptive historical frequencies, not independent-sample probability estimates
or failure thresholds. Half-open intervals include an entry at the left boundary
and exclude one at the right boundary. Incomplete right-edge windows are excluded.
Every complete UTC calendar day contained an entry, which can coexist with a
26-hour trade-to-trade gap spanning parts of two days.

| Scope | Trades in 48 days | Entries/day | Median completed entry gap | Days with no entry |
| --- | ---: | ---: | ---: | ---: |
| Portfolio | 177 | 3.69 | 5 hours | 0 |
| Core crypto together | 17 | 0.35 | 54 hours | 35 |
| Three HIP-3 assets together | 160 | 3.33 | 5 hours | 0 |
| BTC | 3 | 0.06 | 264.5 hours | 45 |
| ETH | 3 | 0.06 | 329 hours | 45 |
| SOL | 5 | 0.10 | 226 hours | 43 |
| HYPE | 6 | 0.13 | 80.67 hours | 42 |
| SPCX | 52 | 1.08 | 22 hours | 10 |
| SNDK | 47 | 0.98 | 22 hours | 13 |
| BRENTOIL | 61 | 1.27 | 19 hours | 7 |

The HIP-3 median becomes six hours when simultaneous entries are combined into
unique episodes. The maximum core gap is 183.75 hours. These sparse core samples
cannot support precise route-specific forecasts. The later 20-day portfolio
averages 3.35 entries/day versus 3.93 earlier; empty eight-hour windows rise from
21.95% to 27.91%. The periods were already explored and are not fresh holdouts.

The existing account disposition remains 295 source-priced proposals, 177
accepted entries and 118 native-routing exclusions while a provider position was
already open. Those excluded close-only/occupied decisions are not automatically
missed executable trades. This study does not change that ownership contract.

## Waiting longer did not establish a higher chance of profit

An episode combines the final net outcome of trades opened at one timestamp.
Its preceding wait is the time since the previous portfolio entry episode.
The first episode is excluded because its preceding wait crosses the left edge.
These are completed ex-post outcomes, not information available when entering.

| Preceding portfolio wait | Episodes | Profitable, adverse costs | Total episode net, adverse costs | Median episode net |
| --- | ---: | ---: | ---: | ---: |
| Under 6 hours | 87 | 40 / 87 (45.98%) | +$54.52 | -$3.28 |
| 6 to under 12 hours | 52 | 21 / 52 (40.38%) | +$131.55 | -$1.71 |
| 12 to under 24 hours | 24 | 8 / 24 (33.33%) | -$115.75 | -$3.15 |
| At least 24 hours | 3 | 0 / 3 | -$11.86 | -$1.39 |

Across waits of at least twelve hours, **8 of 27 episodes were profitable** and
their modeled net was **-$127.61** under adverse costs. The three 24-hour cases
are particularly weak evidence. The same long-wait groups remain negative under
the other two original cost anchors. All 90 group/period/cost combinations and
all four bins, including empty bins, remain in the result.

This does not justify an automatic wait-based filter. It is a small, selected,
dependent historical sample with asset, side, time and regime composition mixed
within bins. Some lifecycles overlap. The first excluded portfolio episode is a
winning SNDK entry; bin totals therefore do not equal full-account profit. No
threshold was optimized and no inference of causation or future win probability
is made. Historical funding, slippage, timing and fee assumptions are inherited;
the full HIP-3 fee case remains stress rather than a current fee quote.

## Validation, provenance and operational boundary

Research source **f1fa951ba708a531daad9ce83c2324e77f62c7fa** is isolated in
`hypervector-v89-entry-waiting-20260912`. Twenty-nine offline tests pass with
**50/50 measured statements and 14/14 branches** covered in the arithmetic module.
Ruff, formatting and file/function-size checks pass. Operator-wide unit coverage
is not claimed. All five source-archive members match their source files.

All 64 direct historical/presentation input identities authenticate. Original
contribution sums reconcile exactly to all 48 published case net totals.
Independent DuckDB queries read the three original account case files, not the
newly exported entry rows. They reconcile **150,432 window/day/gap rows and 2,520
outcome fields**, with maximum cash residual **5.6843e-14 USD**. Eight intentionally
corrupted counts, gaps and outcomes are rejected. A fresh run of the final
formatted source reproduces all five output/verification files byte-for-byte.
The original financial simulator and its underlying market-price qualification
were reused; this is not a new independent financial replay.

At **September 12 04:34:55 UTC**, seven unsigned venue responses retain the existing
**0.306 SNDK short at 1629.2, 10x isolated**, **-$1.4076 unrealized**, and full-size
reduce-only Stop Market **542326955281** at **1669.9**. Fourteen funding cash rows
sum to **+$0.095742**. Core is flat/order-free in that capture. Original trading
PIDs are absent, seven terminal rows remain unchanged, and installed binary,
profile and original ledger hashes match their prior identities. Process access
limits machine-wide absence claims; the venue capture is a sequential snapshot.
No deployment, signing client or financial mutation occurred. Both prospective
hypothetical outcome seals remain unopened.

## Recommendation and next investigation

Retain this measurement and distinguish historical setup cadence from technical
health and a stopped backend. An inactivity duration alone does not demonstrate
a defect, while a missing/stale heartbeat still requires technical diagnosis.
Do not introduce a wait-based entry filter or larger position size from this study.
The current pending 64-file installation proposal is unchanged.

| Alternative | Benefit | Limitation / decision |
| --- | --- | --- |
| Keep only average trades/day | Simple | Conceals frequent multi-hour inactivity; retain the additional descriptive evidence |
| Change entry filters using the wait bins | Would alter the trade set | No causal or fresh validation; no live proposal |
| Validate the existing candle-fetch session candidate over additional public-only runs | Tests a concrete path toward lower decision-to-dispatch delay | More paired timing evidence is needed; this is the next investigation |

The next highest-value experiment is a predeclared extension of the pending
session-reuse latency candidate's four paired public observations, focused on
the configured 30/60-second entry budgets. It must preserve payload equality and
order-management sequencing and must not place orders. This targets a specific
technical delay without reopening rejected strategy ideas or treating cadence
as execution latency. Installation and trading activation remain separate human
decisions under the objective's Human control clause; no new approval is requested
by this descriptive study.

Changed source hashes, wrong interval endpoints, unexplained SQL residuals,
scenario pooling or different entry identities invalidate these measurements.
New causal observations under the same configuration and source coverage could
update the historical cadence assessment. Future profitability and full live
readiness remain unproven.

Evidence: `data/logs/research/bidirectional_cohort/v89_entry_waiting_time_20260912_v1/`.
Primary files are `result.json`, `independent_verification.json`,
`negative_controls.json`, `reproduction_verified.json`, `source.json` and
`publication_boundary/verified.json`. Preserve the accepted study; append a
superseding research revision if its interpretation or implementation changes.
