# Qualify routing over complete historical fresh-intent sets

The original scope remains every minute in `(July 21, September 7] UTC`, both
core source revisions and both retained XYZ history conventions. This is a
research compatibility study, not a new allocation trial or a live change.
Existing full provider comparisons continue from their frozen archives.

## Evidence and assumptions

The revision-19 authenticated snapshot permits a complete first-core/full-prefix
XYZ intersection through August 11: 30,240 minute sets, 127,008 scheduled provider
rows and 139 entry intents. Nine minutes have two different assets' intents; no
same-symbol duplicate occurs. Those comparison payloads contain provider evidence,
not independent canonical telemetry. This finding is high confidence within that
snapshot and must not be extrapolated to unfinished streams.

Reuse `collect_bound_provider` for source-bound canonical evidence: it already
calls the native canonical collector on supported one-minute sources and records
XYZ's unavailable native-minute source explicitly. Do not add a second canonical
binder, invent minute candles from quarter bars or relabel provider diagnostics
as independent canonical telemetry. The original native-history sources contain
gaps; they must not be silently replaced with the later complete warmup sources.

The existing `project_routing_cycle` is an offline projection for fresh supplied
intents. It does not assemble configured exits or apply account events. Its
controlled checks are insufficient evidence for complete historical routing.

## Implementation and measurable acceptance

1. Add a typed reader for immutable completed comparison snapshots. Authenticate
   the snapshot and each consumed summary/payload against their declared hashes
   and sizes. Decode intents losslessly, preserve the actual decision clock and
   fail on malformed identities, duplicate rows, omitted scheduled decisions or
   substituted source variants. Every core minute and scheduled XYZ quarter must
   be represented, including empty batches; non-due XYZ minutes are explicit.
2. Derive the common completed interval for a requested core/XYZ variant pair.
   Report partial completion explicitly. A shorter prefix can qualify only that
   prefix; the final requirement remains all 48 days and all four variant pairs.
   Preserve the exact inputs so later completion expands coverage without
   reopening already tested hypotheses or rerunning signal models unnecessarily.
3. Compare native publication ordering and pure native routing with the research
   projection on complete sets. Retain action identity, side, quote, anchors,
   ordering and withholding reasons. Exercise configured admissible position
   states and independently verify simultaneous-asset admission order. Label
   counterfactual position contexts clearly; do not infer actual historical
   positions or new account returns from those routing comparisons.
4. Supply independently reconstructed canonical evidence where native source
   cadence permits it. Demonstrate any economic invariance claim under its exact
   one-intent-per-asset and capacity assumptions, including counterexamples when
   those assumptions are relaxed. A limited invariance result does not supply
   missing telemetry or qualify HYPE's future holding rule.
5. Integrate configured exits and dynamic account state only after their clocks,
   same-decision occupancy, audit retention and original frozen holding semantics
   reconcile. Keep the generic account primitives unchanged unless a separately
   reproduced defect justifies a correction. Preserve all fixed cost/source axes.
6. Freeze implementation, verify focused fault and integration tests, reproduce
   results from an authenticated archive and journal the exact remaining scope.
   No prospective signal, position, trade or return reconstruction is permitted
   before the existing outcome seals open.

## Failure modes and alternatives

Wrong source/decision identity, silent omissions, noncausal canonical selection,
lost intent fields, unstable global ordering or a same-decision replacement would
invalidate the corresponding compatibility claim. Missing source cadence remains
missing; a zero-mismatch prefix does not establish agreement outside its bounds.

Recomputing all original signal models in a second implementation would add cost
and drift risk; reuse the authenticated full comparison outputs. Substituting
fixed completed lifecycles would avoid dynamic routing and therefore cannot
qualify the intended evaluator. Reuse the native pure helpers with independent
contract checks, then test their integration with source and account phases.

This plan requires no live approval because it authorizes only already permitted
research work. It proposes no change to strategy, route, sizing, leverage, risk,
execution, deployment or TUI behavior. The profitability mandate remains unmet
until supported by appropriate economic evidence and an approval-ready proposal.
