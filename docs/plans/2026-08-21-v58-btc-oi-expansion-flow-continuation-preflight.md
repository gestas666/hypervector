# V58 BTC OI-Expansion Flow-Continuation Preflight Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a report-only, receipt-causal preflight that determines whether BTC upside shocks accompanied by expanding open interest, buy flow, and bid-side depth occur often enough to justify a separately frozen after-cost continuation replay.

**Architecture:** Reuse the verified live-event minute loader and its receipt-time clock, but implement a new BTC-only signal family rather than modifying the rejected OI-deleveraging or one-minute order-flow experiments. The first stage computes feature and onset counts only; it must not load forward quotes, prices, returns, fees, funding, or PnL. A strict predeclared cadence rule chooses at most one upper-tail quantile before any outcome code is allowed.

**Tech Stack:** Python 3.13, pandas, DuckDB read-only inputs, pytest, immutable JSON evidence, SHA-256 source registration.

**Safety:** Every artifact is report-only with `execution_authority=none`. Do not edit V58 configuration, restart the live backend, construct an exchange client, or submit an order. The worktree is shared and dirty, so commit steps are intentionally omitted.

---

### Task 1: Freeze the count-only research contract

**Files:**
- Create: `docs/research-journal/v58-btc-oi-expansion-flow-continuation-preflight-preregistration-20260821-v1.json`
- Test: `tests/test_v58_btc_oi_expansion_preflight_preregistration.py`

**Step 1: Write the failing test**

Assert that the preregistration declares:

- hypothesis `V58_BTC_OI_EXPANSION_FLOW_CONTINUATION_LONG_PREFLIGHT_V1`;
- BTC only and long only;
- completed five-minute decisions using receipt-causal OI, trades, and L2;
- candidate quantiles exactly `0.75`, `0.80`, and `0.90`;
- fixed minimum positive shock `13` bps and OI expansion `0.0005`;
- terminal trade imbalance and top-ten book imbalance both positive;
- one 60-minute non-overlap window;
- strictest-quantile selection using development counts only;
- no forward outcome access in this stage;
- zero execution/live authority.

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_v58_btc_oi_expansion_preflight_preregistration.py
```

Expected: FAIL because the frozen preregistration does not yet exist.

**Step 3: Create the minimal preregistration**

Freeze these windows:

- warmup begins `2026-07-26T23:41:00Z`;
- development `[2026-07-28T00:00:00Z, 2026-08-04T00:00:00Z)`;
- validation `[2026-08-04T00:00:00Z, 2026-08-10T00:00:00Z)`;
- pseudo-holdout `[2026-08-16T00:00:00Z, 2026-08-21T00:00:00Z)`.

The preflight may inspect only counts and source continuity. Choose the strictest quantile with at least 20 non-overlapping development candidate onsets. If none qualifies, stop as data-insufficient. Validation and pseudo-holdout counts are descriptive acceptance checks only and cannot change the selected quantile; each must contain at least ten candidate onsets before an outcome experiment can be preregistered.

**Step 4: Run test to verify it passes**

Run the command from Step 2. Expected: PASS.

### Task 2: Implement causal BTC OI-expansion signals with TDD

**Files:**
- Create: `src/hypervector/research/btc_oi_expansion_continuation.py`
- Create: `tests/test_btc_oi_expansion_continuation.py`
- Reuse: `src/hypervector/research/oi_deleveraging_inputs.py`

**Step 1: Write failing business-logic tests**

Cover one behavior per test:

1. exact five-minute groups only;
2. gaps create new segments and reset rolling history;
3. price and OI thresholds use prior rows only via `shift(1)`;
4. positive price shock and positive OI expansion are both required;
5. aligned buy flow and positive book imbalance define the full candidate;
6. the four fixed attribution arms are nested but only the full arm is selectable;
7. a persistent qualifying state emits one onset inside a 60-minute window;
8. invalid timestamps, duplicate minutes, null features, or unsupported quantiles fail explicitly;
9. output contains no forward-return, quote, fee, funding, PnL, order, or authority-bearing field.

**Step 2: Run tests to verify RED**

```bash
uv run pytest -q tests/test_btc_oi_expansion_continuation.py
```

Expected: collection/import failure because the module does not exist.

**Step 3: Write the minimal implementation**

Expose typed public functions:

```python
def build_oi_expansion_preflight(
    minutes: pd.DataFrame,
    *,
    quantile: float,
    minimum_shock_bps: float = 13.0,
    minimum_oi_expansion_pct: float = 0.0005,
    warmup_bars: int = 288,
    non_overlap_minutes: int = 60,
) -> pd.DataFrame:
    """Return receipt-causal count-only BTC continuation onsets."""
