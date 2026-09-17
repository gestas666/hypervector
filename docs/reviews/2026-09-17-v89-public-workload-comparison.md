# Public workload comparison and frozen collector compatibility

The complete declared physical replay reduced fabricated HTTP calls from **113
to 102 with strict timing consent**, or **61 with explicit 1000 ms earlier consent**.
All three arms returned the same 113 status/body pairs within their original
10-second deadlines. Sharing added approximately one second of median delivery
delay. Confidence is high for these authenticated fixed-input measurements;
confidence in collector adoption or financial benefit remains unestablished.

No live strategy, order, configuration, collector, TUI or research job changed.
No sealed prospective economics were evaluated. The original workload process,
session 46959 / PID 59503, finished normally with exit code 0; the final client
completed at **2026-09-17 16:00:26.403 UTC**. It was not restarted.

## Measurement contract and results

The declaration SHA is
`50f6f5f21c7efd30b69d67fb08e5a626fbf440c92b7f84a7f74fbef7cc000fb0`.
It freezes execution source `b85936caff95a6a274cd28f54304c062cfe94484`, five
serial collector actors, five service worker slots, fixed original request
timing, and a ten-second deadline measured from original translated due time.
All 113 attempts are included: 105 window attempts and eight warmup attempts.
Original bodies and leader durations are fixed; process startup, worker startup,
SQLite, queues, pipe reads and acknowledgements are physically measured.
The mock delays headers because original header-arrival times are unavailable.

| Metric | Independent | Strict sharing | Earlier-consent sharing |
|---|---:|---:|---:|
| Fabricated HTTP calls | 113 | 102 | 61 |
| Same status/body and timely delivery | 113 | 113 | 113 |
| Known mock weight upper total | 2385 | 2152 | 1287 |
| Startup, ms | 1167 | 1583 | 1562 |
| Additional read delay vs paired independent, min / median / p95 / max, ms | reference | 463 / 1042 / 2372 / 2850 | 406 / 970 / 2467 / 2938 |
| Additional iteration delay, min / median / p95 / max, ms | reference | 477 / 1063 / 2389 / 2865 | 426 / 987 / 2487 / 2956 |
| Newly late reads / iterations | reference | 0 / 0 | 0 / 0 |
| Newly unavailable/non-200 or changed status/body | reference | 0 | 0 |

The p95 is the nearest-rank sample percentile. Paired delays subtract the measured
independent arm after translating each arm's anchor. They differ slightly from
delay against the original historical receipt: independent 1–11 ms, strict
464–2853 ms, earlier-consent 414–2944 ms. These are single sequential runs under
the existing machine load, without repeated-run uncertainty estimates.

`completed_ms` marks the end of the harness attempt, **not actual collector
ingestion**. Read time and durable acknowledgement remain distinct. Full timely
success requires both a timely response and its authenticated final acknowledgement.
The independent arm uses the common current single-attempt capture primitive;
it does not execute all five frozen collectors' full scheduling/recovery loops.

No adaptive retries, store-driven replanning, changing venue responses, live rate
feedback, unknown external-IP traffic, or long-duration service resource use are
represented. Known mock weight is not measured global-IP headroom. No weight quota
was selected or deployed. Prior physical failure-fanout controls remain relevant:
a failed shared leader can remove a follower's otherwise successful response.

## Verification and reproducibility

Comparison/probe source is committed as
`b60985097f9c3974f7655e7be8dc215ea2f3e6e6` on
`research/v89-collector-compatibility-20260917`. The comparator invokes the existing
independent verifier for every arm before checking declaration identity, worker
count, deadline, paired request identities, body/status and clocks.

Eight focused controls pass from candidate and final archive. Hand-calculable
controls separate timely reads from late iteration completion, retain lost
responses and reject missing/duplicated identities. Wrapper controls reject
changed input hashes and declared controls. The complete unmocked comparison
reproduces exactly from the archive. A synthetic peer projection also reproduces
except for its explicitly different source path. Ruff and file/function limits pass.
The earlier runner's 395-control archive qualification remains separate evidence;
that suite was not rerun for this stdlib comparison wrapper.

Final archive `source_v3.tar` contains 1468 files / 13,322,240 bytes, SHA
`061efac8744960e9d65e8c608c570e9c476cf5f5c6f37dab780172f1fc26db96`.
All archived files match committed blobs and the candidate, and were rechecked
after archive execution. Preserve earlier archives and failed logs: an initial
test edit misplaced duplicate-ID assertions; archive v2 omitted the transitive
service verifier and failed import. Both issues were corrected before final
qualification. No deployed code was involved.

