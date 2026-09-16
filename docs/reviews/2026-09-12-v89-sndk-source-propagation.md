# SNDK source differences do not explain the measured entry weakness

The 16 observed native/vendor opening and closing differences do not materially
change the previously measured SNDK entry-quality results. The largest change
in an earlier/later matched-excess gap is **0.00546 bps**. The primary long
one-hour gap remains **−66.24644 bps**, and the day-class sensitivity remains
**−61.23073 bps**. Neither changes beyond floating-point reconciliation noise.

Confidence is **high for this fixed arithmetic sensitivity**: original results
reconcile, independent raw-JSON SQL checks every measurement, and the source
archive reproduces all six outputs byte-for-byte. Confidence in strategy
causality or future profitability remains **low**. A changed source identity,
missing original membership or failed independent reproduction would invalidate
the affected result.

## Fixed measurement and findings

The [protocol](../../data/logs/research/bidirectional_cohort/v89_sndk_source_propagation_20260912_v1/source_archive/docs/plans/2026-09-12-v89-sndk-source-propagation.md)
was committed as `63867100e558019b208aa4fe09fe8c8aa9820db5` before evaluating
propagation. Six inputs were hash-pinned to published source and background
evidence. Source is frozen at `d05c390b0defdb541e2e38aa1fe52649b161ea95` in
`hypervector-v89-sndk-propagation-20260912`.

The comparison retains all 47 entries, four horizons, two matching methods,
both directions, cohort labels, original missing values and control memberships.
It compares the original native measurement with one conditional perturbation:
qualified vendor closes replace August 19 native closes, while other dates
retain their native values. This is not a full vendor-history backtest. Original
modeled entry prices, fees, funding, quantities, exit policies and PnL stay fixed.

| Measurement | Retained rows | Rows changed beyond 10⁻⁸ bps |
|---|---:|---:|
| Calendar price paths | 4,608 | 2 |
| Entry returns in matched comparisons | 376 | 0 |
| Matched-control means / excess returns | 376 | 1 / 1 |
| Modeled-entry target returns, six original cases | 1,128 | 0 |

All 11 opening differences have zero use in these completed-close measurements.
Three of the five closing differences also fall outside the measured endpoints.
The 19:00 and 23:00 candle closes each affect one 15-minute calendar target.
Only the 23:00 target participates in an original matched-control pool. None
of the five differing closes is an entry measurement anchor or modeled-entry
target in the retained roster. This does not establish that opening differences
would be irrelevant to a separate fill repricing or signal resimulation.

The affected comparison is the later short entered at **August 30, 23:00 UTC**,
15-minute horizon, same-hour matching. Its 19-control mean increases by
**0.0327392255 bps**, and its excess decreases by the same amount. The earlier/
later short 15-minute gap moves from **−77.6019934 to −77.6074499 bps**.
All 16 earlier/later excess-gap signs remain unchanged. The maximum calendar
return shift is **1.2772207676 bps**.

See the [complete summary](../../data/logs/research/bidirectional_cohort/v89_sndk_source_propagation_20260912_v1/summary.json),
[all source-cell uses](../../data/logs/research/bidirectional_cohort/v89_sndk_source_propagation_20260912_v1/analysis/difference_uses.json)
and [full comparison report](../../data/logs/research/bidirectional_cohort/v89_sndk_source_propagation_20260912_v1/analysis/report.json).

## Verification and limitations

**52 offline tests pass**, including altered endpoints, direction, missingness,
duplicated identities, changed control memberships and incorrect group/gap
projections. New code has **90% combined statement/branch coverage**; endpoint
arithmetic covers all **29 statements and 10 branches**. CLI/orchestration and
some rejection paths remain outside the unit coverage claim.

Independent SQL reads the original JSON directly and checks all **4,608
calendar rows**, **376 comparisons**, **1,128 modeled-entry rows**, **32 groups**,
**16 decompositions** and **16 differing source cells with their uses**. Baseline
arithmetic and coverage reconcile before perturbation. The [independent receipt](../../data/logs/research/bidirectional_cohort/v89_sndk_source_propagation_20260912_v1/independent_verified_v3.json)
retains the queries. The earlier receipts retain their narrower scopes.
The primary report retains its pre-independent stage marker; the completed
independent receipt establishes the final SQL verification.

The 11-file committed source archive passes the same 52 tests. Its standalone
analysis and SQL verifier reproduce **five analysis files plus the independent
receipt byte-for-byte**; see the [reproduction check](../../data/logs/research/bidirectional_cohort/v89_sndk_source_propagation_20260912_v1/reproduction_verified.json).
The initial missing-module test and seven SQL-fixture parsing failures remain
retained. The fixture alias was corrected; no failed attempt is called successful.

This remains an explored sensitivity over dependent historical observations.
It adds no independent days or prospective evidence and cannot identify the
cause of weak follow-through. Qualified candle agreement does not establish
venue mark-price triggers, liquidity, physical fills or complete-history accuracy.
The 11 unused opening differences were not used to reprice modeled entry fills.

## Decision and next investigation

Accept the bounded sensitivity and **reject these observed source differences
as a material explanation for the existing matched entry-quality finding**.
Do not choose a feed by PnL, fit a live filter or rerun the completed acquisition,
day-influence or historical matrix because of this result.

The single next investigation is **causal entry-time regime/context attribution**
for the original fixed SNDK entries and controls: qualify the retained trend,
volatility and breakout-context fields, then predeclare comparisons before
evaluating their relationship to fixed-horizon excess. Keep August 19 influence
explicit and preserve both directions and cohorts. This can test whether the
remaining weakness clusters in observed conditions; it cannot by itself justify
a fitted rule or causal claim.

No live change is proposed from this result. Both installation questions remain
pending and both prospective outcome seals remain unopened. Installed/candidate
hashes are rechecked by the publication audit. The reused **09:37:22 UTC** account
snapshot is dated evidence, not a new account refresh or current PnL claim.
Broad live readiness remains unproven.
