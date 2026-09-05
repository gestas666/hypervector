# BTC Trend-Pullback Reacceleration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and validate the preregistered report-only BTC 15-minute trend-pullback reacceleration long experiment without changing V58 live authority.

**Architecture:** Resample the immutable one-minute BTC cache into causal completed 15-minute and one-hour bars, run one explicit pullback/reacceleration state machine, and project one-shot long entries back onto the minute index. Reuse the existing shared bar portfolio engine for the frozen 60-bps stop, 60-bps target, 24-hour fallback, sizing, fees, slippage, liquidation proxy, and funding; publish immutable JSON and Parquet evidence plus an independent reproduction check.

**Tech Stack:** Python 3.13, pandas, NumPy, PyArrow/Parquet, pytest, Ruff, existing Hypervector shared-bar portfolio research modules.

---

### Task 1: Freeze and validate the preregistration identity

**Files:**
- Existing: `docs/research-journal/v58-btc-trend-pullback-reacceleration-preregistration-20260821-v1.json`
- Create: `tests/test_btc_trend_pullback_reacceleration_preregistration.py`

**Step 1: Write the identity verification test**

```python
from hashlib import sha256
from pathlib import Path
import json


def test_preregistration_is_report_only_and_source_bound() -> None:
    path = Path(
        "docs/research-journal/"
        "v58-btc-trend-pullback-reacceleration-preregistration-20260821-v1.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["hypothesis_id"] == (
        "V58_BTC_15M_TREND_PULLBACK_REACCELERATION_LONG_V1"
    )
    assert payload["authority"]["execution_authority"] == "none"
    assert payload["authority"]["automatic_live_change"] is False
    for evidence in payload["source_evidence"].values():
        source = Path(evidence["path"])
        content = source.read_bytes()
        assert len(content) == evidence["bytes"]
        assert sha256(content).hexdigest() == evidence["sha256"]
```

**Step 2: Run the test to verify the already-frozen contract**

Run: `uv run pytest -q tests/test_btc_trend_pullback_reacceleration_preregistration.py`

Expected: PASS only when the preregistration and all three evidence sources retain their exact bytes. This is a frozen-document verification, not a production-code TDD red step.

**Step 3: Commit checkpoint**

```bash
git add docs/research-journal/v58-btc-trend-pullback-reacceleration-preregistration-20260821-v1.json tests/test_btc_trend_pullback_reacceleration_preregistration.py
git commit -m "test: freeze BTC pullback preregistration"
```

### Task 2: Implement the completed-bar signal state machine with TDD

**Files:**
- Create: `src/hypervector/research/btc_trend_pullback_reacceleration.py`
- Create: `tests/test_btc_trend_pullback_reacceleration.py`

**Step 1: Write failing causal-state tests**

Cover these exact behaviors in separate tests:

```python
def test_signal_requires_completed_hourly_uptrend() -> None: ...


def test_pullback_arms_only_at_or_below_hourly_ema21_above_ema55() -> None: ...


def test_first_four_bar_high_reacceleration_emits_once() -> None: ...


def test_emission_requires_new_pullback_before_rearming() -> None: ...


def test_pullback_expires_after_eight_completed_bars() -> None: ...


def test_hourly_trend_failure_clears_armed_state() -> None: ...


def test_signal_is_projected_at_completed_15m_endpoint() -> None: ...


def test_gap_resets_warmup_and_pullback_state() -> None: ...


def test_invalid_or_negative_market_values_fail_explicitly() -> None: ...
```

Use deterministic one-minute fixtures whose final 15-minute decision bar can be mutated after the expected endpoint. Assert that the earlier signal set does not change, proving no future-bar use.

**Step 2: Run the tests to verify failure**

Run: `uv run pytest -q tests/test_btc_trend_pullback_reacceleration.py`

Expected: FAIL because the candidate module does not yet exist.

**Step 3: Implement the minimal typed state machine**

Create frozen dataclasses:

```python
@dataclass(frozen=True)
class BtcTrendPullbackConfig:
    """Exact parameters from the authority-none preregistration."""

    fast_ema_hours: int = 21
    slow_ema_hours: int = 55
    pullback_expiry_bars: int = 8
    reacceleration_lookback_bars: int = 4
    report_only: bool = True
    execution_authority: str = "none"


@dataclass(frozen=True)
class BtcTrendPullbackSignals:
    """Minute-aligned entry pulses and completed-bar diagnostics."""

    entries: pd.DataFrame
    diagnostics_15m: pd.DataFrame
    completed_hourly: pd.DataFrame
```

Implement public function:

