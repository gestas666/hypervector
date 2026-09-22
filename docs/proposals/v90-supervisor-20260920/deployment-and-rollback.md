# Cohort monitoring, research capture and restart deployment

Revised 2026-09-20. Implementation is staged in an isolated checkout. Deployment
is authorized by the operator **when flat**; V90 allocation remains a pending
proposal. Consult
`docs/reviews/2026-09-20-v90-monitoring-capture-acceptance.md` before rollout.

## September 21 deployment and hold

Read-only services and the reviewed 37 maintenance files are deployed with an
exact backup. Observer capture survived restart; checkpoint follows the latest
complete V89 run. The backend supervisor remains unloaded because the operator
requested corrected profit protection and V90 readiness before trading resumes.
Do not follow the earlier V89 restart instruction below during this hold.
The completed drain remains installed. Use `v90-activation.md` and the corrected
protected V90 review for the final transition after its separate decision.

## Components and authority

- `hip3_roster_observer.py`: unsigned account/market telemetry; no signer or orders.
  Its existing `metaAndAssetCtxs` request also writes public premium/oracle/mark,
  funding and universe metadata to daily research JSONL files. It records nulls
  explicitly, preserves history across restarts and reports failed polls as gaps.
- `cohort_backend_supervisor.py watch`: reads files/process identity and reports
  unavailable, stopped, malformed or stale observations. It does not restart the
  backend or alter entries. Local notification and journal sinks are enabled.
- `local.hypervector.cohort.checkpoint`: supervises the read-only checkpoint
  writer with `--follow-latest-run`. It selects the latest complete live snapshot
  matching V89's profile identity on each refresh, and keeps publication bounded
  to that run. It refuses a conflicting explicit run pin or another profile.
  This replaces the old manually launched writer pinned to a single run.
- `cohort_backend_supervisor.py supervise`: forwards the exact supplied command;
  its supplied plist names **V89**, with both explicit live-arm flags. This is
  process-restart authority. It does not approve or activate V90.
- Supervisor support modules remain under `scripts/`, outside the implementation
  source hash. The research-capture extension changes `src/hypervector`, so deploy
  it only at the approved boundary with an exact file backup.

## Restart policy and persistent state

| Event | Result |
| --- | --- |
| Existing backend, no `--adopt` | Refuse a competing owner |
| Existing backend, `--adopt --adopted-exit-policy hold` | Observe; hold when it ends |
| STOP exists before launch | Persist hold; do not spawn |
| Owned child exits 0 | Persist operator/bounded-run stop |
| Owned child exits 2 | Persist technical hold and continue alerting |
| Other owned-child exit | Back off and retry within the durable allowance |
| Five restarts within six hours | Persist exhausted hold; no further child launch |
| Corrupt journal or different command digest | Refuse launch |
| Hung but alive child | Alert; no automatic kill |

An exclusive supervisor lock covers startup, adoption and backoff. Every launch
is reserved on disk before spawning. `supervisor_events_restart_state.json`
retains the command digest, timestamps and terminal hold. Launchd restarting the
supervisor does not reset this state. An explicit operator-reviewed recovery may
archive the state file **after verifying no backend or supervisor owns it**;
retain the archive rather than deleting evidence. A new command needs its own
approved identity and an archived previous journal.

## Boundary and installation

1. Finish the tests and code review. Verify the current source hashes against the
   staging baseline so unrelated edits are preserved.
2. Confirm fresh backend and unsigned venue evidence: all positions zero, all
   owned orders absent, no unresolved execution, and the old owner safely stopped
   before handing restart ownership to a new supervisor. A checkpoint alone is
   insufficient. If a drain is authorized, preserve strategy exits and protection;
   do not market-close positions just to accelerate this maintenance.
3. Back up every changed source file and installed plist, plus the current roster
   snapshot and operational state. Record SHA-256 hashes and exact source/target
   paths in a deployment manifest. Existing live ledgers remain untouched.
4. Apply the reviewed files. Precreate `data/runtime/research` and
   `data/runtime/bidirectional_cohort`, because launchd log paths need parents.
5. Retain the existing checkpoint writer's arguments and checkpoint, terminate
   that exact read-only owner, and verify writer-lock release. Install the
   checkpoint, roster observer and watch definitions. Use the modern lifecycle:

   ```bash
   launchctl bootout gui/$(id -u)/local.hypervector.research.roster_observer
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.hypervector.research.roster_observer.plist
   launchctl print gui/$(id -u)/local.hypervector.research.roster_observer
   ```

   Boot out only if that exact service is loaded; absence is not a failure to hide
   behind a catch-all. Repeat for `local.hypervector.cohort.watch` and
   `local.hypervector.cohort.checkpoint`. Verify loaded arguments and paths with
   `launchctl print`; the checkpoint service must use `--follow-latest-run`
   without `--run-id`.
