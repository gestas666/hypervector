# V52 HYPE Aligned Fixed-Target Sensitivity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Measure whether a fixed take-profit improves the exact v52 HYPE aligned-entry cohort after costs without changing entries, using development-only selection and later-confirmation evaluation that cannot influence the selected target.

**Architecture:** Add an authority-free fixed-entry counterfactual evaluator that overlays a predeclared target grid on the existing immutable `aligned_only` lifecycle sidecars. The evaluator keeps each baseline entry and native exit fixed, lets the native exit win any same-bar ambiguity, models fees, funding, and adverse target-exit slippage, selects one target from development only, then evaluates only that frozen identity on the previously opened later-confirmation segment. A thin immutable command verifies every source and generator hash before publication; it does not import live execution factories or modify v52.

**Tech Stack:** Python 3.13, pandas/Parquet, pytest, Ruff, Hypervector immutable evidence utilities.

---

### Task 1: Fixed-entry target lifecycle evaluator

**Files:**
- Create: `src/hypervector/research/hype_fixed_target_sensitivity.py`
- Test: `tests/test_hype_fixed_target_sensitivity.py`

**Step 1: Write the failing target-hit and same-bar-precedence tests**

```python
def test_long_target_uses_first_completed_bar_and_exact_costs() -> None:
    result = evaluate_fixed_target_period(
        market=_target_market(),
        trades=_one_long_trade(),
        target_bps=60.0,
        config=_execution(),
        fold_count=1,
        target_exit_slippage_bps=2.0,
    )
    outcome = result["outcomes"][0]
    assert outcome["status"] == "target_triggered"
    assert outcome["target_timestamp_utc"] == "2026-01-01T00:01:00+00:00"
    assert outcome["target_reference_price"] == pytest.approx(100.6)
    assert result["entry_identity_sha256"] == entry_identity(_one_long_trade())


def test_native_exit_wins_when_target_is_only_visible_on_native_exit_bar() -> None:
    result = evaluate_fixed_target_period(
        market=_same_bar_ambiguity_market(),
        trades=_one_long_trade(exit_time="2026-01-01T00:01:00Z"),
        target_bps=60.0,
        config=_execution(),
        fold_count=1,
        target_exit_slippage_bps=2.0,
    )
    assert result["outcomes"][0]["status"] == "native_exit_preserved"
```

**Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest -q \
  tests/test_hype_fixed_target_sensitivity.py::test_long_target_uses_first_completed_bar_and_exact_costs \
  tests/test_hype_fixed_target_sensitivity.py::test_native_exit_wins_when_target_is_only_visible_on_native_exit_bar
```

Expected: collection/import failure because `hype_fixed_target_sensitivity` does not exist.

**Step 3: Implement the minimal evaluator**

```python
def evaluate_fixed_target_period(
    market: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    target_bps: float,
    config: HypeExitReplayConfig,
    fold_count: int,
    target_exit_slippage_bps: float,
) -> dict[str, object]:
    """Evaluate one fixed target without changing baseline entries."""
    outcomes = tuple(
        _evaluate_trade(market, row, target_bps, config, target_exit_slippage_bps)
        for row in trades.to_dict(orient="records")
    )
    if not outcomes:
        raise ValueError("HYPE fixed-target sensitivity requires lifecycles")
    return {
        "target_bps": target_bps,
        "fixed_entry_cohort": True,
        "entry_identity_sha256": entry_identity(trades),
        "native": _summary(outcomes, "native_net_return_bps"),
        "challenger": _summary(outcomes, "challenger_net_return_bps"),
        "folds": _folds(market.index, outcomes, fold_count),
        "outcomes": list(outcomes),
    }