```python
def build_btc_trend_pullback_signals(
    minute_bars: pd.DataFrame,
    config: BtcTrendPullbackConfig | None = None,
) -> BtcTrendPullbackSignals:
    """Build causal one-shot BTC pullback-reacceleration long entries."""
```

Keep each helper below 50 lines. Validate aware, unique, monotonic minute input; nonnegative volume; strictly positive internally coherent OHLC; explicit gap markers; and report-only authority. Resample only complete 15-minute and one-hour buckets. Iterate completed 15-minute rows chronologically with typed state fields `armed_at`, `expires_after_position`, and `consumed`; do not vectorize state in a way that can leak later rows.

**Step 4: Run signal tests**

Run: `uv run pytest -q tests/test_btc_trend_pullback_reacceleration.py`

Expected: PASS.

**Step 5: Commit checkpoint**

```bash
git add src/hypervector/research/btc_trend_pullback_reacceleration.py tests/test_btc_trend_pullback_reacceleration.py
git commit -m "feat: add causal BTC pullback signals"
```

### Task 3: Reuse the shared bar portfolio under the exact economic contract

**Files:**
- Create: `src/hypervector/research/btc_trend_pullback_reacceleration_replay.py`
- Create: `tests/test_btc_trend_pullback_reacceleration_replay.py`

**Step 1: Write failing replay tests**

```python
def test_replay_uses_next_minute_entry_and_fixed_60_60_exit() -> None: ...


def test_same_bar_stop_and_target_resolve_stop_first() -> None: ...


def test_nominal_and_stress_change_only_taker_slippage() -> None: ...


def test_exact_hourly_funding_has_long_side_sign() -> None: ...


def test_missing_or_nonfinite_funding_fails() -> None: ...


def test_ten_percent_margin_ten_x_leverage_caps_notional_at_5000() -> None: ...


def test_entry_window_does_not_force_close_at_partition_boundary() -> None: ...
```

**Step 2: Verify the tests fail**

Run: `uv run pytest -q tests/test_btc_trend_pullback_reacceleration_replay.py`

Expected: FAIL because the replay adapter is absent.

**Step 3: Implement the minimal replay adapter**

Expose:

```python
def evaluate_btc_trend_pullback_reacceleration(
    minute_bars: pd.DataFrame,
    slippage_bps_per_taker_side: float,
    *,
    entry_start_utc: pd.Timestamp | None = None,
    entry_end_utc: pd.Timestamp | None = None,
) -> BtcTrendPullbackReplay:
    """Replay the frozen candidate with no execution authority."""
```

Construct `SharedPortfolioConfig` with `$5,000` initial equity, `0.10` margin fraction, `10x` leverage, `$5,000` maximum notional, 6% margin target and stop (60 price bps at 10x), 24-hour maximum hold, 4.5-bps taker fees, 1.5-bps target maker fee, exact funding, stop-first ambiguity, one-bar cooldown, and same-side reset. Do not alter the shared simulator unless a failing generic regression proves a reusable engine defect.

**Step 4: Run replay and shared-engine regression tests**

Run: `uv run pytest -q tests/test_btc_trend_pullback_reacceleration_replay.py tests/test_shared_bar_portfolio.py`

Expected: PASS.

**Step 5: Commit checkpoint**

```bash
git add src/hypervector/research/btc_trend_pullback_reacceleration_replay.py tests/test_btc_trend_pullback_reacceleration_replay.py
git commit -m "feat: replay BTC pullback economics"
```

### Task 4: Load and bind immutable historical inputs

**Files:**
- Create: `src/hypervector/research/btc_trend_pullback_historical.py`
- Create: `tests/test_btc_trend_pullback_historical.py`

**Step 1: Write failing source-integrity tests**

Test exact byte/hash validation for the preregistration, BTC bar cache, and funding Parquet; reject changed source bytes, duplicate funding timestamps, unordered funding, missing hourly settlements inside the requested window, non-Hyperliquid/non-gap-fill source labels, and gaps silently bridged without reset metadata.

**Step 2: Verify failure**

Run: `uv run pytest -q tests/test_btc_trend_pullback_historical.py`

Expected: FAIL because the loader is absent.

**Step 3: Implement typed loading and funding projection**

Expose:

```python
def load_btc_trend_pullback_history(
    preregistration_path: Path,
) -> BtcTrendPullbackHistory:
    """Load exact registered bars and funding without execution authority."""
```

Reuse existing sweep-relaxation input validation and funding projection helpers where their semantics match; extract a shared helper only if doing so removes more than ten duplicate lines without behavior drift.

**Step 4: Run loader tests**

Run: `uv run pytest -q tests/test_btc_trend_pullback_historical.py`

Expected: PASS.

