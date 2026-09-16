# Authorized V89 backend restart — September 16

The user explicitly approved restoring live execution: `approve to unstop it`.
The existing V89 configuration was restarted as a standalone backend, with its
reporter attached to the new run. No strategy, assets, routes, sizing, leverage,
risk parameters or runtime source were changed by this restart.

## Observed result

Backend **67727**, born **14:46:18.755897 UTC**, owns run
`bidirectional-live-1789569979897`. Its first observed live heartbeat was at
**14:59:17.463847 UTC**. At **15:04:09 UTC**, two independently refreshed
checkpoints showed `running_consistent`, healthy backend, zero faults, all seven
provider/asset pairs present, six flat assets and the protected Brent short.
The second checkpoint contained 20 completed poll cycles. Startup took about
13 minutes, primarily while backing up and reading retained ledger history;
that observation is not a promised duration for future starts.

Brent was adopted at **14:58:34.260935 UTC** with the original short size **4.9**,
entry OID **546683502888**, stop OID **546683530230**, original opened-at clock
and complete execution plan. The retained startup prefix contains no new order
intents, order acknowledgements or cancellation intents. Unsigned venue checks
before launch and during initialization found the same 10x isolated short and
full-size reduce-only stop open at **103.18**. Later backend reconciliation also
reported it protected. These observations do not guarantee future venue state.

## Backup and validation

- **86 tests passed** in 1.95 seconds across startup ownership reconciliation,
  protective restart guards, binary launcher and pre-start backup tests.
- A non-mutating native ownership check using current venue receipts and retained
  ledger tails returned six `flat` dispositions and Brent `restore_open` before
  launching. Normal startup subsequently ran the complete native checks.
- The startup backup verified with `strategy_changed=no`, 1,929 implementation
  files, and the same profile fingerprint as the stopped run.
- Fresh checkpoints at **15:01:54.393788** and **15:03:37.212817 UTC** bind the new
  run. The latter was 31.89 seconds old when its acceptance was recorded.
- The installed binary was exercised in a separate read-only 170x45 terminal.
  Portfolio, setup and regime views rendered; all nine acceptance checks passed,
  including `LIVE EXECUTION ARMED`, `RUNNING CONSISTENT`, `LEV C/V`, Brent
  `10x/10x`, and stop 546683530230. That test TUI quit with exit code zero and
  preserved the financial backend process identity.

Backup:
`data/backups/bidirectional_cohort/prestart_20260916T144619.897627Z_39e334fc97f3/`.
Manifest SHA256:
`9a9cdc6899d0fe67f4a392c2d0a12e9f45d8630a62149443435345ac800b0404`.
Implementation SHA256:
`0d830a407b46e766b7bb3dfcbd23c6c2aa7d03df41b769f1fd905aa9ed646164`.
Profile fingerprint:
`39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.

## Process ownership and limits

Reporter **6596**, born **15:00:39.457270 UTC**, is explicitly bound to the new
run. Existing read-only TUI **42506** and its original monitor parent remain open.
The prior reporter 42503 was bound to the stopped run; it received SIGINT and
released its writer lock. A non-child wait timed out because its original monitor
parent has not yet reaped the exited process. Its observed zombie state and free
writer lock were verified before starting the replacement. The existing monitor
may report that old reporter's interrupted exit when it later quits. This does
not stop the independently running backend or replacement reporter. A subsequent
normal monitor launch can attach to the active writer.

The first terminal-capture harness rendered the three views but stopped draining
PTY output while waiting for quit. Closing that test PTY ended only its read-only
child. A corrected harness drained output through a verified zero exit; both
attempts' captures remain retained. This was not attributed to a trading fault.

The original backend's 13:38 UTC stop was recorded as `operator_stop`; the initiating
person/action remains unverified. This restart has no automatic relaunch service.
Closing the read-only TUI leaves the standalone backend running. Process death,
stale heartbeats, new faults, missing protection, wrong run identity or different
source/configuration hashes require renewed operational validation. High confidence
is limited to the observed restart and reporting acceptance; no claim of bug-free
operation, future profits or research-candidate qualification follows from it.

Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_authorized_restart_20260916_v1/`:
`backend_launch.json`, `recovery_precheck.json`, unsigned response receipts,
`backup_manifest_verified.json`, `brent_native_startup_prefix.json`,
`reporter_reattach_intent.json`, `reporter_launch.json`,
`running_checkpoint_first.json`, `running_checkpoint_second.json`,
`live_acceptance.json`, and `tui_capture_validation_v2.json`.
