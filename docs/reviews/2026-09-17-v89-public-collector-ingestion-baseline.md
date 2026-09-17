# V89 original collector scheduling and ingestion baseline

Status: **observed, offline baseline qualified; guarded ingestion is not implemented**.
No live strategy, configuration, execution, collector deployment or frozen study was changed.

Source: `2a38d4d97e2e82b4fde4f890a004059ac47c1615`, branch
`research/v89-collector-ingestion-20260917`, worktree
`/Users/gestas/Prototypes/hypervector-v89-collector-ingestion-20260917`.
Parent: `eb8b2cd06f15dae9b57616bfca50ef42f235c1a7`.

## Decision and findings

High confidence in the measured original-code behavior under the declared fixtures:
**a check only before initial ingestion cannot establish durable service availability**.
Every original store replays an otherwise valid orphan raw response without service
return attestation. This is a counterexample to a proposed integration assumption,
not evidence that current independent collectors have ingested a failed shared-service
delivery; they have not adopted that service.

Three original policy families must be preserved independently:

| Actual frozen sources | Local budget | First full cycle: complete / persistent 429 | Calls after cancellation on first 429 | Extra persistent table on original reopen |
|---|---:|---:|---:|---|
| Original SNDK/Brent and its follow-up, PIDs 43671/27818 | No `RequestBudget` implementation | 5 / 15 | 3 | Accepted by old opener |
| Seven-asset capture and follow-up, PIDs 45939/51194 | 600 planned weight per rolling minute | 20 / 60 | 1 | Rejected |
| Native-minute continuation, PID 44810 | Durable one-minute reservations and peer guard | 1 / 1 | 1 | Rejected |

Counts describe one declared logical-clock fixture cycle, not a production rate or
venue quota. The budgeted 60-attempt scenario waits as needed; it is not 60 attempts
within one minute. Original cancellation behavior is measured, not normalized by
the harness. The old versions finish the current three-attempt retry sequence.

Additional measured invariants:

- After raw persistence but before consume, original recovery adds **1 / 10 / 7**
  observations for old-quarter / budgeted / native versions respectively, with no
  service-return attestation. Those numbers reflect each original first query.
- Both budgeted runtimes restore unexpired original request weights before resumed
  collection. Combined first/resumed calls remain within 600 planned weight per
  rolling minute. The recovered orphan's 21-weight obligation remains present.
- Native reservation-only failure retains its slot and prevents immediate repeat
  admission. After the original 60-second spacing it advances to the next slot.
- The native full loop exercises six slots: SPCX/SNDK/Brent recent, then their history
  slots. Reservations remain durable and spaced; repeated observations retain the
  original native receipt semantics.
- Native HTTP 429 sets its original five-minute cooldown. Admission refuses a
  request with fewer than ten logical seconds remaining before receipt cutoff.
- Both budgeted full loops expose pending work at a bounded deadline and resume
  using newly constructed runtime/budget objects and the original recovered store.
  The separate cycle audit verifies three first-run cycles, two with deferral
  before cancellation, and all 56 first-run attempts for each source in both runs.

The original metadata, funding and candle streams are exercised according to each
source's declared roster. Normalized first/latest receipt semantics and native JSON
hash encoding are checked independently; the latter intentionally uses different
JSON whitespace than the quarter index.

