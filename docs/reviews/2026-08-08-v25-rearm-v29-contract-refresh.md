# v25 live re-arm and v29 transition-contract refresh

## Problem restatement

The explicitly requested outcome was to re-arm the v25 live canary, preserve
every existing venue-protected lifecycle, and keep the next-flat v29 candidate
reconstructable from current implementation bytes. Success required exact
runtime identity, zero unhandled faults, venue-native protection on every open
position, an immutable and report-only v29 source baseline, an append-only
research decision, and passing Python and Rust/TUI validation. Profitability
was not an acceptance gate.

## Observed live result

At `2026-08-08 13:03:33 EDT`, launchd reported
`com.hypervector.v25.live` running as PID `37897`, launch count one, with no
exit. Checkpoint `2026-08-08T17:03:09.529765+00:00` reported:

- run `bidirectional-live-1786182011216`;
- profile `multi_asset_bidirectional_complete_portfolio_canary_v25`;
- profile fingerprint
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`;
- lifecycle `running_consistent` and zero faults;
- BTC long `0.00038`, protected by order IDs `512826144316` and
  `512826131342`;
- SOL long `1.0`, protected by order ID `512630736897`;
- `xyz:GOLD` long `0.0172`, protected by order ID `512544517709`;
- `xyz:SPCX` long `0.56`, protected by order ID `512769547957`.

No route, order, close, resize, stop, target, allocation, or risk parameter was
mutated during the transition-contract refresh. The checkpoint sidecar remained
PID `85772`, launch count one, with no exit.

## Technical defect and staged repair boundary

A report-only current-run prefix audit did not establish complete technical
coverage. It recorded `provider_metric_telemetry_missing` with 244 null
`pressure_age_seconds` or `imbalance_10` values across five HIP-3
breakout-pressure routes. The gap predates the staged repair.

The diagnostic evidence supports a clock-ordering cause: the loaded v25 runner
sampled the decision cutoff before same-cycle reconciliation or book capture.
Current source instead reconciles or captures the book first and samples the
causal cutoff afterward. This is a source and unit-test result, not live
acceptance. The running process loaded implementation identity
`072653bdf42439cae34c5ec43906c5b43d9402b540e075aba7b664ce9fc1cef9`
and therefore cannot acquire the repair without a later safe restart.

Historical gaps remain immutable and are not backfilled. The repair is
falsified if a future process repeatedly receives a causal book inside the
30-second window for an applicable completed HIP-3 decision but still records
null pressure metrics.

## v29 provenance refresh

The inactive v29 baseline is now:

- bundle
  `data/backups/bidirectional_cohort/prestart_20260808T163708.093622Z_d1f4cd3b0319`;
- manifest SHA-256
  `ee60373354d57b28ac6507dcd559781e8aba673ee8f03ed1e919ead3d103793b`;
- 1,257 implementation files with aggregate SHA-256
  `914c62b7efaa5b8d18d6833c79299ecfb3a3f84f9f6000d23f129e34da5d068a`;
- live runner SHA-256
  `693a5e1948602a70e533a87357ff6ba91ff6d03005690830617ab284720084a7`;
- observer runner SHA-256
  `b1892ec25e94b6ad04b11094c41b487f1b9b2c745d565e51a9fbabd57de430d0`.

Independent backup verification passed. The manifest has
`execution_authority=none`; creating it did not claim a live run identity.

Research revision 6 was appended to DuckDB as
`48065e346de21ffb45e7d58de7e4c2de4173966755480214283e3db16805321e`.
All 31 evidence references across the six-revision chain matched, with zero
changed or missing references. Revision 6 leaves v29 inactive and preserves
revision 5's low-to-medium economic confidence and concentrated common-window
result. It grants no automatic promotion or execution authority.

The transition guide binds the current v25 run, immutable protected-position
snapshot, v29 profile, refreshed bundle, and revision 6. Its SHA-256 is
`f6c39254c9fff35e4407c019e3a0e754906a4bd08910668f3793d23ec3da282c`.
The guide still requires an explicitly authorized transition drain followed by
a verified flat, order-free boundary. No hot restart or hot rollback is
permitted.

## Validation

- 87 focused v29, runner-clock, HIP-3 provider, and signal-outcome tests passed.
- 14 v26-v29 transition-chain tests passed after obsolete tests were corrected
  to validate frozen archive integrity and the current v29 supersession target.
- The full non-network Python suite passed: 4,099 passed, four deselected, and
  27 deprecation warnings.
- The complete `cargo test -p hypervector-tui` library, integration, and doc
  test set passed.
- Ruff, Python format checks, JSON decoding, diff whitespace, CLI status, and
  journal evidence-integrity checks passed.

The warnings concern third-party WebSocket deprecations and
`Timestamp.utcnow`; they did not fail this acceptance but remain maintenance
work.

## Confidence, risks, and falsification

Confidence is high for the observed v25 identity, zero-fault checkpoint,
venue-protection projection, v29 source identity, journal-chain integrity, and
test results. Confidence is medium that clock ordering is the sole cause of all
future pressure gaps because the staged code has not yet run against a new live
HIP-3 decision. Economic confidence in v29 remains low-to-medium because its
positive replay is concentrated and not a future-profit forecast.

The live assessment is falsified by a PID/run/profile change, a missing or
wrong-size protective order, a nonzero runtime fault, or venue/checkpoint
reconciliation disagreement. The v29 transition assessment is falsified by
profile, source, bundle, route, side, or journal identity drift. The pressure
repair is updated only by fresh post-restart causal telemetry.

## Next authorized boundary

Keep v25 running and collecting exact fills, fees, funding, slippage, exits,
regime context, and missed opportunities. At a separately authorized boundary,
drain v25 without new entries, prove every asset flat and every owned order
absent, archive the run, create the mandatory startup backup, and launch the
approved successor with explicit live-risk flags. The first applicable HIP-3
decision in that new run is the live acceptance test for the clock repair.
