# V62 ETH Adaptive Stop and BRENTOIL Profit Protection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete an evidence-bound ETH adaptive-stop challenger, BRENTOIL profit-lock decision, and eight-route stop diagnostic without mutating V61 unless a frozen challenger passes every promotion criterion.

**Architecture:** Extend the existing report-only replay with a causal, signal-row structural stop anchor that is clamped from the actual next-open entry fill. Keep entry signals, opposite-intent behavior, costs, funding, and occupancy fixed. Reuse the existing completed-bar profit-lock mechanism for BRENTOIL and publish route diagnostics from immutable checkpoint/audit evidence.

**Tech Stack:** Python 3.13, pandas, pytest, existing Hypervector replay/audit modules, TOML live configuration, JSON research journal.

---

## Frozen experiment contract

- Control: ETH 60-bps fixed stop, 12-hour fallback, 4.5 bps fee and 2 bps slippage per side, same-provider opposite entry closes the open lifecycle at the next open.
- Candidate `atr_structure_60_120_v1`:
  - completed one-minute bars only;
  - Wilder ATR(14), including the completed signal bar;
  - 12-completed-bar adverse structure, including the signal bar;
  - volatility anchor is signal close minus/plus `1.5 * ATR(14)`;
  - structure anchor is rolling low for longs and rolling high for shorts;
  - choose the more adverse causal anchor;
  - after the actual next-open entry fill, clamp distance to `[60, 120]` bps;
  - candidate notional scale per lifecycle is `60 / resolved_stop_bps`.
- Chronology:
  - construction ends `2026-03-28T12:00:00Z` exclusive;
  - one-day purge;
  - confirmation begins `2026-03-29T12:00:00Z` and ends `2026-05-28T12:00:00Z` exclusive;
  - the previously opened `2026-05-29` through `2026-07-28` block is descriptive audit only.
- No parameter retuning after the first candidate replay. Failure produces a rejection artifact.
- BRENTOIL evaluates the already-predeclared `a25_floor15_trail10`, `a40_floor15_trail20`, and `a60_floor15_trail30` policies. The V58 excluded long is development-only; only post-registration resolved lifecycles count as confirmation.
- Every report remains `execution_authority=none`, `automatic_promotion=false`, and `runtime_strategy_changed=false`.

## Promotion criteria

ETH must satisfy all of the following against the corrected live-parity control:

1. Exact entry-signal count parity and identical source timestamps.
2. Positive equal-risk net delta in construction and confirmation.
3. Positive equal-risk result after removing the largest winner in both partitions.
4. Nonnegative worst chronological monthly fold delta in confirmation.
5. No worse equal-risk maximum drawdown in confirmation.
6. Both long and short confirmation slices nonnegative.
7. The descriptive opened-final block must not contradict confirmation on net-delta sign.

BRENTOIL requires:

1. At least one resolved post-registration long and short current-identity lifecycle.
2. Positive delta for each side after fees, funding, and measured fill-ratio reuse.
3. Positive leave-largest result across eligible current-identity lifecycles.
4. No missing completed one-minute candle coverage.

## Task 1: Freeze provenance and runtime control

**Files:**
- Create: `docs/research-journal/v62-eth-brentoil-exit-priority-preregistration-20260825-v1.json`
- Read: `configs/multi_asset_growth_first_5000_eight_asset_sndk_exit_preserved_candidate_v61.toml`
- Read: `data/runtime/bidirectional_cohort/latest_checkpoint.json`

1. Record V61 profile/fingerprint, immutable ETH data hashes, formulas, boundaries, costs, and criteria.
2. Verify the live checkpoint is fresh, running-consistent, and configuration-matched.
3. Verify that no experiment artifact grants execution authority.

## Task 2: Add causal structural stop support to the replay

**Files:**
- Modify: `src/hypervector/research/hype_breakout_exit_models.py`
- Modify: `src/hypervector/research/hype_breakout_exit_replay.py`
- Modify: `src/hypervector/research/hype_breakout_exit_validation.py`
- Test: `tests/test_hype_breakout_exit_replay.py`

