# Mapped reporting snapshots: deployment proposal

Recommendation: deploy reporting reader revision `7a30d04`, then replace only
the checkpoint reporter. Status: offline accepted, deployment approval pending.
The production checkout and running reporter still use the prior reader.

Why now: the existing reporter wrote 3.63 GB in a measured 15-minute interval.
The first memory-buffer candidate reduced writes but accumulated memory and
was rejected. The replacement uses anonymous mappings that are closed after
parsing, with temporary-file spill above the 128 MiB raw snapshot limit.

Observed problem: repeated snapshot copies create avoidable reporting I/O.
This proposal makes no claim about increasing trade frequency or profitability.
Applicable market regime: independent of market regime; reporting only.

## Evidence and validation

Frozen acceptance record:
`data/logs/research/bidirectional_cohort/v89_mapped_snapshot_acceptance_20260908_v1.json`.
Candidate source archive:
`data/logs/research/bidirectional_cohort/v89_mapped_snapshot_source_7a30d04.tar`.
Paths in this document are relative to `/Users/gestas/Prototypes/hypervector`
unless explicitly qualified.

| Check | Observed result |
| --- | --- |
| Offline regression suite | 148 passed; both snapshot I/O modules have 100% statement and branch coverage |
| Complete checkpoint comparisons | 25 files across two frozen fixtures; all matched their respective baseline |
| Median physical writes, three independent runs | 150,671,360 to 2,781,184 bytes; 98.154% reduction |
| Median elapsed time including imports | 4.632 to 4.672 seconds; no speed advantage claimed |
| Eight publications in one process | Candidate peak 1,127,104,512 versus baseline 1,131,364,352 bytes |
| Eight-publication physical writes | 22,249,472 versus 1,189,576,704 bytes |
| Forced spill with isolated 32 MiB limit | One spill file, closed after use, complete output matched |
| Fresh fixture at 06:08:45 UTC | Four fills and one closed trade; complete output matched |
| Frozen candidate package | 1,338 Python source hashes verified against measured source |

Validation denied network access in benchmark processes and retained input and
source hashes. The 18.1-second baseline timing outlier remains in the evidence.
Physical writes measure process I/O, not net disk allocation. The unexplained
whole-filesystem capacity swings remain a separate unresolved observation.

## Alternatives and trade-offs

| Alternative | Benefit | Cost or limitation | Decision |
| --- | --- | --- | --- |
| Keep existing disk snapshots | No deployment | Existing snapshot write load continues | Available fallback |
| Previous heap-buffer candidate `00237bb` | Lower writes | Repeated-process memory growth | Rejected; preserve evidence |
| Mapped reader `7a30d04` | Lower writes with baseline-comparable measured memory | Added I/O implementation and deployment validation | Recommend |
| Change trading frequency or sizing | Different financial behavior | Outside this storage hypothesis and its evidence | No recommendation here |

Expected upside: materially less checkpoint snapshot I/O for snapshots below
the memory limit. Raw storage is bounded per snapshot; decoded history still
grows with the run. Eight fixed-prefix publications do not establish indefinite
memory stability. Larger snapshots spill to disk and can reduce the benefit.

## Concrete change and backup

Prepared bundle:
`data/logs/research/bidirectional_cohort/v89_mapped_snapshot_deployment_20260908_v1/`.
Its `maintenance.json` records candidate and prior hashes, prior file absence,
process lifetime identities, configuration and TUI hashes, and reporter arguments.
`candidate/` contains six source modules and two test files. `prior/` contains
the four existing files; four new paths were absent. `observer_owner.py` is an
exact copy of the existing read-only reporter owner. No new owner has started.

The changed modules are `paper/report.py` and research modules
`checkpoint_ledger_projection.py`, `cohort_live_checkpoint.py`,
`live_ledger_snapshot.py`, `ledger_snapshot_io.py`, `mapped_snapshot_file.py`.
The first four retain parsing/projection behavior while supporting streams;
the last two own the bounded storage and cleanup. Tests are
`test_memory_ledger_snapshot.py` and `test_mapped_snapshot_file.py`.

## Deployment runbook, after approval

1. Verify every bundle hash and the live prior hashes. Verify the recorded
   backend, supervisor, TUI, collector, and reporter PID start times and parents.
   Stop this procedure if they differ; do not infer identity from a reused PID.
2. Verify configuration hash, reporter script hash, TUI binary hash, run ID,
   current position/fill/stop state, and a fresh healthy checkpoint. Preserve
   that checkpoint and process snapshot in a new deployment record.
3. Wait for research sync to be ready, not in progress, with its actual success
   timestamp less than 40 seconds old. Record the approval separately. Confirm
   the new bundle has no `started.json` or `finished.json` before launching it.
4. Send SIGINT only to the identity-verified report-only child, currently PID
   48897. Wait for it and its owner, currently 48894, to exit. If they remain,
   stop the procedure and diagnose; do not launch an overlapping reporter.
5. Atomically install only the eight listed candidate files. Recheck hashes.
   Launch the copied `observer_owner.py` once using the existing interpreter,
   repository working directory, detached session, and retained log output.
   The owner uses the existing reporter arguments recorded in the manifest.
6. Verify the replacement owner and reporter identities, and a new checkpoint
   generated after startup for the same run and configuration. Reconcile any
   intervening real trades against the ledger rather than expecting positions
   to remain frozen. Confirm health, stop coverage, and successful research sync.
7. Open a separate `cohort-tui --mode monitor` to verify checkpoint freshness,
   visible fills, positions, costs, stops, and expected panes. Do not quit or
   replace the original supervising TUI as part of this procedure.

The backend (4965), supervisor (4954), original TUI (8440), and prospective
collector (75062) are outside this procedure's process-control scope. Trading
configuration, execution clients, venue orders, STOP files, and command queues
are outside the change. No live arming command is part of the bundle.

## Remaining validation and rollback

Success metrics: fresh same-run checkpoints, correct trade and protection
data, healthy reporting and sync, visible monitor data, and reduced physical
writes with no candidate-specific sustained resident-memory growth. Measure
the replacement through at least eight publications and a 15-minute process
I/O observation; retain raw results and ledger sizes to interpret growth.

Technical rollback triggers: parser/cleanup failure, reporter exit, wrong run
or configuration, unexplained missing or changed economic fields, checkpoint
staleness beyond two reporting cycles, new sync failures attributable to the
replacement, or reproducible candidate-specific memory growth.

Rollback only the replacement reporting process and the eight installed files.
Verify its process identity before stopping it. Restore existing files from
`prior/`; remove a newly added path only if its hash still equals the installed
candidate and its backed-up candidate is verified. Preserve logs and failed
checkpoints. Restart the prior reader with the same read-only reporter arguments
from a fresh owner directory, using the saved prior owner source and manifest.
Do not reuse a directory with `started.json`, and do not run two reporters.
Recheck freshness, run/configuration identity, and reporting health afterward.

Confidence: high for the measured output parity and I/O reduction; moderate
for long-lived live-process behavior until post-deployment observation passes.
Any output mismatch or reproducible additional memory growth falsifies the
acceptance claim and requires a new diagnosis. TUI visual acceptance remains
pending; these storage tests do not prove that missing panes are repaired.

Explicit approval requested: install this reporting-only revision and replace
only its checkpoint reporter using this runbook. The continuous-agent brief's
Human control clause requires approval before deployment configuration changes.