6. Observe at least two successful polls: current roster `status=available`,
   `lifecycle=running`, receipt times advancing and at least two durable context
   rows. Restart the observer and verify earlier history remains. Then check
   `cohort_backend_supervisor.py status`; unavailable evidence must remain visible.

Watch and observer deployment do not provide automatic backend recovery. For
restart ownership, install the reviewed V89 supervisor at the stopped boundary,
verify its exact arguments, and verify the restarted backend's prestart backup,
profile fingerprint, account reconciliation and fresh heartbeat. An adopted
backend defaults to hold; adoption alone is not an uptime fix.

The operator authorized transition drain on 2026-09-21; V89 activated request
`af62626d50cc4b10880109cb6eef735c` at 05:37:30 UTC. Wait for its completed
marker, stopped owner and fresh venue reconciliation. A recovery can rebind the
drain to a new run; read its current `run_id` from the completed durable marker
and verify that identity against the final checkpoint. Before the maintenance
restart, preview `scripts/cohort_transition_drain_archive.py --expected-run-id
<verified-completed-run-id>`, then perform the verified archive with `--yes`.
The helper retains identical evidence before clearing the start blocker; this is
required even when restarting the same V89 profile. An active or incomplete
drain must not be cleared to expedite deployment.

The September 21 gateway incident also requires the reviewed candle-read retry
and transient-error classification fixes. They remain staged until this same
boundary. Same-profile drain recovery before flat uses the unchanged live source
and `--resume-transition-drain`; it does not clear the drain or install changes.
The installed checkpoint follower binds to the new run after its first complete
snapshot. The existing TUI reads that checkpoint. Retain the manually pinned
writer's old checkpoint and arguments for rollback; a writer explicitly pinned
with `--run-id` cannot follow recovery automatically.

## Acceptance without live orders

Run the targeted supervisor process tests. They kill disposable stub children,
verify relaunch, exercise repeated crashes across supervisor invocations, preserve
STOP/clean exits, and prove exclusive ownership and corrupted-state refusal.

Production-entrypoint acceptance must use **`multi_asset_bidirectional_observe.py`
with an isolated `--ledger-root`**, without live-arm flags. First seed that
ledger with a bounded one-poll observe run, read its exact run ID, and include
`--resume-run-id <that-id>` in the supervised observe command. Keep the exact
`--ledger-root` spelling from the seed command: switching a relative path to an
absolute path changes the configured identity and is correctly refused. Otherwise the
observer correctly refuses to reopen its existing ledger after the kill. Supply the supervisor
with paths rooted in that same disposable acceptance directory (including
`observer.lock`), and disable external notifications. Wait for actual observe-mode
heartbeat before killing the disposable child. Confirm relaunch and subsequent
graceful stop from its own event journal. Never use the armed live entrypoint for
this kill test: starting flat does not prevent a new entry before the kill.

Observe acceptance cannot prove adoption of an existing live position. That
capability must retain the existing reconciliation/ownership tests and remains an
operational limitation of this acceptance evidence.

## Editing a loaded service definition

`kickstart` uses the already-registered service definition. After editing a plist,
**boot out and bootstrap** it, then inspect its loaded arguments before accepting
its identity. At a future approved V90 transition, first verify flat/order-free
state, archive the completed drain and old supervisor journal, change the config,
reload the definition, and check the approved candidate fingerprint. Do not use a
plist edit followed only by `kickstart -k`.

## Rollback

Boot out each affected service by exact label. Restore source files and plists
from the verified deployment backup, verify their recorded hashes, and bootstrap
only the previously approved services. Retain new research data and restart
journals. A supervisor's graceful stop is forwarded only to a child it owns; it
does not signal an adopted backend. Recheck venue and owner state before any
backend restart. Rollback does not authorize a different strategy or allocation.

## Limits and observability

The observer and watchdog cannot detect a powered-off host from within that host.
An operator-configured external dead-man service can cover that failure mode;
none is provisioned or messaged by this implementation. Optional endpoint URLs
remain local configuration, never repository content. No forecast of 3x more
trades is an acceptance criterion; uptime, detection latency and restart bounds
are measured separately from trading results.
