# Complete Portfolio Cockpit v25 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore a complete backend-authored portfolio cockpit covering the full BTC/ETH/SOL/HYPE strategy matrix and the qualified HIP-3 roster, with real setup readiness, candles, L2, routing, positions, and journal evidence instead of empty panels.

**Architecture:** The Python cohort configuration remains the single source of truth for assets, providers, route authority, and one-position-per-asset limits. Core-perp and namespaced HIP-3 instruments share the existing serialized Hyperliquid client boundary, while provider collectors publish a common `ProviderEvaluation` contract consumed unchanged by the router, checkpoint, and Rust TUI. The TUI validates expected-versus-observed setup coverage and renders explicit technical unavailability rather than omitting rows or manufacturing values.

**Tech Stack:** Python 3.13, typed dataclasses, pandas, official Hyperliquid SDK, JSONL ledgers, TOML profiles, Rust/Ratatui, pytest, cargo test.

---

## Acceptance contract

- The replacement profile declares nine unique assets: `BTC`, `ETH`, `SOL`, `HYPE`, `xyz:SP500`, `xyz:SPCX`, `xyz:SNDK`, `xyz:GOLD`, and `xyz:BRENTOIL`.
- `maximum_positions` equals nine, while the existing engine invariant remains one position per asset.
- The core setup roster restores 14 provider-symbol identities: Hulk on four assets, Range Onset on four, Source Follow on BTC, Breakout Onset on four, and ETH Pullback on ETH.
- HIP-3 setup telemetry publishes both frozen research families for every qualified HIP-3 asset: Swing/HA and Breakout Pressure, for ten additional provider-symbol identities.
- Every configured provider-symbol identity produces a current `ProviderEvaluation`, including readiness fraction, exact blockers, indicators, source timestamp, decision timestamp, side, and authority.
- The setup screen reports `expected`, `observed`, and `missing` counts. Missing identities are an explicit error state and cannot appear as a blank successful panel.
- Charts and depth can select all nine assets. They use backend candles and venue L2 only.
- Core and HIP-3 execution routes are explicit configuration data. No route is inferred from visibility, research results, or a TUI label.
- Namespaced HIP-3 execution remains fail-closed until authenticated adapter preflight, effective fee evidence, position/order reconciliation, and mutation tests pass.
- No active backend is hot-mutated. Transition requires a verified pre-change backup, completed drain, flat/order-free venue boundary, new pre-start backup, and explicit live-risk flags.

### Task 1: Freeze and verify the current live implementation baseline

**Files:**
- Read: `configs/multi_asset_bidirectional_eth_sol_full_observation_canary_v24.toml`
- Create by command: `data/backups/bidirectional_cohort/prestart_<timestamp>_<fingerprint>/`

**Step 1:** Run the credential-free pre-change backup against v24.

**Step 2:** Run `scripts/cohort_prestart_backup_verify.py` against the exact emitted bundle.

**Step 3:** Record the active run ID, profile fingerprint, asset states, owned orders, and transition-drain state without changing the backend.

### Task 2: Add a failing complete-roster configuration test

**Files:**
- Create: `tests/test_complete_portfolio_cockpit_v25_config.py`
- Create later: `configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml`

**Step 1:** Write a test requiring the nine assets, nine position slots, 14 core setup identities, ten HIP-3 setup identities, both directions, unique provider priorities, and explicit execution scopes.

**Step 2:** Run the isolated test and verify RED because the v25 profile does not exist.

**Step 3:** Add the minimal TOML profile needed to satisfy configuration identity assertions.

**Step 4:** Run the test and retain any parser failure as the next red test for Task 3.

### Task 3: Support exact namespaced assets in live configuration

**Files:**
- Modify: `src/hypervector/live/multi_asset_live_config.py`
- Modify: `src/hypervector/live/bidirectional_cohort_factory.py`
- Test: `tests/test_multi_asset_live_config.py`
- Test: `tests/test_bidirectional_cohort_factory.py`

**Step 1:** Write failing tests that accept exact lowercase-dex/uppercase-asset HIP-3 identities and reject malformed namespaces.

**Step 2:** Verify RED at the current core-symbol-only `AssetExecutionEnvelope` validation.

**Step 3:** Add one shared venue-identity parser returning display symbol and optional perp-dex namespace; reuse `validate_hip3_symbol` rather than duplicating syntax rules.

**Step 4:** Run focused tests GREEN and verify legacy core fingerprints remain unchanged.

### Task 4: Extend the authenticated SDK factory for HIP-3

**Files:**
- Modify: `src/hypervector/live/hyperliquid_sol_factory.py`
- Modify: `src/hypervector/live/hyperliquid_btc_adapter.py`
- Modify: `src/hypervector/live/bidirectional_cohort_factory.py`
- Modify: `src/hypervector/live/serialized_hyperliquid_clients.py` only if a missing protocol method is proven
- Test: `tests/test_hyperliquid_sol_factory.py`
- Test: `tests/test_hyperliquid_btc_adapter.py`
- Test: `tests/test_bidirectional_cohort_factory.py`

**Step 1:** Write failing tests proving one authenticated SDK pair receives the exact `xyz` perp-dex list and each HIP-3 adapter binds its namespace.

**Step 2:** Verify RED without constructing a network client.

**Step 3:** Extend the injected builder protocol with a backward-compatible `perp_dexes` argument, pass it to official `Info` and `Exchange`, and pass each adapter's exact namespace to `HyperliquidPerpReader`.

**Step 4:** Test market entry, reduce-only stop, close, open-order read, position read, and leverage update payload identity using fakes.

