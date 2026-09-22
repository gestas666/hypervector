# Recent V89 profit giveback

September 21, 2026. Report only; no exit-policy or sizing change.

High confidence in the recorded fills and sampled gross peaks below. The
operator's observation is supported for SOL, BRENTOIL and SNDK. The most recent
SPCX trade retained most of its gain; the preceding SPCX trade did not.

| Trade, identified by entry order | Highest recorded gross unrealized PnL | Final net PnL | Actual exit |
| --- | ---: | ---: | --- |
| SOL 550026282998 | $17.9648 | $1.763317 | Opposite range-onset signal |
| BRENTOIL 550252286842 | $8.41519 | -$0.602497 | Hourly price-recipe exit |
| SPCX 550990689720 | $1.43 | -$1.545079 | Protective stop |
| SPCX 551355410685 | $2.6244 | $2.093359 | Hourly price-recipe exit |
| SNDK 551070922979 | $11.6901 | -$1.742266 | Hourly price-recipe exit |

Peaks come from account/position snapshots of the exact entry order, not the
portfolio balance or a different trade. Sample counts are respectively 6,330,
4,697, 1,352, 1,153 and 2,809. Gross peak and net final PnL are deliberately
labelled differently: final net includes lifecycle fees and funding. Peaks are
sampled marks, not executable liquidation values or a promised obtainable exit.

SNDK's recorded peak was at 13:28:22 UTC (09:28 EDT), with a mark near 1830.50.
It entered at 1788.60 and closed at 1782.70 at 14:00:14 UTC. Fees were $0.086087,
funding was -$0.010079, and gross realized PnL was -$1.6461. The hourly signal's
reference price was 1778.20, so the actual fill was better than that reference;
adverse execution slippage does not explain this giveback. Its bound execution
plan had no profit lock or profit target and honored the hourly recipe exit.

The SNDK peak occurred hours after backend recovery. The SOL and BRENTOIL exits
preceded drain activation. The outage and drain therefore cannot be the sole
explanation for the observed pattern. The drain preserved the configured exits.

The completed-candle audit reports missing path data for four of these trades,
including 126 missing one-minute candles for SNDK. Consequently these sampled
peaks are lower bounds on recorded-observation coverage, not exact intratrade
maxima. The latest SPCX candle path resolves: approximately 81.7% gross favorable
excursion capture. No unobserved path has been filled in.

## Implication and validation

Operational availability repairs do not change these exit rules. A profit-lock,
trailing-stop or partial-exit proposal would be a separate strategy change.
To assess one, compare the existing exit with predeclared alternatives over the
full eligible sample, including trades where an early exit would have cut off
a later winner; include fees, funding, spread, latency and unavailable paths.
Then validate chronologically on data not used to choose the rule. These five
outcomes alone do not establish a superior threshold.

Evidence in the original checkout:
`data/logs/operations/v89_flat_maintenance_20260921T1422Z/last-five-trade-giveback.json`,
the live cohort snapshots, asset fills, and current checkpoint trade reflections.
A mismatched entry identity, corrected venue fill or newly recovered path data
would update this assessment. No profit-lock rule was enabled by this review.

## September 21 corrective implementation

Profit protection is now a concrete V90 requirement. The candidate binds the
100/25/50-bps completed-minute rule to all three active hourly routes under a new
provider identity. Recovered ledger/startup evidence resolves 27 of 28 closed
paths, including all five trades above. Read
`2026-09-21-v90-profit-protection-readiness.md` for delayed-execution results,
cut-winner costs, sizing and validation. No live policy has been activated.
