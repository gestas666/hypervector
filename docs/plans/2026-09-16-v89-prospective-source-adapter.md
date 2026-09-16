# Prospective source identity adapter implementation plan

**Goal:** connect the separately registered later capture to the existing receipt-level source reader without changing original studies or economic rules.

**Architecture:** preserve the completed historical account/routing engine. Introduce an explicit reader-side capture identity that accepts the original four-field contract and the separately declared later five-field contract, authenticates the exact matching SQLite identity, and preserves the original receipt-order/as-of selection. Do not edit any running collector.

**Tech stack:** Python, read-only SQLite snapshots, existing immutable publisher and pytest. Use the isolated `hypervector-v89-prospective-account-20260916` checkout from `b26b2735fc4de983ec6532417231edf778cdf6bc`.

## Reconciled status

The September 9 revision-22 routing gaps were superseded by the subsequent native account integration and complete historical matrix. The actual September 10 report contains 48 completed cases and 48 results, hash `4648cc0a47b69e9f54ec2c13378ae24aa315099fd06c5777cc201cbdb97566cf`. Do not rerun or rebuild that completed work.

The new preflight reproduces `source manifest contract fields differ` in `allocation_source_tape._manifest_contract` against the pinned later capture manifest. This is a reader compatibility gap, not evidence of a live trading defect. The full prospective evaluator is still unqualified: this adapter is one necessary component, not its replacement.

## Task 1: reproduce identity and causal receipt boundaries

- Add `tests/test_allocation_capture_identity.py` using the existing real raw/index receipt fixtures. Original four-field snapshots must retain their exact source document. The later fixture must use its explicit study ID and fixed September 9 bootstrap / September 23 start / October 7 end, with 60-second source allowance.
- Test every intermediate A/B/A/B/A first/latest receipt query, not only final values. Add changed manifest/index study IDs, absent/mismatched explicit ID, unknown extra fields, malformed identity values, changed fixed dates/allowance and raw/index drift.
- Run the new tests before implementation and retain expected failures. Qualification does not read any sealed interval's signals or outcomes.

## Task 2: implement a reader-side identity only

- Add `src/hypervector/research/allocation_capture_identity.py` with a typed frozen identity and exact original/new contract serialization. Keep original `CaptureContract` and collector modules unchanged.
- Update `allocation_source_tape.py` and its existing `allocation_capture_snapshot.py` caller to carry the exact identity. Preserve the numeric `_manifest_contract` interface used by original warmup readers. Preserve all original raw membership, hashing, failure receipts, publication atomicity and query semantics. Add a real snapshot-to-tape positive test for the later identity and retain the original mutation-during-copy rejection.
- Run new tests plus existing source-tape, independent/source-corruption and source-query/window tests. Require meaningful branch coverage of new identity validation. Preserve old output semantics for original input contracts.

## Task 3: authenticate real pre-start source conversion

- Copy an immutable later snapshot and every raw request it names into a separate read-only research input directory. Verify request names/counts/hashes. Never open active collector indexes for writing.
- Build a receipt tape with the candidate. Independently reconcile request count, native receipt identities, first/latest fields and representative intermediate reversions against original raw data. Retain the unchanged manifest and seed/source pins.
- Verify original collector and financial process births, raw/source hashes and finite observers. Record exact source commit, tests, input/output manifests, storage cost and limitations. Journal and commit the bounded result; preserve all old evidence.

## Remaining full objective

Continue the original 24-cell prospective contract after this adapter: exact fourteen-day source assembly, provider/canonical causal publications, native routing at actual decision positions, both modeled clocks, original costs/funding/reservations/rounded dynamic sizing, terminal marks, independent accounting and source-frozen reproduction. Reuse completed generic/native components. Do not assume the historical output writer accepts prospective timing or provenance; inspect its historical-only boundary and add a separately tested path. Preserve original September 22/23 and later October 7 seals. No strategy or allocation promotion follows automatically.

High confidence is limited to reproduced compatibility failure and inspected reusable components. A prior compatible reader, changed pinned identity, incorrect as-of result or altered original output would update this plan. No human clarification is required for this authorized isolated research work.