**Step 5: Commit checkpoint**

```bash
git add src/hypervector/research/btc_trend_pullback_historical.py tests/test_btc_trend_pullback_historical.py
git commit -m "feat: bind BTC pullback evidence inputs"
```

### Task 5: Publish all partitions and both cost scenarios without performance aborts

**Files:**
- Create: `src/hypervector/research/btc_trend_pullback_experiment.py`
- Create: `tests/test_btc_trend_pullback_experiment.py`

**Step 1: Write failing report-contract tests**

Require exactly 18 standalone summary rows: three partitions × two scenarios × candidate/control/no-action. Require every registered metric, even for zero trades; represent undefined profit factor as `null`, not zero. Require all acceptance predicates to be computed after the complete result and never to suppress a row.

**Step 2: Verify failure**

Run: `uv run pytest -q tests/test_btc_trend_pullback_experiment.py`

Expected: FAIL because the report builder is absent.

**Step 3: Implement the report builder**

Expose:

```python
def build_btc_trend_pullback_report(
    history: BtcTrendPullbackHistory,
    preregistration: Mapping[str, object],
    *,
    generated_at: datetime,
) -> BtcTrendPullbackExperiment:
    """Build complete registered results and a trade-level sidecar."""
```

Include signal cadence, interarrival distribution, overlap between candidate and sweep control, trade results, largest-winner removal, fees, funding, drawdown, liquidation, ambiguity, gap, and end-of-data fields. Preserve all losing and sparse cells. Do not select parameters or create a live profile.

**Step 4: Run experiment tests**

Run: `uv run pytest -q tests/test_btc_trend_pullback_experiment.py`

Expected: PASS.

**Step 5: Commit checkpoint**

```bash
git add src/hypervector/research/btc_trend_pullback_experiment.py tests/test_btc_trend_pullback_experiment.py
git commit -m "feat: report BTC pullback experiment"
```

### Task 6: Add current-V58 shared BTC route competition

**Files:**
- Create: `src/hypervector/research/btc_trend_pullback_route_competition.py`
- Create: `tests/test_btc_trend_pullback_route_competition.py`

**Step 1: Write failing portfolio-interaction tests**

Test explicit route priority, one BTC position, no simultaneous long/short fill, same-minute conflict attribution, candidate displacement by an already-open control route, and exact baseline/candidate reconciliation. If either V58 short identity cannot be reconstructed from its immutable evidence, require an `identity_unavailable` result with the missing dependency rather than substituting Hulk v2 or another profile.

**Step 2: Verify failure**

Run: `uv run pytest -q tests/test_btc_trend_pullback_route_competition.py`

Expected: FAIL because the route-competition adapter is absent.

**Step 3: Implement exact-route comparison**

Build two chronological shared-account cases from exact existing V58 route signal generators:

- baseline: both V58 Hulk short identities plus the unchanged sweep long;
- candidate: baseline plus the new pullback long.

Preserve provider identity and priority in every scheduled or displaced signal. Report incremental PnL, drawdown, occupancy, route fills, displacement, conflicts, fees, funding, and largest-winner sensitivity. This module remains report-only and imports no live adapter.

**Step 4: Run route-competition tests**

Run: `uv run pytest -q tests/test_btc_trend_pullback_route_competition.py`

Expected: PASS or an explicit registered `identity_unavailable` outcome when exact historical reconstruction is not technically possible.

**Step 5: Commit checkpoint**

```bash
git add src/hypervector/research/btc_trend_pullback_route_competition.py tests/test_btc_trend_pullback_route_competition.py
git commit -m "feat: compare BTC pullback route interaction"
```

### Task 7: Add immutable CLI publication and reproduction

**Files:**
- Create: `scripts/v58_btc_trend_pullback_reacceleration.py`
- Create: `tests/test_v58_btc_trend_pullback_reacceleration_script.py`

**Step 1: Write failing CLI tests**

Test `--help`, unique output-directory refusal, report/Parquet/manifest creation, source and generator hashes, authority-none fields, and no overwrite. Run the script twice to two temporary directories and require normalized report equality plus exact trade-sidecar equality.

**Step 2: Verify failure**

Run: `uv run pytest -q tests/test_v58_btc_trend_pullback_reacceleration_script.py`

Expected: FAIL because the script is absent.

**Step 3: Implement the CLI**

The parser must require an explicit unique `--out-dir` and default only the registered preregistration path. Publish `report.json`, `trades.parquet`, and `manifest.json` atomically; refuse existing outputs. Console output should show only result locations, hashes, row counts, disposition, and authority-none status.

**Step 4: Run CLI tests**

