# ETH Breakout Transfer Observer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task.

**Goal:** Freeze the ETH-only breakout transfer candidate as a prospective, report-only provider without changing the running live execution mappings.

**Architecture:** Wrap the causal canonical breakout-onset collector and admit only ETH events whose measured entry telemetry shows prior 15-minute BBWP minimum at or below 40 and a non-positive directional bar body. Give the candidate an independent strategy identity and fixed 60-bps stop/12-hour hold contract. Add it to the v10 observation profile with an empty execution-symbol set.

**Tech Stack:** Python 3.13, pandas, typed Hypervector provider contracts, TOML configuration, pytest.

---

### Task 1: Freeze the evidence contract

**Files:**
- Add: `docs/reviews/2026-08-05-eth-sol-breakout-transfer-tuning.md`
- Reference: `data/logs/research/eth_hype_breakout_entry_tuning_development_v1_20260805.json`
- Reference: `data/logs/research/sol_hype_breakout_entry_tuning_development_v1_20260805.json`

1. Record the complete data split, friction assumptions, bounded trial count, selected ETH parameters, one-time final-block result, and SOL rejection.
2. Record uncertainty and explicit prospective falsifiers.

### Task 2: Add the ETH causal provider using TDD

**Files:**
- Create: `tests/test_eth_breakout_transfer_provider.py`
- Create: `src/hypervector/live/eth_breakout_transfer_provider.py`

1. Write failing tests proving ETH-only validation, both-side preservation, the BBWP/pullback conjunction, readiness blockers, and intent identity.
2. Run the focused test and verify failure because the provider is absent.
3. Implement the smallest wrapper around `HypeBreakoutOnsetCollector`.
4. Run the focused test and verify it passes.

### Task 3: Register the observer without execution authority using TDD

**Files:**
- Modify: `tests/test_evidence_routed_hype75_all_asset_observe_candidate_config.py`
- Modify: `src/hypervector/live/multi_asset_intent_poller.py`
- Modify: `src/hypervector/live/multi_asset_live_config.py`
- Modify: `src/hypervector/live/multi_asset_strategy_evidence.py`
- Create: `configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml`

1. Add failing config tests for ETH-only observation, `execution_symbols = []`, 60-bps stop, and 43,200-second hold.
2. Verify the current loader/collector registry rejects the new identity.
3. Register the typed collector, validator, and research evidence.
4. Verify the executable mapping set remains exactly Hulk/BTC and canonical HYPE/HYPE.

### Task 4: Verify and observe

**Files:**
- No live configuration authority changes.

1. Run focused Python tests.
2. Run all non-network Python tests and Rust TUI tests.
3. Do not restart the current live backend; record that the observer becomes active only on a separately backed-up restart.
4. After a safe restart is explicitly chosen, verify checkpoint/TUI readiness includes the ETH candidate and that no order/fill can carry its strategy identity.
