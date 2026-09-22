# V91 code review and acceptance

## Review conclusion before deployment

High confidence in the exercised mechanics: no remaining blocking finding in the
reviewed V91-only diff. This is a self-review, not an independent second review,
and is not evidence of guaranteed profit or absence of all bugs.

Reviewed against the recorded 84-file dirty baseline, preserving unrelated work:
exact lifecycle binding, legacy fingerprint stability, long/short price choice,
completed-bar causality, freshness, monotone floors, durable append before action,
latched close recovery using a fresh quote, existing reduce-only execution,
partial-close reconciliation errors, same-cycle entry suppression, monitoring
fault visibility, restart-budget persistence and actual TUI policy projection.

Repairs include mutation-capable transport failures being surfaced as execution
errors; independent alert sinks surviving another sink's disk failure; durable
supervisor holds before fault logging; unresolved supervisor sessions retaining
restart authority restrictions; and a 60-second launchd shutdown timeout above
a 30-second child wait, with durable stop persistence before waiting and
interruptible health-loop sleep. An empirical host probe rejected the earlier
180-second assumption: launchd clamps it to 60. Two added regression tests
failed before correction; all 83 supervisor/reliability tests pass afterward.

## Reproducible checks

Artifacts: `data/logs/research/bidirectional_cohort/v91_adaptive_exits_20260922/`.

- `pytest_full.log`: 10,169 passed, 4 deselected, 27 warnings (625.74 seconds).
- `final_targeted.log`: 136 passed after final projection/helper changes.
- `adaptive_coverage.json`: focused adaptive/ML suite 40 passed; statement
  coverage controller 93%, input preparation 97%, journal 90%, policy 96%,
  shadow forecast 89%. This is not a claim of 100% overall branch coverage.
- `cargo_test.log`: full `hypervector-tui` suite passed; the live-ledger-only
  V90 QA test is intentionally ignored by that suite.
- `cargo_adaptive_label.log`: additional adaptive-policy label test passed.
- Ruff passed for changed/new Python runtime and research modules.
- Clippy with `-D warnings` passed. All changed Rust files are formatted.
  Whole-repository `cargo fmt --check` still reports four unchanged baseline
  files (`cohort_format.rs`, `cohort_regime.rs`, `cohort_setup_detail.rs`, `lib.rs`);
  their formatting is unrelated and was preserved.
- Deployed Python smoke suite: 60 passed before the timeout correction.
- `launchd_boundary_green.log`: 83 passed after the timeout correction.
- Five reproduced reliability regression tests failed before their repairs and
  pass afterward. Disposable subprocess acceptance exercises restart/hold paths;
  no live position-holding process is killed for testing.

## Expected behavior and limits

All eight configured assets become executable under their existing entry-side
contracts and sizing caps. Gross price profit activates protection at the larger
of 60 bps, twice minute ATR, and estimated friction plus 20 bps. The floor ratchets
upward, with wider trend-supported allowance and tighter opposed/corroborated
allowance. It does not promise an executable fill at the floor. Native initial
stops and recipe/terminal exits remain in force.

The replay covers 26 eligible historical lifecycles, not a fresh full eight-asset
portfolio backtest. Its gain at modest slippage weakens under higher slippage.
Historical book/regime paths are unavailable, so those branches have causal
fixture validation rather than historical PnL validation. ML comparisons did not
validate model-controlled exits; prospective Ridge telemetry has no execution
authority. Full research, sizing and limits are in the frozen research report.

Confidence would decrease if live observations showed stale inputs, incorrect
side/context binding, floor regression, missing durable evidence, unexplained
fees/slippage, or monitor/restart failures. Inspect these by exact lifecycle and
preserve native ownership while correcting any fault. Rollback requires the
existing drain/flat boundary, not a hot source reversal under exposure.

## Deployment acceptance — passed at 11:03:58 UTC

High confidence in observed deployment identity and health; confidence in future
profitability remains low until prospective outcomes exist.

