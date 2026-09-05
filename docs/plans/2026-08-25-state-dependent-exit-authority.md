# State-Dependent Exit Authority Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace blind maximum-hold exits as the primary decision mechanism with route-specific, causal state-dependent exits where exact replay evidence supports them, while preserving protective stops and treating maximum hold as a documented fallback.

**Architecture:** Freeze V61 as the control. Evaluate each route independently using exact provider identity, causal publication timestamps, venue-depth execution, fees, funding, and stressed friction. The first bounded challenger is close-only opposite-direction authority for short-only SP500 and SNDK routes: an opposite signal may close an existing short but can never open a long. ETH and BRENTOIL retain their existing bidirectional opposite-signal close behavior unless a distinct preregistered challenger beats the control. Runtime/config changes are permitted only after a challenger passes; otherwise V61 remains unchanged.

**Tech Stack:** Python 3.12, pandas, pytest, TOML live profiles, Hyperliquid/HIP-3 frozen data, Rust TUI tests.

---

## Empirical status and limits

- V61 control identity: `multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61`.
- BTC, SOL, SP500, and SPCX already have target, strategy-recipe, or completed-bar profit-lock logic in addition to stops and maximum hold. BTC and SOL use reward/risk targets; SPCX uses its cash-close recipe; SP500 uses a completed-one-minute-bar trailing lock.
- ETH and BRENTOIL can already close on an eligible opposite provider intent. HYPE also has opposite closes plus regime-supported hold extension.
- SP500 and SNDK are short-only for entry authority. Their provider can observe long signals, but the current execution-direction filter discards them before they can close an open short.
- Prior SNDK fixed-target and completed-bar trailing candidates failed frozen development robustness criteria. Unconditional ETH opposing-breakout and component-decay candidates also failed. Those rejected families will not be silently reintroduced.
- Historical proxy evidence is not proof of live profitability. Missing exact marks, insufficient independent trades, dependence on one winner, or route identity drift falsifies promotion.

## Task 1: Freeze route controls and immutable inputs

**Files:**
- Read: `configs/multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml`
- Read: `data/live/research/xyz_sp500_fresh15_v3_decisions.jsonl`
- Read: `data/logs/research/hip3_breakout_pressure_transfer_sndk_gold_disabled_brent_v1.json`
- Create: `docs/research-journal/state-dependent-exit-authority-preregistration-20260825-v1.json`

1. Record normalized provider, side, stop, target, profit-lock, recipe-exit, and hold contracts for all eight assets.
2. Record source hashes, immutable prefix lengths, time bounds, side counts, execution-depth coverage, and mark coverage.
3. Freeze V61 as the control and freeze the only initial challenger: opposite provider side may close an existing position but may not enter or reverse.
4. Predeclare route-level promotion criteria before reading challenger validation results.

## Task 2: Add a report-only close-only lifecycle challenger using TDD

**Files:**
- Create: `tests/test_hip3_close_only_opposite_exit.py`
- Create: `src/hypervector/research/hip3_close_only_opposite_exit.py`
- Modify: `scripts/hip3_shadow_lifecycle_replay.py`
- Modify: `tests/test_hip3_shadow_lifecycle_replay_script.py`

1. Write failing tests for causal opposite-signal timing, no same-cycle reversal, short-only route filtering, flat-state suppression, venue-depth exit pricing, fee/funding/friction inclusion, censoring, and source identity.
2. Run the focused tests and retain the expected initial failure.
3. Implement the smallest typed, execution-incapable evaluator by reusing the existing HIP-3 lifecycle engine.
4. Emit control and challenger results under nominal and stressed costs, per fold, without-largest-winner, maximum drawdown, exit-reason counts, and data-censoring counts.
5. Reject success-shaped fallbacks: incomplete marks or depth produce censored lifecycles, not synthetic profits.

## Task 3: Run frozen development and untouched validation

**Files:**
- Create: `data/logs/research/bidirectional_cohort/sp500_close_only_exit_development_20260825_v1.json`
- Create: `data/logs/research/bidirectional_cohort/sndk_close_only_exit_development_20260825_v1.json`
- Create only after selection freeze: corresponding `*_validation_20260825_v1.json` reports.

1. Run SP500 v3 and SNDK exact-route development comparisons against their V61 controls.
2. Require positive stressed net, stressed improvement over control, nonnegative result without the largest winner, no worse maximum drawdown, and nonnegative worst fold.
3. Require at least three independently resolved challenger-relevant lifecycles in development and at least two in untouched validation. If exact data cannot meet those minimums, report `insufficient_evidence` and do not promote.
4. Freeze at most one accepted rule per route, then open validation once.
5. Preserve ETH and BRENTOIL unchanged in this revision unless separately preregistered future evidence passes the same standard.

## Task 3A: Diagnose stop whipsaw without changing account risk

