# V89 research-import visibility and reporting refresh

The running reporter now publishes import status independently of execution
health. The rebuilt TUI exposes failures, retries and the last successful import
in every view, using the existing footer border so body panes retain their space.
Confidence is high in this measured reporting correction. It does not establish
strategy profitability or qualify an order that the providers did not produce.

## Problem and decision

September 7's disk shortage deferred research imports while the live checkpoint
continued updating. The log consumer removed each transient error, and checkpoint
publication had no import-status input. A fresh backend therefore could coexist
with an undisclosed import failure. The prior storage recovery restored imports;
this change makes recurrence visible.

Retain source commit `710ada5`, installed on main as `2986216`. The explicit
report-only envelope has schema 1 and execution authority `none`. Missing legacy
status is UNREPORTED. An importer with no database is DISABLED. Unresolved errors
survive log consumption and retries until an actual successful import clears
them. Missing prior success/count remains unavailable. Malformed explicit status
is rejected by the TUI projection.

| Alternative | Result | Decision |
|---|---|---|
| Leave reporting unchanged | Import failure can remain absent from a healthy-looking TUI | Rejected |
| Add a header row | Two existing layout tests demonstrated clipped panes | Rejected |
| Retain state and use the footer border | Visible import state without losing body rows | Retained |

This is a pre-authorized corrective reporting change. No further permission was
needed. No live strategy, asset, leverage, sizing, routing or order behavior was
changed. The measured absence of entries remains a strategy diagnostic question.

## Validation

- 80 relevant Python tests passed. Tracker statement coverage was 100%; the
  background worker was 90%. Five propagation tests passed again after the final
  formatting-only shortening of the rolling publisher.
- Full offline Python result: 7,791 passed, 275 failed, four deselected. The same
  275 failing nodes reproduced on unchanged `a42afa8` in an isolated checkout.
  These local historical evidence/model/vendor fixture dependencies prevent an
  all-green full-suite claim; none was a new failing node from this correction.
- Full Rust result: 507 passed, zero failed, 23 explicit opt-in tests ignored.
  One V86 fixture-dependent failure first reproduced on the baseline; two local
  fixture files were then copied and SHA-256 verified for final acceptance.
- Clippy with warnings denied, Rust formatting, Ruff, diff checks and release
  compilation passed. A shared Cargo target initially retained a baseline library;
  the candidate was explicitly recompiled before final acceptance.
- Two read-only integration runs captured all nine views at 100x28, 120x36 and
  190x52: 54 screens total. Predeployment used a separate one-shot output without
  database import, correctly showing DISABLED. Postdeployment used the actual
  continuous reporter's frozen checkpoint and showed its successful import.
- The installed release binary was run in a separate 120x36 terminal. It showed
  IMPORT OK, LAST OK, 38 events, LIVE EXECUTION ARMED and all three HIP-3 symbols.
  Switching to Setups retained the blockers and navigation. Its detached quit
  returned zero while the original live process lifetimes remained unchanged.

The generic `hypervector status` command also completed, but its default
`can_start` field describes that invocation's defaults; active execution state
was verified from the live heartbeat and ledger instead.

## Reporting adoption and runtime evidence

All maintenance evidence is below the original checkout's
`data/logs/research/bidirectional_cohort/v89_sync_reporting_refresh_20260907_v1/`.

The old reporter, PID 11730, received SIGINT only after checking its exact start
time, command and ownership. Its existing report-only owner exited naturally.
New owner 48894 started reporter 48897, bound to the original supervisor 4954 and
backend 4965. Supervisor 4954, backend 4965 and foreground TUI 8440 retained their
original process start times. Source backups, prior checkpoint and prior/updated
binaries were preserved before installation. The new binary was installed by
atomic replacement, retaining the running TUI's old inode.

At 20:20:44 ET the checkpoint was running consistently with 1,144 polls, zero
runtime faults, zero current-run submissions/fills and zero eligible evaluations
for each of the seven configured routes. Successful imports contained 38 and
288 events. The last successful import was 20:20:10 ET. Free storage after
installation was approximately 9.85 GiB, above the unchanged 8 GiB requirement.

The live configuration hash remained
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.
The installed binary hash is
`d9bdb416439b47292a32d091a7d65cfdcdce1fca4fdcf7b131601fd0041e9730`.
Current run: `bidirectional-live-1788809099824`.

## Operator command and limitations

Open the updated monitor in a new terminal:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml
```

Monitor resolution was verified to produce no backend or audit command and to
set detached lifecycle. Its normal Cargo launch can rebuild the binary for the
original checkout. The existing foreground TUI 8440 has not hot-reloaded; it
belongs to the live supervisor, so quitting that original window also invokes
its supervisor's backend shutdown. The separate monitor leaves the backend
running when closed.

Import completion time is not the newest source-candle time. Counts describe the
last successful import batch, including a legitimate zero-event batch. Long
errors can clip at narrow widths; their full content remains in the checkpoint.
Status starts without a success history after a reporter restart. Clock or
schema inconsistency can fail reporting explicitly. The existing supervisor
still retains its original retired reporter handle, an earlier ownership
limitation that this reporting-only maintenance does not repair.

## Rollback and next investigation

Falsifiers include an unresolved error disappearing before success, a projected
count disagreeing with the same checkpoint, stale publication, lost body panes,
changed live ownership, or import failure after the refresh. Any such evidence
requires revising this assessment.

For reporting rollback, identify the replacement reporter's exact PID/start
time, stop only that report-only worker, restore the affected reporting sources
from `prior_source`, and launch its report-only owner again. Restore the preserved
`prior_tui_binary` by atomic replacement if needed; retain the evidence bundle.
The maintenance record identifies newly added files and each prior file hash.
There is no order-backend restart in this rollback.

The continuous research goal remains active. Highest-value next investigation:
reconcile the current no-entry window with causal provider inputs and configured
decision clocks, then test any frequency proposal with independent validation
and realistic costs. Sparse trading alone does not establish a large-win edge.
