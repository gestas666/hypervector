# Versioned collector admission and transport lineage qualification

The offline candidate now retains durable local admission, subscriber API return,
original raw receipt and distinct transport evidence separately. **503 public
controls pass from the final worktree and from a clean source archive.** The five
new production-candidate modules cover **267/267 statements and 98/98 branches**
in both the final focused run and archived suite. This is high-confidence evidence
for the tested contracts, not proof of complete collector adoption or profitability.

The previous goal turn made progress by specifying this boundary and retaining
failing admission controls. This turn implements, tests, independently verifies,
archives and commits the component. The continuous improvement goal remains active.

## Source and reproduction

Source **eb8b2cd06f15dae9b57616bfca50ef42f235c1a7**, branch
`research/v89-collector-lineage-20260917`, worktree
`/Users/gestas/Prototypes/hypervector-v89-collector-lineage-20260917`, is committed
and pushed. The parent is `ca9445af15b0a88ec3ebe4918860e99705d3d602`.
The implementation plan is `docs/plans/2026-09-17-public-collector-lineage.md`.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_collector_lineage_20260917_v1`.
`source.tar` contains **3,277 files / 25,364,480 bytes**, SHA-256
`7f27c8ce261db31f15ef55e1fde3c64a00fbb24b796f6bac22e19ffefd37cfe4`.
Git archive, source worktree and extracted bytes match. All 152 original and
archived producer source files were rechecked against the prior frozen inventory.
The existing producer archive remains pinned by its earlier journal revision.

Final runs are `candidate_final_tmp` and `archive_full_tmp`; logs are
`candidate_final.txt` and `archive_full.txt`. The candidate finished 503 tests in
150.91 seconds; the archive finished 503 in 158.46 seconds. The earlier 494-test
run preceded the final setup/raw-size hardening and nine additional controls.
`coverage_final_v3.json` and `archive_coverage.json` retain the measured coverage;
coverage does not include every old dependency or the entire research harness.

Both independent verification summaries authenticate **14 original-producer cases
per source**, including five with the new lineage enabled: four scenarios and one
additional 429 case supporting verifier corruption tests. That is 70 producer
executions per final source, 25 of them through the new ledger. The original
capture, original ingest, reopen and recovery paths remain in use.

Tests deny network access, secret-file reads, writes to live/runtime/research DB
and configuration/source roots, and writes to all five original producer trees.
Ordinary tests without an explicit frozen producer inventory skip the optional
handoff families; those skips are not qualification. These final runs explicitly
selected the authenticated archived producer inventory and ran those families.
Ruff, return annotations and 500-line-file/50-line-function checks pass for the
21 changed Python files. No live backend, collector, TUI or research job changed.

## Behavior and observed results

`PublicCollectorLedger` opts into an exclusively owned service namespace. It
rejects silent adoption of unversioned requests. A successful registration and
its original dispatch authorization commit atomically with the admission record.
A deadline, capacity or shared-429 deferral is durable without an owned transport.
Repeating that same local attempt cannot turn the old rejection into a new call;
a new attempt needs a new identity. Existing service users remain unchanged until
they explicitly enable the ledger. Versioned service namespaces reject bypass
through the ordinary submission interface.

Return records bind original intent, registration, prepared service evidence,
acknowledgement, trusted local API return clock and optional exact raw bytes.
They reject changed/reused raw paths, mismatched bytes/scope, future or backdated
clocks, missing original service envelopes and rewrites of derived availability.
A late API return is unavailable even if the pipe read was timely. A later
acknowledgement cannot upgrade the frozen first return. A raw local failure
overrides an otherwise successful service acknowledgement. Raw reads have a
16 MiB bound. Failed persistence leaves no partial admission/return, and failed
research-context setup releases the acquired service lock.

Accounting deduplicates authenticated transport identities while retaining each
local obligation. It distinguishes queued work, unresolved running dispatches,
terminal observed starts, terminal missing-start evidence and abandoned starts
whose terminal worker receipt was lost. Planned weight is a local reservation
quantity. **Venue-charged weight and external IP headroom remain unknown**; no
quota or per-study budget discount is installed.

| Actual frozen-producer scenario | Local attempts | Distinct transports | Deferrals without dispatch | Stored observations |
|---|---:|---:|---:|---|
| Complete candle | 5 | 2 | 0 | One per producer |
| Incomplete 200, then complete | 9 | 3 | 0 | Four quarter-hour producers; native incomplete |
| 503, then complete | 9 | 3 | 0 | Four quarter-hour producers; native incomplete |
| Persistent 429 | 13 | 2 | 8 | None |

The independent stdlib verifier cross-checks the old service verifier, original
producer traces, every raw/index record, all admission/return rows and recomputed
transport accounting. Ten controls include nine corrupt-report cases; rewritten
content hashes do not make false accounting or altered return evidence pass.
The focused suite has 62 controls, including partial failures, cancelled grants,
unknown dispatch outcomes, lost acknowledgement, atomic rollback and reopen.
Four defects found during development are retained as failing evidence: missing
local-API-failure precedence, boolean schema acceptance, context lock leakage and
unbounded raw reads. These were defects in the new offline candidate, not newly
discovered defects in the deployed collectors.

## Limits and next decision

The actual-producer harness records lineage **after original ingestion and
recovery**. It validates those observed clocks and bytes; it does not yet enforce
the new availability decision before the original consumer ingests data. A
production adapter must establish that earlier boundary. HTTP response availability
also does not establish complete or correct market data: 429 and 503 response
bodies can arrive successfully while observation count remains zero.

The fixture uses synthetic SNDK candles, empty headers, explicit 1000 ms earlier
admission consent and original quarter-hour retries. Native uses its original
single-admission capture path and peer guard over empty synthetic peer indexes;
its full scheduler and durable slot reservation are not exercised. This is not
a latency benchmark. General HTTP headers, larger real payloads, full scheduling,
study budgets, cancellation/restart through complete producer loops and migration
of frozen studies remain unqualified. Unkeyed hashes and local clock reports
assume trusted local writers; they are not protection against a compromised host.
A durable start record marks the call boundary, not proof of wire arrival or
external venue charging. No sealed prospective economic results were inspected.

**Recommendation:** Retain this offline candidate and move to pre-ingestion
availability, full scheduling, native reservations and unchanged per-study budget
semantics. **Why now:** The old capture/store qualification exposed eight local
429 deferrals that cannot honestly be counted as physical HTTP requests.
**Evidence reviewed:** Final source/archive suites, original-producer raw/index
receipts, independent verifier controls and frozen source manifests.
**Observed opportunity:** Reduce duplicate public traffic without losing original
attempt or receipt evidence. **Applicable regime:** Public-data transport and
receipt correctness; burst behavior around fast markets still needs measurement.
**Proposed live change:** None at this stage. **Expected upside:** The synthetic
cases demonstrate fewer distinct calls and accurate deferral attribution; actual
data-capture or trading improvement is not established.

| Alternative | Benefit | Limitation / decision |
|---|---|---|
| Keep current independent collectors | Preserves current budgets and study continuity | Retained in production while this work proceeds |
| Replace only the HTTP session | Smaller change | Insufficient: admission, return timing, budgets and migration still need explicit handling |
| Qualify the complete versioned adapter | Can preserve both local and transport truth | Next investigation; scheduling and pre-ingestion enforcement are still required |

**Main risks:** Incorrect availability before ingestion, changed retry/cooldown
policy, reservation double counting or inappropriate discounts, missing headers,
incomplete crash recovery, and study discontinuity. **Validation completed:** The
bounded admission/return/accounting component and stated synthetic original
capture/store cases. **Validation required:** Complete producer-loop scheduling,
budget/reservation and pre-ingestion tests, shared429 policy choice, cancellation,
deadline/restart behavior and a concrete migration/rollback proposal.
**Success metrics:** Conserved original attempts and budgets, exact causal clocks
and bytes, no false HTTP count, no discount for unknown work, independently
reproducible completed study coverage. **Failure / rollback triggers:** Any changed
frozen source, lost identity/receipt, invented timely availability, altered budget
semantics or unexplained study coverage loss. The original collectors and parent
source remain preserved. **Confidence:** High for the tested component contracts;
insufficient for live adoption or financial upside. **Explicit approval requested:**
None now; a live change requires a completed, reviewable proposal and approval.

Runtime at **17:27:02 UTC**: all eleven established process identities matched,
5,270 backend polls, zero faults, `running_consistent`, unchanged live config.
Collector heartbeat ages were 10.52–25.22 seconds. Original native baseline,
reproduction and candidate jobs reached 20,916 / 21,168 / 27,468 first-variant
decisions, with no failure or final result. They remain the existing running jobs.
