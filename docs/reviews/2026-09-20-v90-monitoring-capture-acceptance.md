# Monitoring and research capture — implementation and code review

Date: 2026-09-20. Branch: `fix/v90-monitoring-capture-20260920`, based on
`4731eac`. Prepared checkout:
`/Users/gestas/Prototypes/hypervector-v90-monitoring-capture-20260920`.

## September 21 operational acceptance

The flat boundary was confirmed by unsigned venue preflights at 14:22 and 14:32
UTC. The 37-file maintenance deployment was backed up under
`data/backups/bidirectional_cohort/maintenance_20260921T1436Z/`. Read-only observer,
checkpoint follower and watchdog are installed and running. At 14:50 UTC the
observer had seven durable context records; restart preserved the prior byte
prefix and collection resumed. Loaded arguments and post-restart acceptance
are retained in `data/logs/operations/v89_flat_maintenance_20260921T1422Z/`.

The checkpoint follows the latest complete matching-profile live run; it rejects
partial trailing ledger records and mismatched identities. The combined
flat-boundary regression run passed 395 tests, with 4 network tests deselected.
The supervisor's disarmed restart validation remains valid, but its live service
is deliberately not loaded. The operator subsequently required profit protection
and V90 readiness; trading remains stopped while that proposal is reviewed.
The watchdog correctly reports the stopped/stale backend and no read-only
service fault. Completed drain evidence remains intact.

The dated September 20 "not deployed" observations below are historical.

## Result and authorization

September 21 amendment: the operator subsequently activated the drain. A public
candle HTTP 502 then stopped V89; unchanged-source drain recovery and a separately
staged retry fix are documented in `2026-09-21-v89-gateway-recovery.md`. The dated
September 20 observations below are historical. Flat-boundary rollout is still
pending; the additional fix passes 231 targeted tests.

**Implementation and local validation passed; operational rollout is pending the
operator's flat-account condition.** High confidence in the reproduced defects
and tested repairs; deployment behavior remains unverified on the live service.
The live checkout, launchd services, entries and allocation were not changed.
No transition drain was activated. V90 approval remains a draft.

At the final read-only check, **2026-09-20 16:36:25 UTC**, backend PID 83722
was alive with a 7.1-second ledger age. The 16:35:22 UTC checkpoint showed SOL
and xyz:BRENTOIL open, all other assets flat, and drain inactive. The repaired
health evaluator reported the stale roster observer explicitly. This checkpoint
does not substitute for fresh venue reconciliation at eventual deployment.

The final self-review found no remaining reproducible defect in the changed
paths. This is bounded evidence, not a claim that all regressions or bugs have
been excluded. The existing full-suite failures and deployment limits below
remain visible.

## Changes and review findings resolved

| Finding | Repair and evidence |
| --- | --- |
| Unavailable/null or malformed roster data crashed monitoring or appeared healthy | Validate schema, lifecycle, embedded UTC observation times and executable-market fee evidence; report unavailable/stale explicitly |
| Restart budget reset when launchd replaced the supervisor | Exclusive ownership plus atomic, command-bound journal; reserve before spawn; persist clean-stop, technical-failure and exhausted-budget holds |
| Standing STOP could still permit an initial child launch | Check it before reservation/spawn; regression proves zero launches |
| Optional alert delivery could crash or silently fail | Catch expected channel failures at the boundary, emit structured diagnostics without endpoint values, preserve local journal errors |
| Observer retained funding only in a replaceable latest snapshot | Reuse one public context response for existing funding telemetry and full-xyz-universe research history; retain premium/oracle/mark, missingness and metadata |
| History could conceal incomplete writes or failed polls | Locked append with flush/fsync, explicit gap records, invalid-value rejection and refusal to overwrite an incomplete tail |
| Plist edits were not reliably loaded | Boot out/bootstrap exact labels and inspect registered arguments; source and plist backups required |
| Kill acceptance could affect an armed backend | Use only isolated observe entrypoint, exact resume ID and identical ledger-root spelling; no live-arm flags |