Workload evidence:
`data/logs/research/bidirectional_cohort/v89_public_workload_20260917_v1/full_run_v2/`.
Comparison/compatibility evidence:
`data/logs/research/bidirectional_cohort/v89_public_collector_compatibility_20260917_v1/`.
The final `full_comparison.json`, `archive_v3_full_comparison.json`, archive
verification, source manifests, control logs and projection results are retained.

## Compatibility findings

The five active collectors use **five distinct frozen worktrees**. Every source
file named by their respective manifests matched on inspection. This corrects
any shorthand suggesting they all run the storage-SPCX build.

| Collector PID | Frozen worktree suffix | Manifest schema |
|---|---|---:|
| 43671 | v89-prospective-20260908 | 1 |
| 45939 | v89-storage-spcx-20260908 | 2 |
| 27818 | v89-followup-capture-20260916 | 1 |
| 51194 | v89-equal-cap-followup-20260923 | 2 |
| 44810 | v89-native-minute-continuation-20260916 | 1 |

Manifest schema and raw receipt schema are separate contracts. Older quarter-hour
captures omit dex in their query descriptor while retaining xyz in the wire
request. Their capture loop lacks the newer admission hook and permits three
attempts with one-/two-second retry waits. Newer captures support admission and
local cycle budgets. Native capture reserves one durable attempt per minute,
uses its own receipt cutoff, quarter-boundary blackout, peer checks and 429
cooldown, and prevents inner retries. Coverage-dependent scheduling is absent
from this fixed-attempt replay. A shared global cooldown could change existing
collectors' independent retry behavior.

Capture stamps receipt after the HTTP abstraction returns and before raw fsync
and ingestion. A transport adapter that waits for acknowledgement must retain
that actual return boundary; it cannot silently substitute an earlier pipe-read
timestamp. Deferral without an HTTP attempt, lost acknowledgement and shared
subscriber lineage require explicit versioned representation. Reusing original
study roots or ignoring their source manifests is not a qualified migration.

The unchanged native peer guard counts peer receipt rows as physical requests.
A synthetic four-peer probe with seven rows each produces 28 receipts and weight
588, withholding collection. Adding identical per-slot proposed shared-transport
tags changes nothing. Seven actual transports would illustrate weight 147, but
this fixture authenticates **no physical shared transports** and authorizes no
discount. Its tiny fabricated body exercises accounting, not ingestion. Current
independent collectors are counted correctly. A future adapter needs authenticated
transport identity and explicit subscriber accounting to avoid duplicate charging.

## Decision and next investigation

Retain the service as an offline candidate. The measured savings justify testing
collector compatibility; delivery overhead and unqualified adaptive behavior
prevent treating the replay as adoption or financial proof.

| Alternative | Benefit | Remaining cost or uncertainty |
|---|---|---|
| Keep current independent collectors | Preserves frozen study continuity | Duplicate request load remains |
| Strict sharing candidate | Eleven fewer mock calls | About 1.04 s median read delay; integration unqualified |
| Earlier-consent candidate | Fifty-two fewer mock calls | Requires explicit timing consent; about 0.97 s median delay |

The single next investigation is an **offline collector-adapter contract test**
using all five authenticated producer versions. Test actual API return, raw
receipt, durable acknowledgement, ingestion, adaptive recovery, retries, partial
200 responses, 429, deadline expiry, cancellation and native reservations. Require
authenticated transport accounting, retained local study budgets and independent
receipt lineage. Prove restart/continuity without changing original roots. Do not
retune quotas to make the experiment pass or accept untrusted deduplication labels.

A wrong original request/deadline, changed accepted source bytes, missing receipt,
fabricated earlier availability, accounting misattribution or newly lost/late
observation would update this assessment. No live change or approval is requested
at this stage; an eventual deployment needs a concrete validated proposal.

At 16:05:52 UTC, all eleven existing runtime/research process identities matched;
the backend was running consistently with 4945 polls and zero faults. Collector
heartbeats were 3.31–15.01 seconds old; live config hash was unchanged. Native
baseline/reproduction/candidate jobs had 15624 / 15624 / 20412 first-variant
decisions, with no failure or final qualification artifact. Their broader source
comparison and account handoff remain pending.