1. Write a failing test proving a signal-row anchor is converted from the actual next-open fill and clamped to explicit minimum/maximum bps.
2. Run the focused test and require the expected missing-contract failure.
3. Add optional `stop_anchor_column`, `minimum_stop_bps`, and `maximum_stop_bps` replay fields with strict all-or-none validation.
4. Resolve the stop using the same long/short clamp semantics as `BoundExecutionPlan`.
5. Re-run focused tests and retain fixed-stop compatibility.

## Task 3: Build the ETH causal anchor and equal-risk report

**Files:**
- Create: `src/hypervector/research/eth_adaptive_stop_challenger.py`
- Create: `tests/test_eth_adaptive_stop_challenger.py`
- Create: `scripts/eth_adaptive_stop_challenger.py`
- Create: `tests/test_eth_adaptive_stop_challenger_script.py`

1. Write failing tests for causal ATR, signal-row anchors, no future-bar dependence, warmup withholding, side-specific structure, and equal-risk scaling.
2. Implement `build_eth_adaptive_stop_market(...) -> pd.DataFrame` and `build_equal_risk_comparison(...) -> dict[str, object]` with complete type hints and public docstrings.
3. Write a failing command test for immutable inputs, source hashes, corrected opposite-intent control, chronology, and no-authority output.
4. Implement the immutable command using the existing exact ETH entry replay.
5. Run the command once and publish a new immutable artifact under `data/logs/research/bidirectional_cohort/`.

## Task 4: Publish BRENTOIL current-identity profit-lock decision

**Files:**
- Create: `src/hypervector/research/brentoil_profit_lock_decision.py`
- Create: `tests/test_brentoil_profit_lock_decision.py`
- Create: `scripts/brentoil_profit_lock_decision.py`
- Create: `tests/test_brentoil_profit_lock_decision_script.py`

1. Write failing tests that separate excluded development lifecycles from post-registration confirmation and require both confirmation sides.
2. Implement a source/profile/strategy-bound decision over exact closed lifecycle rows only.
3. Publish an immutable checkpoint-prefix audit and a BRENTOIL decision artifact.
4. If both-side evidence is incomplete, return `retain_v61_insufficient_confirmation` without creating a candidate config.

## Task 5: Complete route-by-route stop diagnostics

**Files:**
- Create: `src/hypervector/research/cohort_route_stop_diagnostic.py`
- Create: `tests/test_cohort_route_stop_diagnostic.py`
- Create: `scripts/cohort_route_stop_diagnostic.py`
- Create: `tests/test_cohort_route_stop_diagnostic_script.py`

1. Write failing tests for all V61 executable route identities, exact protective-stop counts, whipsaw counts, and explicit insufficient-evidence states.
2. Implement one bounded report that never drops a route because it has zero stopped trades.
3. Publish the immutable eight-asset diagnostic from a stable checkpoint prefix.

## Task 6: Decide and prepare a successor only if supported

**Files:**
- Create: `docs/research-journal/v62-eth-brentoil-exit-priority-disposition-20260825-v1.json`
- Conditional create: `configs/multi_asset_growth_first_5000_eight_asset_exit_priority_candidate_v62.toml`
- Conditional test: `tests/test_v62_exit_priority_config.py`

1. Apply the frozen promotion criteria without selecting from headline net PnL alone.
2. If neither challenger passes, record rejection/insufficient evidence and preserve V61.
3. If one passes, create a V62 config changing only that route's validated execution contract.
4. Test full V61 inheritance, exact route scope, leverage, sizing, and exit precedence.

## Task 7: Verify and reconcile

1. Run focused tests during every red/green cycle.
2. Run Ruff check and format verification on every changed Python file.
3. Run `uv run pytest tests/ -q -m "not network"`.
4. Run `cargo test -p hypervector-tui -q`.
5. Run `uv run python -m hypervector status`.
6. Recheck live heartbeat, fingerprint, open positions, and protective orders.
7. Do not cut over while any lifecycle or owned order remains unless restart adoption is independently proven.

