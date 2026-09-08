# Incremental shared-account arithmetic

Research source `a7d8e93a0ca3853e2dc9efd8a48203bddf9d6ea0` qualifies an
incremental account component for explicitly supplied modeled events. High
confidence within the tested scope: 186 offline tests passed from the worktree
and its exact archive, with independent Decimal reconciliation. The complete
prospective replay remains **unqualified**, and future profitability remains
unmeasured. No new-study strategy outcome was computed or inspected.

## Verified behavior

The account starts flat with its caller's declared calendar, capital and maximum
position count. Every batch has an explicit timestamp, marks, observed funding
rates and price proxies, exits and already-routed entry opportunities. It has no
venue clients, signing authority, signal selection or price acquisition.

Each accepted entry sizes from its own account's marked equity using the existing
`CohortEntrySizing` policy. Quantity rounding precedes notional, margin and fee
calculation. Decimal budget/price division feeds the existing round-down helper;
an explicit overshoot correction prevents a floating quotient from rounding
above the budget. Fixtures cover both $0.29/$0.01 = 29 units and a budget just
below the 101-unit boundary that must produce 100 units.

Cash and margin remain separate. Entry fees reduce cash; initial margin is
reserved rather than deducted as a second expense. Available cash is cash less
reserved initial margin. Unrealized P&L affects sizing equity without becoming a
cash deposit. Existing positions close before new entries; explicit priority and
identity ordering determines competition for shared cash. Occupied symbols,
configured slots, insufficient cash and zero rounded quantities remain recorded
entry dispositions.

Funding uses the supplied native timestamp, signed rounded exposure and declared
price proxy. The ordering implements entry < settlement <= exit: an observation
at entry does not charge the new position, while one at exit charges the existing
position before closure. Measured zero or flat-account observations remain
records; absent observations are not synthesized as zero funding. Source grid
completeness still requires separate upstream validation.

Every snapshot reconciles cash to initial capital plus closed gross P&L, less
entry and exit fees, plus funding. Marked equity adds unrealized P&L; exposures
and reserved margin are reported separately. All closes preserve their supplied
ordinary or special exit fee and execution price. The account does not silently
clip a negative-equity result or abort a trial because of loss. Nonpositive
sizing equity produces an explicit disposition and the calendar continues.

The exclusive terminal boundary permits marks only. It requires a mark for each
open symbol, preserves the positions and charges no invented closing fee. Bad
identities, future decisions, missing entry/terminal marks, duplicate events and
backward clocks fail explicitly. A failure after funding, closure and an earlier
entry in the same batch leaves the prior published account unchanged; corrected
input can reuse the rejected batch's timestamp and identities.

## Evidence and independent checks

There are 62 direct account/contract/fault tests and 29 independent-oracle tests,
plus related replay, sizing, rounding and historical marking regressions. The
three account modules cover 353/353 statements and 82/82 branches. The independent
stdlib auditor covers 197/197 statements and 76/76 branches, including its actual
CLI invocation. Coverage is evidence about exercised code, not a guarantee of
unobserved behavior.

The independent implementation recomputes cash from exact Decimal debit/credit
postings, instead of importing the account code or trusting its accumulated
balances. Ten exported synthetic cases include mixed sides, cash competition,
instant exits, zero trades, insolvency, precision boundaries, position limits
and a 120-trade sequence. The complete bundle contains 124 closes and 259 path
snapshots. Every nested output was compared, including 8,951 numeric fields;
quantities matched exactly and the maximum monetary difference was `5E-13` USD
against a declared `1E-8` USD arithmetic tolerance. Tampering with cash, quantity,
closed gross P&L, funding, row/field counts, booleans and clock types was rejected.

The archived fourteen-day zero-trade check processed 20,161 batches and 20,162
snapshots with unchanged equity. This is an account-only calendar-scale check;
it does not measure provider, source-assembly or loaded-position throughput.

All 5,205 Git blobs in the source archive were verified. Archive SHA-256:
`a265ee806e08bd413d0cf54254497e1c992f11d1f9b85ca3f94b2dd537ce79ed`.
The archived 186-test suite passed. Its 657,103-byte synthetic result bundle and
independent audit report reproduced the original bytes exactly. Evidence lives
under `data/logs/research/bidirectional_cohort/v89_incremental_account_qualification_20260908_v1/`.
The journal amendment is
`docs/research-journal/v89-equal-cap-prospective-20260909-v4.json`.

## Limits and next investigation

| Requirement | Current evidence | Remaining qualification |
|---|---|---|
| Dynamic equity, rounded quantities, cash and reservations | Synthetic and independent account parity | Bind exact frozen profiles and available venue metadata |
| Fees and funding cashflows | Explicit event arithmetic and native-time boundary tests | Full route-cost adapter and complete observed funding grids |
| Stops, targets and liquidation | Supplied exit prices/fees accounted for | Original barrier triggers and conservative intrabar ordering |
| Entry eligibility and marks | Future decisions rejected; explicit current entry marks required | Provider/regime parity, first/latest sources, receipt deadlines and modeled fill clocks |
| Terminal open exposure | Marked without an invented close | Real source-terminal coverage and full-study reconciliation |
| Historical compatibility | Existing marking regressions still pass | Reproduce registered controls using original supplied quantities and clocks |

The next investigation is an explicit legacy-input adapter and complete old-control
path reproduction. It must retain the original unrounded quantities, original
entry/exit clocks and funding schedules. That separate mode must not silently
replace prospective dynamic sizing or assert that rounded future results should
byte-match unrounded old controls. Then integrate and qualify provider, clock and
source assembly before any evaluation of the sealed interval.

Using the existing completed-lifecycle simulator unchanged remains insufficient
for dynamic acceptance and terminal opens. Treating this component as the full
replay would also be unsupported. No new allocation, strategy, route, risk gate,
TUI deployment or real-money process change is included. At the recorded 21:22
UTC check, both public collectors were live, all fifteen pinned collector files
matched, and the active profile SHA remained `696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.

An independent arithmetic mismatch, changed source identity, unregistered cost or
clock interpretation, missing source coverage or failed provider/control parity
would invalidate the affected replay claim. Both fixed prospective outcome seals
remain closed; accounting qualification supplies no evidence of future return.
