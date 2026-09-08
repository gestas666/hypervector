# Qualify the frozen prospective allocation replay

The economic study is `v89_equal_cap_prospective_20260909_v1`, September 9
00:00–September 23 00:00 UTC, with the exact protocol/config/cost artifacts in
`docs/proposals/v89-equal-cap-20260908/`. The source collector is a separate
running process whose fifteen manifest-pinned implementation files must remain
unchanged. This plan authorizes only already-approved research implementation
and historical/synthetic qualification. It changes no live execution.

## Inspected reuse and gaps

High confidence in these code-level findings; runtime counterexamples or a
previously overlooked reusable interface would update the implementation plan.

- `scripts/v89_equal_cap_replay.py` reconstructs registered fixed lifecycles and
  rescales their quantities. Its capacity check establishes compatibility only
  for those inspected historical paths; it is not a dynamic future allocator.
- `scripts/v89_shared_marked_portfolio.py` fixes START/END/INITIAL, supplies
  complete `MarkedLifecycle` records and reconciles final cash to closed-trade
  net sums. Its funding helper uses hourly source timestamps and opening prices.
- `scripts/v89_shared_portfolio_attribution.py` imports fixed calendar boundaries;
  `scripts/v89_equal_cap_statistics.py` fixes the old August 18 partition and
  checks proportional daily changes. Those old dates/identities must not leak
  into the new fourteen-day account comparison.
- `src/hypervector/research/concurrent_mtm_portfolio.py` contains reusable marked
  accounting references but its lifecycle contract requires an exit timestamp,
  exit price and completed net cashflow. Future terminal open positions need a
  separate explicit representation.
- `src/hypervector/research/shared_bar_portfolio.py` is a one-position, one-asset
  simulator and forces an end close. Its existing pricing, barrier, funding and
  signal-ordering primitives are useful references; calling its current complete
  evaluator does not satisfy the new shared-account/terminal-open contract.

These are limits on direct reuse, not evidence that the previously reconciled
historical results are arithmetically wrong. Do not reinterpret old explored
outcomes as new independent evidence.

## Implementation and acceptance sequence

1. Authenticate the prospective registration, frozen protocol, inactive configs,
   costs, historical warmup and captured sources before evaluation. Introduce an
   explicit window/initial-capital contract rather than changing module globals.
   Test UTC day boundaries, the exclusive terminal boundary, fourteen daily rows,
   first-seven/last-seven partition, missing grids and wrong source fingerprints.
   Evaluation before the prospective seal opens must fail before strategy or
   account simulation. Historical qualification reads only pinned sources ending
   September 7; synthetic shifted calendars are permitted.
2. Inventory each configured provider/side, signal recipe and complete exit/cost
   contract. Reuse the current provider logic and existing strategy primitives;
   no new route, filter, stop, target, selection or allocation tuning. Canonical
   5m/1m/15m regime remains conflict preference and preserves unknown-regime and
   lone-eligible-intent behavior. Test parity against pinned historical controls
   and controlled conflicts before evaluating any new prospective interval.
3. Assemble separate first/latest source variants, with explicit event, native
   availability and first/last receipt clocks. Preserve the distinction between
   a modeled candle execution price/clock and an achievable receipt-time fill.
   Audit how first-receipt eligibility and configured entry deadlines map onto
   the frozen recorded-bar model before qualification; do not silently substitute
   another clock or charge funding before the model's stated position entry.
   Funding retains native settlement offsets; missing observations never become
   zero funding. Metadata size/leverage observations need an explicit as-of join.
4. Implement incremental shared accounting with typed events/open positions and
   existing sizing/precision/barrier primitives where their semantics match.
   Each allocation uses its own marked equity, rounded quantity, entry fees,
   available cash and reserved initial margin. Record every accepted/rejected
   opportunity and its technical/cash reason. Report configured cash constraints
   rather than adding implicit performance or drawdown gates. Preserve all
   frozen ordinary/special-exit/liquidation costs and conservative intrabar
   ordering; do not transfer the retrospective single-event sampled stop.
5. Keep terminal positions open and mark them at the exclusive end. Separately
   reconcile realized/unrealized cash, fees, funding, reserves and exposures.
   Validate hand-calculated cases for simultaneous entries, changing equity,
   cap/fraction transitions, round-down, insufficient cash, opposite sides,
   funding at entry/exit boundaries, same-bar barriers, liquidation, zero trades,
   missing terminal marks and an open terminal position. Assert invariance under
   harmless input ordering and reject duplicate/conflicting event identities.
6. Require exact old-control reproduction in an explicit legacy-input mode using
   the original supplied quantities/clocks. Then qualify prospective rounding,
   native settlement timing and dynamic sizing with separate independently
   calculated fixtures; do not claim rounded results must byte-match unrounded
   old controls. Compare complete paths/daily totals, not just terminal net.
   Run date-shifted synthetic controls to expose hidden date constants.
7. Freeze the qualified source and all 24 declared cells / 12 paired comparisons
   before any new-study outcome computation. Reconcile independent accounting
   and archive replay, then journal source hashes, commands, coverage and limits.
   After September 23 00:00 UTC, compute and publish the complete fixed result,
   including unfavorable, missing, unresolved or zero-trade cases. No automatic
   promotion and no calendar extension.

## Alternatives and limits

| Approach | Benefit | Limitation / decision |
|---|---|---|
| Reuse the fixed-lifecycle comparison unchanged | Exact known historical replay | Cannot express the new dynamic/open-position contract; reject as full evaluator |
| Change shared historical modules in place | Less adapter code | Risks changing pinned controls/running dependencies; preserve them |
| Add a small incremental account layer around verified primitives | Explicit future equity, source clocks and open positions | More accounting to qualify; preferred subject to parity and fault tests |
| Defer outcomes until the fixed end while building qualification now | Preserves the preregistered experiment | Economic evidence remains unavailable until the seal opens; required |

Good enough means every frozen economic requirement has observable, independently
reconciled behavior and the old controls retain their qualified semantics.
Passing a window wrapper alone is insufficient. Any unresolved timing, provider,
funding, sizing or terminal-state mismatch remains a documented qualification
failure. No human clarification is currently required for the independent
inspection/qualification work; any material interpretation that changes the
frozen economics must be surfaced before use.