- Supervisor PID 1616 owns backend PID 1619. Actual run:
  `bidirectional-live-1790073983560`, `LIVE ARMED`, profile
  `multi_asset_growth_first_5000_adaptive_eight_asset_v91`, fingerprint
  `00ca7e008e8b2ec7cbeac4b9541cabf39a8576a23769b92a169e984616fe8d8c`.
- Ten new-run heartbeats observed; latest 11:03:51 UTC. No degraded/fault events
  in the acceptance window. All eight execution scopes are active; all five
  providers bind the adaptive policy. Setup coverage is 8/8 complete.
- All eight L2 books are 3.6–6.9 seconds old at their cohort observation.
  Canonical evidence exists for all eight, 8.4 seconds old at publication.
- Two independent supervisor status observations report healthy. The final
  heartbeat/checkpoint ages are 7.7/6.0 seconds; roster age 101 seconds. Disk
  free 19.3 GiB. Current checkpoint matches the exact V91 run and fingerprint.
- `v91_live_cockpit_acceptance.log`: actual live-ledger/checkpoint projection
  passes across nine screens at 120x36 and 176x65. All eight markets and restored
  `[LIVE]` routes appear; adaptive labels render; no `BACKEND ERROR`. This is
  deterministic renderer acceptance, not a claim of a human desktop sign-off.
- `final_deployed_critical.log`: 46 passed after deployment; real routing checks
  cover both sides and pass canonical deterioration through the production
  exit-batch boundary with same-cycle entry suppression.
- `launchd_shutdown_acceptance.json`: actual disposable launchd supervision
  persisted stop in 0.967 seconds and completed the child's graceful shutdown
  in 3.137 seconds. The loaded service timeout is 60 seconds; child wait is 30.
  No live backend was used for this failure-boundary test.
- Roster observer is running and append-only capture contains oracle, premium
  and funding values for SPCX, SNDK, Brent and TSLA, with no missing fields in
  the sampled records. Capture has no signing or execution authority.
- `live_input_ml_smoke.json`: production Ridge inference succeeds for all eight
  exact captured startup candle histories, with the approved model SHA-256.
  This is a read-only inference check, not a live trade or predictive validation.
  Automatic per-lifecycle forecasts will be journaled when positions are open.

At acceptance the venue-backed cohort snapshot is flat with no new fills/actions.
V91 is armed and evaluates normal signals; no order was forced for acceptance.
A completed live adaptive exit is therefore not yet observed. Replay, causal
fixtures and native execution regressions support implementation confidence;
actual retention, cut winners and fill slippage remain forward measurements.

## Exact recovery evidence

Deployment backup:
`data/backups/bidirectional_cohort/v91_deployment_20260922T103814Z/`.
Its `source/`, `launchd/`, archived journals, correction subdirectory and
`reviewed_candidate.tar.gz` preserve original and deployed material. The initial
V91 pre-start attempt was gracefully stopped for the discovered timeout mismatch,
before any new run configuration/heartbeat or order. Its evidence was retained.

Verified startup bundle:
`data/backups/bidirectional_cohort/prestart_20260922T104623.560600Z_00ca7e008e8b`.
Manifest SHA-256:
`e6cdd969f5d9e55703c6af6bb2c8fbf89e787f1b10eb5dfc99a8e7b463c867cc`.
All 1,941 backed-up implementation sources match the running checkout; aggregate:
`2a6618c13cdf664f65f7ae64f7c65441ee6a231a8ead3bcdd3553e0f211e938d`.

Use deployment/rollback **revision 2**, referenced by the validated approval.
The old procedure's 180-second assumption is superseded by measured host behavior.
`HANDOFF.md` points to the current procedure; older hashed V90 plans remain intact
as historical evidence. Operations and source manifests are in the artifact root.
No git commit or unrelated working-tree reversal was performed.

Final whitespace check removed one extra blank line at the end of
`cohort_profit_lock_controller.py` after live acceptance. The full serialized
compiled module is byte-identical before and after, so this is a documented
source-byte-only difference from the running backup, not a behavior change or a
reason to restart trading. Original bytes and both hashes are retained in the
operations manifest and `post_acceptance_cosmetic/`. Final `git diff --check`
passes. Other 1,940 implementation files remain byte-identical to the live backup.