**Files:**
- Modify: `tests/test_cohort_stop_recovery_sensitivity.py`
- Modify: `src/hypervector/research/cohort_stop_recovery_sensitivity.py`
- Create: `tests/test_route_stop_recovery_sensitivity_script.py`
- Create: `scripts/route_stop_recovery_sensitivity.py`
- Create: `data/logs/research/bidirectional_cohort/v61_route_stop_whipsaw_20260825_v1.json`

1. Freeze the exact V61 entry events, stop calculations, mark source, costs, and causal volatility inputs before evaluating alternatives.
2. Report each route's stop distance in price bps, causal ATR units, recent range units, and dollar loss at configured notional. Leverage must not be described as changing the price distance; it changes margin return and liquidation headroom.
3. For every attributable stop exit, measure MAE/MFE before the stop and the causal 15-minute, 1-hour, 4-hour, and original-horizon path after the stop. Classify a possible whipsaw only when price subsequently recovers the entry or reaches the original favorable objective before the original maximum hold.
4. Compare the exact control with a small preregistered family of volatility/structure-clamped stops. Recalculate notional so maximum dollar risk is held equal to the control; do not gain apparent performance by silently increasing risk.
5. Require improved stressed expectancy, no worse maximum drawdown, positive result without the largest winner, nonnegative worst fold, and adequate independent stopped lifecycles. Otherwise preserve the current stop.
6. Treat missing post-stop marks, ambiguous fills, and insufficient samples as `insufficient_evidence`, not as proof that the stop is correct or incorrect.

**Observed disposition:** ETH produced four post-stop entry recoveries among seven
resolved 15-minute post-stop paths, so the whipsaw hypothesis is real for part of
the live sample. The fixed-width challenger still failed strategy-level promotion:
no 80-180 bps equal-dollar-risk width exceeded the 60-bps control in both frozen
historical partitions. BTC robust-v3 stop-cap evidence favored the existing 75-bps
cap over both 60 and 90 bps in development, while its current live stop sample is
only one trade. Preserve the stop contracts and research a separately preregistered
volatility/state challenger rather than widening static barriers.

## Task 4: Implement explicit close-only authority only for an accepted route

**Files:**
- Modify: `src/hypervector/live/multi_asset_live_config.py`
- Modify: `src/hypervector/live/multi_asset_execution_authority.py`
- Modify: `src/hypervector/live/cohort_route_cycle.py`
- Modify: relevant focused parser/route tests
- Create: `tests/test_v62_state_dependent_exit_config.py`
- Create only after acceptance: `configs/multi_asset_growth_first_5000_eight_asset_state_exit_candidate_v62.toml`

1. Write failing runtime tests before implementation.
2. Require an explicit per-symbol `close_only_side_overrides` declaration; reject unknown symbols, sides outside provider capability, overlaps with entry sides, and unsupported route identities.
3. Prove an opposite close-only intent closes an existing opposite position but never opens, adds, reverses, or acts when flat or same-side.
4. Prove stale or missing position state fails closed.
5. Preserve every non-accepted provider, sizing, stop, target, profit-lock, recipe-exit, and hold contract at its normalized payload level.
6. Surface close-only direction and last evaluation in the ledger/TUI without labeling it as a live entry side.

## Task 5: Verification, rollback, and cutover

**Files:**
- Verify: targeted research, config, authority, router, ledger, and TUI tests
- Verify: `tests/ -q -m "not network"`
- Verify: `cargo test -p hypervector-tui`

1. Run focused tests, configuration parsing, fingerprint checks, and report reproducibility.
2. Run the full non-network Python suite and Rust TUI suite.
3. Run execution-incapable successor preflight and confirm eight assets, ten-position portfolio cap, exact sizing, and complete exit telemetry.
4. Query venue and checkpoint state immediately before cutover. Require flat/order-free reconciliation unless exact open-position plan adoption is explicitly proven by tests and direct order reconciliation.
5. Keep V61 available as rollback. Abort cutover on stale data, source identity mismatch, unexpected open orders, profile drift, missing protective stop, ledger/TUI mismatch, or backend multiplicity.
6. After startup, verify one backend, one run identity, fresh heartbeat, correct profile fingerprint, protective orders, ledger writes, and TUI parity.

## Success, falsification, and trade-offs

- **Research success:** a route-specific challenger meets every frozen development and untouched-validation condition after costs and stress.
- **Technical success:** close-only authority is impossible to convert into an entry or reversal, and all unchanged route contracts remain identical.
- **Falsifiers:** insufficient independent lifecycles, negative stressed validation, largest-winner dependence, worse drawdown, missing causal data, direction leakage, position-state ambiguity, or normalized drift outside the accepted route.
- **Simpler alternative:** retain V61 unchanged while collecting exact prospective samples. This avoids unvalidated logic drift but leaves maximum hold as the fallback for SP500/SNDK when no existing profit lock or stop triggers.
- **Trade-off:** a close-only opposite exit can reduce giveback and adverse persistence, but it can also exit before recovery. Route-specific replay and prospective validation determine whether that trade-off is favorable; no profitability guarantee is claimed.

Commits are intentionally deferred because the shared working tree contains extensive user-owned changes. The implementation must not mix, revert, or overwrite unrelated work.
