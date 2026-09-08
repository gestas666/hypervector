# Frozen allocation replay inputs and entry-clock boundaries

Research source `66a07abf9e3f6663326cbba3bac679b98d99d84b` now authenticates the
September 9–23 study's economic inputs. High confidence in this bounded result:
145 offline checks passed from the worktree and again from its exact source
archive. Full replay qualification remains **open**; no new-study signals,
positions, trades, returns or equity curves were computed or inspected.

## What is qualified

- The immutable preregistration SHA-256 is the trust anchor for all six economic
  files. Both byte count and digest must match before parsing. The date contract,
  primary comparison, cell counts and research authority are checked separately.
- Both complete profiles load in observe mode with disabled execution flags,
  retain their registered fingerprints and share the exact seven-route scope.
  Authenticated profile bytes are parsed from private temporary copies so a
  later original-path change cannot alter what the loader consumes. Consumers
  must use the returned bindings; their source paths identify provenance and
  are not permission to reread an unchecked replacement.
- All 21 original route/cost payloads are preserved in full, including special
  exits and liquidation parameters. The three historical source files remain
  hash-bound provenance. Missing, duplicate or substituted route costs fail
  explicitly. These are model assumptions, not observed future fees or fills.
- The 24 cells use first receipts/latest revisions, nominal/adverse/
  `hip3_full_fee`, recorded-bar/`late_intrabar_exit`, and control/equal allocation.
  First receipts/adverse/recorded-bar remains the two-allocation primary pair.
- A tested evaluation-input entry point checks the September 23 00:00 UTC seal
  before any file read. This is a component contract; the future market loader
  and full evaluator still need to be wired through it. It is not evidence of a
  system-wide outcome-access barrier.

Thirty input-authentication tests cover hash/length changes, missing files,
parser fingerprint drift, live flags, changed route scope, incomplete costs,
source substitution and the authenticated-byte reread race. The new module has
138/138 statements and 30/30 branches covered. The calendar component retains
57/57 statements and 22/22 branches. These coverage claims do not describe the
whole existing poller, provider or portfolio engine.

## Clock evidence and its limits

Twenty-four synthetic checks use the actual frozen provider configs, existing
causal batch validator/entry-age filter, and public candle normalization. The
source candle's inclusive close converts to the provider's close-known decision
boundary. A decision in the future fails causal validation before age filtering.
Entry limits include the exact boundary and reject one millisecond beyond it:

| Routes | Configured maximum entry age | A first receipt 45 seconds after decision |
|---|---:|---|
| BTC | 30 seconds | Timely source; stale entry |
| ETH, SOL, HYPE | 60 seconds | Timely source; age-eligible entry |
| SPCX, SNDK, Brent | 30 seconds | Timely source; stale entry |

The collector's 60-second receipt threshold measures source timeliness. It does
not supersede the route deadline or prove a fill. Source inspection confirms
that the existing poller passes its pre-fetch `observed_ms` to the age filter;
a controlled 20-second poll start / 40-second receipt yields different
eligibility on a 30-second route. This is consistent with the previously pending
entry-dispatch deadline proposal, not a new deployment or an inferred cause of
recent losses. No poller or real-money behavior changed here.

The full replay must still define and test how retained receipt times, decision
eligibility, modeled bar entries, native funding offsets, metadata as-of joins
and latest-revision sensitivity interact. These tests do not justify backdating
a receipt-time fill, charging funding before modeled entry, or treating a late
revision as a contemporaneous observation.

## Independent and archive verification

The standard-library profile auditor again verified the complete allowed raw
TOML semantics and allocation arithmetic. A separate binding audit, importing no
Hypervector implementation, authenticated ten consumed artifacts and matched
all 21 complete cost payloads, 24 cells, primary pair and stored fingerprints.

The source archive contains 5,195 verified Git blobs. SHA-256:
`bcc1c910aa8ffc94f373ab47661d565db1939e9228b437443eeb1fb5c433bd8f`.
The archived suite passed 145 tests, and its full exported binding semantics
matched the worktree result. The archive and qualification scripts are retained;
only the verified expanded copy is eligible for cleanup.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_equal_cap_replay_inputs_20260908_v1/`.
The immutable research journal amendment is
`docs/research-journal/v89-equal-cap-prospective-20260909-v3.json`.

## Remaining work and decision

| Next option | Benefit | Limitation / decision |
|---|---|---|
| Treat input authentication as full qualification | No further implementation | Cannot establish dynamic equity, funding or terminal accounting; reject |
| Reuse fixed historical lifecycles for all future comparisons | Preserves a known control | Cannot represent dynamic acceptance or terminal open positions; legacy control only |
| Build the incremental shared account with explicit clock events | Tests the frozen future-account contract | Additional accounting and parity work; next investigation |
| Leave the economic protocol fixed while finishing qualification | Preserves the prospective test | Missing implementation/data remains a reported deficiency, with no window extension |

Next, qualify dynamic sizing, quantity rounding, reservations, fees, native-time
funding and terminal open marks with independent hand-calculated fixtures and
then old-control reproduction. Provider/canonical-regime parity and source as-of
assembly remain required. No allocation, route, risk setting or live process
change is included. Both prospective outcome seals remain closed.

Confidence in future profitability remains low. A changed source identity,
provider mismatch, clock inconsistency, missing essential coverage or accounting
reconciliation failure would invalidate the affected replay claim. Only the
complete fixed-window outcomes after the seal opens can update the allocation's
prospective economic assessment.
