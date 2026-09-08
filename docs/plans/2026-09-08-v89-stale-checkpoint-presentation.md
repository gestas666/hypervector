# Stale checkpoint presentation

Hypothesis: `v89_stale_checkpoint_presentation_20260908_v1`.

The September 8 14:11 UTC incident capture shows a stopped backend and absent
reporter, with a still-open monitor. Its header correctly says BACKEND STALE,
but the archive panel repeats RUNNING CONSISTENT and the footer repeats IMPORT
OK with a frozen 79-second age. These values describe the last checkpoint.

Source inspection locates the presentation defect: both renderers consume the
cached values without qualifying them when the publication is retained. The
existing stale flag also covers fresh reports of an unhealthy backend. A control
test rejected treating that flag as publication age. Add a local, independent
publication-stale flag for timeout, missing files and failed refreshes; preserve
the backend-health flag and its existing operational semantics. No Python
checkpoint schema or stale threshold changes. Shutdown attribution is separate:
all seven asset
ledgers record operator_stop, while the signal latch discards signal identity.
A bounded OS-log search returned no matching events for the tracked processes.

1. Reproduce stale import status and lifecycle presentation in offline render
   tests, covering all nine views at 100x28, 120x36 and 160x45.
2. Qualify stale import status as historical and omit its frozen relative age.
   Preserve the absolute last-success time, result/error and event count.
   Qualify stale lifecycle text as AT SNAPSHOT. Keep fresh presentation intact.
3. Verify transitions back to fresh evidence, error and disabled states, missing
   legacy telemetry, and preserved panes. Run the Rust suite, formatting and
   Clippy. Render the recorded incident through the candidate without any
   trading process or interactive operator controls.
4. Freeze source/evidence and publish a reviewable reporting-only proposal.
   Do not deploy, replace the visible monitor, restart a reporter or backend,
   alter execution settings, or inspect sealed prospective outcomes.

Success means stale values cannot be read as current import or lifecycle
health, while recorded facts remain inspectable. No trading benefit is claimed.
Existing stale thresholds remain unchanged. A missing qualification, a lost
pane or a regression in fresh-state display invalidates acceptance. Confidence
is high in the observed presentation mismatch; shutdown cause remains unknown.
