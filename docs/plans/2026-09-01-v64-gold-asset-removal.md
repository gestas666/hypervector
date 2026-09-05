# V64 GOLD Asset Removal Implementation Plan

> Status: implementation authorized by the operator's instruction to remove GOLD after unresolved growth-mode fee evidence. This plan does not authorize live order execution.

## Problem restatement

V63 adds `xyz:GOLD`, but the 2026-09-01 flat preflight cannot establish an
effective GOLD fee for growth-mode sizing. The successor must remove GOLD from
both the asset roster and every executable provider scope while preserving the
remaining V63 contracts.

Success criteria:

- V63 remains byte-for-byte unchanged and usable as the rollback source.
- V64 contains eight assets and no `xyz:GOLD` provider or execution scope.
- The remaining asset, provider, sizing, risk, and exit contracts match V63.
- The approval validator distinguishes terminal removal of an absent asset from
  unsupported retirement of a route for an asset that remains in the roster.
- Approval and recommendation artifacts bind exact profile fingerprints and
  file hashes while granting no execution authority.
- A fresh report-only preflight observes the removed asset as flat with no open
  orders and reports the retained portfolio technically ready.
- The TUI labels the staged successor as V64, renders the eight-asset/23-side
  scope, and preserves GOLD's retired flat/order-free evidence on Screen 9.

## Assumptions and falsifiers

- Assumption: GOLD is the only technical preflight blocker. Falsifier: a fresh
  V64 preflight reports any retained asset, ledger, order, sizing, fee, or
  observer blocker.
- Assumption: removal is terminal at the asset level, not replacement of a GOLD
  strategy. Falsifier: GOLD remains in the candidate asset roster or gains a
  newly executable replacement scope.
- Assumption: the operator instruction approves the exact removal transition,
  not starting live execution. Falsifier: no fingerprint-bound approval can be
  produced from the exact candidate or a later candidate differs from it.

## Implementation

1. Add approval-unit coverage for explicit `replacement_scope: null` only when
   every retired scope belongs to a symbol absent from the candidate roster.
2. Add a V64 configuration contract test that initially fails because the
   successor does not yet exist.
3. Create the eight-asset V64 profile by changing only profile/approval metadata,
   deleting the GOLD asset, and removing GOLD from the shared HIP-3 provider.
4. Generate immutable recommendation evidence from the unresolved V63 preflight,
   then bind V63 rollback and V64 candidate identities in the transition approval.
5. Run focused unit/config tests, temporarily start required read-only observers,
   and produce a fresh flat-state V64 preflight.
6. Stop temporary observers, confirm no live backend is running, and run the
   proportional non-network regression suite plus repository hygiene checks.
7. Extend the Rust growth-preflight projection and staged runtime QA so all nine
   TUI screens retain valid data while Screen 9 exposes the exact GOLD removal.

## Failure modes and rollback

- Approval schema drift: fail closed before live-client construction.
- GOLD venue exposure or owned orders: block transition until reconciled flat.
- Retained-route freshness or fee failure: report the blocker; do not arm live.
- Candidate drift: fingerprint/hash mismatch invalidates the approval.
- Rollback target: the immutable V63 config and its verified fingerprint/hash.

## Validation matrix

| Component | Evidence | Pass condition |
|---|---|---|
| Terminal asset retirement | Unit tests | Null replacement accepted only for absent candidate symbol |
| Candidate scope | V64 config tests | 8 assets, 23 directions, no GOLD references in runtime scope |
| Governance | Approval validation | Exact hashes/fingerprints, execution authority `none` |
| Venue/ledger | Report-only preflight | GOLD retired state flat/order-free; retained portfolio ready |
| TUI | Rust parser/render/runtime QA | V64 identity, 8 assets, 23 sides, retired GOLD visible |
| Regression | Non-network tests | No failures attributable to the transition |
| Safety boundary | Process/status checks | No live backend, no temporary observer left running |
