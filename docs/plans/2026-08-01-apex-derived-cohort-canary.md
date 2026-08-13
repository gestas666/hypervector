# Apex-Derived Cohort to Canary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adapt a small cohort of Apex strategy concepts into correctly attributed Hypervector research candidates, run bounded chronological validation with realistic Hyperliquid execution assumptions, and prepare staged live canaries that can collect real execution evidence after explicit user approval.

**Architecture:** Keep the retired Hypervelocity strategy and all Hypertrader paper claims outside this work. Implement pure candidate policies and a report-only event replay over the verified Hyperliquid DuckDB archive; reuse existing causal five-minute features and production queue-accounting components where their contracts match. Directional candidates and two-sided market making retain separate attribution but later share one portfolio allocator. No candidate receives shadow or live authority from offline results.

**Tech Stack:** Python 3.12, pandas, NumPy, DuckDB, pytest, Ruff, Hypervector event models, Hyperliquid L2/public trades/funding archives, Rust Ratatui telemetry only after research adapters are verified.

---

## Evidence and Scope Constraints

- Retired Hypervelocity/Hypertrader-derived execution is excluded.
- Existing `apex_trend`, `apex_ensemble`, and `apex_breakout` artifacts are retained as negative evidence and are not rerun or retuned.
- Offline work is bounded to one development pass, one chronological validation pass, and one robustness pass per candidate.
- Performance never creates an implicit technical abort under `SRS_HV1_NO_GATES`; every completed trial is reported.
- Paper/shadow code never constructs a live client. Live canaries remain fail-closed and require fresh explicit `--enabled --i-accept-live-risk` authorization.
- Historical fill evidence must report queue and mark-price limitations explicitly.
- No repository commit or push occurs without a separate user request.

## Selected Cohort

1. `apex_mean_reversion_v2`: completed five-minute price deviation plus causal exhaustion confirmation, one position per symbol, mean-cross/invalidated-extreme/maximum-hold exits.
2. `apex_oi_trend_v2`: completed five-minute price/OI agreement using true interval volume and point-in-time OI. When historical OI coverage is insufficient, report the candidate as `observer_only_insufficient_history` rather than substituting repeated 24-hour values.
3. `apex_regime_mm_v2`: two-sided L2 quoting with actual microprice, public-trade queue depletion, partial fills, cancel/replace latency, inventory skew/caps, adverse-selection markouts, fees, funding, and liquidation-distance telemetry.

### Task 1: Freeze Candidate and Evidence Contracts

**Files:**
- Create: `tests/test_apex_cohort_contract.py`
- Create: `src/hypervector/research/apex_cohort_contract.py`

**Step 1: Write failing contract tests**

Require three immutable candidate identifiers, report-only authority, one-position-per-symbol directional behavior, distinct market-maker inventory accounting, and the exact three-pass research budget.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_apex_cohort_contract.py -q`

Expected: FAIL because `hypervector.research.apex_cohort_contract` does not exist.

**Step 3: Implement the minimal typed contracts**

Add frozen dataclasses and literals for candidate identity, segment identity, execution authority, fee assumptions, latency assumptions, and portfolio limits. Reject unknown candidates, non-positive equity, invalid fees, invalid chronology, and live authority.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_apex_cohort_contract.py -q`

Expected: PASS.

### Task 2: Repair Mean-Reversion and OI Signal Semantics

**Files:**
- Create: `tests/test_apex_cohort_signals.py`
- Create: `src/hypervector/research/apex_cohort_signals.py`

**Step 1: Write failing signal tests**

Require completed-bar inputs, strictly causal rolling statistics, fresh episodes rather than repeated entries, true interval volume, point-in-time OI, explicit exit signals, and no signal when required OI coverage is missing or stale.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_apex_cohort_signals.py -q`

Expected: FAIL because the signal module does not exist.

**Step 3: Implement pure builders**

Implement:

```python
def build_apex_mean_reversion_v2(
    bars: pd.DataFrame,
    books: pd.DataFrame,
    config: MeanReversionConfig,
) -> pd.DataFrame: ...

def build_apex_oi_trend_v2(
    bars: pd.DataFrame,
    contexts: pd.DataFrame,
    config: OITrendConfig,
) -> pd.DataFrame: ...
```

Keep entries, exits, and diagnostics explicit. Do not add an ML gate.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_apex_cohort_signals.py -q`

Expected: PASS.

### Task 3: Implement the Two-Sided Quote Policy

**Files:**
- Create: `tests/test_apex_regime_mm_policy.py`
- Create: `src/hypervector/research/apex_regime_mm_policy.py`

**Step 1: Write failing quote-policy tests**

Require real L2 microprice input, fee-covering spread floors, volatility widening, inventory skew toward flat, hard-cap behavior, stale-book refusal, and cascade-side quote reduction. Verify bids remain below asks and post-only quotes never cross the displayed book.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_apex_regime_mm_policy.py -q`

Expected: FAIL because the policy module does not exist.

**Step 3: Implement the pure policy**

Implement a frozen policy config and a pure `quote()` function. Do not import or call Apex runtime code; translate only the documented inventory/regime hypotheses and fix their known data-flow defects.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_apex_regime_mm_policy.py -q`

