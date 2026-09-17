# Original collector runtime witnesses and process recovery

## Decision and scope

Retain this offline candidate and continue Task 3 qualification. High confidence
in the exercised cases: all five frozen source versions ran their original
`_Collector.run`, capture, normalization, budget and native reservation logic.
The full coexistence, sustained scheduling and operational migration requirements
are still incomplete. This work establishes no financial improvement and changes
no live strategy, source collector, asset, risk setting or deployment.

Source commit: `acd14adbc3fd3aa09f6f750af333b6f2702f3500`, pushed on
`research/v89-collector-runtime-20260917`. The implementation is isolated in
`/Users/gestas/Prototypes/hypervector-v89-collector-runtime-20260917`.
Its parent is the qualified guarded-store commit `7cb79c3`.

## What changed and why

The new portable journal records the original attempt before transport, then its
API return, then the exact filename and payload before the original raw writer.
The original writer and fsync still execute. A complete witness lets recovery
explicitly ask the original service for ingestion authorization; it does not
infer ownership from matching payloads or nearby timestamps.

The capture bridge preserves original ingestion and normalization under the
previous guarded-store contract. It retains unindexed quarter-budget obligations
after durable attempt creation and deduplicates them by exact raw filename when
an indexed receipt already exists. Original native reservations remain durable.

Separate `ingestion_latest.json` telemetry reports unresolved attempts, missing raw
files, API returns, original request statuses and available/unavailable responses.
The original publisher retains its own health, coverage and return value. A
snapshot taken inside an index transaction labels that fact explicitly.

Four candidate integration issues were reproduced and corrected:

1. Recovery compared an unnormalized intent with the service identity, which
   includes a derived request hash. It now uses the existing service validator
   before comparing the original fields and computed hash.
2. An admission-callback exception incorrectly created an API-return witness even
   though transport had not begun. It now remains unresolved and retains its
   local obligation.
3. The native alarm could interrupt return-witness persistence when the recorder
   was placed inside `DeadlineSession`. The recorder now wraps the original
   runtime session, retaining the original native deadline wrapper inside it.
4. Counting only the original `unavailable` request status missed non-HTTP failed
   returns. Additional telemetry reads the bound service availability decision
   separately from original HTTP/completeness statuses.

A fixture also selected a native bar too soon during the original five-second
publication delay. The fixture now selects an eligible completed bar, including
at the start of a minute. The original scheduler was not changed.

## Verified cases

Each final qualification ran 18 scenarios across five producers: 90 producer
cases and 50 actual SIGKILL events, followed by fresh interpreters. The source and
archive runs each passed 59 tests.

| Process-death boundary | Verified restarted behavior |
|---|---|
| Durable begin, before API return, after API-return commit | Nonzero failure with unresolved provenance; no new transport or observations |
| Raw-path commit before the original writer | Missing raw file reported; nonzero failure and no invented receipt |
| Original raw fsync, service return saved, authorization issued, local binding committed, index committed | Exact saved receipt recovered without another transport call |
| Inside the original SQL transaction before its first observation | New read-only connection observes zero committed request/observation rows; fresh interpreter replays the saved receipt |

Response cases cover complete data, a partial first body, initial connection
failure, interrupted response streaming, HTTP 503 retry and cancellation after
the first indexed receipt. Real wall-time tests delay API return and original raw
receipt beyond the unchanged ten-second deadline; unavailable attempts do not
become observations. These are not complete transport-timeout interaction tests.

An independent stdlib verifier reads original SQLite tables and raw bytes, checks
packet hashes and exact ownership, compares every normalized observation to its
available original response, and checks source hashes and service counts. It
verified all 90 cases in each final run and rejected inflated reported request
and observation counts.

Additional negative controls cover altered witnesses, cross-witness linkage,
unknown copied raw files, wrong paths and symlinks, missing or changed journal
schema/identity, invalid clocks/weights/authority, competing writer ownership,
resource closure, and a resealed foreign authorization.

The related regression suite passed **754 tests, 58 skipped**. The skipped tests
require separate historical integration-fixture selectors and are not presented
as covered here. Two retained unsuccessful verification runs were launcher
errors: stdin could not be imported by spawned workers, and a subprocess lacked
the worktree `PYTHONPATH`. The corrected final run used `python -m pytest` with
the worktree path supplied.

Measured coverage in both final runs:

- New portable core: **302/302 statements and 84/84 branches** across the attempt
  journal, capture bridge and runtime status modules.
- Core plus research harness: **753/782 statements and 196/220 branches**.
- All 20 new Python files passed Ruff, explicit-annotation checks and the
  500-line file / 50-line function limits; maxima were 335 and 49 lines.

Measured coverage is not proof of all failure modes, power-loss durability,
correct production integration, original-producer coverage or economic benefit.

## Evidence and rollback

Artifacts are under
`data/logs/research/bidirectional_cohort/v89_public_collector_runtime_20260917_v1/`:
`candidate_final_v2.txt`, `archive_final.txt`, their coverage and independent
verification JSON, `regression_final.txt`, `source_structure.json`,
`source_integrity_final.json`, and retained failure/reproduction logs.

`source.tar.gz` contains 5,728 files, 33,278,881 compressed bytes, SHA-256
`0e5d157c32c86ae94f85ae93826f6a4196af41798bb936d203b2b0b33e8f3379`.
All source and extracted archive hashes matched after verification.
The original five producer import trees remain separately authenticated by the
previous archive inventory and every result's imported-source hashes.

Rollback is to leave the candidate branch unadopted; the live backend and frozen
collectors retain their existing implementations. The guard/journal use explicit
new namespaces. Do not silently reopen one as an unguarded historical store.

## Highest-value next investigation

Run genuine simultaneous traffic from the four original quarter collectors and
the original native collector, retaining their actual peer-health and receipt
checks. Current native peer fixtures are explicitly empty and do not establish
five-collector coexistence or shared-IP headroom.

Remaining qualification includes sustained bounded/unbounded cycles, full
six-slot native rotation, persistent HTTP 429 and complete transport-deadline
interactions, whole-study grids, recovery time/memory at study scale, and the
quarter-budget acquire-to-durable-begin crash gap. Whole-service death/restart and
power loss remain distinct from the tested producer SIGKILL cases.

Task 4 still requires operational CLI integration, new-study declarations,
frozen-study migration/rollback and an approval-ready deployment proposal. The
continuous strategy diagnostics and three long native comparison jobs remain
active; no sealed prospective outcomes were evaluated here.

An unavailable observation inserted or refreshed, a normalized-value mismatch,
lost budget/reservation evidence, false recovery after missing provenance, source
drift or disagreement in archive reproduction would falsify the corresponding
claim and require further investigation before adoption.
