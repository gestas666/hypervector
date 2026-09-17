# V89 bounded public HTTP worker qualification

Confidence: high for the tested component contracts, not for complete transport
coordination or economic improvement. No live, collector or strategy deployment.

Candidate **29f4d098ba8eb277476c640ecfcc70c168b99b6d**, branch
`research/v89-public-http-worker-20260917`, worktree
`/Users/gestas/Prototypes/hypervector-v89-public-http-worker-20260917`.
Parent is the qualified owned-clock revision **3252022**. The candidate only adds
research modules, tests, a verifier and a plan; existing broker code is unchanged.

## Observed problem and result

A streaming HTTP request can exceed a per-read timeout when bytes keep arriving.
A partially received HTTP 429 also needs to remain distinguishable from an unknown
status. The standalone worker now retains separate request, start, header-status,
terminal and supervisor observations, plus bounded decoded body bytes. A partial,
crashed or timed-out request has no consumable response body. Header-status evidence
survives a later stream failure. This is required input to the future coordinator;
it does not implement broker cooldown for partial 429 responses yet.

Every invocation uses a fresh spawned process and exclusive output directory, one
fixed-scope public Info request, no automatic retries or redirects, and a fresh
public session with environment proxy/netrc discovery disabled. No financial client
is constructed. The default Requests adapter retry count, empty credentials/cookies,
fixed URL, request payload and streaming options are tested without network access.
`Accept-Encoding: identity` is requested; retained bytes are explicitly decoded
entity bytes. A real Requests/urllib3 in-memory gzip control proves the retained
limit also applies when a peer sends compressed content.

The supervisor includes process startup in its monotonic timeout. It terminates,
then escalates to kill if needed, with two 250 ms cleanup allowances. A separate
child alarm bounds work after the child entry point and covers session setup,
streaming and cleanup. Its emergency exit code is 124. A physical control kills
the supervisor and verifies that its hanging worker stops independently, leaving
partial evidence and no fabricated terminal or supervisor receipt.

Development controls caught and repaired failed-spawn handle cleanup, repeated
cleanup attempts after an unkillable worker, inconsistent completion/error flags,
and invalid supervisor fields. The orphan control failed before the independent
child deadline was added. Unexpected errors propagate or remain explicit process
failures; exception messages are not copied into transport receipts.

## Validation

- **217 candidate + 217 archive tests pass**: prior 159 controls and 58 new controls.
- New modules cover **206/206 statements and 58/58 branches** with multiprocessing
  coverage enabled. This is measured source coverage, not exhaustive state-space proof.
- Real spawned processes exercise full responses, HTTP 429/307/503, connection and
  partial-read failures, oversized bodies, crashes before/after headers, cleanup
  failure, timeout, ignored termination signals and lost supervisors.
- Corruption controls reject changed files, deleted header evidence, changed receipt
  fields even after receipt rehashing, changed authority, invalid clock ordering,
  inconsistent completion claims, short writes and changed final body reads.
- Independent stdlib verification authenticates 15 candidate and 15 archived process
  captures, raw hashes, clock boundaries, status, availability and body lengths.
  Those outcomes and retained lengths match. Real timestamps and PIDs differ;
  these artifacts are not claimed to be byte-reproducible.
- Ruff, whitespace checks, explicit argument/return annotations, public-function
  docstrings and file/function size checks pass for the added Python files.

Archive: **3,698 files**, **29,112,320 bytes**, SHA-256
`82cd0fc018f19f68b45c0f9315b35a81a0af4be293cdd4ca9a352c5e26c3aec8`.
Every extracted file matches its Git blob and candidate worktree bytes.
Evidence: `data/logs/research/bidirectional_cohort/v89_public_http_worker_20260917_v1`.
Preserve both selected test artifact sets; do not reuse their pytest basetemp paths.

The instrumented candidate samples show **410–447 ms** before the child request
start; non-coverage archived samples show **354–379 ms**. These are fabricated
local process observations, not venue latency or a performance benchmark. They
invalidate applying the prior zero-IPC-overhead sharing simulation directly to
this implementation. Complete admission/delivery replay must include measured
process overhead before interpreting timing or request-load benefits.

## Limits, alternatives and next investigation

| Alternative | Benefit | Cost / remaining evidence |
| --- | --- | --- |
| Retain existing collectors | Preserves declared studies and current receipts | Duplicate public requests remain |
| Fresh process per request, qualified here | Isolated failure and independently bounded worker | Startup cost, filesystem work; no coordinator yet |
| Persistent or prewarmed workers | May reduce startup delay | New ownership, cleanup and crash controls required |

This is a trusted local macOS/Linux component, not an authenticated remote service.
Hashes detect inconsistent evidence, not a privileged writer rewriting every file.
Bounds apply to retained decoded bytes, not total interpreter memory. Full HTTP
header maps and raw compressed wire bytes are not retained; `headers.json` records
only the observed status and header-receipt clock. The storage helper does not
establish power-loss durability. OS scheduling, process creation, filesystem stalls
and uninterruptible processes prevent a hard real-time guarantee; an unkillable
worker raises an explicit error with its PID. The child alarm assumes its handler
is not replaced by injected code. A deliberately uncooperative test disables it
and verifies the surviving supervisor's kill escalation.

No durable dispatch claim, broker publication integration, aggregate admission
budget, shared subscriber IPC service or collector continuity plan is implemented.
Repeated standalone invocations with new directories are separate requests; this
API alone does not guarantee one dispatch per broker grant. A lost supervisor leaves
an incomplete capture requiring explicit later coordinator recovery, not a retry.
Partial 429 status must trigger cooldown independently of body completeness. An
unknown worker finish must not be replaced with a supervisor observation and then
called a transport receipt. Client delivery still needs the owned-clock adapter's
separate acknowledgement contract.

Highest-value next investigation: integrate durable one-grant dispatch ownership,
partial-status publication and abandoned-worker recovery; then qualify bounded
admission and complete process delivery against declared failure-aware workloads.
Use a new revision from this commit and preserve current evidence. Existing
collectors require a separately reviewed continuity/declaration plan and explicit
approval before deployment. No approval is needed for the next offline work.

Falsifiers: duplicate dispatch under one grant, a surviving worker beyond tested
bounds, body availability after incomplete transport, discarded observed HTTP 429,
altered scope, fabricated receipt time or failed reproduction reopens the relevant
qualification. This component provides no demonstrated profitability improvement.

## Runtime continuity

At **2026-09-17 13:13:34 UTC**, backend 83722, reporter 18490, TUI 42506, five
collectors and three native research jobs matched recorded process identities.
The latest checkpoint (13:12:42 UTC) reported `running_consistent`, 4,256 polls,
zero faults, open SNDK and Brent positions with recorded protective stops. Other
assets were flat. Collector health was fresh with no current errors. No process
was restarted or financial configuration/source changed.

Native baseline/reproduction had each recorded 4,032 first-variant decisions;
candidate 5,292. No failure or completed qualification result existed. Full source
comparisons and account qualification remain pending; these counts are technical
progress, not completed economics or a go-live estimate. The backend is already live.
