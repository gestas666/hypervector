# Source-Follow Confirmed-Pivot Stop Plan

**Goal:** Test whether a frozen, causally confirmed 1-minute pivot stop improves
the liquidation tail of the profitable legacy Recipe C source-follow short
candidate without adding an entry gate or changing runtime behavior.

## Known evidence

- The frozen legacy source-follow candidate produced 30 development fills,
  29 targets, one liquidation, $25,219.35 final equity, and -46.95% maximum
  drawdown under public trade-through execution.
- The first later event filled and reached its target. That is supportive but
  too sparse to estimate stop behavior.
- Fixed 6/10/14/18% margin stops all lost to the no-stop control.
- A structural wick or pivot stop has not been tested on this leader.
- Runtime remains paper/shadow, ML remains observe-only, and the TUI has no
  execution authority.

## Frozen hypothesis

For each source-follow signal, use the latest strict 1-minute swing high that
was confirmed by two completed bars on each side. Publish the short stop only
after the two right-side bars have completed, then freeze that value at entry.
If the stop is absent, below entry, or at/above the modeled isolated
liquidation boundary, run that lifecycle without a discretionary stop. A
trigger exits at adverse BBO with the configured taker fee.

The first screen uses zero buffer. Buffer tuning, trailing, and different pivot
widths are separate hypotheses and are not part of this test.

## Success and rejection criteria

The fixed-lifecycle screen must report targets stopped, liquidations avoided,
effective/missing stops, fee-adjusted PnL delta, and every affected lifecycle.
It qualifies for stateful replay only if development counterfactual net PnL is
higher than the frozen control and the fresh target is not stopped. Otherwise
the candidate is rejected without a stateful replay.

If qualified, replay the same entry decisions with stop prices through touch,
one-tick book-through, and public trade-through evidence. Promotion would
require higher geometric final equity and non-worse liquidation count under
all three fill assumptions, with no unacceptable stop/re-entry churn. This
experiment itself cannot promote runtime behavior.

## Implementation sequence

1. Add failing tests for a report-only command that accepts the frozen source
   artifact, uninterrupted Hyperliquid 1-minute candles, and an immutable
   output path.
2. Reuse the existing causal `2-left/2-right` confirmed-pivot implementation;
   do not duplicate pivot logic.
3. Validate the input artifact contract and extract development/fresh
   lifecycles without success-shaped fallbacks.
4. Run the fixed-lifecycle screen and evaluate the predeclared qualification
   criteria.
5. Run a stateful maker replay only if the screen qualifies.
6. Record hashes, limitations, runtime non-promotion, and fresh shadow safety;
   run focused tests, Ruff, the non-network Python suite, and Rust TUI tests.

## Risks and falsifiers

The main failure mode is stop regret: normal BTC wicks may hit the pivot before
the original 20-bps target. A favorable additive screen can also fail after
stateful re-entry changes the portfolio path. Any look-ahead in pivot
publication, disagreement across fill assumptions, worse geometric equity, or
stopping the only fresh target falsifies the candidate.

Confidence is medium that the test is mechanically valid because the pivot and
stateful stop engine already have unit coverage. Confidence is low that the
stop will improve the leader until the screen and, if qualified, stateful
replay complete.
