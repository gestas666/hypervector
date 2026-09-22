# V91 deployment and rollback contract, revision 2

User authority: the active request explicitly calls for the corrected aggressive
eight-asset version live and trading. Transition drain was explicitly authorized.
All changes are staged and reviewed in `hypervector-v91-adaptive-exits-20260922`.
No new permission checkpoint is implied by this runbook.

1. Require focused adaptive/recovery tests, legacy regression tests, full Python
   non-network suite and Rust suite. Record failures and repairs before deployment.
2. Require exact V90-to-V91 approval validation and unchanged hashes for every
   main-checkout file to replace. Preserve the 84 pre-existing dirty files; deploy
   only differences introduced after the recorded baseline. Back up original
   files, plists and supervisor journal with a manifest before writing.
3. Verify the old run `bidirectional-live-1790053305835` completed drain and both
   owned processes exited. Independently refresh unsigned venue flat/order-free
   truth and sizing. Use the existing archive command against that exact run;
   keep its authenticated completed-drain evidence.
4. Stop the loaded, already-exited supervisor service before archiving its held
   restart journal. A changed command requires an explicit archived boundary;
   never reset a live process's budget. The new durable session marker prevents a
   failed stop write from granting a later supervisor a fresh launch.
5. Deploy reviewed source/config/model files and point supervisor/checkpoint
   plists to `configs/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml`.
   Supervisor `ExitTimeOut` is 60 seconds, exceeding the child wait of 30.
   The host experimentally caps 180-second requests at 60. Persist the operator
   stop before waiting; poll sleep is interruptible at one-second intervals.
   Keep read-only roster/watch services running or reload their repaired code.
6. Start the exact profile with `--enabled --i-accept-live-risk` through the
   installed supervisor. Existing startup performs its full backup, profile-change
   approval, archived flat boundary, live reconciliation, ownership and candle
   validation. Let it finish; do not bypass or kill it to shorten startup.
7. Verify the actual loaded command/timeouts, new profile fingerprint and source
   identity, authenticated backup, no competing owner, healthy heartbeat, all
   eight executable symbols and fresh canonical/book telemetry. Model forecasts
   are report-only and appear when a lifecycle is evaluated. Natural valid entry
   signals are required; do not send a manual order to manufacture acceptance.

Rollback preserves live ownership. If no new position exists, use the normal
drain/stop path, verify venue flat and order-free, and restore exact backed-up
files/plists with appropriate profile transition evidence. If V91 holds exposure,
retain V91's bound exit policy and native protection until its drain completes;
do not hot-revert the controller or overwrite its durable observations. A
technical fault is surfaced and recovered using existing exact order receipts.

Trade-offs: software profit floors can execute below their threshold during
polling/venue gaps. A displayed floor is not a guaranteed fill or net profit.
Healthy trends get a wider allowance but still ratchet protection; cut winners
remain an expected cost. All-eight authority increases aggregate possible
exposure. The ML comparison did not validate model-controlled exits, so the
model cannot suppress or relax any trading rule.

Deployment results and exact backups belong in the dated V91 operations manifest
and acceptance report. This file is the immutable procedure referenced by approval.

Revision 2 supersedes the original timeout requirement after real launchd
inspection and isolated probes showed requested 45 -> loaded 45, requested 180
-> loaded 60. The initial V91 attempt was gracefully stopped during its
pre-start backup, before a new configuration/heartbeat or order authority was
published. Preserve that incomplete backup and restart journal. This correction
does not change the candidate profile, allocations, exit parameters or authority.
A hung child is never force-killed by the supervisor: after 30 seconds it records
a stop-incomplete hold. Native protection remains; the independent watcher
continues to expose the still-owned backend. The durable session reservation
retains a hold if the supervisor itself is killed before stop completion.
