# Regime Component Attribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an immutable, report-only one-year Hyperliquid attribution that measures whether canonical RANGE labels and observe-only regime components explain future directional or absolute price paths across BTC, ETH, SOL, and HYPE.

**Architecture:** A pure research module will validate venue candle provenance, calculate the existing causal canonical classifier and component bank, then resolve strictly future 5/15/30/60-minute labels inside frozen chronological segments. A thin CLI will process assets sequentially and write one immutable JSON artifact. It will report all observations, non-overlapping effective counts, state-onset results, daily rank-association summaries, and explicit technical gaps; it will not simulate fills, PnL, thresholds, or strategy mutations.

**Tech Stack:** Python 3.13, pandas, NumPy, SciPy, existing Hypervector regime/component modules, pytest, immutable JSON writer.

**Workspace note:** This repository is an active shared dirty worktree. Preserve unrelated changes and do not commit unless the user explicitly requests it.

---

### Task 1: Freeze the point-in-time attribution contract

**Files:**
- Create: `tests/test_regime_component_attribution.py`
- Create: `src/hypervector/research/regime_component_attribution.py`

**Step 1: Write the failing causality and segmentation tests**

Define the wished-for public API:

```python
def build_component_attribution(
    bars: pd.DataFrame,
    *,
    symbol: str,
    segments: tuple[AttributionSegment, ...],
    horizons_minutes: tuple[int, ...] = (5, 15, 30, 60),
) -> dict[str, object]: ...
```

Tests must prove:

- the decision reference is the completed bar close;
- the first label bar begins one minute after that bar;
- a horizon may not cross its chronological segment boundary;
- any `hl_gap_fill` decision or label-path minute is excluded and counted;
- feature values for a historical prefix do not change when future bars are appended;
- segment boundaries are ordered, adjacent or gapped, non-overlapping UTC timestamps;
- execution, model, threshold, fill, and PnL authority are all explicitly absent.

**Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/test_regime_component_attribution.py -q
```

Expected: import failure because the attribution module does not exist.

**Step 3: Implement the minimal validated frame builder**

Use `classify_multitimeframe()` and `build_regime_component_frame()` without duplicating their formulas. Normalize input to an ordered UTC index, accept only `hl` and explicit `hl_gap_fill`, and compute each segment independently so labels cannot cross boundaries.

**Step 4: Run the focused tests and verify GREEN**

Run the same pytest command. Expected: all Task 1 tests pass.

### Task 2: Measure range quality and directional component association

**Files:**
- Modify: `tests/test_regime_component_attribution.py`
- Modify: `src/hypervector/research/regime_component_attribution.py`

**Step 1: Write failing summary tests**

Require each symbol/segment/horizon to report:

- total, usable, gap-excluded, right-censored, and non-overlapping observations;
- canonical state counts and state-onset counts;
- RANGE versus non-RANGE mean/median absolute close return, favorable excursion, and adverse excursion;
- long/short directional-return summaries for directional canonical calls;
- exact `-1/0/+1` direction/alignment outcomes and exact `-3..+3` MTF bias outcomes;
- numeric component daily Spearman IC median, IQR, worst day, ICIR, sign consistency, and number of valid days;
- no pooled-IC field.

Use hand-built bars whose future paths make the expected RANGE and directional relationships unambiguous.

**Step 2: Verify RED**

Run the focused test file and confirm missing summary fields—not test setup—cause failure.

**Step 3: Implement descriptive summaries**

Use every resolved row for descriptive totals, but separately count greedily non-overlapping samples at each horizon. For categorical components report both active-state and state-onset results. For numeric components compute Spearman IC per UTC day and summarize daily ICs; do not pool rows into one correlation.

**Step 4: Verify GREEN and refactor**

Run the focused test file. Keep every public function documented and under 50 lines by separating validation, label resolution, categorical summaries, numeric IC summaries, and artifact assembly.

### Task 3: Add the immutable multi-asset CLI

**Files:**
- Create: `scripts/regime_component_attribution.py`
- Create: `tests/test_regime_component_attribution_script.py`

**Step 1: Write failing CLI tests**

The CLI contract is:

```bash
uv run python scripts/regime_component_attribution.py \
  --bars BTC=data/cache/BTC_1m_365d.parquet \
  --bars ETH=data/cache/ETH_1m_365d.parquet \
  --bars SOL=data/cache/SOL_1m_365d.parquet \
  --bars HYPE=data/cache/HYPE_1m_365d.parquet \
  --development-start 2025-07-28T00:00:00Z \
  --development-end 2026-01-28T00:00:00Z \
  --validation-end 2026-05-28T00:00:00Z \
  --pseudo-holdout-end 2026-07-28T00:00:00Z \
  --output data/logs/research/regime_component_attribution_20260803.json
```

Tests must reject duplicate/missing symbols, non-UTC or unordered boundaries, missing files, unsupported provenance, output overwrite, and partial artifact publication. They must prove all four assets are retained even when their results are weak or contradictory.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_regime_component_attribution_script.py -q
```

Expected: missing script/module behavior.

**Step 3: Implement the thin CLI**

Parse exactly four symbol/path mappings, process one asset at a time, fingerprint each input, retain row/source/time coverage, and publish through `write_immutable_json`. The artifact contract must include:

```python
{
    "schema_version": 1,
    "mode": "regime_component_attribution_report_only",
    "execution_authority": "none",
    "model_authority": "none",
    "thresholds_selected": False,
    "fills_assumed": False,
    "pnl_claimed": False,
    "segments": {"development": ..., "validation": ..., "pseudo_holdout": ...},
    "assets": {...},
    "limitations": [...],
}
```

**Step 4: Verify GREEN**

Run both new test files plus Ruff.

### Task 4: Execute the one-year four-asset attribution

**Files:**
- Create at runtime: `data/logs/research/regime_component_attribution_20260803.json`

**Step 1: Run the frozen command**

Use the command from Task 3 against the four existing `*_1m_365d.parquet` files.

**Step 2: Validate the artifact**

Confirm:

- each asset has exactly the declared input window and provenance counts;
- every segment and horizon appears;
- no label crosses a split boundary;
- gaps and censored paths remain explicit;
- no execution/model/threshold/PnL authority exists;
- development, validation, and pseudo-holdout results are reported separately.

**Step 3: Produce a decision table**

For each component, assign `PROCEED`, `REVISE`, or `STOP` based on cross-asset and cross-segment sign stability, effective count, and whether typical movement plausibly clears costs. These are research dispositions only, not runtime gates.

### Task 5: Integrate evidence into operations without changing execution

**Files:**
- Modify: `docs/guides/acceptance-visual-and-holistic.md`
- Modify: `skills/hypervector-regime-detector/SKILL.md`

**Step 1: Document the artifact and falsifiers**

State that live screen-9 forward counts remain the deployment evidence, while the historical artifact is a venue-matched prior. A component can receive execution weight only after consistent pseudo-holdout and independent live evidence; contradictory live evidence demotes it.

**Step 2: Run final verification**

```bash
uv run pytest tests/ -q -m "not network"
uv run ruff check src/hypervector/research/regime_component_attribution.py scripts/regime_component_attribution.py tests/test_regime_component_attribution.py tests/test_regime_component_attribution_script.py
cargo fmt --all -- --check
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo test -p hypervector-tui
```

Expected: all checks pass. Live backend health, exact BTC/HYPE venue stops, and current checkpoint timestamps must be revalidated independently after the research run.
