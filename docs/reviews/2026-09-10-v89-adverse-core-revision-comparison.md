# Adverse-cost core revision comparison

The original first/latest core-observation contrasts produce identical reported
economic results in the complete-account engine for both allocations. High
confidence applies to the retained historical calculations: all reported equity
paths, trades, contribution groups, concentration measures and proposal-disposition
tables match exactly. This does not establish broader historical data quality,
real fill behavior or future profitability.

Cases 4/28 compare first versus latest core observations under control allocation;
cases 5/29 do the same under equal allocation. Both contrasts keep full-prefix
XYZ history, the original adverse-cost assumptions, recorded-bar exit clock and
the July 21–September 7 calendar. Nineteen non-source manifest fields match.
All seven route execution policies, venue units, funding bindings and row counts
match. Core price/canonical source references and revision labels change as
declared. XYZ retains the same physical price/canonical bindings; its inherited
revision label changes without selecting different XYZ prices.

| Either core revision, adverse-cost case | Control | Equal allocation |
| --- | ---: | ---: |
| Net equity change | +$95.72 / +1.97% | +$368.92 / +7.59% |
| Maximum marked drawdown | $198.28 / 3.90% | $287.72 / 5.50% |
| Closed trades | 177 | 177 |
| Trades added or removed by revision choice | 0 | 0 |
| Changed per-trade fields | 0 | 0 |
| Net equity, fee or funding difference | $0 | $0 |

All 177 ordered trade identities match within each contrast, including entry and
exit timestamps/prices, quantities, holding times, reasons, fees, funding and
gross/net PnL. The complete `path`, `trades`, `groups`, `concentration` and
`entry_fates` sections also match as canonical serialized bytes. Separate
section hashes reproduce this equality; it is not inferred from rounded totals.
This comparison does not assert that every empty per-minute provider evaluation
or raw candle field is identical.

The comparison authenticates 2,516 unique references. Each existing baseline
checks 2,297 references; each new analysis checks 2,294. All four fresh independent
account audits match their retained matrix audits and conserve seven equity
totals. The reporter remains qualified source 3400457, with implementation
identities checked before and after both new analyses. The new case analyses
finish at 09:50:56/09:50:58 UTC in approximately 4.44/4.48 record-clock minutes.

The analysis driver reuses the prior qualified reporting invocation with only
the explicit allowed case indices changed. The comparison preserves prior
authentication and conservation arithmetic while changing the fixed comparison
axis/cost and retaining complete economic-section equality checks. Source changes
are retained in `compare_changes.patch`. Lint, annotations and function/file-size
checks pass. The eight-file source archive restores exact bytes; SHA256 is
`8429bb39b266cd64bf0b99bbfda4c1eee33bd097a204898f4b09b49b200ecb9b`.

The September 7 source study already found identical first/latest lifecycle
results under the older replay. This extends that finding to the current complete
account engine and equal-allocation counterpart; it does not reopen the older
experiment or claim the prior evidence was missing. Core-source membership and
the historical hybrid/gap-price assumptions retain their separate qualifications.

Retain the first/latest invariance for these original cases. It provides no
additional financial advantage and does not resolve the existing cost sensitivity,
later-period losses or concentration. In particular, the separate higher-fee
stress remains a different cost assumption with its previously reported results.
Neither source revision is selected because of PnL.

Changed evidence hashes, a different fixed-axis scope, nonconserved attribution,
changed economic-section bytes or disagreement between fresh and retained audits
would invalidate the corresponding finding. These four historical cases do not
replace the full 48-case comparison or establish new out-of-sample evidence.
Both prospective seals remain intact. No live strategy, universe, allocation,
leverage, execution, deployment configuration or installed TUI changed.

Evidence root: `data/logs/research/bidirectional_cohort/`
`v89_adverse_core_revision_comparison_20260910_v1/`, with the full new analyses
in `v89_original_account_case_28_analysis_20260910_v1/` and
`v89_original_account_case_29_analysis_20260910_v1/`. Use `comparison.json`,
`source_scope_check.json`, `route_scope_check.json` and
`independent_section_equality.json` alongside the pinned reporting source.
