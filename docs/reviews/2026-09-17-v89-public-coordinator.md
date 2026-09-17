# V89 durable public coordinator qualification

Confidence: high for the tested per-grant coordinator and worker contracts.
Aggregate request budgeting, a complete client IPC service and collector deployment
remain unqualified. No financial source/configuration or running collector changed.

Candidate **39e96dea9daa2d9307edf82513e8a3766a42b9b2**, branch
`research/v89-public-coordinator-20260917`, worktree
`/Users/gestas/Prototypes/hypervector-v89-public-coordinator-20260917`.
Parent: bounded worker **29f4d09**, with owned-clock broker **3252022** unchanged.

## What changed and why

A standalone worker did not establish durable one-grant dispatch ownership or
coordinate recovery against a child that had not started yet. The new coordinator
reserves a dispatch record atomically with each new broker grant. A per-grant OS
lock covers the dispatch call, and a child must atomically bind its PID/birth to
that grant before constructing its public HTTP session. Recovery leaves a live
registered child alone. If recovery wins before child admission, the late child
is rejected before HTTP. An original ticket cannot dispatch twice.

Before child admission, the coordinator rechecks lease, original request/policy,
429 cooldown and whether any subscribers remain pending. Controls found and fixed
two startup races: a newly observed 429 and last-subscriber cancellation previously
could occur after dispatch began but before the child made its request. A separate
control found that a miswired worker could issue a different public request/policy
before publication rejected it; admission now authenticates the persisted request
against the durable grant before HTTP starts.

The header observer records HTTP status before body streaming and starts 429
cooldown immediately. Publication and recovery preserve that first observation
without extending its cooldown repeatedly. Complete worker captures publish through
the existing broker response helpers. Partial, expired or abandoned requests have
no consumable broker body. Separately authenticated coordinator outcomes preserve
worker status/errors/raw evidence without inventing a missing transport receipt
clock. Subscriber cancellation, deadlines and separate client acknowledgement
remain under the existing owned-clock contract.

Recovery also handles a lost dispatcher whose worker received 429 but could not
commit its header transaction. After proving the registered process is no longer
alive, it authenticates the stable partial capture, preserves the raw header and
applies cooldown. It does not create a completed worker receipt or retry HTTP.
Disabling this recovery path makes the physical orphan-header control fail.

## Correction to the preceding worker qualification

The earlier Python SIGALRM callback called `os._exit(124)`. It passed Python sleep
and streaming controls, but the new locked-database orphan test showed that Python
could defer the callback while SQLite waited in C. The worker remained alive beyond
the configured test deadline after its supervisor was killed. This narrows the
previous fallback qualification; its frozen evidence remains preserved.

The child now installs **SIGALRM's OS default termination**, which does not wait for
Python callback dispatch. The same physical test holds a SQLite write lock, waits
for the raw HTTP header, kills the dispatcher, and verifies the child stops while
the database is still locked. The raw 429 is then recovered without a fabricated
terminal receipt. The previous exit-124 callback is removed in this candidate.
This does not establish a hard real-time guarantee under uninterruptible OS work.

## Validation and reproducibility

- **279 candidate controls**: 278 in the combined suite, then one additional durable
  reopen control. **279 tests pass together from the authenticated source archive.**
  This retains the prior 217 controls and adds 62 coordinator controls.
- Changed coordinator/worker modules cover **603/603 statements and 198/198 branches**
  with multiprocessing coverage. This is measured source coverage, not exhaustive
  state-space proof or coverage of the whole trading engine.
- Real worker processes and concurrent clients exercise shared leader/follower
  delivery, independent cancellation, duplicate tickets, immediate/partial 429,
  publication rollback, lost supervisors, live-child recovery and locked SQL.
- Identity/provenance controls reject changed policy, path traversal, mismatched
  complete captures, rehashed but mislinked rows, reverted terminal state, invalid
  clocks, changed partial files and HTTP without matching durable admission.
- Independent stdlib verification authenticates **14 candidate and 14 archive
  ledgers**, their raw captures, terminal grant links, header cooldown, subscriber
  preparation and acknowledgement. Dispositions/status/body lengths/subscriber
  states match; real timestamps and PIDs differ, so these are not byte-identical runs.
