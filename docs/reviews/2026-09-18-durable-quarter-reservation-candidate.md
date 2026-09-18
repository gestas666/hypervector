# Durable quarter reservation candidate and newly exposed supervisor defect

Research review, 2026-09-18 02:02 UTC. No live deployment change.

The original successful-acquire/pre-begin failure is repaired in the isolated
candidate `d5de1628e02f61bffed5bda7776e5364684edb82`, on pushed branch
`research/v89-durable-quarter-reservations-20260918`. This is a bounded accounting
result, not full qualification: an existing worker-supervisor defect caused one
archive regression failure and is the next investigation.

## Verified reservation behavior

Both exact frozen quarter-v2 source versions retain their original capacity,
weight, rolling expiry, waiting and acquire implementation. An owned deque
adapter commits the original monotonic reservation before exposing its memory
append. A separate exact binding associates that reservation with the subsequent
attempt identity before durable HTTP begin. Local obligations are not labeled as
HTTP submissions, venue charges or usable observations.

Same-boot recovery restores exact monotonic timestamps once. It rejects a changed
clock domain, missing/corrupt evidence, duplicate binding, inconsistent begin, or
an attempt to omit the initially selected recovery version. A caught persistence
fault cannot continue with inconsistent memory. Pre-begin bindings without an
HTTP begin remain local obligations; unresolved actual attempts retain the
existing explicit recovery fault.

The original scoped acquisition probe was replayed against candidate and exact
archived bytes: six actual SIGKILL/new-interpreter controls per source tree, with
all six classifications matching. For both original collector versions:

| Original boundary | Durable local weight | Durable HTTP weight | Restored memory |
|---|---:|---:|---:|
| Before acquire | 0 | 0 | 0 |
| Successful acquire, before begin | 21 | 0 | 21 |
| After durable begin | 21 | 21 | 0; unresolved-attempt fault before restore |

All probe controls retained zero service admissions, subscriptions, physical
transports, dispatches, raw responses and indexed observations. Candidate recovery
was observed 428–460 ms after suspension, below the original 60-second expiry.
The raw database and source hashes were independently checked. Additional tests
kill both exact original versions before/after reservation commit, after binding,
after begin, after raw fsync, and after indexing: 12 cases per full suite.

The final focused run passed 66 tests under OS network denial. The three new core
modules cover 260/260 statements and 80/80 branches. The candidate full suite
passed 453 tests with four skips in 441.53 seconds. Exact-archive full replay had
452 passes, four skips and one failure in 446.21 seconds. This failed replay has
not been relabeled as a pass or discarded. Coverage does not prove all schedules,
operating systems, power-loss behavior or market conditions.

The source archive contains 5,799 files. Post-run verification matched all 11,598
candidate/archive file checks with no missing or changed bytes. Archive SHA-256:
`00f067516e841f36f40b9e935f07eed7346547bdb47134d7aa1eafb769a08cfc`.

One hundred measured real-clock pairs, after five warmups, found median added
acquire overhead of 326 microseconds and median exact-binding overhead of
332.458 microseconds. Every sampled one-second acquisition deadline remained
unchanged and unmet by completion. These fresh-namespace measurements exclude
network, saturated-budget and runtime-checkpoint IPC latency; they are not a
production deadline guarantee.

## Archive failure and next investigation

The failed late-response test expected one deliberately unavailable response but
observed an additional unavailable retry shared by the two quarter-v2 collectors.
The failed case did not enable durable reservations. Its existing supervisor
recorded `WorkerDeadlineExceeded` after 532.463 ms despite `timeout_ms=8000`, a
complete 1,101-byte response, a terminal record with no transport error, and exit
code zero. Both subscribers correctly inherited that erroneous unavailable
classification; original retries then completed.

The unchanged supervisor treats `child.is_alive()` after a single `join()` as
proof of deadline expiration. Local Python 3.13 multiprocessing code can return
an interim unknown status if another thread has reaped the child but has not yet
published its cached exit code. The service runs workers from a thread pool.

A deliberately scheduled probe used an actual spawned child, actual successful
`waitpid`, and original supervisor/process method results. Delaying publication
of that reaped status reproduced the false deadline in 431.725 ms with exit code
zero. High confidence that this interleaving can cause the observed defect;
medium confidence that it uniquely explains the uninstrumented archive event,
whose exact thread interleaving was not captured. The first probe failed during
spawn because local instance-method wrappers were not picklable; its failed
driver and the corrected class-scoped probe are both retained.

Highest-value next experiment: recheck child status within the unchanged absolute
timeout, rather than converting an early join/status race into a deadline. Test
the real race, normal exit, genuine timeout, termination and kill escalation,
then replay the failed original workload and broader candidate/archive suites.
Do not weaken the assertion that unavailable receipts cannot become observations.

## Decision and limits

Retain this as an offline candidate pending the supervisor repair and complete
integration qualification. Expected benefit is accurate crash accounting and
fewer incorrectly discarded research responses; no return forecast follows.
The applicable domain is collector/research infrastructure, independent of market
regime. The alternatives remain keeping the documented gap or logging only after
acquire, which leaves a smaller version of the same gap. New persistence adds
disk latency and explicit recovery evidence requirements.

Lost committed weight, duplicated recovery, invented HTTP state, changed original
capacity decisions or changed deadlines falsify the respective candidate claim.
Leaving the candidate unadopted is rollback. No live strategy, asset, leverage,
sizing, risk, execution, deployment or TUI change is proposed in this review;
no live approval is requested. Full continuous-system objectives remain active.

Artifacts are under
`data/logs/research/bidirectional_cohort/v89_public_collector_durable_reservations_20260918_v1/`.
The initial acquisition-probe driver failed to service newly introduced checkpoint
handshakes; its failure is retained beside the corrected candidate/archive probes.
The completed prior health-source extraction was verified against its journaled
archive and removed only after confirming no direct evidence pins or open handles.
The archive and exact restoration command remain retained; measured free space
increased by 233,156,608 bytes. Frozen collector source worktrees remain intact.