Run: `uv run pytest -q tests/test_v58_btc_trend_pullback_reacceleration_script.py`

Expected: PASS.

**Step 5: Commit checkpoint**

```bash
git add scripts/v58_btc_trend_pullback_reacceleration.py tests/test_v58_btc_trend_pullback_reacceleration_script.py
git commit -m "feat: publish BTC pullback evidence"
```

### Task 8: Run the frozen experiment once and independently reproduce it

**Files:**
- Create: `data/logs/research/bidirectional_cohort/v58_btc_trend_pullback_reacceleration_20260821_v1/`
- Create: `data/logs/research/bidirectional_cohort/v58_btc_trend_pullback_reacceleration_20260821_v2_reproduction/`

**Step 1: Run the registered experiment**

Run:

```bash
uv run python scripts/v58_btc_trend_pullback_reacceleration.py \
  --out-dir data/logs/research/bidirectional_cohort/v58_btc_trend_pullback_reacceleration_20260821_v1
```

Expected: immutable complete report, trade sidecar, and manifest regardless of economics.

**Step 2: Run the independent reproduction to a new path**

Run:

```bash
uv run python scripts/v58_btc_trend_pullback_reacceleration.py \
  --out-dir data/logs/research/bidirectional_cohort/v58_btc_trend_pullback_reacceleration_20260821_v2_reproduction
```

Expected: normalized reports and trade rows match exactly; only publication timestamps and self-identifying output paths may differ.

**Step 3: Verify manifests and registered comparisons**

Run the script test plus a direct SHA-256/row-count reconciliation. Treat any mismatch as a technical failure; do not interpret economic results until resolved.

### Task 9: Journal the result and attach it to continuous improvement

**Files:**
- Create: `docs/research-journal/v58-btc-trend-pullback-reacceleration-result-20260821-v1.json`
- Modify: `src/hypervector/research/v58_btc_long_coverage_context.py`
- Modify: `tests/test_v58_btc_long_coverage_context.py`

**Step 1: Write the result journal from the immutable report**

Include recommendation, why now, evidence reviewed, problem/opportunity, applicable regime, alternatives, proposed live change, expected upside, risks, completed and remaining validation, success metrics, rollback triggers, confidence, and explicit approval request. A rejected result must name the failed predicates and prohibit nearby retuning; a supported result must still propose no automatic live change.

**Step 2: Write the failing continuous-ledger test**

Require exact result/evidence hashes and attach the new hypothesis as accepted, rejected, or deferred without changing the current V58 route row or execution authority.

**Step 3: Verify failure, implement minimal attachment, and rerun**

Run: `uv run pytest -q tests/test_v58_btc_long_coverage_context.py`

Expected: initial FAIL, then PASS after the typed attachment is implemented.

**Step 4: Commit checkpoint**

```bash
git add docs/research-journal/v58-btc-trend-pullback-reacceleration-result-20260821-v1.json src/hypervector/research/v58_btc_long_coverage_context.py tests/test_v58_btc_long_coverage_context.py
git commit -m "docs: record BTC pullback disposition"
```

### Task 10: Full verification and completion audit

**Files:**
- Verify all files above; do not modify the V58 live config.

**Step 1: Run focused tests**

Run:

```bash
uv run pytest -q \
  tests/test_btc_trend_pullback_reacceleration_preregistration.py \
  tests/test_btc_trend_pullback_reacceleration.py \
  tests/test_btc_trend_pullback_reacceleration_replay.py \
  tests/test_btc_trend_pullback_historical.py \
  tests/test_btc_trend_pullback_experiment.py \
  tests/test_btc_trend_pullback_route_competition.py \
  tests/test_v58_btc_trend_pullback_reacceleration_script.py \
  tests/test_v58_btc_long_coverage_context.py
```

Expected: PASS.

**Step 2: Run project verification**

Run:

```bash
uv run pytest tests/ -q -m "not network"
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
cargo test -p hypervector-tui
git diff --check
```

Expected: all commands exit zero. Ignored network or real-checkpoint tests remain explicitly identified.

**Step 3: Audit scope and safety**

Verify:

- `configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml` is byte-identical to the pre-experiment source;
- no live ledger, order, position, stop, target, sizing, leverage, or authority field changed;
- every preregistered partition/scenario/comparison is present or explicitly `identity_unavailable` with technical provenance;
- manifests reproduce exact report and trade-sidecar hashes;
- result confidence and falsifiers match the observed evidence;
- no rejected idea was silently retuned.

**Step 4: Commit only after reviewing the existing dirty worktree**

Stage only task-owned files. Do not include unrelated user changes. Do not push unless current operator authorization explicitly includes publishing the reviewed commit.
