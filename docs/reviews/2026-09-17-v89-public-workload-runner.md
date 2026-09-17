# V89 physical public workload runner — qualification and pending comparison

Execution authority: **none**. The backend, TUI, five collectors, three native
research jobs and live configuration were not changed or restarted.

**Decision:** retain the tested offline runner and complete its already-running
three-arm comparison. Collector adoption, deployment and financial benefit remain
unqualified. This is a runner milestone, not a completed workload-benefit result.

## Scope and trace contract

The comparison retains all **113 original requests** (105 window requests and eight
warmup requests) from the authenticated September 16 21:45–21:55 trace. Each of the
five collectors has a separate spawned process and preserves its serial request
order. Original offsets run at wall-clock speed; the roughly 10.5-minute schedule
is not compressed. The response body and duration come from the actual original
leader's fixed record, never a favorable follower chosen after observing outcomes.

The independent arm uses the existing collector `_capture_once` function with a
fabricated session. The other arms use the complete service, spawned HTTP workers,
coordinator, process pipes, actual client reads and durable acknowledgements. Their
timing policies are strict admission and explicit 1000ms earlier-admission consent.
That opt-in is a proposed policy, not a claim about the current collectors' consent.

Each obligation is due at its translated original schedule time plus 10000ms.
Queueing cannot extend that deadline. This is an explicit comparison contract;
current collectors do not already have this service-client deadline contract.
Original candle availability plus 60000ms is reported as a separate freshness proxy.
Initial actor startup is measured separately; per-request child startup, SQLite and
IPC costs occur inside the request path. Five worker slots reflect the five serial
collectors. One preconnected peer per request bounds the finite harness at 113 peers;
this is not a production listener or a capacity recommendation. No weight quota is
installed. Unknown outside-IP traffic stays unknown.

## Findings and corrections before the full comparison

- A physical failure-fanout control confirms that a follower whose independent
  request succeeds can lose its response when it shares a failed leader. Reduced
  calls therefore need to be assessed alongside changed availability.
- The first full run stopped on two legacy metadata records. Their descriptive
  query omitted `dex`, while the authenticated wire payload explicitly named `xyz`.
  The runner had reconstructed the current query class's empty-dex default. The
  corrected adapter uses the explicit original payload only when the older query
  field is absent; conflicting explicit fields still fail. All 113 query payloads
  are now preflighted before starting actors. Source data was not changed.
- A separate clock-boundary control demonstrated that sampling time twice could
  generate a negative sleep when a millisecond boundary was crossed. The wait loop
  now samples the remaining interval once. This was an offline harness defect.
- Independent-verifier mutation controls initially exposed insufficient checking
  of indexed cost/freshness fields and unreported raw attempts. The verifier now
  recomputes accounting from authenticated payload/body bytes and checks artifact
  conservation, in addition to original deadlines, serial order and read receipts.

The failed first full run, its initial declaration, source archive and raw prefix
remain retained. Revised timing/worker/consent parameters were not tuned to obtain
a favorable result; the second declaration records the technical repair.

## Source and validation

Worktree: `/Users/gestas/Prototypes/hypervector-v89-public-workload-20260917`.
Branch: `research/v89-public-workload-20260917`.
Runner commit **b85936caff95a6a274cd28f54304c062cfe94484** is frozen in the second
declaration. Final source commit **8c6d1831fbb406e28c41669e7264af12c9fd1ff8** changes
only the accounting test fixture to meet the function-length standard; every
runtime/research module still matches the running declaration.

There are **44 passing focused controls** (38 together plus six accounting checks),
including real process/pipe paths, short deadlines, complete/partial 429, partial
200, connection failure, correlated failure, legacy metadata and clock boundaries.
The earlier combined candidate suite passed 366 controls before the additional
boundary/verifier/accounting tests. The first archive passes all **395** public
controls together. The final archive also passes all **395 controls together** in
103.60 seconds (`archive_v2_tests.txt`). An independent stdlib verifier authenticates
the three small complete physical arms from both candidate and final archive: three
requests each, all timely and body/status-matched. Physical timings differ. This
small-path verification does not substitute for the pending 113-request comparison.

Multiprocessing/thread coverage records **453/506 statements and 107/138 branches**
across the seven research modules: 89.53% statements, 77.54% branches, 86.96%
combined. Input validation covers 35/35 statements and 14/14 branches; independent
accounting covers 36/36 and 10/10. Do not claim full harness coverage. Unexercised
branches include CLI paths and defensive process/integrity failure guards.
Ruff, annotations, public docstrings, whitespace and file/function limits pass.
Tests and the full replay deny network and writes to live/runtime/research database,
configuration and installed source directories.

The final archive has **3,866 files**, **30,218,240 bytes**, SHA
`9a772ce6a0d8431aa2be7456873fcd1d26e2716559923388c6e852a1c80e6d0d`.
It contains tracked source/configuration/tests/tooling plus the specific plan,
rather than historical report archives. Each file matched its Git blob, worktree
and extraction; all 3,866 extracted files were rechecked after the tests. The seven
running research modules still match the second declaration. Preserve the archives
and selected test evidence after journaling.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_public_workload_20260917_v1`.
The active second-run log and output directory remain mutable and must not be pinned
as finished evidence. The immutable declaration SHA is
`50f6f5f21c7efd30b69d67fb08e5a626fbf440c92b7f84a7f74fbef7cc000fb0`.

## Limits, alternatives and recommendation

| Option | Supported opportunity | Unresolved cost or risk |
|---|---|---|
| Continue independent collectors | Preserves existing receipt and study continuity | Duplicate public reads remain |
| Strict service sharing | Enforces each original request's timing consent | Worker/IPC overhead may outweigh limited sharing |
| Explicit earlier-admission service | More overlapping identical requests may share | Changes consent and concentrates transport failures |

Confidence is **high for the exercised source, timing and accounting controls**,
and **unverified for full-workload benefit or live profitability**. An omitted
attempt, changed original payload/deadline, invented read/acknowledgement, or accepted
corrupted accounting would falsify the corresponding qualification. Additional late
or unavailable responses can make sharing unattractive even if calls decline.

The historical trace is development evidence, not a fresh holdout. All observed
trace responses were successful; synthetic fault controls supplement them. Mock
HTTP places the observed duration before headers because original header timing is
unknown. The experiment does not reproduce adaptive collector replanning, retries,
new venue response values, shared-IP competition, realistic rate-limit feedback,
or economic outcomes. It preserves every recorded attempt once rather than inventing
a different future request schedule. Local known weight is not global headroom.
Long-duration resource use, dynamic listener operation, collector receipt compatibility
and sealed-study continuity remain requirements before adoption.

**Highest-value next action:** verify the original process handle and finish all
three complete arms, then independently authenticate the results and compare calls,
body/status equivalence, actual delays, newly late responses and lost availability.
Do not restart on a polling timeout. A completed comparison must retain unfavorable
outcomes, and any harness repair requires preserved failed evidence and a new
declaration. No deployment approval is requested for this offline milestone.

At **15:30:55 UTC**, all 11 prior process identities matched, backend checkpoint was
`running_consistent` with 4,806 polls and zero faults, collector health ages were
8.36–18.28 seconds, and the live configuration hash matched. Native baseline,
reproduction and candidate reached 13,356 / 13,356 / 17,388 first-variant decisions
without failure or final-qualification artifacts. They remain active and untouched.
