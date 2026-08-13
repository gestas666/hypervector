# BTC Structural + HYPE V4 Candidate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stage an independently attributed, bidirectional BTC structural-continuation provider and the matched fixed-60 HYPE V4 provider for activation only after an exact flat-account boundary.

**Architecture:** Preserve the canonical providers as causal signal sources and wrap only exact-one-blocker evaluations in independent flat-entry-only collectors. Each candidate owns a durable accepted-entry clock, a unique strategy identity, a fixed 60-minute exit contract, explicit modeled friction evidence, and no authority until selected by a separately validated profile. The running live process and venue orders remain untouched during implementation.

**Tech Stack:** Python 3.13, pandas, TOML profiles, append-only JSONL ledgers, pytest, Rust/Ratatui checkpoint projection.

---

### Task 1: Share durable candidate cadence state

**Files:**
- Create: `src/hypervector/live/cohort_candidate_entry_clock.py`
- Modify: `src/hypervector/live/hype_relaxed_one_blocker_provider.py`
- Test: `tests/test_cohort_candidate_entry_clock.py`

1. Write failing tests proving accepted entries are recovered by exact strategy and symbol, incomplete tails fail closed, and unrelated actions do not consume cadence.
2. Run `uv run pytest -q tests/test_cohort_candidate_entry_clock.py` and require failure because the module is absent.
3. Extract the existing append-only offset/line parser into a typed `AcceptedEntryClock`; preserve the HYPE error alias for compatibility.
4. Run the new tests plus `tests/test_hype_relaxed_one_blocker_provider.py`; require all pass.

### Task 2: Implement the BTC structural exact-one-blocker collector

**Files:**
- Create: `src/hypervector/live/btc_structural_contract.py`
- Create: `src/hypervector/live/btc_structural_one_blocker_provider.py`
- Test: `tests/test_btc_structural_one_blocker_provider.py`

1. Write failing tests for exact `awaiting_hourly_sma_cross` matching, causal use of `readiness.side`, long and short emission, 60-second freshness, 75-minute accepted-entry spacing, startup seed non-execution, and existing-ledger recovery.
2. Run the focused test and verify a missing implementation failure.
3. Implement `BTC_STRUCTURAL_FIXED60_STRATEGY = "btc_structural_continuation_fixed60_bidirectional_v1"` and a BTC-only collector. Emit an intent only when the canonical range evaluation has exactly one blocker, a structural long/short side, is fresh, and is rearmed.
4. Copy regime/readiness telemetry without creating a new threshold or score. Label the candidate `staged_profile_only`, `fixed_60m`, and `opi_execution_gate=false`.
5. Run the focused tests and require pass.

### Task 3: Register independent collectors and strict source contracts

**Files:**
- Modify: `src/hypervector/live/hype_relaxed_contract.py`
- Modify: `src/hypervector/live/multi_asset_intent_poller.py`
- Modify: `src/hypervector/live/multi_asset_live_config.py`
- Modify: `crates/hypervector-tui/src/backend_cohort_provider.rs`
- Test: `tests/test_multi_asset_intent_poller.py`
- Test: `tests/test_multi_asset_live_config.py`

1. Add failing tests requiring default collector construction for BTC V1 and HYPE V4 and rejecting wrong symbols, clocks, or widened execution scopes.
2. Run the focused tests and verify failure.
3. Add HYPE V4 to the fixed-horizon identity set; map both new identities to 1-minute sources and readiness lookbacks.
4. Construct candidate collectors only when their provider identities exist in the profile.
5. Add Python and Rust semantic validation: BTC candidate is BTC-only/1m/BTC execution; HYPE candidates are HYPE-only/1m/HYPE execution.
6. Run Python and Rust focused tests and require pass.

### Task 4: Stage the next flat-boundary profile

**Files:**
- Create: `configs/multi_asset_bidirectional_evidence_candidate_v4.toml`
- Create: `tests/test_multi_asset_evidence_candidate_config.py`

1. Write a failing profile test asserting four isolated assets, both directions everywhere, one position per coin, maximum four positions, and exact provider priorities/scopes.
2. Stage legacy range-onset as observation-only. Add BTC structural V1 at `$25`, `5x`, 60-bps stop, no target, fixed 60-minute hold, 75-minute accepted-entry spacing, and `flat_entry_only`.
3. Add HYPE matched fixed-60 V4 at `$25`, `5x`, 80-bps stop, no target, fixed 60-minute hold, and `flat_entry_only`.
4. Retain canonical HYPE and BTC source-follow as observation-only because their exact deployed-shape evidence is negative. Keep BTC structural and HYPE V4 above Hulk for same-cycle flat-entry conflicts while preserving all evaluations.
5. Load in observe and armed-live modes without starting either; require exact fingerprint stability.

### Task 5: Bind evidence and TUI labels

**Files:**
- Modify: `src/hypervector/live/multi_asset_strategy_evidence.py`
- Modify: `crates/hypervector-tui/src/cohort_widgets.rs`
- Test: `tests/test_multi_asset_strategy_evidence.py`
- Test: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

1. Add failing tests requiring exact evidence records rather than `unreviewed_exact_mapping`.
2. Bind BTC V1 to the retrospective N10/all-long result and prospective N0 conflict journal; bind HYPE V4 to matched N3 evidence. State low confidence and explicit falsifiers.
3. Add compact TUI aliases and assert both providers remain visibly distinct from their source strategies.
4. Run focused tests and require pass.

### Task 6: Full validation and flat-boundary handoff

**Files:**
- Update: `docs/reviews/2026-08-04-live-executable-opportunity-matrix.md`
- Update: `skills/hypervector-cli/SKILL.md`

1. Run `uv run pytest tests/ -q -m "not network"`.
2. Run `uv run ruff check` on changed Python files.
3. Run `cargo fmt --all -- --check`, `cargo test -p hypervector-tui`, `cargo clippy -p hypervector-tui --all-targets -- -D warnings`, and `cargo build --release -p hypervector-tui`.
4. Verify the current backend process, position, venue stop, target, and checkpoint remain unchanged.
5. At a later exact flat boundary, verify zero positions and zero open orders from venue-backed checkpoint evidence before replacing the live profile. If either remains, do not restart.
6. After activation, require an immutable configuration identity, fresh strategy journals, fee/funding/slippage telemetry, and no duplicate-symbol position before calling the canary active.

No commit is included in this execution plan because the current worktree contains a large pre-existing user-owned change set; commit scope requires an explicit user request.