Expected: PASS.

### Task 4: Add Report-Only Event Replay

**Files:**
- Create: `tests/test_apex_regime_mm_replay.py`
- Create: `src/hypervector/research/apex_regime_mm_replay.py`

**Step 1: Write failing lifecycle tests**

Cover submit latency, cancel/replace latency, displayed queue ahead, aggressor-side trade depletion, partial fills, maker fees, taker unwind fees, hourly funding, inventory caps, midpoint-mark liquidation distance, adverse-selection markouts, end-of-window flattening, and immutable strategy attribution.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_apex_regime_mm_replay.py -q`

Expected: FAIL because the replay module does not exist.

**Step 3: Implement the smallest event state machine**

Consume normalized `L2SnapshotEvent` and `PublicTradeEvent` sequences. Preserve simultaneous bid and ask orders and cancel/requote state. Refuse unordered evidence, missing trade prints, stale books, invalid funding chronology, or a configuration that could construct live execution.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_apex_regime_mm_replay.py -q`

Expected: PASS.

### Task 5: Add the Bounded Research Command

**Files:**
- Create: `tests/test_apex_cohort_screen_script.py`
- Create: `scripts/apex_cohort_screen.py`

**Step 1: Write failing command tests**

Require explicit `--candidate`, `--segment`, `--start`, `--end`, `--database`, and immutable `--out`. Require `report_only=true`, `execution_authority=none`, `place_attempted=false`, input fingerprints, assumptions, limitations, attribution, and complete negative-result retention.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_apex_cohort_screen_script.py -q`

Expected: FAIL because the command does not exist.

**Step 3: Implement the command**

Use the existing read-only DuckDB loaders for five-minute candidates and add a bounded event query for market making. Refuse output overwrite and refuse more than the declared development, validation, or robustness segment.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_apex_cohort_screen_script.py -q`

Expected: PASS.

### Task 6: Execute the Fixed Offline Budget

**Files:**
- Create: `data/logs/research/apex_cohort_<candidate>_<segment>_v1.json`

**Step 1: Run development once per candidate**

Use the predeclared chronological windows in the cohort contract. Do not tune validation from development outcomes beyond selecting among the small predeclared parameter set.

**Step 2: Run validation once per candidate**

Run every candidate regardless of development performance, preserving the charter's ungated trial rule.

**Step 3: Run one robustness pass per candidate**

Use one predeclared higher-friction or latency perturbation, not a parameter grid.

**Step 4: Publish a concise cohort table**

Report trades/fills, net PnL, profit factor, maximum drawdown, fees, funding, liquidation count/distance, queue depletion, markouts, and evidence limitations. Do not claim private queue fidelity or authentic historical mark price when those are unavailable.

### Task 7: Shared Portfolio and Canary Readiness

**Files:**
- Create: `tests/test_apex_cohort_portfolio.py`
- Create: `src/hypervector/research/apex_cohort_portfolio.py`
- Create: `docs/reviews/2026-08-01-apex-cohort-readiness.md`

**Step 1: Write failing shared-capital tests**

Require one portfolio balance, deterministic conflict resolution, one directional position per symbol, market-maker inventory reservation, per-strategy attribution, aggregate exposure caps, and no double-counted cash or fees.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_apex_cohort_portfolio.py -q`

Expected: FAIL because the portfolio module does not exist.

**Step 3: Implement the portfolio comparison**

Replay timestamped candidate outcomes through one allocator without granting execution authority. Preserve rejected/conflicting intents in telemetry.

**Step 4: Verify and review**

Run:

```bash
uv run pytest tests/test_apex_cohort_contract.py tests/test_apex_cohort_signals.py tests/test_apex_regime_mm_policy.py tests/test_apex_regime_mm_replay.py tests/test_apex_cohort_screen_script.py tests/test_apex_cohort_portfolio.py -q
uv run ruff check src/hypervector/research/apex_* scripts/apex_cohort_screen.py tests/test_apex_*
```

Expected: all focused tests PASS and Ruff is clean.

Document which candidates are technically ready for a staged canary, which remain observer-only, and why. Performance is reported evidence, not an implicit execution gate.

### Task 8: Staged Canary Telemetry and Fail-Closed Launchers

**Files:**
- Modify only after Task 7 evidence identifies the advancing candidates.
- Test paths must be declared before implementation under TDD.

**Step 1: Define candidate-specific telemetry**

Include strategy ID, intent reason, quote/order role, order lifecycle, fills, fees, funding, slippage, queue-ahead estimate, markouts, inventory, liquidation price/distance, and shared available capital.

**Step 2: Add fail-closed canary configurations**

Default each candidate to shadow/observer. Live mode must require both `--enabled` and `--i-accept-live-risk`; secret values remain masked and are never written to artifacts.

**Step 3: Verify TUI projection**

The TUI consumes backend telemetry only. It must not simulate fills, positions, PnL, or strategy decisions.

**Step 4: Stop for explicit arming approval**

Provide exact staged canary commands and capital/exposure assumptions. Do not arm or submit without a fresh user instruction.

