# V89 bounded public service qualification — 2026-09-17

Candidate **194b217e936240d1f76a207b9c6279e076f0b99a**, branch
`research/v89-public-service-20260917`, builds on coordinator **39e96de** in
`/Users/gestas/Prototypes/hypervector-v89-public-service-20260917`.
Execution authority: **none**. The live backend, TUI, financial source/configuration,
five collectors and three native research jobs were not changed or restarted.

**Decision:** retain this offline service implementation and proceed to a declared
collector-workload comparison with physical overhead and failures. Do not deploy
it on the strength of the earlier zero-IPC logical savings model.

## Problem, implementation and observed correction

The prior coordinator owned individual grants but did not bound aggregate workers
or outstanding subscriber obligations. It also lacked durable queue scheduling and
a complete client delivery protocol. These gaps matter when public reads overlap:
deduplication alone cannot control concurrent work or establish timely client data.

`AdmissionLimits(max_workers, max_subscribers, planned_weight=None, window_ms=None)`
is explicit and immutable within a coordinator namespace. Worker reservations count
until terminal recovery, including expired leases and surviving orphan processes.
Unchanged client retries consume no new subscriber slot. Shared followers do consume
slots; prepared but unacknowledged responses retain theirs until acknowledgement or
the original deadline. Cancellation releases the applicable subscriber obligation.

The optional weight policy measures **planned local admission weight**. Running
reservations remain charged even while startup exceeds the rolling window; completed
admitted work ages from the actual owned child-admission clock. Failed/partial
admitted work is not refunded. This does not measure actual failed-request cost,
venue window implementation, unexpected returned rows or other shared-IP consumers.
There is no implicit 600-, 900- or 1200-weight deployment policy.

`PublicRequestService` requires explicit limits and an exclusive scheduler context.
Subscription and original positive queue authorization commit atomically. Restart
can schedule a reserved original grant, but cannot redispatch a consumed one or
replace a surviving worker. Queue deferrals retain first/latest observation times,
first/latest reason and attempt count. Deferral preserves the client's deadline.

`PublicPipeChannel`, `PublicPipeServer` and `PublicPipeClient` provide the complete
local request/response/acknowledgement path over preconnected process pipes. Each
peer has one bounded outgoing frame and one bounded partial incoming frame. Writes
and reads yield under backpressure. Client arrival is observed after actual frame
read; local data has an explicitly unconfirmed receipt until the broker acknowledges.
Late reads discard body availability. Missing acknowledgement stays missing.
Frozen delivery envelopes cannot gain later worker diagnostics after transmission.

The large-response premature-acknowledgement control exposed an implementation
defect: the first version wrote the durable acknowledgement before checking whether
the outgoing frame was fully transmitted. `backpressure_red.txt` records that
failure. The check now precedes the ledger write; the same control passes, while
a physically stalled leader leaves its shared follower independently deliverable.
This defect was confined to the offline candidate.

## Validation

- **351 candidate controls passed:** 350 in `candidate_tests.txt`, plus the added
  deferral-integrity control in `deferral_integrity_test_v2.txt`.
- **351 controls passed together from the archived source**, in 81.16 seconds.
- Changed production modules cover **534/534 statements and 168/168 branches**,
  with both thread and multiprocessing coverage enabled.
- An independent standard-library verifier authenticates **16 candidate and 16
  archived ledgers**, **18 terminal grants each**, including raw worker captures,
  original timing consent, queue authorization, frozen envelopes and acknowledgement.
  Terminal grant/status and subscriber delivery states match across both runs.
  Timestamps, process identities and some observation timing differ; these physical
  runs are not byte-identical.
- A copied-ledger negative control changes original client timing. Independent
  verification rejects it; the original evidence is untouched.
- Real process tests cover timely/late/lost-ack delivery, HTTP 429, partial 200/429,
  connection failure, child startup crash, killed service owner with a living orphan,
  subscriber/worker saturation, quota expiry, partial frames, oversized frames,
  corrupted provenance, atomic queue rollback and exclusive service ownership.
- Existing public broker, HTTP worker and coordinator controls remain included.
  Ruff, source size, typed signatures, public docstrings and whitespace checks pass.
  Tests deny network access and writes to live/runtime/research/config/source roots.

