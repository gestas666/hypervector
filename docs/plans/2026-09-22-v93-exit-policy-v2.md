# V93 exit policy v2 implementation plan

Spec: `docs/superpowers/specs/2026-09-22-exit-policy-v2-design.md`.
Evidence: `data/logs/research/bidirectional_cohort/v93_exit_design_probe_20260922/`.

## Task 1: policy state machine
Add `RetentionExitObservation`, `RetentionExitState`, `advance_retention_exit`
and the `ADAPTIVE_EXIT_POLICIES` registry to
`src/hypervector/live/cohort_adaptive_exit_policy.py`. Tests first in
`tests/test_cohort_retention_exit_policy.py`: long/short symmetry, activation at
exactly 0.5R, floor arming at 2R with monotone floor, regime gate requires known
opposed alignment, profit floor precedence, terminal exit, backwards clock,
same-stamp idempotence, nonfinite rejection.

## Task 2: controller, journal, recovery, mirrors
Dispatch on `plan.adaptive_exit_policy` in `cohort_adaptive_exit_controller.py`;
compute `risk_bps` from `plan.stop_price(entry_price, side)`; journal payload
carries `policy`, `risk_bps`, `state`; `_recover` validates the v2 shape and exit
reasons; expose `breakeven_stop_requested` for the runner. Replace the three
Python allow-lists with the registry. Tests in
`tests/test_cohort_adaptive_exit_controller.py` (v2 cases) and mirrors.

## Task 3: venue break-even stop raise
Protocol methods (`modify_order` on the exchange protocol,
`modify_protective_stop` on the adapter protocol), `BtcHyperliquidAdapter`,
`MultiAssetDirectionalAdapter`, `SolOrderSubmission.modify_protective_stop`,
state machine `replace_protection`, engine `raise_protective_stop`, runner
protection-adjustment step after exits inside `execution_phase`, replay fixture
`_modify`. Tests: engine replay raises after +2R, rejected modify keeps the old
stop and journals, state machine rejects non-OPEN replacement.

## Task 4: structural anchor hazard
`_stop_distance_bps` minimum-clamp fallback plus `structural_anchor_overrun`;
engine journals the overrun; `execute_routing_action` refuses non-adverse
anchors with a journaled `entry_refused` decision. Update
`tests/test_cohort_stop_risk_sizing.py` expectations; add engine and routing
tests.

## Task 5: Rust cockpit
Single `ADAPTIVE_EXIT_POLICIES` constant in `backend_cohort_configuration.rs`
used by the four validators; v2 labels in `cohort_config_exit.rs`,
`cohort_config.rs`, `cohort_widgets.rs`, `cohort_profit_lock_labels.rs`; unit
tests; `cargo test -p hypervector-tui`; release build and sha256.

## Task 6: V93 proposal profile
Write the profile, validate with `scripts/cohort_runtime_validation_check.py
--mode observe`, add a fingerprint/identity test alongside the V92 tests.

## Task 7: reproduction script and review
`scripts/v93_exit_v2_matrix.py` reproduces the composite table from the V92
screen artifacts and the live paths; `docs/reviews/2026-09-22-v93-exit-policy-v2.md`.

## Task 8: verification and records
Full non-network Python suite, Rust suite, Ruff, HANDOFF entry, memory note,
commit.
