# Native entry routing at the actual account boundary

A synthetic integration diagnostic reproduces a slot-ordering difference between
native routing and the existing chronological account admission path. Confidence
is high in the observed diagnostic and low in any historical or live implication.
The current seven-slot configuration is unchanged.

At the second minute, BTC and ETH occupy a two-slot synthetic account. ETH has a
recipe close and SOL has a fresh short intent. Native routing withholds SOL with
`portfolio_position_capacity`; its routing cycle does not free ETH's slot first.
The original account path accepts SOL after its current-cycle exits. This produces
three closed synthetic positions in the original path versus two when native entry
selection is applied. It is a controlled integration counterexample, not evidence
of a defect in the current seven-slot live configuration or a profitable filter.

The same instrumented native entry selection leaves complete retained account
values identical in all 24 seven-slot source/cost/clock/allocation comparisons.
The two-slot difference reproduces in all 24 matching controls. Each of the 96
runs covers every native source bar and funding observation in one artificial
hour, with 60 decision-boundary cycles. Sources are programmed 2030 fixtures.
The replay contract spans two days, so terminal evaluator acceptance is not claimed.

All 96 artifacts reproduce byte-for-byte from frozen source `9e3ecac`. Independent
Decimal checks cover accepted sizing/rounding, notional, margin, entry/exit fees,
signed funding, trade net and final observed cash. The verifier also checks the
actual decision-position set, native ETH recipe exclusion, SOL withholding reason
and the original modeled ETH close timestamp.

The prototype retains full native controller decision payloads and uses actual
simulated position quantities and entry times. Its first attempt incorrectly fed
resolved static targets into native dynamic target binding; native validation
rejected that input before publishing a case. The corrected probe binds original
source intent anchors and verifies that they reproduce the accepted barriers.
This was a probe assembly error, not a demonstrated live defect.

Native configured closes remain observations; the account still uses its original
frozen exit semantics. The diagnostic qualifies neither full native transport,
HYPE soft/hard holding intervals, future UNKNOWN handling, full terminal coverage
nor historical profits. The instrumentation is process-local and not a production
integration. No prospective outcomes, live account outcomes, strategy, configuration
or process lifecycle were changed or evaluated.

Next, execute the [typed account integration plan](../plans/2026-09-09-v89-native-account-routing-integration.md).
Changed source/anchor identities, nonmatching archive bytes, wrong clock/occupancy,
failed Decimal reconciliation or contrary independent replay would falsify the
corresponding diagnostic. Full historical and untouched forward evidence are still
needed to assess performance.

Evidence: `data/logs/research/bidirectional_cohort/v89_routed_account_integration_20260909_v1/`.
