# V89 passive source-health watch and funding recovery

The September 16 source audit found two prospective public-data collectors
stopped for about 49 hours. The exact frozen collectors were resumed in the
preceding recovery work. This change adds a separate observer so absent,
stopped, stale or altered collection state produces a retained alert while the
observer runs. The original interruption's cause remains unknown.

## Installed behavior and evidence

The observer binds each collector's PID, birth time, command, capture directory,
cadence and manifest SHA256. Every observation checks the manifest and its
declared source/protocol hashes, health schema and authority, study dates,
heartbeat timestamps, waiting schedule, process identity, open lock-file owners
and occupied writer lock. Valid collection states are `waiting` and `capturing`.
Completion requires an explicit `finished` state and the frozen final boundary;
a stopped job is not treated as completed collection.

The heartbeat threshold is 120 seconds, with a five-second clock tolerance and
15-second observer interval. Waiting publishers heartbeat every 30 seconds;
capture publishes after each query. Transport has three ten-second timeouts and
one/two-second retry delays, plus bounded request-budget waits in the seven-asset
collector. The threshold is an operational diagnostic, not a worst-case network
duration guarantee: DNS, slow reads, filesystem stalls and host suspension can
still exceed it. An alert requests investigation and never restarts a collector.

The finite loop retains immutable input pins, start, first observation and final
result, plus an atomic current status. It reads after its last sleep before
reporting a deadline. The observer reads metadata and timing evidence; market
outcomes remain sealed. `healthy` means these runtime checks passed at the
observation time, not that the study's historical coverage is complete.

Validation:

- Initial missing implementation was reproduced. Five additional failures then
  exposed missing error-field validation, missing retained initial evidence and
  missing pin-file validation. Those failing receipts are preserved.
- Candidate and installed suites each pass **78 offline tests**. Both observer
  modules have **191/191 statements and 92/92 branches** covered. This does not
  claim universal bug freedom, or coverage of external OS/network behavior.
- Actual installed CLI read both current collectors as healthy, inspected again
  at its two-second deadline and exited 0. Replaying the two retained historic
  stopped health files produced alerts and exit 2, with explicit stopped-state
  reasons. No collector was stopped or signalled to test this.
- New six-hour observer: **PID 47064 / exec session 24644**, started
  **2026-09-16 00:55:41 UTC**, deadline approximately **06:55:41 UTC**. Its
  initial receipt and live tool handle were verified.
- Installation added four files, authenticated against the candidate and retained
  source copies, without overwriting prior implementation. The installed code
  and offline tests are recoverable in the evidence directory.

## Scheduled funding recovery

After the actual September 16 01:00 UTC collection and 60-second maturity
allowance, all **14 required identities** authenticate: the old September 15
00:00 funding identity and new September 16 01:00 identity for every asset.
The seven new first receipts arrived **14,874–18,436 ms** after availability,
within the frozen 60-second allowance. All seven old identities are recovered
and remain late. A deliberately changed first-receipt timestamp is rejected.

Independent Python and SQL counts match the preserved health snapshot for
every asset: **170 expected, 170 captured, zero missing, 49 late, 121 timely**.
The read-only SQLite backup passes integrity checking, and health bytes stayed
stable during the snapshot. Original raw envelopes and response-body hashes
authenticate the 14 selected receipt tuples. This does not reauthenticate every
historical raw response in the full index; that broader check was recorded in
the preceding recovery. The original study's timely coverage stays incomplete.

## Financial observation continuity

The preceding passive lifecycle observer actually ended at **00:49:57 UTC** with
`observation_deadline`. Its final eight cursors were inspected and preserved.
The exact previously qualified handoff reader resumed from those offsets:
**PID 50314 / session 51386**, start **00:56:57 UTC**, two-hour duration. The
first eight-ledger scan found zero matching lifecycle/fault events in the
handoff interval. The existing diagnostic watcher **67653/session82480** remains
pending near **01:09:07 UTC**. These are read-only observers of user-owned
financial processes.

## Decision, tradeoffs and limits

| Alternative | Effect | Limitation / decision |
| --- | --- | --- |
| Keep only occasional manual checks | No additional process | Already missed a long source outage; rejected as the sole check. |
| Separate passive finite observer | Retained alerts with pinned source/process identity | Installed; requires agent follow-up and handoff at the real deadline. |
| Independent OS service and notification | Could detect failure of the agent's observer itself | Separate operational work; this implementation does not claim that coverage. |

Confidence is high for the tested contracts, preserved stopped-state replay and
observed live attachment. A wrong identity, falsely accepted stale/stopped state,
missing terminal read, corrupted receipt or source change reopens this repair.
Checks are snapshots; transient between-poll changes can escape detection. An
observer killed with the collectors cannot issue an alert after its own death.
No independent notification delivery is claimed.

The expected benefit is earlier detection of unavailable research evidence and
better attribution of late data. There is no measured strategy-return benefit.
Existing authorization covers this report-only technical repair; no financial
deployment approval is being requested here.

Rollback: verify the four new file hashes in `installation_verified.json`, then
remove only those files if needed; retain all evidence and prior binaries.
Collector and financial process control is outside this rollback procedure.

Next work: qualify the separately preregistered **September 23 04:00–October 7
04:00 UTC** SNDK/Brent capture before its fixed start. Preserve the original
September 22/23 outcome seals and incomplete timely-coverage classification.
The later collector is not yet implemented or launched.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_prospective_health_watch_20260916_v1/`.