```

The target path is `[entry_time, native_exit_time)`. The target reference is `entry_price * (1 +/- target_bps / 10_000)`. A long uses the first bar with `high >= target`; a short uses the first bar with `low <= target`. The exit price applies adverse target-exit slippage, fees use the frozen 4.5-bps-per-side formula, and hourly funding is retained only through the target timestamp. No target visible only in the native exit bar may replace the native exit.

**Step 4: Add failing validation tests, then implement fail-closed validation**

Cover:

- missing lifecycle minute;
- unordered/duplicate market timestamps;
- nonpositive/nonfinite target;
- invalid side;
- duplicate entry identity;
- target slippage below nominal or nonfinite;
- an empty cohort;
- long and short target direction;
- funding through the target boundary;
- entry identity invariant across every target.

Run:

```bash
uv run pytest -q tests/test_hype_fixed_target_sensitivity.py
```

Expected after GREEN: all focused tests pass.

### Task 2: Development-only grid selection and confirmation isolation

**Files:**
- Modify: `src/hypervector/research/hype_fixed_target_sensitivity.py`
- Modify: `tests/test_hype_fixed_target_sensitivity.py`

**Step 1: Write failing selection-isolation tests**

```python
def test_confirmation_cannot_change_development_selection() -> None:
    baseline = build_fixed_target_report(..., confirmation_periods=_quiet_confirmation())
    changed = build_fixed_target_report(..., confirmation_periods=_extreme_confirmation())
    assert baseline["selection"] == changed["selection"]
    assert baseline["later_confirmation"] != changed["later_confirmation"]


def test_report_is_report_only_and_preserves_all_grid_trials() -> None:
    report = build_fixed_target_report(...)
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert tuple(row["target_bps"] for row in report["development_grid"]) == (
        40.0, 60.0, 80.0, 100.0, 150.0, 200.0, 300.0, 500.0
    )
```

**Step 2: Verify RED**

Run:

```bash
uv run pytest -q \
  tests/test_hype_fixed_target_sensitivity.py::test_confirmation_cannot_change_development_selection \
  tests/test_hype_fixed_target_sensitivity.py::test_report_is_report_only_and_preserves_all_grid_trials
```

Expected: `build_fixed_target_report` is missing.

**Step 3: Implement the frozen selection contract**

Predeclare the development grid as:

```python
TARGET_GRID_BPS = (40.0, 60.0, 80.0, 100.0, 150.0, 200.0, 300.0, 500.0)
TARGET_EXIT_TAIL_SLIPPAGE_BPS = 5.0
```

Each grid target reports nominal target exits at 2 bps and a target-exit-only tail at 5 bps. The native lifecycle remains the exact baseline outcome in both views; therefore the 5-bps view is explicitly labeled a target-execution tail sensitivity rather than a full-strategy stress replay.

Select from development only using the deterministic key:

```python
def _selection_key(row: Mapping[str, object]) -> tuple[object, ...]:
    tail = _object(row["target_exit_tail"])
    folds = _object(tail["folds"])
    summary = _object(tail["challenger"])
    return (
        int(folds["positive_folds"]),
        float(folds["worst_fold_net_bps"]),
        float(summary["without_largest_winner_net_bps"]),
        float(summary["net_return_bps"]),
        -float(row["target_bps"]),
    )
```

The report retains every grid row and labels the rule as development tuning, not a performance gate. Freeze the selected target and entry identity before evaluating later confirmation. Later confirmation evaluates the selected target only and cannot change `selection`, `selected_target_bps`, or the development entry identity.

**Step 4: Verify GREEN**

Run:

```bash
uv run pytest -q tests/test_hype_fixed_target_sensitivity.py
```

Expected: all tests pass.

### Task 3: Immutable exact-v52 command boundary

**Files:**
- Create: `scripts/hype_aligned_fixed_target_sensitivity.py`
- Create: `tests/test_hype_aligned_fixed_target_sensitivity_script.py`

**Step 1: Write failing command-boundary tests**

Test that the command:

- accepts only the complete v6 alignment manifest;
- requires `compression_alignment_replay.contract.frozen_compression_policy_id == compression_5m50_1m40_pullback`;
- filters only `cohort == aligned_only`;
- requires 41 development rows and 1 uncensored later-confirmation row for the frozen source artifact;
- verifies all baseline, candle, funding, and generator hashes;
- refuses a pre-existing output;
- publishes nothing after an injected source/generator mutation;
- does not import live order or signing factories.

Run:

```bash
uv run pytest -q tests/test_hype_aligned_fixed_target_sensitivity_script.py
```

Expected: import failure because the script does not exist.

**Step 2: Implement the thin command**

The defaults are:

```python
_BASELINE = _ROOT / "data/logs/research/hype_compression_breakout_challenger_20260816_v6_alignment"
_DEVELOPMENT_BARS = _ROOT / "data/cache/HYPE_1m_365d.parquet"
_DEVELOPMENT_FUNDING = _ROOT / "data/cache/vendor/hyperliquid/HYPE/20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
_CONFIRMATION_CANDLES = _ROOT / "data/cache/vendor/0xarchive/hyperliquid/HYPE/20260728T000000000000Z_20260810T234500000000Z_candles_1m/candles.parquet"
_CONFIRMATION_FUNDING = _ROOT / "data/cache/vendor/hyperliquid/HYPE/20260728T000000000000Z_20260811T000000000000Z_funding/funding.parquet"
```

The command builds the same development and continuous confirmation market segments as the v6 source, filters the immutable alignment sidecars to `aligned_only`, snapshots file evidence before evaluation, rechecks it before publication, and uses `write_immutable_json`. It prints only the output path, selected development target, disposition, and `execution_authority=none`.

**Step 3: Verify GREEN and boundaries**

Run:

```bash
uv run pytest -q \
  tests/test_hype_fixed_target_sensitivity.py \
  tests/test_hype_aligned_fixed_target_sensitivity_script.py
