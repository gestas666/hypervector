# V89 durable collector availability enforcement

Status: **offline candidate; storage boundary qualified under the stated fixtures**.
Full scheduler integration, OS process-failure recovery and study migration remain
unqualified. Current collectors have not adopted this service. No live strategy,
configuration, orders, backend, TUI or frozen study was changed.

Source: `7cb79c32a753d5360754d96643795efea4f15e16`, pushed branch
`research/v89-collector-enforcement-20260917`, worktree
`/Users/gestas/Prototypes/hypervector-v89-collector-enforcement-20260917`.
Parent: `2a38d4d97e2e82b4fde4f890a004059ac47c1615`.
Evidence directory: `data/logs/research/bidirectional_cohort/v89_public_collector_enforcement_20260917_v1`.

## Problem and implemented behavior

The preceding five-source baseline demonstrated that the original stores recover
an otherwise valid orphan raw response without checking shared-service delivery
availability. That was a counterexample to proposed integration behavior, not an
observed production corruption incident: current collectors remain independent.

High confidence in the following bounded results, supported by actual original
store implementations, genuine owned-service receipts and fresh archived replay:

- The service now issues immutable ingestion authorization from an already saved
  admission, return and exact raw receipt. Study, declaration, raw path, namespace,
  original service identities and receipt hashes must match. The caller's receipt
  time is checked independently of the earlier reported session-return timestamp.
- A new, explicitly created namespace retains original normalization and index
  transactions. Persistent SQL guards require a connection-local authorization
  scope for request and observation writes. An unavailable valid HTTP 200 is an
  incomplete `unavailable` request, with no inserted or refreshed observations.
- Authorization is committed separately before the original request/observation
  transaction. Injected observation-insert failure rolls back both original row
  types while retaining the durable binding. Recovery then succeeds from the
  original service decision.
- Reopen requires the expected namespace, original class-source hash, contract,
  original schema and stored identity, version and exact persistent guards. The
  original store constructor rejects extended newer schemas, so the explicit
  guarded opener restores its qualified fields and performs these validations.
- Recovery preflights all raw authorizations and required indexed/bound filenames.
  Missing authorization or raw evidence fails before replay. A missing local
  binding can be restored from an already-issued service decision. A saved return
  without an issued authorization remains unresolved until explicitly authorized.
- Reopened stores cannot ingest before recovery. The actual native scheduler also
  cannot reserve before recovery; reservation-only restart retains its original
  60-second spacing. Quarter request weights and native stored planned/actual
  weights remain original producer evidence.

The guard uses original store methods; it does not replace their normalizers or
infer missing service-return identities from similar payloads or nearby clocks.

## Reproduced candidate defects and repairs

| Reproduced failure | Repair and evidence |
|---|---|
| New ingestion could precede recovery after reopen | Explicit recovery prerequisite; both quarter and native negative controls pass |
| Binding-only receipt disappeared without failing recovery | Bound and indexed filenames join the required raw evidence set |
| Guarded reopen bypassed original stored contract identity checks | Namespace now binds and revalidates original identity contents |
| SQLite URI metacharacters selected the wrong path | Canonical file URI encoding; `?`/`#` directory test passes |
| List-valued namespace family raised an unhelpful type error | Explicit family type validation before membership lookup |

These defects were in the undeployed candidate. Their red test artifacts are
retained. The first coverage wrapper additionally broke `Popen[bytes]` annotations;
the corrected wrapper preserves the Popen class contract. This instrumentation
failure changed no candidate implementation. Preserve `candidate_final.txt` and
`qualify_source_v1.py`; they are not passing final evidence.

## Validation and evidence boundaries

- **754 passed, 58 skipped** in the related public-service, collector,
  prospective-market and native-minute regression suite. Skipped historical
  integration fixtures were not supplied their separate selector variables.
- **65 focused tests pass from committed candidate and fresh archive**, with
  network access and writes to live/runtime/research databases denied by the
  retained OS sandbox policy. The new original-source guard tests are included.
- Each final focused run launches five authenticated original-source interpreters
  for available and late-caller scenarios: **10 producer cases, three schema
  families**. Actual original `_capture_once`, normalization, SQL ingestion,
  close/reopen and recovery execute. Every available case retains its candle;
  every late case remains incomplete with zero observations after reopen. Ordinary
  second SQLite connections fail without the required guard callbacks.
