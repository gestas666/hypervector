# First complete historical account: result and resource estimate

The first original 48-day account case is complete and independently reconciled.
This is one of 48 required historical cases, not a completed comparison or a
live-readiness finding. Confidence is high in the recorded calculation within
its qualified accounting scope; confidence in future profitability is unresolved.

The case is `first_full_prefix_nominal_recorded_bar_clock_control`, covering
July 21 through September 7 UTC with the original 28/20-day split. It includes
BTC, ETH, SOL, HYPE, xyz:SPCX, xyz:SNDK and xyz:BRENTOIL. Starting equity is
$4,857.58724349. Nominal costs, prices and timing remain modeled historical
assumptions, not observed live fills. The later segment is not a new holdout.

| Metric | Complete case result |
| --- | ---: |
| Net equity change | +$196.85 (+4.05%) |
| Ending equity | $5,054.44 |
| Maximum marked drawdown | $140.67 (2.74%) |
| Earlier 28-day equity change | +$214.58 |
| Later 20-day equity change | -$17.73 |
| Accepted and closed trades | 177 |
| Open terminal trades | 0 |
| Wins / losses | 74 / 103 |
| Win rate | 41.81% |
| Entries per day | 3.6875 |
| Median / maximum entry gap | 5 / 26 hours |
| Net excluding three largest closed winners | -$31.83 |
| Net excluding three largest positive marked days | +$18.84 |

The concentration diagnostics answer different questions and remain separate.
Aggregate performance depends on a small number of winners while the later period
loses money. This does not support an assumption that infrequent trading means
most entries will win. This control case also does not establish an improvement
over current allocation. Negative results remain observations, not trial gates.

All 295 source-priced proposals are accounted for: 177 accepted, none rejected
by account constraints, and 118 excluded by native routing because the provider
already had a position open. Empty evaluations are not missing trades. The
independent Decimal audit passes over 69,121 timestamps and 1,018,908 numeric
fields. Fresh and retained audits match; 2,281 case references were reauthenticated
and seven independently summed equity totals reconcile. The ledger audit does
not independently qualify source-price or native-routing selection.

The account and independent audit took 1,931.31 seconds after 199.62 seconds of
source setup. Peak resident memory was 16,914,300,928 bytes; the complete case
occupied 184,712,040 bytes. Four workers at this rate project to about 6.5 hours
for all 48 account cases before reporting and reproduction. Confidence in this
planning estimate is medium: case differences, contention and later validation
can change it. It is not a live launch deadline.

At September 10 02:25 UTC, free disk space was 5,009,059,840 bytes and no matching
local live backend, checkpoint writer, TUI or account research worker was observed.
The pilot is finished; the full matrix is not running. Forty-eight outputs at the
pilot's size project to 8,866,177,920 bytes before overhead. An alternate output
folder with at least 15 GB free was requested; its response is pending. No source
evidence was deleted. Process absence is not a fresh venue account snapshot.

Replay engine: `69dd84a990836c30cd56b1effa524b0e20f88acd`.
Reporter: `34004579e2cb21d13c55e01c47fa6f69e70d76ff`, whose 199 integrated tests
pass in both worktree and verified archive. The pilot completed at 02:02:46 UTC,
analysis at 02:10:14 UTC, and retained verification at 02:20:24 UTC on September 10.

Evidence is under
`data/logs/research/bidirectional_cohort/v89_first_complete_historical_account_20260910_v2/`:
`pilot_report.json`, `analysis_report.json`, `analysis_provenance.json`,
`analysis_verified.json`, `source_pair.json`, `launch.json`, and the complete
case directory. Reporter qualification is recorded separately in
`v89_historical_account_reporting_qualification_20260910_v1/verified.json`.

Next obtain sufficient storage, finish every original cost, timing, source and
allocation case, then publish and reproduce the paired comparisons. A live
proposal still needs those results and remaining technical deployment checks.
There is no defensible live-start ETA yet. No new live approval is requested by
this review. Both prospective outcome seals remain intact.

Changed evidence hashes, accounting disagreement, nonconserved contributions or
different case identity invalidate this result. The remaining comparisons can
change its practical meaning. No live strategy, sizing, leverage, risk, execution,
deployment or process lifecycle changed during this analysis.