uv run ruff check \
  src/hypervector/research/hype_fixed_target_sensitivity.py \
  scripts/hype_aligned_fixed_target_sensitivity.py \
  tests/test_hype_fixed_target_sensitivity.py \
  tests/test_hype_aligned_fixed_target_sensitivity_script.py
```

Expected: all tests and Ruff pass.

### Task 4: Run, verify, and journal the immutable experiment

**Files:**
- Create: `data/logs/research/hype_aligned_fixed_target_fixed_entry_sensitivity_20260816_v1.json`
- Create: `docs/research-journal/v52-hype-aligned-fixed-target-sensitivity-v1.json`

**Step 1: Publish the immutable report**

```bash
uv run python scripts/hype_aligned_fixed_target_sensitivity.py \
  --out data/logs/research/hype_aligned_fixed_target_fixed_entry_sensitivity_20260816_v1.json
```

Expected: one JSON line with `execution_authority=none`; no runtime/config/process files change.

**Step 2: Independently validate the report**

Verify:

- all recorded source and generator hashes;
- exact development entry count 41, 19 long/22 short;
- exact later-confirmation entry count 1, long;
- identical development entry identity for control and all targets;
- development selection rule reproduced from serialized grid rows;
- confirmation did not affect selection;
- fees, funding, slippage, target timestamps, and leave-largest calculations reconcile;
- output contract says report-only, no automatic promotion, no runtime change;
- live v52 PID, fingerprint, positions, and orders are unchanged.

**Step 3: Write the decision journal**

Use the mandated proposal schema. If the frozen target does not outperform the native exit robustly in development and later confirmation, record `rejected` or `deferred` and keep v52 unchanged. If it does, record an approval-ready proposal but set `explicit_approval_requested=true`; do not edit or restart v52 without a new human approval.

**Step 4: Final verification**

```bash
uv run pytest -q \
  tests/test_hype_fixed_target_sensitivity.py \
  tests/test_hype_aligned_fixed_target_sensitivity_script.py \
  tests/test_hype_breakout_exit_replay.py \
  tests/test_hype_compression_exit_challenger.py \
  tests/test_hype_compression_breakout_challenger_script.py
uv run ruff format --check \
  src/hypervector/research/hype_fixed_target_sensitivity.py \
  scripts/hype_aligned_fixed_target_sensitivity.py \
  tests/test_hype_fixed_target_sensitivity.py \
  tests/test_hype_aligned_fixed_target_sensitivity_script.py
uv run ruff check \
  src/hypervector/research/hype_fixed_target_sensitivity.py \
  scripts/hype_aligned_fixed_target_sensitivity.py \
  tests/test_hype_fixed_target_sensitivity.py \
  tests/test_hype_aligned_fixed_target_sensitivity_script.py
git diff --check -- \
  src/hypervector/research/hype_fixed_target_sensitivity.py \
  scripts/hype_aligned_fixed_target_sensitivity.py \
  tests/test_hype_fixed_target_sensitivity.py \
  tests/test_hype_aligned_fixed_target_sensitivity_script.py \
  docs/plans/2026-08-16-v52-hype-aligned-fixed-target-sensitivity.md \
  docs/research-journal/v52-hype-aligned-fixed-target-sensitivity-v1.json
```

Require every new file to be at most 500 lines and every function at most 50 lines. Stage or commit only through an explicit reviewed path manifest; do not use `git add -A` in the existing dirty worktree.

