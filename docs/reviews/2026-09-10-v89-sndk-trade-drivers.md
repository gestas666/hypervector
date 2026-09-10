# SNDK long trade deterioration: fewer winners and more stop exits

The fixed six-case historical trace retains all 47 SNDK identities per case,
including 29 longs and 18 shorts. High confidence applies to source-bound counts,
cash and sampled-price arithmetic. A causal explanation or a new entry/exit
policy remains unproven. The 282 repeated case rows are not independent trades.

The primary comparison below uses the original full-fee control allocation.
Trades are grouped by entry before or at/after August 18 UTC; each row retains
its whole lifecycle. These entry cohorts differ from marked 28/20-day account
periods because one earlier SNDK long crosses the split.

| SNDK longs, full-fee control | Earlier entries | Later entries |
| --- | ---: | ---: |
| Trades | 18 | 11 |
| Winners / losers | 7 / 11 | 2 / 9 |
| Win rate | 38.89% | 18.18% |
| Full-lifecycle net PnL | +$130.63 | -$35.16 |
| Stop exits | 7 | 8 |
| Signal exits | 3 | 1 |
| Modeled liquidation exits | 1 | 0 |
| Winners reaching the 24-hour hold limit | 7 | 2 |
| Mean gross stop return | -206.28 bps | -207.74 bps |
| Net excluding up to three largest winners | -$40.68 | -$94.43 |
| First-hour observations / trades | 16 / 18 | 10 / 11 |
| Mean first-hour return, observed subset | +22.21 bps | -38.83 bps |

All nine winning longs exit at the 24-hour hold limit. Earlier winners contribute
$243.22 and later winners +$59.27; stop losses total -$77.94 and -$90.35. Average
gross stop loss barely changes while the stop count rises and winning trades
become less frequent. This supports a working hypothesis of weaker sustained
follow-through, not a demonstrated cause or a calibrated probability of recovery.

The earlier entry cohort's marked contributions are +$132.70 before the split
and -$2.06 after it. Adding later entries gives long-side later marked PnL of
-$37.23. Short contributions remain in the complete SNDK asset attribution.
Equal allocation retains the same identities and normalized outcomes; long entry
cohort cash is +$280.12 and -$75.11. It adds no independent evidence.

Entry publications show median ATR/reference of 116.41 versus 122.97 bps,
breakout beyond the prior channel of 51.04 versus 75.65 bps, and channel width
of 416.57 versus 389.47 bps. No threshold was fitted. These small selected
samples do not establish that a larger breakout or a particular UTC hour causes
losses. First-hour results exclude trades closed sooner, so their changing
sample composition prevents treating them as an unbiased entry-quality estimate.

## Path and source qualification

Only 15-minute bars entirely inside the modeled holding interval are used.
Favorable/adverse excursions use completed closes with a zero entry anchor;
partial holding bars and exit-bar future prices are excluded. These are sampled
trade-price paths, not continuous extrema, venue mark prices or executable peak
exits. The signed peak-to-exit gap is descriptive and can be negative when an
exit beats previously sampled closes. No missing path is filled with zero.
One earlier long lacks a complete held bar; first-hour paths are censored for
two earlier and one later long. Six of nine later losing longs had a positive
completed-close gross excursion, but that does not establish a profitable
realizable early-exit policy after costs and effects on winning trades.

The fixed plan was committed before evaluation. Source identity checks cover
2,367 references, including 48 daily provider files with 4,608 publications and
the declared 4,800 native price bars including warmup. Exact accepted entry
identities and causal publication clocks match; raw original account prices,
quantities, cash and exit reasons match qualified trade reports.

Forty synthetic tests pass in the working operators and verified five-member
archive. The metric/context module covers 89/89 statements and 28/28 branches.
The initial missing-module test failure is retained; an initial pytest cache
warning is absent from the archive run, which disables cache writing. The
operator driver itself is checked through historical source/reconciliation
controls, not claimed to have the metric module's unit coverage.

Independent Decimal account calculations and DuckDB queries of the original
Parquet source pass 2,070 cash, path and cohort comparisons without importing
the new diagnostic implementation. Maximum numerical residual is 2.08e-12
across the mixed cash/return units. Eighteen marked cash totals match the prior
period attribution; all six cases retain the same 47 ordered identities.

## Disposition

Retain this descriptive diagnosis and combine it with the pending full 48-case
report. Do not reopen the rejected faster-entry proposal or repeat the accepted
ambiguous-stop investigation without new evidence. No new live filter, profit
lock, sizing change or deployment follows from this selected historical sample.
Any policy proposal needs a fixed causal rule and an appropriately separate
evaluation that accounts for both saved losses and interrupted large winners.

Changed source identities, mismatched publication clocks, missing held bars or
unexplained independent residuals would invalidate the affected measurements.
The earlier/later history has already been explored, modeled costs/fills retain
their limitations, and both prospective outcome seals remain intact.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_sndk_trade_driver_diagnostic_20260910_v1/`.
Use diagnostic.json, case_*.json, independent_verified.json and qualified.json;
source archives, fixtures, accepted provider bindings and logs remain retained.
