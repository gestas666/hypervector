# v25 bounded checkpoint acceptance

## Problem restatement

The live v25 backend was healthy, but the report-only checkpoint worker repeatedly
copied and decoded approximately 1.23 GB of append-only ledgers. The observed
worker consumed 4.14 GB RSS immediately before cutover and had previously reached
approximately 5.9 GB. The required outcome was a lower-cost rolling cockpit
checkpoint without restarting execution, losing all-time history, changing
routing, or weakening live-position reconciliation.

## Implemented boundary

Continuous checkpoint publication now snapshots only the exact suffix sharing
the selected run's profile ID, profile fingerprint, and run fingerprint. It
rebases snapshot-local sequence numbers while retaining the original byte and
sequence boundaries as evidence. All-time research projections come from the
last complete report-only checkpoint only when both the exact execution-fill
signature and DuckDB closed-lifecycle count still match. Any mismatch triggers
one full-ledger refresh rather than silently serving stale history.

One-shot audit mode remains a full-ledger operation. The cache cannot carry
execution authority, alter strategy state, or affect routing.

## Acceptance evidence

- Only `com.hypervector.v25.checkpoint` restarted. The live job remained on
  PIDs `37897/37912`, launch count one, run
  `bidirectional-live-1786182011216`, and profile fingerprint
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- The exact pre-cutover checkpoint was copied to
  `data/backups/bidirectional_cohort/checkpoint_pre_bounded_20260808T110742Z.json`.
  Its SHA-256 is
  `89750c143d4e666ca3285214adfcc8e71e609842dfd19204e85a1faf59e0f478`.
- Repeated bounded publications retained the same execution identity, all 24
  executable provider-symbol routes, 24/24 readiness coverage, eight compatible
  fills, two compatible closes, and 28 all-time closed lifecycles.
- ETH, SOL, and `xyz:GOLD` remained open with the same three stop OIDs. Fresh
  read-only Hyperliquid reconciliation confirmed each stop was reduce-only,
  full-size, and attached to an isolated 5x position.
- The monitor's own profile/run/freshness validator accepted the new checkpoint.
- The bounded worker observed 396,832-500,176 KiB RSS while idle and 1,104,816
  KiB during a publication, versus 4,143,424 KiB immediately before cutover.
  This is an observed reduction of about 73% at the compared publication peak,
  not a universal resource guarantee.
- The focused checkpoint suite passed 62 tests. The complete
  `cargo test -p hypervector-tui` command exited zero. Ruff, format, diff
  whitespace, and modified-production-file line-limit checks passed.

Machine-readable evidence is
`data/logs/research/bidirectional_cohort/v25_bounded_checkpoint_acceptance_20260808T1114Z.json`.

## Remaining risks and failure modes

The periodic isolated DuckDB importer still reached 5,227,248 KiB RSS. It exits
after each import and no longer bloats the checkpoint worker, but it can still
cause transient machine pressure every two minutes. It should be optimized by
avoiding a full historical portfolio projection when no closed-lifecycle
identity changed, or by materializing incremental lifecycle state. That change
requires its own red-green tests and resource measurement.

Checkpoint coverage still reports `provider_metric_telemetry_missing`. The same
gap existed before this cutover; bounded publication did not introduce it.
Until the already staged readiness telemetry correction is loaded at a proven
safe boundary, the cockpit must continue showing that gap rather than a false
complete state.

## Confidence and falsification

Confidence is high for execution isolation, identity preservation, history
preservation, and the measured checkpoint reduction because they were checked
against fresh process, ledger, checkpoint, monitor, and venue evidence.
Confidence is medium for long-duration resource stability because the observed
window covers several publications, not days.

Any backend PID/run change, missing protective stop, execution-signature drift
without a full refresh, loss of the 28-lifecycle archive, monitor identity
refusal, or return to multi-gigabyte unchanged-history checkpoint scans would
falsify the corresponding acceptance claim.