- The late-caller fixture intentionally suspends the outer session wrapper after
  the inner relay reports return and before original raw receipt. It tests the
  distinct recorded clocks; it is not a measured production delay distribution.
- Independent checks read exact raw bytes, service authorization rows, namespace
  seals, original SQLite rows, normalized candle values and imported source hashes
  for all ten cases in each final run. Three corrupted result controls are rejected.
- Coverage combines parent and isolated children for the seven affected measured
  modules: **516/536 statements and 124/144 branches**. Service ingestion issuance,
  resolution and the public ledger API have 100% measured statement/branch coverage.
  This is not 100% guard, original producer or whole-system coverage.
- Ruff, diff whitespace and 500-line/file, 50-line/function, explicit argument/
  return annotation checks pass for changed source. No `Any` annotations are added.
- The committed source archive has **5,707 files**, **32,988,288 compressed bytes**,
  SHA-256 `6ebd08dcd61182cf1a3008b362baa38cb6c97a6221a550882011824ce5fa8c27`.
  Source and extracted archive files match after tests. The original producer
  inventory remains authenticated; no original source was edited.

Final focused artifacts: `candidate_final_v2.txt`, `candidate_final_v2_tmp/`,
`candidate_final_v2_coverage.json`, `candidate_final_v2_independent.json`, and their
`archive` equivalents. Other evidence includes `regression.txt`, `source_manifest.json`,
`post_test_source_integrity.json`, `code_structure.json` and retained red controls.

## Limits, failure conditions and next investigation

The measured improvement is data-integrity enforcement. Financial benefit,
production latency, shared-IP headroom and collection throughput are unestablished.
Authorizations currently revalidate retained raw evidence on lookup; startup cost
and memory use need measurement at actual study sizes. Hashes assume trusted local
writers and do not defend against a compromised host removing guards and evidence.

These tests qualify the storage boundary. They do not qualify full service-backed
`_Collector.run` scheduling, CLI singleton/manifest lifecycle, actual OS kill/restart,
power loss, all cancellation/429/deadline interactions, or frozen-study migration.
Native health reporting needs explicit unavailable-response telemetry; the original
counter does not include this new request status. Complete admission/return/binding
crash phases must be wired into the full integration before adoption.

Any unavailable observation insertion/refresh, orphan bypass, changed original
normalization, lost reservation/weight, raw/identity mismatch, or disagreement in
archived reproduction updates or falsifies the corresponding qualified claim.

| Alternative | Benefit | Remaining cost | Decision |
|---|---|---|---|
| Keep current independent collectors | Preserves frozen studies | No shared-service adoption | Continue current deployment |
| Transient check only before ingestion | Small integration | Demonstrated recovery bypass | Insufficient |
| New namespace with durable guard | Availability survives measured recovery cases | Full scheduler and operational qualification | Continue offline candidate |
| Modify existing frozen indexes in place | Avoids new namespace | Changes declared evidence and schema behavior | Not qualified |

Next highest-value work: integrate the guarded store with each original full
collector loop, maintaining its precise budget, reservation, retry, cancellation,
peer and deadline behavior. Add real process kill/restart at each durable boundary,
availability telemetry, full-grid accounting and explicit migration/rollback before
presenting a live adoption proposal. Do not repeat the completed baseline as a
substitute for that integration.

Recommendation: continue that authorized offline integration. Applicable regime:
technical data integrity, independent of market direction. Expected upside:
avoid treating unavailable shared-service data as usable research observations.
Success: zero such observations, exact request/transport conservation, preserved
original scheduling and reproducible restart. Rollback: retain current independent
collectors and original frozen namespaces. No live change is proposed by this
candidate commit; deployment requires the goal attachment's explicit human approval.

Runtime snapshot v43 at **19:04:21 UTC** confirms all eleven recorded process
identities, running-consistent backend, 5,660 polls, zero faults and unchanged live
configuration. Collector ages were 14.17–26.36 seconds. The three preserved native
comparison jobs were still on their first variant at 27,468 / 27,468 / 35,532 decisions,
with no final result or failure. Prospective economics remain sealed.