- Ruff, whitespace, explicit argument/return annotations, public-function docstrings,
  and file/function size checks pass for added/changed Python files.

Archive: **3,719 files**, **29,224,960 bytes**, SHA-256
`155238d819d5b2215b29e039c8faa310cec0b203eee1e7be9322cec36bc55abf`.
Every extracted file matches the committed Git blob and candidate worktree bytes.
Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_coordinator_20260917_v1`.
Selected `candidate_test_tmp` and `archive_test_tmp` ledgers/captures are frozen
journal evidence; do not reuse their pytest basetemp paths.

Development logs preserve the original failures. The first external negative-control
invocation selected the main checkout's import path and failed during collection;
it is not proof of the intended behavior. The explicit-root second invocation fails
at the missing recovered 429 as intended. Initial hook tests also needed the fixture's
explicit 1.5-second timeout; their earlier failure is retained. Final/archive results,
not filenames containing `green`, establish the qualification.

## API and boundaries

`PublicTransportCoordinator(path, capture_root, clock=wall_ms, lease_ms=10000,
cooldown_ms=300000, worker_timeout_ms=8000, body_limit=8388608)` owns one isolated
namespace. `subscribe` reserves/join/retries under the original client contract;
`dispatch(ticket)` consumes only the original positive grant; `recover(transport_id)`
examines one grant without redispatch; `outcome(transport_id)` returns its separately
sealed worker evidence. `prepare_delivery`, `acknowledge` and `cancel` preserve the
existing subscriber semantics. Use the coordinator API; direct kernel mutation is
outside this protocol. A pending observation is explicit, not a successful response.

The worker adds an optional trusted-local lifecycle observer and SHA-256 capture
identity. Standalone calls still do not own broker dispatch authority. Private
capture directories, same-host process identity and SQLite/file-lock semantics are
assumptions. A privileged writer can rewrite every hash; this is not remote
cryptographic authentication. Permission errors are not interpreted as process death.

Per-grant ownership does not bound aggregate concurrent workers, queue depth or IP
request weight. Recovery is explicit per transport; no background service schedules
it yet. Diagnostic worker outcomes are separate from client preparation/acknowledgement,
not a complete client IPC envelope/service. Process startup and lock/serialization
costs still need complete admission/delivery replay. The earlier zero-overhead sharing
simulation cannot establish this implementation's timing or production savings.

| Alternative | Benefit | Trade-off |
| --- | --- | --- |
| Keep existing collectors | Preserves current study declarations and receipt continuity | Duplicate public requests remain |
| Qualified per-grant coordinator | Durable ownership and explicit partial/error recovery | Aggregate admission/client service still needed |
| Persistent/prewarmed service | May reduce measured startup overhead | Requires separate lifecycle, queue and failure qualification |

## Next investigation and authority

Highest-value next investigation: implement and qualify bounded aggregate admission
and complete subscriber IPC delivery, retaining explicit client temporal consent,
partial-status truth, loss of acknowledgement and actual process overhead. Declare
failure-aware workload and queue/budget policy before interpreting benefit. Unknown
shared-IP traffic remains unknown; do not install an arbitrary conservative budget.

Existing collector/study continuity and deployment need a separately reviewable
proposal and explicit approval. Independent offline implementation remains authorized.
Applicable market regime: none; this is research transport infrastructure and changes
no entry, exit, sizing, leverage, asset or regime-selection logic. No profitability
improvement or collector deployment readiness is demonstrated.

Falsifiers: duplicate dispatch under one grant, HTTP before matching admission,
lost known 429, fabricated worker/client time, partial bytes exposed as a response,
wrong-process recovery or failed reproduction reopens the corresponding qualification.

## Runtime continuity

At **2026-09-17 13:56:44 UTC**, backend 83722, reporter 18490, TUI 42506, five collectors
and three research jobs matched recorded process identities. Latest checkpoint was
`running_consistent`, 4,428 polls, zero faults. SNDK and Brent were open with recorded
protective stops. Collector health ages were 0.34–7.78 seconds. Live configuration SHA
remained `696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.

Native baseline/reproduction each reported 7,056 first-variant decisions; candidate
9,072. No failure or completed qualification result existed. Full source comparisons
and account qualification remain pending. The backend is already live; these are
research progress counts, not a go-live estimate. The continuous goal remains active.
