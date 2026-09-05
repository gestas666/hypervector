# V55 SPCX Cash-Open Live Candidate Implementation Plan

> **For Codex:** Use the project hypervector CLI skill, test-driven development, and verification-before-completion. Execute incrementally and stop before live cutover until the user explicitly approves the reviewed staged profile.

**Goal:** Add one exact SPCX cash-open gap-reversal route to the unchanged v53 BTC/HYPE foundation without copying the mechanism to another asset or changing existing route parameters.

**Architecture:** Build a dedicated 15-minute SPCX provider from receipt-causal public trades so its signal OHLC matches the frozen archive-research construction. Preserve the prior cash-session close as a dynamic absolute target through evaluation, intent routing, execution-plan binding, restart serialization, and venue protection. Use an 80-bps reduce-only stop plus recipe-authoritative cash-close/source-recovery exits and a 25-bar maximum hold. Stage a successor configuration only after source, execution, telemetry, TUI, and preflight tests pass.

**Tech Stack:** Python 3.12, pandas, Hyperliquid public trade/event ledgers, typed cohort execution contracts, pytest, Ruff, Rust TUI acceptance tests.

---

## Frozen candidate contract

- Base: preserve the running v53 BTC and HYPE providers, parameters, sizing, and exits.
- Added symbol: `xyz:SPCX` only.
- Provider: `hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1`.
- Signal source: receipt-causal Hyperliquid public trades aggregated by `(exchange_ts_ms, trade_id)` into completed 15-minute OHLC.
- Session: U.S. cash session under a maintained exchange calendar; no hard-coded archive-only holiday list in live code.
- Entry: at least 20-bps gap from prior eligible cash-session close; decide after the completed 09:30-09:45 New York bar; first-bar close must remain beyond prior close; fade the gap.
- Target: exact prior eligible cash-session close, persisted as an absolute favorable target anchor.
- Stop: fixed 80 bps from actual fill, reduce-only.
- Fallback exits: provider-authoritative cash close, source recovery/failure close when required, and 25 completed 15-minute bars maximum.
- Sizing candidate: $5,000 notional, 10x isolated, 10% of a $5,000 portfolio as initial margin; no variable sizing in this increment.
- Frequency reference: development 20 trades / approximately 3.94 per week. This is provisional, not a live guarantee.
- Evidence limitation: development was positive under nominal/stress and largest-winner removal, but 11 development lifecycles were technically unresolved and validation/holdout remain unopened.
- Authority: staged candidate only until explicit reviewed live-cutover approval.

## Task 1: Add exact dynamic-target execution plumbing

**Files:**
- Modify: `src/hypervector/live/bidirectional_intents.py`
- Modify: `src/hypervector/live/multi_asset_signal_source.py`
- Modify: `src/hypervector/live/cohort_execution_plan.py`
- Modify: `src/hypervector/live/cohort_execution_contract_selection.py`
- Modify: `src/hypervector/live/cohort_entry_submission.py`
- Test: `tests/test_bidirectional_intents.py`
- Test: `tests/test_cohort_execution_plan.py`
- Create: `tests/test_cohort_dynamic_target_binding.py`

1. Write failing tests proving a positive finite target anchor survives evaluation-to-intent-to-action routing, execution binding, payload serialization, and restart recovery.
2. Require an explicit `absolute_anchor` target policy and reject missing, non-favorable, crossed, or incompatible anchors at actual fill.
3. Preserve legacy providers byte-for-field equivalent when no target anchor is supplied.
4. Run the focused tests and Ruff before proceeding.

## Task 2: Build a receipt-causal SPCX public-trade provider

**Files:**
- Create: `src/hypervector/live/hip3_cash_open_trade_source.py`
- Create: `src/hypervector/live/hip3_cash_open_gap_provider.py`
- Test: `tests/test_hip3_cash_open_trade_source.py`
- Test: `tests/test_hip3_cash_open_gap_provider.py`

1. Write failing tests for canonical trade dedup/conflict rejection, receipt cutoff, completed bars, restart boundary, source gaps, exact session calendar, both entry sides, no-entry bars, target anchor, and recipe exits.
2. Reuse the frozen research signal function after constructing the exact live-source frame; do not duplicate its trading logic.
3. Emit complete readiness telemetry and no intent when source/session/target evidence is incomplete.
4. Prove the prospective Aug. 17 decision remains no-entry under the live source.

## Task 3: Register the isolated provider and execution contract

**Files:**
- Modify the smallest existing provider registry/factory modules that remain under project size limits.
- Create a new registry helper if an existing module would exceed 500 lines or a function 50 lines.
- Test the exact provider, symbol, both-side capability, entry delay, stop, target, recipe-exit, and maximum-hold identity.

1. Add the exact SPCX provider without modifying older HIP-3 provider identities.
2. Bind `absolute_anchor`, 80-bps stop, `provider_recipe_exit_policy="honor"`, and 22,500-second maximum hold.
3. Fail closed if the target is not favorable at actual fill.

## Task 4: Stage the successor profile

**Files:**
- Create: `configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml`
- Create: `tests/test_growth_first_5000_spcx_cash_open_v55_config.py`

1. Clone v53 semantically, retaining BTC/HYPE unchanged.
2. Add SPCX at 10x, $5,000 maximum notional, 10% margin fraction, and one exact provider route.
3. Require three assets, six directional scopes, no observe-only routes, and portfolio capacity consistent with enabled assets.
4. Verify route-to-execution-contract coverage exactly.

## Task 5: Complete telemetry, TUI, and operational acceptance

**Files:**
- Add focused Python telemetry/checkpoint tests.
- Add focused Rust 160x50 TUI acceptance tests.
- Create a staged transition runbook and accounting-epoch/preflight contract.

1. Show SPCX signal state, opening gap, threshold distance, prior-close target, source/session readiness, entry/stop/TP/exit state, actions, withholds, and lifecycle PnL.
2. Ensure current v53 remains attachable and staged v55 is visually distinct.
3. Require flat/order-free venue and ledger reconciliation, fresh fee/leverage/depth inputs, backup, and exact profile fingerprint before cutover.

## Task 6: Verify and request live approval

1. Run all affected Python tests without network, full relevant config/runner tests, Ruff, Rust acceptance tests, line/function limits, JSON/TOML parsing, and `git diff --check`.
2. Run a bounded report-only provider poll with no signing/order client and verify the exact decision/target payload.
3. Reconcile the running v53 PID/profile/positions/orders after tests.
4. Present the 15-field proposal, exact risks, rollback, evidence limitation, and command.
5. Do not stop v53 or arm v55 until the user explicitly approves the final reviewed profile.

