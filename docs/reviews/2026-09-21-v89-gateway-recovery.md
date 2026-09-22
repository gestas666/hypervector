# V89 gateway failure and drain recovery

## Result

High confidence from fresh ledger, checkpoint and unsigned venue evidence:
V89 position management recovered with the operator's transition drain intact.
At 07:11:19 UTC on September 21, ten completed polling cycles had emitted fresh
heartbeats, no runtime fault, no routing actions and no order submissions. The
checkpoint reported `healthy` and `running_consistent`. SNDK long 0.279 and SPCX
short 3.24 remained reconciled and fully covered by reduce-only stops. This is
point-in-time operational evidence; another venue failure can invalidate it.

Production source and V89 sizing are unchanged. The gateway fix is prepared in
the isolated maintenance checkout and has **not** been deployed. Observer,
watchdog and supervisor installation still require the approved flat boundary.
V90 allocation remains pending approval.

## Cause and recovery evidence

- Old run `bidirectional-live-1789586105858`, PID 83722, last heartbeat
  06:15:56 UTC; runtime fault at 06:16:06 UTC during `intent_polling`, with
  `orders_attempted=false`. The traceback ends at the public candle request:
  `HTTPError: 502 Server Error: Bad Gateway` from Hyperliquid's `/info` endpoint.
- Production candle retries handled 429 and transport exceptions, but raised
  HTTP 502 immediately. The transient classifier also rejected this HTTP error.
  Drain activation had succeeded at 05:37:30 UTC and its marker remained active.
- Before recovery, an unsigned venue preflight reconciled the two positions and
  both protective stops. No force close or drain-marker clearing was performed.
- Restart used the existing V89 live command with `--resume-transition-drain`.
  Its mandatory backup was independently verified. Implementation SHA-256
  `bb0a45996f63d310760e38936b741eefdfeead5ca614cfceca2087220232b9d6`
  matches the previous backend; `strategy_changed=false`.
- Recovered run `bidirectional-live-1789973504608`, PID 97443, retained request
  `af62626d50cc4b10880109cb6eef735c` and incremented its resume count to one.
  First recovered heartbeat: 07:07:57.803104 UTC. Backup and historical replay
  made startup take approximately 16 minutes; process existence alone was not
  treated as successful recovery.
- The read-only checkpoint writer was explicitly pinned to the old run. Its
  checkpoint and arguments were retained, PID 18490 was terminated, writer-lock
  release was verified, and identical options were relaunched with the new run
  as PID 98930. Fresh checkpoint lifecycle is healthy with no runtime exception.
  Research synchronization completed with 94 imported events and no error.
- Post-recovery unsigned venue preflight at 07:09:43 UTC reconciled all seven
  assets: two positions and two full-size reduce-only stops. Its exit code 3
  reflects a non-flat account, not a reconciliation failure.

The terminal screen was not visually inspected: computer-use access to Terminal
was denied. Recovery acceptance uses the actual checkpoint consumed by the TUI,
fresh backend events and independent venue reconciliation.

## Staged repair and code review

`src/hypervector/data/hl.py` extends the existing four-request candle retry
budget to HTTP 500/502/503/504. Delays remain 1/2/4 seconds, with the existing
15-second Retry-After cap. Exhaustion raises the final response error; there is
no stale-data substitute. The existing 30-second request timeout still applies,
so a failing poll can delay subsequent deadline handling by the retry budget.

`src/hypervector/live/transient_transport.py` classifies those exhausted reads
for the existing degraded-polling path. Causal candle boundaries remain intact,
entries are withheld on that failed poll, and unconditional deadline exits
remain available. Permanent request errors remain fatal. Review traced all
classifier callers, including observers and account reconciliation, and checked
the signed mutation wrappers. Ambiguous signed responses retain their typed
identity error and are not retried as reads. Order submission code is unchanged.

No further reproducible defect was found in this bounded self-review. It does
not establish that the repository or deployment is free of defects.

## Validation

- Before the fix, six new candle tests and five classification/integration cases
  reproduced the missing behavior.
- After the fix: **231 passed, 4 network cases deselected** across candle reads,
  poller boundaries, degraded deadlines, drains, startup, observers, funding,
  order identity/submission and native receipt recovery. No network calls in tests.
- A coverage run passed 78 cases. The classifier covered 32/35 statements and
  19/22 branches (89% combined); the new server-error paths were exercised. The
  broader historical candle module was only partially covered by this selection
  (57% combined), so no module-wide coverage target is claimed for it.
- Ruff, formatting of the added test file and whitespace checks passed.
- The first expanded test attempt had two missing historical-fixture failures.
  Copying the existing ignored V58 stress artifact from the original checkout,
  with SHA verification, resolved both. A package-specific pytest coverage
  invocation also hit a NumPy import conflict; path-filtered `coverage run`
  succeeded without changing the environment.
- Earlier maintenance validation and full-suite limitations remain in
  `2026-09-20-v90-monitoring-capture-acceptance.md`; that full suite was not
  rerun for this narrowly scoped amendment.

Production evidence is retained in the original checkout under
`data/logs/operations/v89_transition_drain_20260921T053727Z/recovery_20260921T065143Z/`.
It includes backup verification, old/new checkpoint arguments, both checkpoints,
post-recovery venue report, snapshot and `verification.json`. Test and coverage
logs remain in the isolated checkout under
`data/logs/research/v90_monitoring_capture_20260920/`.

## Remaining boundary and falsification

The account is not flat. Keep the drain active and allow existing exits to work.
At completion, verify current run identity, absent positions/orders and stopped
ownership before archiving the completed marker and installing reviewed changes.
Use the marker's current run ID, not the pre-recovery run. Rollback retains the
documented exact-file backups and operational journals.

A stale heartbeat, new runtime fault, missing stop, unmatched venue state, new
entry during the drain or competing owner would invalidate recovery acceptance.
Until the staged retry fix is deployed, this same production 502 failure remains
possible. Even after deployment, retries cannot make an unavailable venue supply
fresh data or guarantee execution timing.