Development logs remain evidence of intermediate results. `admission_green.txt`
contains one fixture failure because the mock initially rejected the alternate
metadata payload; `admission_boundaries.txt` passes after correction.
`recovery_controls.txt` initially queried a not-yet-created test table; v2 fixes
test initialization. The first `deferral_integrity_test.txt` used the wrong policy
when reopening its fixture; v2 preserves the immutable policy and passes. Those
failures are not represented as successful qualification runs.

## Physical timing and limits of inference

The eight complete process-pipe scenarios measured:

| Observed component | Candidate with coverage | Archived run without coverage |
|---|---:|---:|
| Initial client creation to service registration | 487–507 ms | 378–396 ms |
| Dispatch start to actual child admission | 436–453 ms | 371–391 ms |
| Small, timely prepared-frame to client read | 7–13 ms | 5–13 ms |

These are local fabricated HTTP experiments, not Hyperliquid latency benchmarks.
The registration delay includes starting a fresh service process in the harness;
it should not be assigned to every request of a persistent service. Worker startup
is still per dispatch. Include these separate costs in the next workload study.
The intentionally delayed read expires; a lost acknowledgement has no verified
broker-side arrival clock. In non-IPC unit cases, the verifier's `pipe_delivery_ms`
field is only a reported clock difference, not a physical pipe measurement.

The official rate-limit documentation checked September 17 reports an aggregate
REST allowance per IP and additions based on returned candle/funding rows. It does
not establish this namespace's share of that allowance or all error-path charges.
[Hyperliquid rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

## Evidence preservation and reproducibility

Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_service_20260917_v1`.
The full tracked-tree archive contains **5,642 files**, **222,136,320 bytes**, SHA
`134e287d29d61bc3c475a593d62553b4f4720bace21380a9f4b955a56e13a2ca`.
Unlike the earlier source-only archive, this includes tracked historical documents.
Every archived file matched its Git blob, candidate file and extracted bytes; all
were rechecked after archive tests. Preserve the selected `candidate_test_tmp` and
`archive_test_tmp` SQLite ledgers and capture files. Do not reuse those basetemp
paths or mutate the archived source after journal registration.

Key records: `source_manifest.json`, `source_review.json`, `final_coverage.json`,
`archive_verification.json`, `independent_candidate_verification.json`,
`independent_archive_verification.json`, `independent_negative_control.json`,
`runtime_verification.json`. The implementation plan is archived with the candidate.

## Recommendation, alternatives and falsifiers

| Option | Benefit | Cost / unresolved evidence |
|---|---|---|
| Keep current collectors running | Preserves existing study continuity now | Duplicate public reads remain |
| Qualify this service against declared collector workloads | Measures sharing benefit with real startup, queue and delivery costs | Additional offline experiment; no assumed latency benefit |
| Deploy immediately | Potentially fewer duplicate reads | Collector consent/receipt compatibility and operational continuity are not qualified |

**Highest-value next investigation:** compare complete service and independent
request paths on a declared workload derived from authenticated collector traces,
including original consent, short deadlines, partial failure, 429 and unknown
external traffic. Report newly late/unavailable requests as outcomes. Do not choose
a blanket conservative budget to force a passing result.

This implementation is a library service over preconnected pipes, not an installed
daemon or collector integration. It has no dynamic listener, historical ledger
retention policy or validated long-duration resource benchmark. Frame bounds do
not by themselves prove a particular peak RSS. Client receipt reports are trusted
same-host reports; hashes detect consistency errors, not a privileged attacker
rewriting all evidence. OS stalls and SQLite lock waits preclude a hard real-time
guarantee. Existing per-worker deadline/recovery controls remain in effect.

Confidence is **high for the exercised local ownership, admission and delivery
invariants**, and **unverified for production savings or financial improvement**.
A duplicate HTTP dispatch, premature slot release, accepted cross-scope receipt,
fabricated acknowledgement or body delivered after its declared deadline would
falsify the corresponding claim. A collector workload showing additional late or
unavailable data would lower confidence in adoption even when unit controls pass.

Offline rollback is selecting the prior committed branch. Any live collector or
deployment change requires a concrete continuity/rollback proposal and explicit
human approval; no deployment approval is being requested for this isolated result.

At **14:51:59 UTC**, all 11 runtime/collector/research identities matched; latest
checkpoint was `running_consistent`, 4,650 polls, zero faults, with SNDK and Brent
open and recorded protective stops. Live configuration hash was unchanged. Native
baseline/reproduction/candidate had 10,584 / 10,836 / 14,112 first-variant decisions,
with no failure or final qualification artifacts. Full source/account qualification
remains pending. The backend is already live; these are research milestones.
