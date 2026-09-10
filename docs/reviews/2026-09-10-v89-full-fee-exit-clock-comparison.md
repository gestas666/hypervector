# Higher-fee exit-clock comparison

The original higher-fee clock contrasts are complete for both allocations.
Changing from recorded-bar to late-intrabar exit timestamps changes holding
time and average capital exposure, but does not change these cases' trade
prices, fees, funding, net results or maximum marked drawdown. High confidence
applies to the retained historical calculations and their modeled execution
rules. This is not evidence of resilience to adverse live fills or arbitrary
venue latency.

Cases 8/10 retain control allocation; cases 9/11 retain equal allocation.
All four use first-observation core history, full-prefix XYZ history and the
original higher-fee assumptions over July 21–September 7 UTC. Cases 10/11 were
already completed by the original matrix; their account analyses reuse the
unchanged qualified reporter 3400457. No native replay was repeated.

| Metric | Control | Equal allocation |
| --- | ---: | ---: |
| Net result under either exit clock | -$33.44 / -0.69% | +$92.00 / +1.89% |
| Maximum marked drawdown under either clock | $233.56 / 4.67% | $365.68 / 7.05% |
| Average gross notional, recorded clock | $872.60 | $1,765.76 |
| Average gross notional, later clock | $878.99 | $1,778.97 |
| Average gross-notional increase | 0.7325% | 0.7481% |
| Mean holding time, recorded clock | 10.71149 hours | 10.71149 hours |
| Mean holding time, later clock | 10.79181 hours | 10.79181 hours |

Both contrasts retain all 177 ordered trade identities. Fifty-six exits move
899,999 ms later, thirteen move 59,999 ms later and 108 do not move. Only
`valuation_time_ms` and `holding_hours` change, for the same 69 trades in each
allocation. All other per-trade fields match exactly, including entry/exit
prices, quantities, reasons, gross/net PnL, fees and funding. No trade is added
or removed. Account fee, funding and closed/open net totals also match.

An independent calculation reproduces the timestamp histogram, changed-field
counts and 4.81920-minute increase in mean holding time. The largest per-trade
holding-time identity residual is below 4.5e-15 hours. These checks preserve
the exact source differences rather than hiding them behind rounded summaries.

The comparison authenticates 2,321 unique references. Each new analysis checks
2,294 references and each existing baseline checks 2,297, with shared references
deduplicated only after identity agreement. All four fresh independent account
audits match their retained matrix audits and conserve seven equity totals.
The qualified reporting implementation matches before and after both runs.
Driver/comparison lint, annotation and function/file-size checks pass. A six-file
source archive restores identical bytes; its SHA256 is
`242d0e61acef53bdd6834585068d9494b7d24921b2852a3ade187f3623b287e8`.

The new analyses contain 138,241 modeled timestamps each, versus 69,121 in their
recorded-clock counterparts. Both complete successfully at approximately 09:30
UTC after 6.99 minutes measured from their launch-record clocks. Together with
the recorded-clock samples, this remains consistent with the four-to-six-hour
full-report planning allowance; it does not measure that full run in advance.

Retain this result as a timing-convention sensitivity measurement. It provides
no additional financial advantage for either allocation and does not qualify
live fill quality. The higher-fee scenario remains a stress assumption, not proof
of actual historical fee eligibility. The previously observed cost sensitivity,
larger equal-allocation exposure and concentration remain relevant.

Changed source/evidence hashes, mismatched trade fields, nonconserved equity,
or a discrepancy between fresh and retained audits would invalidate the
corresponding acceptance. These four cases do not replace the original 48-case
report, and the historical segments are not newly unseen holdouts. Both prospective
outcome seals remain intact. No live strategy, allocation, leverage, execution,
configuration, deployment or installed TUI changed.

Evidence root: `data/logs/research/bidirectional_cohort/`
`v89_full_fee_exit_clock_comparison_20260910_v1/`. The new full case reports are
in `v89_original_account_case_10_analysis_20260910_v1/` and
`v89_original_account_case_11_analysis_20260910_v1/`. Use `comparison.json`,
`independent_clock_arithmetic.json` and the retained source/provenance files.