```

Keep every function under 50 lines, type every function, and document public functions.

**Step 4: Run tests to verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 3: Publish an immutable count-only preflight

**Files:**
- Create: `scripts/v58_btc_oi_expansion_preflight.py`
- Create: `tests/test_v58_btc_oi_expansion_preflight_script.py`
- Create at runtime: `data/logs/research/bidirectional_cohort/v58_btc_oi_expansion_flow_continuation_preflight_20260821_v1/report.json`
- Create at runtime: `data/logs/research/bidirectional_cohort/v58_btc_oi_expansion_flow_continuation_preflight_20260821_v1/manifest.json`

**Step 1: Write failing publisher tests**

Require the publisher to:

- refuse an existing output directory;
- open DuckDB read-only;
- bind the preregistration, generator files, and every relevant `live_event_files.file_id` into evidence;
- verify the source evidence is unchanged before and after evaluation;
- publish counts by partition, quantile, and attribution arm;
- select only from development counts using the frozen rule;
- publish no signal timestamps or outcomes;
- state `execution_authority=none`, `report_only=true`, `outcomes_computed=false`, and `live_change=false`.

**Step 2: Run tests to verify RED**

```bash
uv run pytest -q tests/test_v58_btc_oi_expansion_preflight_script.py
```

Expected: FAIL because the publisher does not exist.

**Step 3: Implement the minimal publisher**

The command is:

```bash
uv run python scripts/v58_btc_oi_expansion_preflight.py \
  --database data/research/market.duckdb \
  --output data/logs/research/bidirectional_cohort/v58_btc_oi_expansion_flow_continuation_preflight_20260821_v1
```

The report must not contain forward quotes or returns. It should fail rather than bridge the August recorder gap.

**Step 4: Run tests to verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 4: Register inputs before the first count run

**Files:**
- Create: `docs/research-journal/v58-btc-oi-expansion-flow-continuation-preflight-input-registration-20260821-v1.json`
- Test: `tests/test_v58_btc_oi_expansion_preflight_input_registration.py`

**Step 1: Write a failing registration test**

Require exact SHA-256 and byte identities for the preregistration and generators, plus a stable aggregate identity for the relevant BTC event-part file IDs. Require `outcomes_computed=false` and `execution_authority=none`.

**Step 2: Run the test to verify RED**

```bash
uv run pytest -q tests/test_v58_btc_oi_expansion_preflight_input_registration.py
```

Expected: FAIL because the registration does not exist.

**Step 3: Create the registration from verified current inputs**

Do not edit a registered generator afterward. If a defect appears, invalidate the run and create a new version rather than silently updating the registration.

**Step 4: Run the test to verify GREEN**

Run the command from Step 2. Expected: PASS.

### Task 5: Run once, reproduce, and apply the frozen disposition

**Files:**
- Create at runtime: `data/logs/research/bidirectional_cohort/v58_btc_oi_expansion_flow_continuation_preflight_20260821_v1_reproduction/`
- Create: `docs/research-journal/v58-btc-oi-expansion-flow-continuation-preflight-result-20260821-v1.json`

**Step 1: Run the registered count-only preflight once**

Use Task 3's command. Do not edit generators between registration and run.

**Step 2: Reproduce to a distinct immutable output**

Require semantic report equality after removing only generation timestamps.

**Step 3: Apply the preregistered result**

- If no quantile has 20 development onsets, disposition is `data_insufficient`; do not inspect outcomes.
- If the selected quantile has fewer than ten onsets in either OOS partition, disposition is `data_insufficient`; do not inspect outcomes.
- Otherwise freeze a separate outcome preregistration before writing or running any return replay.

**Step 4: Verify no live mutation**

Refresh the current V58 checkpoint and assert runtime profile fingerprint, backend health, protection, and venue reconciliation remain unchanged by this research.

### Task 6: Full verification

Run:

```bash
uv run pytest -q \
  tests/test_v58_btc_oi_expansion_preflight_preregistration.py \
  tests/test_btc_oi_expansion_continuation.py \
  tests/test_v58_btc_oi_expansion_preflight_script.py \
  tests/test_v58_btc_oi_expansion_preflight_input_registration.py
uv run ruff check \
  src/hypervector/research/btc_oi_expansion_continuation.py \
  scripts/v58_btc_oi_expansion_preflight.py \
  tests/test_btc_oi_expansion_continuation.py \
  tests/test_v58_btc_oi_expansion_preflight_script.py
uv run mypy --ignore-missing-imports --follow-imports=skip \
  src/hypervector/research/btc_oi_expansion_continuation.py \
  scripts/v58_btc_oi_expansion_preflight.py
```

Expected: all checks pass, no file exceeds 500 lines, no function exceeds 50 lines, and no live configuration/process/order state changes.
