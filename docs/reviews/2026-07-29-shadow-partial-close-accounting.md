# Shadow Partial-Close Accounting Incident

Date: 2026-07-29

## Problem restatement

Determine whether two shadow trades labeled as isolated liquidations were real
economic losses or simulator defects. Isolated margin, fees, and funding
assigned to an open position must all shrink consistently when a target
partially closes that position; restart must reconstruct the same state; and a
favorable mark must not liquidate a solvent residual position.

No entry rule, regime threshold, target, allocation, leverage, TUI authority,
or ML authority was changed.

## Direct evidence

The authoritative run `51f44ff36f6b` contains three completed lifecycles.
Reconstructed from all fills, fees, and funding, they produced $1,778.61 gross
PnL, $266.72 fees, a $1.40 net funding payment, and $1,513.29 net PnL. Final
durable equity is $11,513.29 from $10,000.

The first lifecycle closed normally at target. The next two were recorded as
liquidations after their maker targets had already closed nearly all quantity.
Both terminal fills were favorable to their entries:

- Short: average entry $63,716; final residual fill $63,577.
- Long: average entry $63,902; average lifecycle exit approximately $64,031.75.

These are simulator labels, not venue liquidations. Three trades are too sparse
to establish durable strategy edge, but the prior `1 target / 2 liquidation`
interpretation is invalid.

## Root cause

`NautilusShadowExecutionPort` reduced isolated margin with current residual
quantity but retained all entry fees, prior target-exit fees, and historical
funding in the residual position's maintenance calculation. After a nearly
complete target fill, those costs could exceed the tiny residual margin and
trigger liquidation even when price moved favorably.

The restart path independently summed all lifecycle fees against any nonzero
residue. A sub-epsilon sign flip at terminal fill could therefore carry the
terminal fee into the next session.

## Correction

- Target and partial-liquidation fills retain only the fraction of entry-fee and
  funding basis attributable to remaining open quantity.
- Exit and liquidation fees remain realized account costs but are not assigned
  to the surviving position.
- Restart reconstructs the same proportional open basis.
- Normalized flat resumes clear open fee/funding basis and liquidation cooldown.
- Liquidation ledger records preserve the pre-execution boundary, trigger mark,
  isolated margin, position equity, and maintenance margin.
- The maker replay separates total lifecycle costs from residual open cost basis.

## Validation

A deterministic 98.75% target-fill regression failed before the correction:
the remaining 0.05 BTC retained all funding and became falsely liquidatable.
After the correction it retains 1.25% of entry costs, keeps its liquidation
boundary adverse to entry, and does not liquidate at the favorable target mark.

Restart reconstruction produces the identical proportional basis. The actual
ledger restores as exactly flat with $0 open fees, $0 open funding, and
$11,513.29 equity.

The corrected seven-block venue replay traversed 40 partial-liquidation events
and reproduced every prior block result and aggregate total to floating-point
precision. The close/reverse rejection therefore remains valid: target-only
retained $22,645.61 of $70,000 aggregate reset capital, versus $13,483.36 for
close/reverse.

Focused validation passed across shadow execution, restart, session parity,
maker replay, authentic mark/funding, and close/reverse paths. The full gate
passed with 1,262 non-network Python tests and 33 Rust TUI integration tests;
task-scoped Ruff checks also passed.

## External venue grounding and uncertainty

Hyperliquid's official documentation says isolated-only margin is
proportionally removed as position size closes, liquidations use mark price,
positions over $100,000 receive a 20% partial-liquidation attempt, the cooldown
is 30 seconds, and book liquidations have no clearance fee. The proportional
correction is consistent with those rules.

The public documentation does not specify enough detail to prove exactly how
ordinary trade fees alter an isolated position's `rawUsd` through every partial
fill. Confidence is high in the internal defect and its correction; confidence
in exact venue fee-to-collateral parity is medium. A bounded live canary that
records `clearinghouseState.position.leverage.rawUsd`, `marginUsed`, position
size, fills, and fees immediately before and after a partial close would falsify
or refine the remaining assumption.

## Operational state and remaining risk

The currently active shadow process started after the accounting correction and
uses it. It predates the later peak-observer integration and should be restarted
only while flat. The durable portfolio should be resumed, not reset. Raw
historical ledger actions remain append-only and still say `liquidation`; the
research view now identifies those two incomplete rows as
`unverified_legacy_liquidations` rather than verified venue liquidations.

Fresh venue-matched shadow trades after restart are the next valid forward
sample. Evidence that a favorable residual still liquidates, restart changes
the liquidation boundary, or venue `rawUsd` does not scale as modeled would
invalidate the implementation and require another accounting revision.
