# Incremental allocation account qualification

Continue the frozen prospective replay plan with an account component driven by
explicit modeled events. This is research implementation, with no live or
collector changes and no prospective outcome access. The component does not
select signals, prices, stops, metadata, source revisions or receipt clocks.
Those adapters still require separate qualification before the full evaluator.

## Inspected reuse

`CohortEntrySizing.planned_notional` defines the configured fractional-equity/
notional-cap calculation. `quantize_size_down` provides decimal round-down.
The existing concurrent marked portfolio defines cash as initial capital plus
realized cashflows, reserved margin separately, and available cash as cash less
reserved initial margin. Its settlement contract is entry < funding <= exit.
Apex and evidence-selected shared portfolios also require completed outcomes;
their implicit outcome scaling cannot express this study's dynamic/open account.

High confidence in these inspected definitions; a counterexample in an existing
qualified control or an unresolved source/model interpretation would update the
integration plan. No new margin-fraction ceiling, drawdown gate or performance
filter is introduced.

## Component behavior to verify

- A batch carries one timestamp and explicit marks, observed funding rates and
  price proxies, exits, entry opportunities, and declared same-time entry exits.
  Prices already include the caller's selected cost contract. The account must
  not replace full route-specific fees or invent slippage itself.
- Apply observed funding to pre-existing positions, update current marks, close
  existing positions, process entries in explicit provider-priority/identity
  order, then process declared immediate exits of accepted new positions.
  This preserves entry < funding <= exit and retains every entry disposition.
- Each entry sizes from that account's current marked equity; round quantity
  down before calculating notional, initial margin and fees. An entry needs an
  explicit contemporaneous mark. Available cash is cash less reserved initial
  margin; unrealized gains affect sizing equity but are not cash deposits.
- Position slots and one position per symbol are explicit account constraints.
  Insufficient cash, a zero rounded quantity, occupied symbols, configured slot
  limits or nonpositive sizing equity are recorded dispositions. Technical input
  faults fail explicitly without partially changing the prior account state.
- Fees are deducted when incurred. Funding uses the supplied native event time,
  signed rounded quantity and explicit price proxy. No observation is inferred
  from the absence of a funding row; source coverage must be proven upstream.
- Snapshot cash reconciles to initial plus closed gross PnL minus entry/exit fees
  plus funding. Equity adds open unrealized PnL; reserved margin and exposures
  reconcile separately. Retain pre-action and post-action snapshots so old
  control ordering can be compared without inventing hidden execution times.
- The exclusive terminal boundary permits marks only, requires an explicit mark
  for every open symbol, preserves open positions and charges no invented exit
  fee. Repeated/backward times and duplicate/conflicting identities fail.

## Validation

Start with hand-calculated fixtures for evolving marked equity, round-down,
fee/reservation cash conservation, mixed long/short funding, same-time entry and
exit settlement boundaries, cash competition, reversal after close, zero trades,
terminal opens and missing terminal marks. Test invariance to harmless input
ordering and atomic rejection of malformed batches. Preserve insolvency/loss
results without silent clipping or a sign-based abort.

Then use an independent Decimal ledger over the exported fixture event stream,
compare every snapshot and per-position cashflow, and test shifted calendars.
Require meaningful fault coverage, source archive replay and immutable evidence.
Only after this component qualifies, integrate provider/clock/source adapters
and reproduce previously registered controls with their original supplied
quantities before claiming the full replay is qualified.

The trade-off is additional account code versus forcing terminal-open/dynamic
semantics into fixed completed lifecycles. Reuse the pricing/sizing primitives;
keep historical and running collector implementations unchanged. Good enough for
this step means independently reconciled event arithmetic, not profitability or
full prospective evaluation readiness.