## Validation and retained evidence

Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_collector_ingestion_20260917_v1`.

**27 tests pass in the final worktree (4.80 seconds); 27 pass from the archive
(6.69 seconds).** Both final runs execute the original `_Collector.run` methods in
five separately sourced interpreters, with **25 scenarios and 675 raw request
attempts per run**. These runtimes use their original schedulers, request budgets,
capture, normalization, storage, recovery and native traffic guard. The injected
transport has no network capability. Final runs additionally deny network access,
`.env` reads and writes to live/runtime/config/source and all five original trees
through the retained sandbox profile.

Independent checks authenticate original raw bytes, body hashes, exact request
payloads, complete synthetic grids, actual SQLite rows, first/latest observations,
source imports, local weight obligations and native reservations. Negative controls
include coordinated report/database alteration, missing observations, changed last
receipt, reservation deletion, slot change, invented zero response weight, shortened
cooldown, budget refund and incomplete bodies with newly computed hashes.

Measured parent/child coverage of the **six new research modules**:
**491/495 statements (99.2%) and 117/122 branches (95.9%)**. Both independent verifier
modules have 100% measured statement/branch coverage. This is not coverage of the
original producers, prior service modules, complete system or all failure modes.
Ruff and the 500-line file / 50-line function / explicit return annotation checks pass.

Retain `candidate_final_v2_tmp` and `archive_test_tmp` as the final qualified matrices.
`candidate_final_tmp` predates the fixture cancellation correction and is not the
final acceptance result. Preserve earlier failing logs and their output directories.
One failing regression demonstrated that the test clock's first-run cancellation
deadline survived into the reconstructed runtime; clearing that fixture-only
deadline fixed the harness, without changing any original collector code.
Earlier fixture/import/verifier errors are also retained, not treated as live faults.

`source.tar.gz`: **5,692 files**, **33,742,403 bytes**, SHA256
`f0f51d3ae7398a8d80f97c23bad12655a34e42865f285d3e52ac8610fc10fbe9`.
Its decompressed tar is **222,433,280 bytes**, SHA256
`319bac7a839639d3a6634c1c830a1e7476123673d745bdf858ead19c6d016c33`.
All source/extracted files and the **152 original/copied producer files** matched
after archive testing. Compression was verified before removing the redundant tar.

## Limits and falsifiers

- Scheduling uses a deterministic injected clock and fabricated constant-price
  candles, funding and metadata. It is not a latency, wall-alarm or financial test.
- Reopen/reconstruction occurs inside each original-source interpreter. Exceptions
  inject the two crash boundaries. Real process kill/restart, power loss, CLI
  singleton/manifest wrappers and host lifecycle behavior remain separate tests.
- Native peer fixtures are explicitly empty and refreshed by simulated external
  actors. This does not qualify measured production aggregate IP headroom.
- The shared service and its admission/return ledger are absent from this baseline.
  Pre-ingestion enforcement, shared 429 policy and full service-backed scheduling
  remain unqualified. The prior lineage harness still records returns after ingest.
- Original request and response weights are accounting fields, not proof of actual
  venue charging or wire arrival. Hashes assume trusted local writers.
- Any raw/index/source mismatch, missing expected scenario, disagreement under real
  process reconstruction, or failure of archived reproduction updates or falsifies
  the relevant claim. No economic improvement is established by this work.

## Next implementation and approval boundary

The single next investigation is **durable, versioned pre-ingestion authorization**:
bind the exact service attempt and caller-side receipt witness before observations
are inserted, enforce the same rule during recovery, retain unavailable attempts
as incomplete budget obligations, and reject unresolved binding before new dispatch.
Do not infer a lost attempt identity from similar requests or overlapping clocks.

| Alternative | Benefit | Defect or trade-off | Decision |
|---|---|---|---|
| Keep existing independent collectors | Preserves frozen studies | Does not qualify service adoption | Continue current deployment |
| Add only a transient pre-ingest check | Small change | Orphan recovery bypass is demonstrated | Reject as sufficient design |
| Add tables to every original database | Durable storage | Newer/native openers reject; oldest accepts without identity validation | Reject implicit in-place migration |
| New versioned namespace with durable binding and guarded recovery | Can preserve availability and accounting together | Requires implementation, crash tests and explicit study transition | Next candidate implementation |

Recommendation: implement and qualify that offline candidate before a live proposal.
Why now: earlier service/lineage work lacks the consumer enforcement required for adoption.
Evidence reviewed: authenticated five-source code, 25-scenario matrices, 675 requests
per run, independent corruption controls and archived replay.
Applicable regime: technical data integrity; independent of market direction.
Proposed live change: none at this stage.
Expected upside: prevent unavailable shared-service responses entering later research
or monitoring data; economic benefit remains unknown.
Main risks: lost binding, partial commits, stale authorization, bypass on recovery,
changed cancellation, erased local budget obligations and silent frozen-study migration.
Validation completed: the original baseline above.
Validation still required: plan Tasks 2–4, including actual service-backed full loops,
process kill/restart, durable availability exclusion, migration and operational rollback.
Success metrics: zero unavailable observation insertions, exact attempt/transport
conservation, preserved per-source budgets/reservations, reproducible restart behavior.
Failure/rollback triggers: any provenance, completeness or accounting discrepancy;
retain the unchanged current collectors and preserved source/raw namespaces.
Confidence: high for this bounded baseline; candidate enforcement remains unproven.
Explicit approval requested: none for authorized offline work. A concrete live adoption
proposal must receive human approval under the goal attachment before deployment.