Supervision remains stdlib-only under `scripts/`. The original public facade and
funding `snapshot()` interface remain available. Source inspection and existing
factory/observer tests preserve unsigned observer construction. New source files
meet 500-line file/50-line function limits and typed argument/return checks.

## Verification

| Check | Observed result |
| --- | --- |
| Focused supervisor, capture, observer, factory and transition/backup suite | 167 passed; 91% combined statement coverage of measured modules |
| Durable restart journal coverage | 100% statements; corruption, changed command, prior holds, clock regression, reservation-before-spawn and singleton cases exercised |
| Production observe entrypoint | Real completed poll, SIGKILL of disposable child, relaunch with another completed poll, graceful stop and persistent `operator_signal_stop` hold |
| Disarmed identity in acceptance ledger | Every row has `live_armed=false` and `execution_authority=none`; 4 heartbeat rows including seed/stop activity |
| Full non-network Python suite in isolated checkout | 9,725 passed, 277 failed, 4 deselected; not a green full-suite result |
| Those 277 failures rerun in unchanged original checkout | 275 passed; 2 pre-existing failures reproduced |
| Rust TUI suite with its two historical fixtures copied into isolation | 655 passed, 23 ignored, zero failures |
| CLI status | `ok=true` |
| Ruff check/format, whitespace, supplied plist syntax | Passed |
| Original checkout preservation | No tracked diff; all 13 original untracked-file hashes unchanged |

The original checkout has local data artifacts omitted from the isolated git
checkout. Rerunning the failing cases there distinguishes those environment
differences from the two baseline failures:

- `test_cohort_funding_recovery.py::test_long_downtime_restores_last_committed_funding_boundary`:
  a mock lacks `bind_startup_input_observer`.
- `test_native_runner_recorded_control.py::test_original_cold_warm_packets_reach_native_cohort_telemetry`:
  expected/actual packet content differs.

These were not edited. Passing the original cases does not prove every missing
fixture case would pass against the changed checkout; targeted coverage provides
the direct evidence for changed paths. Automated tests used no network calls.
The separate operational observe experiment read public mainnet data.

The first observe experiment was correctly refused because a relative seed path
became an absolute resume path. Failed-attempt evidence is retained; the corrected
procedure passed. This was an acceptance-command identity error, not a bypassed
runtime check.

## Retained evidence

Local evidence directory: `data/logs/research/v90_monitoring_capture_20260920/`.
It contains test logs, status, original-file hashes, the acceptance harness and a
prepared deployment manifest. It is an ignored data artifact, not a claim that
files have been installed.

Production observe evidence:
`data/observe/v90_supervisor_acceptance_20260920/acceptance-result.json`,
`events.jsonl`, `events_restart_state.json`, `decisions.jsonl`, and
`first_attempt_path_mismatch/`.

Corrected allocation review:
`docs/reviews/2026-09-20-v90-transition-readiness.md`.
The SNDK experiment there measures historical visible depth, excludes fees and
latency, and ends 45 days before review. It does not establish a current-size edge.

## Remaining acceptance and rollback

Before installation: revalidate the baseline hashes; obtain fresh checkpoint and
unsigned venue evidence that positions and orders are absent; safely stop the
old owner; back up every replaced file and installed plist. Use the reviewed
deployment runbook. Preserve V89 configuration and exact live-arm boundaries.

After installation: verify loaded arguments, one backend owner, profile identity,
fresh heartbeat and reconciled account; observe at least two successful roster
polls and context records; restart the roster observer and prove history retained.
Rollback restores verified source/plist backups while retaining research and
restart evidence. No forced position close is authorized to reach this boundary.

A duplicate backend, relaunch after a terminal hold, malformed data reported
healthy, absent history, changed approval identity, or an armed observe row would
falsify acceptance. Host power/sleep outages, venue changes, disk exhaustion and
open-position recovery are not fully qualified by this local experiment. An
external dead-man service was not configured or contacted. Research timestamps
are local receipt times, not exchange event timestamps; 120-second capture is
prospective research data and does not validate high-frequency trading.
