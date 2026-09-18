# Worker deadline recheck: completed regression validation

The isolated successor `eb0ab69e07727a10bf242c01664fc35cc55c0a3f` corrects a
reproduced false timeout in research HTTP worker supervision. Candidate and
independently extracted source each passed 511 tests with four explicitly
opt-in sustained tests skipped. This qualifies the tested supervisor repair;
it does not qualify deployment or forecast trading returns.

## Observed defect and change

The preceding durable-reservation archive run retained a complete 1,101-byte
response and worker exit code zero, but classified it as timed out after
532.463 ms against an 8,000-ms deadline. This caused two collectors sharing
that response to retry. Durable reservations were disabled in that legacy
control. The failed run and its evidence remain retained.

A real-process probe reproduced an early stale `is_alive()` result after a
second thread reaped the child but before it published multiprocessing's
cached return code. The probe controls that publication interval; it does
not fabricate process status or elapsed time. High confidence in the
reproduced mechanism; medium confidence that this exact interleaving caused
the original uninstrumented failure.

The supervisor now repeats join/status checks within the original absolute
deadline. Process startup remains inside the timeout. True expiration,
termination/kill escalation, body validation and unavailable-response rules
remain enforced. Neither worker-pool serialization nor wider deadlines was
introduced.

## Evidence

Artifacts are under
`data/logs/research/bidirectional_cohort/v89_public_worker_deadline_recheck_20260918_v1/`.

| Validation | Working tree | Archived source |
|---|---:|---:|
| Full regression | 511 pass, 4 skip; 676.79 s | 511 pass, 4 skip; 685.66 s |
| Forced real-process race | 425.118 ms, exit 0, no timeout | 435.674 ms, exit 0, no timeout |
| Replayed failed workload: worker receipts | 35 | 54 |
| Replayed workload: false worker deadlines | 0 | 0 |
| Replayed workload: extra local API failures | 0 | 0 |
| Supervisor coverage | 53/53 statements, 10/10 branches | 53/53 statements, 10/10 branches |
| Durable reservation core coverage | 260/260 statements, 80/80 branches | Same |

The original API-late intervention remains unavailable exactly once in each
quarter-v2 collector in both replays; late data was not promoted to make a
test pass. The replay remains subject to actual scheduling, so physical
coalescing counts differ. All observed worker deadlines remained 8,000 ms.

The focused suite passed 58 tests, including genuine timeouts, ignored
termination, kill escalation, orphan handling and the actual reaping race.
Its retained red test failed before the repair. Both full-suite race children
and the two full-suite drivers were absent after completion. Every one of
5,802 tracked files matched in both source trees: 11,604 matches, zero changed
and zero missing. The compressed source backup is 33,857,987 bytes with SHA-256
`ec4ce2f421a01a9c83824dd99081af894f4bebb5f49f66eb7f6925fc0a6d1bd0`.

## Next experiment and decision

Retain this successor and perform sustained simultaneous operation with
`quarter_budget_reservation_version=1` explicitly bound into the study
declaration and each child configuration. Existing sustained studies leave
that option off and therefore do not validate the new local reservation
path. Require independent reservation-to-attempt accounting, original
quarter/minute schedules, health-read provenance, peer/native cooldowns,
ordinary stop, and exact-source reproduction. Any lost or doubled reservation,
early false deadline, suppressed real timeout, leaked child or accepted late
body falsifies the relevant claim.

| Alternative | Benefit | Cost or limitation |
|---|---|---|
| Retain old supervisor | No code change | Reproduced false timeout remains |
| Bounded status recheck | Resolves tested race within existing deadline | Sustained selected-mode validation remains |
| Serialize or widen timeout | Could hide symptoms | Changes concurrency/latency contract; not selected |

No live change is proposed at this stage. The backend, TUI, frozen original
collectors and long native comparisons retain their existing process and
configuration identities. At 02:24:09 UTC the backend reported 7,418 polls,
zero faults and a consistent running lifecycle. No economic effect is inferred
from this infrastructure regression result.

To maintain room for research, two unused historical release dependency
caches were removed only after complete compressed backup verification,
unchanged-source rechecks, zero open handles and zero direct journal pins.
Recovery manifests and commands are under
`data/backups/cache_compaction/compact_ops_deps_20260918T021930Z/` and
`data/backups/cache_compaction/native_account_release_deps_20260918T022110Z/`.
The running TUI executable and existing research evidence were preserved.
