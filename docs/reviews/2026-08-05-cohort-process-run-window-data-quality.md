# Cohort process-run performance data-quality review

## Decision-useful result

Confidence: high for accounting consistency in the inspected artifacts; low
for strategy inference because the live sample is small and process restarts
are not statistically independent.

The reconciled cohort history can support an all-time performance row, a
current-run row, and descriptive process-run comparisons. It cannot yet support
a claim that performance repeated across independent live market windows. The
TUI therefore labels the process-window count `NOT INDEPENDENT` and keeps the
feature report-only.

## Metric and cohort definitions

- Grain: one row per reconciled terminal live lifecycle.
- All-time cohort: all compatible closed lifecycle records available to the
  checkpoint publisher.
- Current run: closed lifecycles whose backend process run ID matches the active
  run ID.
- Process window: closed lifecycles sharing one backend process run ID.
- `NET/MARGIN`: aggregate net PnL divided by aggregate entry margin.
- `AVG PNL/TRD`: arithmetic mean of each closed lifecycle's net return on its
  own entry margin.

The last two metrics need not match because individual trades can deploy
different margin amounts.

## Evidence inspected

At the 2026-08-05 10:02 EDT checkpoint, execution history reported 13 closes,
9 wins, 4 losses, `+$2.113157` net PnL, and profit factor `3.850614`. Direct
trade provenance placed those 13 closes into six trade-bearing process runs
and three profile fingerprints. Every projected process run is required to map
to exactly one profile fingerprint, and the sum of its performance rows must
reconcile to all-time lifecycle performance.

The live checkpoint was current, reported `running_consistent`, and showed zero
faults. BTC and HYPE were open and venue-protected at the inspection point.
Those open lifecycles are excluded from closed-performance metrics.

## Validation controls

- Partial run provenance fails instead of silently mixing known and unknown
  run identities.
- One run mapped to multiple profile fingerprints fails validation.
- Python aggregation tests cover run, profile, provider-symbol, and side cuts.
- Rust projection rejects a non-report-only contract, an independence claim,
  inconsistent counts, inconsistent net PnL, or totals that do not reconcile.
- The TUI reads backend-authored performance and does not reconstruct fills or
  simulate trade outcomes.

Fresh validation passed 3,470 non-network Python tests with four intentional
deselections and the complete Rust TUI suite. Focused trade-performance tests
also passed after first demonstrating failures for the missing all-time label,
row order, average-per-trade field, run-window title, mixed-profile rejection,
and report-only contract.

## Uncertainties and failure modes

- Restart windows can share adjacent market conditions and code, so they are
  not independent trials.
- Thirteen closed trades are too sparse for a robust claim about expected
  profitability, especially after splitting by strategy, side, and profile.
- The running checkpoint publisher predates the new process-window field. The
  field will remain unavailable in that live artifact until a future safe
  restart loads the new code; no restart was performed for this display change.
- A legacy run can contain strategy/profile behavior that differs from a staged
  candidate. Pooling without the preserved profile identity would mislead.

## Falsifiers and next evidence

This assessment must be updated if lifecycle totals disagree across execution,
reflection, and performance projections; if any run maps to multiple profiles;
if process-window totals fail to sum to all-time history; or if the backend and
venue disagree on a closed lifecycle. Confidence in repeatability should rise
only after multiple forward windows with enough resolved trades under the same
profile and materially different market conditions.

No strategy, allocation, order, position, live authority, or promotion policy
was changed by this work.
