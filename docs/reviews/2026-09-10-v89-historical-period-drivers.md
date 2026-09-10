# Why the original later period weakened

The six original first-core, full-prefix XYZ, recorded-clock cases now have
boundary-aware cash attribution. High confidence applies to these descriptive
historical calculations: independent raw-account arithmetic reconciles 1,302
values, with a maximum residual below $0.000000000003. This does not establish
a market-regime cause, future profitability, or a live deployment recommendation.

The [portable findings report](../../data/logs/research/bidirectional_cohort/v89_historical_period_driver_diagnostics_20260910_v1/report.html)
contains the six-case comparison, asset and cash drivers, and marked account
paths. Its canonical payload and actual DuckDB source queries match all 65
reviewed aggregate rows. Packaged browser verification passes at desktop and
narrow widths, including source interaction, rendered content and no external
requests. The HTML is self-contained; no external publication was performed.

## Measured change

The earlier period is July 21–August 18 UTC, 28 days; the later period is
August 18–September 7 UTC, 20 days. Comparisons below normalize by calendar days.
These are previously available historical periods, not newly unseen holdouts.

| Full HIP-3 fee case | Control | Equal allocation |
| --- | ---: | ---: |
| Earlier net PnL | +$103.59 | +$250.59 |
| Later net PnL | -$137.03 | -$158.60 |
| Later minus earlier net PnL per day | -$10.55 | -$16.88 |
| Gross contribution to daily change | -$10.72 | -$17.67 |
| Lower fees: offset to daily change | +$0.21 | +$0.87 |
| Funding contribution to daily change | -$0.05 | -$0.07 |
| SNDK share of daily net deterioration | 61.15% | 81.97% |
| Later-period fees | $67.43 | $125.32 |

Gross results weaken across all six fixed cost/allocation cases. Fees deepen
the absolute later losses but do not explain the decline as a rising daily
expense: fees per day decrease in the full-fee pair. SNDK is the largest asset
contributor; HYPE adds another 24.46% of control deterioration, based on three
entries per period. The long side explains approximately 98% and 97% of the
full-fee daily decline. Entries decrease from 110/28 = 3.93 per day to
67/20 = 3.35, a 14.73% decline. Low activity alone is an incomplete explanation.

## Attribution and validation

Three positions cross the split: SNDK long, SPCX short and Brent long. Earlier
contributions include their exact boundary marks, entry fees and funding through
the split. Entries and exits at the split belong to the later period; funding
at the split is settled before actions and belongs to the earlier period.
No terminal close or fee is fabricated for an open position. The actual six
accounts end flat; terminal-open behavior is separately covered by fixtures.

Research source c72682e57e9d6d59f224f7a18d0e092d592a87d5 is frozen in
source.tar.gz. Its archive matches 5,639 Git blobs/modes and 1,943 implementation
pins. Forty-seven new synthetic tests and 57 reused account regressions pass in
both the worktree and archive: 104 tests, with 148/148 statements and 48/48
branches covered in the new attribution modules. Boundary ownership, fees,
funding, marked/unrealized value, negative equity and invalid inputs are covered.

Review exposed a missing cash-plus-unrealized-equals-equity check in the new
undeployed implementation. Two failing controls reproduced it; the correction
is included in the frozen, passing source. This is not a deployed defect claim.
The historical evaluation authenticates 2,353 unique references and retains the
exact original boundary event. A separate Decimal script recomputes original
trade quantities, prices, funding and boundary values without importing the new
attribution implementation. Version 2 enforces exact observed asset coverage;
its 1,302 comparisons and numerical results equal version 1.

The first report payload failed the installed source validator because chart
sources required actual SQL. Version 2 executes local DuckDB projections of the
reviewed aggregates and verifies row equality. Prior payloads and scripts are
retained. The final report does not alter the trading calculations. Six operator
scripts pass Ruff and function/file size checks; eight source/plan archive members
are byte-verified. Existing qualifications are reused rather than rerunning the
original historical replay or modifying its active source.

## Decision and next investigation

Retain the marked period decomposition. Prioritize SNDK long concentration,
entry conditions and exit paths across these fixed historical periods, checking
earlier SNDK clock/stop research before adding work. The six-case diagnostic does
not justify removing or reweighting an asset. Combine it with the original
48-case report; do not treat the six related scenarios as independent trials.

Changed source identities, unexplained accounting residuals, different boundary
ownership or contradictory independent arithmetic would invalidate the scoped
finding. Original initialization gaps, conditional missing-minute execution
prices, and modeled fees/slippage remain limitations. Gross PnL already includes
modeled execution-price effects. Actual fee eligibility, fills and causal entry
quality require separate evidence. Both prospective outcome seals remain intact.
No live strategy, allocation, execution, configuration or installed TUI changed.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_historical_period_driver_diagnostics_20260910_v1/`.
Authoritative outputs are diagnostic.json, independent_period_check_v2.json,
artifact_v2.json, report.html and final_artifact_verified.json. Source, tests,
operator archive and prior attempts remain alongside them.
