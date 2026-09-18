# Reproduced quarter-budget reservation gap before durable begin

Research finding, verified 2026-09-18 01:06 UTC. No deployment change.

The two exact frozen quarter-v2 collectors were each run in three private
SIGKILL/restart controls under OS network denial. A scoped profiler observed
their unchanged original `RequestBudget.acquire` and the portable journal's
`CollectorAttempts.begin`. Original clocks, source paths and recovery code were
retained. The parent killed only children it created after an fsynced checkpoint.

| Boundary, repeated for both source versions | Original memory weight | Durable weight after restart | Recovery |
|---|---:|---:|---|
| Before original acquire | 0 | 0 | Normal stopped run; no reservation |
| Successful acquire return, before durable begin | 21 | 0 | Normal stopped run; reservation absent |
| Durable begin return | 21 | 21 | Explicit unresolved-provenance fault |

All six controls had zero service admissions, subscriptions, transport dispatches,
raw responses, indexed requests and observations. These counts were independently
checked from SQLite and disk, not only from the runtime summaries. Recovery was
observed 441–457 ms after each checkpoint, so the lost reservation cannot be
explained by expiration of the original one-minute budget window.

High confidence for this reproduced boundary: a successful in-memory acquisition
can disappear from the new ingestion layer's durable accounting before `begin`.
This contradicts a broad claim that every post-acquire local obligation survives
process death. It does not contradict the narrower qualified claim for obligations
after durable begin. It also does not establish unrecorded venue traffic, missing
usable observations, abnormal live orders or capital loss: these controls reached
no service submission or transport.

Sources were authenticated before launch and again through retained source-import
hashes. The applicable frozen source IDs are 45939 and 51194. The probe result
SHA-256 is `1d22960e91f29d334d71eb8eca5fd0d937461b5e80d80e297578f7c11aeb46c7`.
Full scripts, checkpoints, original configs, databases and independent results are
under `data/logs/research/bidirectional_cohort/v89_public_collector_acquire_boundary_20260918_v1/`.

At 01:09 UTC, the same three probe scripts were reproduced byte-for-byte against
the exact archived `a575c2e` harness. All six boundary classifications matched,
adding six further actual SIGKILL/new-process controls. The archive result SHA-256
is `e1a6619f27929a8c264762a10c29592422570de56002c825505b8d7b4a79ba48`.
This strengthens reproducibility of the observed gap without estimating its
frequency in unattended operation.

## Highest-value next experiment

Qualify a successor that makes a local reservation durable before its successful
acquisition is exposed, then links it once to a later durable attempt. Retain
local reservations separately from service submissions and venue charges. Use a
new study namespace; do not migrate frozen collectors implicitly.

| Alternative | Benefit | Principal limitation |
|---|---|---|
| Keep the measured limitation | No adapter overhead or scheduling change | Cannot claim preservation across the pre-begin gap |
| Record only after acquire returns | Small observer change | A death between memory mutation and the new record remains possible |
| Persist at the reservation-storage boundary | Can cover the observed interval | Requires explicit commit semantics, deduplication, clock-domain and restart tests |

The third option is an experiment proposal, not a selected live implementation.
Investigate a narrow adapter around the original reservation storage and recovery
boundary while retaining the original capacity decision, weights and wait logic.
Do not reconstruct an actual request timestamp from nearby publications. Preserve
the sampled monotonic reservation time and identify its clock domain; same-host
process restart does not prove reboot compatibility.

Required tests: before/during/after reservation commit, before/after durable begin,
false acquisition and deadline refusal, exact rolling-window expiration, repeated
payloads, retry reservations, one-to-one attempt linkage, no duplicate restoration,
corrupted/missing evidence and changed clock domain. Include both exact original
quarter-v2 implementations, real SIGKILL/new-process recovery, original normal
loops, complete accounting reconstruction and exact-archive reproduction. Measure
added latency without extending request deadlines. Keep uncertain states explicit.

Expected benefit is stronger crash accounting and reviewable recovery; no return
forecast follows. A lost accepted reservation, double charge, fabricated HTTP
attempt, altered original capacity decision or unsupported clock conversion
falsifies the corresponding claim. Leaving the successor unadopted is the rollback.
Live strategy, assets, leverage, sizing, risk, execution and deployment remain under
the objective's explicit human-approval requirement. No live approval is requested
for this offline experiment.
