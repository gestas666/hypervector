# v31 continuous route tracking acceptance

Date: 2026-08-09

## Problem and success criteria

The v31 route-pruning artifact could previously be refreshed only by an
operator command. The live backend journal remained continuous, but the
candidate comparison was therefore not operationally continuous.

Acceptance requires a separate process that periodically rebuilds the bounded
v31 comparison, preserves exact v25/v31 identity checks, emits structured
success or failure records, and has no route, order, position, transition, or
promotion authority. Starting it must not restart the active v25 backend or
checkpoint sidecar.

## Implemented boundary

`scripts/v31_route_forward_monitor.py` invokes only the existing one-shot
`scripts/v31_route_forward.py`. It forwards the checkpoint, journal, source
config, candidate config, and output paths explicitly. It does not accept live
arming flags and does not import a venue client.

The monitor:

- defaults to a 120-second refresh interval;
- supports one-shot and bounded-cycle validation;
- rejects nonpositive intervals and negative cycle counts;
- retains evidence of any failed cycle in its process result;
- logs one structured `v31_route_forward_refresh` record per cycle; and
- atomically updates only
  `data/runtime/bidirectional_cohort/latest_v31_route_forward.json` through the
  already-tested one-shot tracker.

The local launchd label is `com.hypervector.v31.route-forward`. Its combined
output is
`data/runtime/bidirectional_cohort/v31_route_forward.launchd.log`.

## Runtime validation

Two successive supervised cycles succeeded with phase
`pretransition_v25_baseline`, state
`candidate_inactive_baseline_captured`, five open positions, one removed-route
eligible signal, and `execution_authority=none`.

After launch:

- v31 monitor: running, run count one;
- v25 live owner: PID `37897`, running, run count one;
- v25 checkpoint owner: PID `23577`, running, run count one; and
- all five reported live positions remained venue-stop protected.

No drain, restart, order, position, stop, route, sizing, or strategy mutation
was performed.

## Verification and failure modes

Four monitor boundary tests pass. They verify exact path forwarding, one-shot
behavior, retry behavior without success-shaped reporting, and interval
validation. The complete v31 focused suite previously passed 23 tests; the
transition/config/tracker subset was rerun after the handoff update and passed
11 tests. Ruff and format checks pass for the monitor and its tests.

The monitoring claim is falsified by a changed v25 PID/run count, any live
arming option in the monitor command, a routed action attributable to the
monitor, output identity drift, a stale checkpoint concealed as success, or a
structured cycle reporting success after the child tracker failed. A process
that is running while repeated cycle errors accumulate is not considered
healthy; the log and output timestamps must both advance.

## Assessment

Confidence is high that v31 tracking is now continuous and execution-isolated
because the child tracker is already identity-bound, the process boundary was
tested, the first real cycle succeeded, and both live owners retained their
PIDs and run counts. This confidence does not extend to v31 economic edge;
route-pruning confidence remains medium pending independent both-side outcomes.
