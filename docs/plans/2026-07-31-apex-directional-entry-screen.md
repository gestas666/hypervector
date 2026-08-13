# Apex Directional Entry Screen Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Translate the potentially useful Apex directional entries onto causal five-minute OHLCV bars and compare them under Hypervector's shared friction model without exposing execution authority.

**Architecture:** Add pure signal builders for the original liquid-market Apex trend, ensemble, and breakout hypotheses. Register them only in the existing report-only shared strategy screen, where every candidate receives identical position, fee, funding, target, stop, and maximum-hold handling. Do not copy Apex's polling-tick buffers, empty position context, or order bridge.

**Tech Stack:** Python 3.13, pandas, pytest, Ruff, existing Hypervector shared bar portfolio.

---

### Task 1: Pure Apex signal contract

**Files:**
- Create: `tests/test_apex_directional_signals.py`
- Create: `src/hypervector/research/apex_directional_signals.py`

**Step 1: Write failing tests**

Require:

- EMA(7/26) entries only on an actual crossover with ADX above the configured threshold.
- The ensemble uses the original four-of-six threshold and treats BB compression as direction-neutral.
- The breakout compares the current close with the prior 20-bar range and uses current bar volume versus prior completed-bar volume.
- All outputs align exactly to the input index, contain long and short entry columns, and reject unordered or malformed OHLCV.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_apex_directional_signals.py -q
```

Expected: collection fails because `hypervector.research.apex_directional_signals` does not exist.

**Step 3: Implement minimal pure builders**

Provide typed, documented builders:

```python
def build_apex_trend_entries(bars: pd.DataFrame, *, adx_threshold: float = 25.0) -> pd.DataFrame: ...
def build_apex_ensemble_entries(bars: pd.DataFrame, *, min_votes: int = 4) -> pd.DataFrame: ...
def build_apex_breakout_entries(
    bars: pd.DataFrame,
    *,
    lookback: int = 20,
    breakout_threshold_bps: float = 50.0,
    volume_surge_mult: float = 2.0,
) -> pd.DataFrame: ...
```

The builders may use only completed bars and must emit entry annotations, not orders.

**Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_apex_directional_signals.py -q
uv run ruff check src/hypervector/research/apex_directional_signals.py tests/test_apex_directional_signals.py
```

Expected: all pass.

### Task 2: Shared report-only cohort

**Files:**
- Modify: `scripts/shared_strategy_screen.py`
- Create: `tests/test_shared_strategy_apex_cohort.py`

**Step 1: Write failing integration tests**

Require an `apex-directional-v1` cohort with three candidates and the existing four uniform exit profiles. Require the output to remain `bar_screen_only_not_executable_evidence` and `selection_applied=false`.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_shared_strategy_apex_cohort.py -q
```

Expected: the new cohort is rejected or missing.

**Step 3: Add the bounded cohort**

Adapt the three pure entry frames into the existing signal schema. Set exit columns false so only the shared profiles determine exits and the experiment measures entry quality consistently.

**Step 4: Verify GREEN**

Run:

```bash
uv run pytest tests/test_shared_strategy_apex_cohort.py -q
uv run ruff check scripts/shared_strategy_screen.py tests/test_shared_strategy_apex_cohort.py
```

Expected: all pass.

### Task 3: Frozen chronological screen

**Files:**
- Create: immutable JSON artifacts under `data/logs/research/` only

**Step 1: Development screen**

Run the three candidates on BTC five-minute bars from 2025-07-28 through 2026-01-28 with all available funding evidence and the fixed shared portfolio profiles.

**Step 2: Rank without selection leakage**

Report trade count, PF, net PnL, fees, maximum drawdown, liquidation count, and monthly dispersion. Preserve every failed trial.

**Step 3: Conditional validation**

Only if a development candidate has PF above one after costs and sufficient trades, run the unchanged candidate on 2026-01-28 through 2026-04-28. Do not tune on validation.

**Step 4: Exact-event follow-up**

Only a candidate that remains positive on validation advances to exact L2/public-trade replay. No candidate is installed into shadow or live from bar-screen evidence alone.

### Task 4: Verification and handoff

**Files:**
- No additional production files

**Step 1: Focused verification**

```bash
uv run pytest tests/test_apex_directional_signals.py tests/test_shared_strategy_apex_cohort.py -q
uv run ruff check src/hypervector/research/apex_directional_signals.py scripts/shared_strategy_screen.py tests/test_apex_directional_signals.py tests/test_shared_strategy_apex_cohort.py
```

**Step 2: Broader non-network verification**

```bash
uv run pytest tests/ -q -m "not network"
```

**Step 3: Evidence-based recommendation**

Recommend promotion, revision, or rejection with confidence, failure modes, and a specific falsifier. Do not commit from the shared dirty worktree unless the user explicitly requests it.
