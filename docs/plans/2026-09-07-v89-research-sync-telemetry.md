# Research sync telemetry implementation plan

> Execute task by task using the executing-plans workflow. Existing user
> authorization covers this report-only correction; routine review checkpoints
> do not require another approval question.

**Goal:** Show research import failures, progress and the last successful import
in the cohort TUI independently of trading-backend health.

**Architecture:** Preserve sync state separately from consumable log messages.
Pass its snapshot through checkpoint publication before the existing atomic
write. Validate and render that optional report-only section in the Rust TUI.

**Tech stack:** Python reporting worker, JSON checkpoints, Rust/Ratatui.

## Evidence and scope

Previous goal turn: progress. The recorded-native comparison was completed,
audited and journaled. The full research/improvement/live-readiness goal remains
active. No blocker streak applies.

The measured September 7 outage was caused by the existing 8 GiB free-space
requirement. Disk recovery restored imports, but `_log_background_sync` consumes
the error via `pop_error`, and `_publish_real_snapshot` receives no sync status.
`CheckpointDocument` consequently has no research-import field to render.
Confidence is high in this traced omission. Failure/recovery tests will falsify
the proposed correction if an error disappears before a successful import.

Use the dedicated `hypervector-v89-sync-20260907` worktree from `a42afa8`.
Preserve the completed research worktree and its source hashes. Do not restart,
arm, disarm or submit anything through the order backend.

## Task 1: Durable sync state

Files: new `src/hypervector/research/cohort_research_sync_telemetry.py`;
modify `cohort_background_sync.py`; add `tests/test_cohort_research_sync_telemetry.py`.

1. Write failing tests for initial state, running import, disk deferral,
   worker error, log consumption, retry and successful recovery.
2. Run the focused tests and preserve the failing output.
3. Add a typed report-only status object with state, last attempt/success time,
   age, current error and imported-event count. Inject the clock for tests.
4. Keep scheduling and disk requirements unchanged. A retry must retain the
   unresolved error until success. Missing prior success is unavailable, not zero.
5. Run new tests and the existing disk-headroom/background-sync tests.

## Task 2: Atomic checkpoint propagation

Files: `scripts/multi_asset_bidirectional_live_checkpoint.py`,
`src/hypervector/research/cohort_rolling_checkpoint.py`,
`src/hypervector/research/cohort_live_checkpoint.py`; focused checkpoint tests.

1. Test that continuous and one-shot publication carry the same status that
   logging observes, including a failed import and current-run-only mode.
2. Add an optional `research_sync` mapping through the publisher interfaces.
   Attach it before the existing atomic write; do not patch a published file.
3. Keep log events consumable without clearing the durable status. If needed,
   move existing logging helpers to one module to respect file-size limits.
4. Test omitted legacy status, failure/recovery propagation and cached-history
   refresh. Sync status has no routing, sizing, execution or restart authority.

## Task 3: TUI projection and display

Files: `backend_cohort_checkpoint.rs`, `backend_cohort_checkpoint_projection.rs`,
new sync projection/view modules, `cohort_view.rs` and focused Rust tests.

1. Write failing tests for valid states, malformed explicit status, absent
   legacy status and compact terminal rendering.
2. Project backend-authored values. Show last successful import as a time/age;
   do not equate successful import time with the newest source candle time.
3. Display unresolved import errors prominently while preserving armed state,
   backend health, current telemetry and navigation. Legacy absence is unreported.
4. Check 100x28 and 120x36 layouts, including long error messages and recovery.

## Task 4: Verification and report-only refresh

1. Run relevant Python tests, Rust format/clippy/tests and captured real-checkpoint
   rendering. Use existing build storage so verification does not recreate the
   disk shortage. Confirm free space remains above the import requirement.
2. Preserve source/binary/reporting ownership evidence before any reporting
   refresh. Update only report-only components; leave the order backend intact.
3. Verify the running publisher emits the new section and the rebuilt monitor
   renders the same state. Source tests alone do not prove live display adoption.
4. Journal the measured result, limitations and rollback. Revert only this
   reporting correction if it corrupts checkpoint publication or existing panes.

No strategy, cost, parameter or allocation recommendation is made by this plan.
Independent strategy validation and prospective execution evidence remain open.

## Source acceptance result

Tasks 1–3 passed: durable failure/recovery evidence reaches the atomic document,
and all nine views display it without consuming existing body rows. The initial
extra-header approach failed two layout tests and was replaced by a footer title.
The new long-error test compares the retained body directly with the legacy view.

Validation before reporting refresh: 80 focused Python tests passed; the tracker
has 100% statement coverage and the background worker 90%. The full offline
Python run had 7,791 passes and 275 failures. All 275 failing nodes reproduced
in an unchanged `a42afa8` checkout; missing local evidence/model/vendor fixtures
prevent an all-green full-suite claim. Five checkpoint tests passed again after
the final formatting-only reduction of the rolling publisher to 48 lines.

The Rust suite passed 507 tests with 23 explicit opt-in tests ignored. Its V86
acceptance fixture was copied from the original checkout and hash-verified after
the missing-fixture failure reproduced on the unchanged baseline. Clippy with
warnings denied, format checking, and release compilation passed. Shared build
artifacts retained a baseline library after the comparison; touching the candidate
library entry point forced recompilation before these final Rust results.

An explicit read-only integration run rendered 27 actual-ledger screens at
100x28, 120x36 and 190x52. The one-shot capture deliberately omitted the database
and correctly showed IMPORT DISABLED; it did not replace the active checkpoint.
Continuous reporter adoption and actual successful-import display remain the
final Task 4 acceptance steps.

Task 4 subsequently passed. Main received the reporting correction as `2986216`.
Only the old report-only worker was stopped; the replacement imported 38 and
then 288 events. Its new section reached the active checkpoint. A further 27
actual-checkpoint captures passed, and the installed release binary displayed
IMPORT OK, import age/count, seven assets and LIVE EXECUTION ARMED in a 120x36
terminal. Quitting that separately owned detached monitor returned zero while
the original supervisor, backend and TUI retained their process lifetimes.
The original foreground TUI still uses its existing binary; open a new monitor
to use the updated display. See the accompanying review for evidence and rollback.