**Step 5:** Run focused tests GREEN.

### Task 5: Publish causal HIP-3 setup evaluations

**Files:**
- Create: `src/hypervector/live/hip3_setup_provider.py`
- Modify: `src/hypervector/live/multi_asset_intent_poller.py`
- Test: `tests/test_hip3_setup_provider.py`
- Test: `tests/test_multi_asset_intent_poller.py`

**Step 1:** Write failing tests for the two frozen provider IDs, completed 15-minute decisions, no retroactive entries, gap reset, both directions, and complete readiness payloads.

**Step 2:** Verify RED because no HIP-3 collector exists.

**Step 3:** Reuse `build_gap_aware_swing_ha_signals` and `build_breakout_pressure_signals`; do not duplicate the research formulas.

**Step 4:** Translate the latest completed signal state into `ProviderEvaluation` and fresh `StrategyIntent` records with explicit source and parameter provenance.

**Step 5:** Include live L2 pressure only for the Breakout Pressure family and expose unavailable pressure as a technical blocker, never numeric zero.

**Step 6:** Run focused tests GREEN.

### Task 6: Enforce setup-coverage completeness in checkpoint and TUI

**Files:**
- Modify: `scripts/multi_asset_bidirectional_live_checkpoint.py`
- Modify: `crates/hypervector-tui/src/backend_cohort.rs`
- Modify: `crates/hypervector-tui/src/cohort_router.rs`
- Modify: `crates/hypervector-tui/src/cohort_setup_detail.rs`
- Test: `tests/test_multi_asset_bidirectional_live_checkpoint.py`
- Test: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

**Step 1:** Write failing Python tests for `expected_provider_symbols`, `observed_provider_symbols`, and exact missing identities.

**Step 2:** Write failing Rust tests requiring a visible incomplete-coverage alarm and selectable unavailable rows rather than empty boxes.

**Step 3:** Publish expected setup identities from the active configuration identity and reconcile them with latest evaluations.

**Step 4:** Render compact roster totals and an explicit missing-identity list; retain full details in the Enter inspector.

**Step 5:** Run Python and Rust focused tests GREEN.

### Task 7: Make all nine assets selectable without layout degradation

**Files:**
- Modify: `crates/hypervector-tui/src/cohort_market_pulse.rs`
- Modify: `crates/hypervector-tui/src/cohort_chart.rs`
- Modify: `crates/hypervector-tui/src/cohort_depth.rs`
- Modify: `crates/hypervector-tui/src/cohort_regime.rs`
- Test: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`
- Test: `crates/hypervector-tui/tests/hip3_roster_view_test.rs`

**Step 1:** Add failing 120x36 and 160x44 render tests with nine assets.

**Step 2:** Verify RED for clipping or missing selection.

**Step 3:** Implement bounded selected-asset windows for tabs and tables while preserving left/right navigation through the entire roster.

**Step 4:** Verify all panels retain real data provenance, timestamps, and authority labels.

**Step 5:** Run render tests GREEN and inspect captured output manually.

### Task 8: Validate the staged profile without live mutation

**Files:**
- Verify: `configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml`
- Verify: relevant Python and Rust files from Tasks 2-7

**Step 1:** Load v25 in observe mode and construct every default collector.

**Step 2:** Run one bounded observe poll against public venue data and require 24/24 setup identities, nine candle streams, and nine L2 snapshots.

**Step 3:** Run all focused Python tests, `uv run pytest tests/ -q -m "not network"`, and `cargo test -p hypervector-tui`.

**Step 4:** Build the release TUI and perform the documented visual acceptance at 120x36 and 160x44.

**Step 5:** Run authenticated read-only preflight for all nine assets, including exact HIP-3 fee and namespace evidence. Do not place or cancel orders.

### Task 9: Prepare, but do not silently perform, the live transition

**Files:**
- Create: `docs/guides/cohort-live-transition-and-rollback-v25.md`

**Step 1:** Record exact old/new profile IDs, fingerprints, expected execution pairs, implementation hash, and rollback profile.

**Step 2:** Require the active backend to drain normally; do not force-close protected positions for a display update.

**Step 3:** At flat/order-free state, archive the completed drain and verify the archive.

**Step 4:** Launch v25 only with explicit `--enabled --i-accept-live-risk`, verify the mandatory new pre-start bundle, and reconcile all nine assets before accepting startup.

**Step 5:** Accept the transition only when the TUI reports 24/24 setup coverage, no routing outside the frozen map, no duplicate positions, owned stops for every open lifecycle, and fresh market data.

## Failure modes and falsifiers

- If the official SDK cannot map a namespaced asset through authenticated `Exchange` calls using the exact configured perp-dex list, HIP-3 execution remains technically unavailable; the setup and market telemetry still remain visible and explicit.
- If the live HIP-3 signal reconstruction disagrees with the frozen research signal on identical completed bars, the provider is rejected until parity is restored.
- If nine-asset polling repeatedly breaches the 15-second cycle or triggers unresolved 429 failures, the shared data acquisition boundary must be redesigned before live activation.
- If the TUI reports complete coverage while any configured provider-symbol identity lacks a current backend evaluation, the implementation fails acceptance.
- Any mismatch between venue positions/orders and backend lifecycle ownership aborts the profile transition.

## Confidence

Medium. Core-roster restoration is high-confidence because the providers and TUI contract already exist. HIP-3 display integration is also high-confidence because the read-only checkpoint is currently fresh. HIP-3 authenticated execution is medium-confidence until the official SDK namespace path passes injected mutation tests and authenticated read-only mainnet preflight; an actual canary fill would be required to validate real order acknowledgements and friction.
