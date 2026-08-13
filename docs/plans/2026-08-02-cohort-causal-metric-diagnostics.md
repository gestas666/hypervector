# Cohort Causal Metric Diagnostics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend each stopped-run cohort audit with causal, report-only summaries connecting exact decision-time readiness metrics to resolved forward paths.

**Architecture:** Keep the execution backend unchanged. The existing forward-outcome parser will retain the readiness `metrics` mapping on each post-activation provider evaluation and feed a bounded online accumulator. A separate module will validate stable metric types and publish descriptive per-provider distributions and horizon-conditioned outcomes without producing orders, model scores, tuning decisions, or performance gates.

**Tech Stack:** Python 3.13, immutable JSONL cohort ledgers, pytest, Ruff, existing Hypervector stopped-run audit.

---

## Constraints and evidence contract

- Follow `@hypervector-cli`, `@hypervector-regime-detector`, and `@ml4-trading`.
- Preserve point-in-time decision metrics; never derive them from future candles.
- Future candles may label outcomes only after the recorded decision boundary.
- Separate numeric and categorical metrics and reject type drift rather than silently coercing it.
- Treat overlapping forward paths as descriptive; expose non-overlapping counts.
- Missing metric telemetry is a technical coverage gap, not negative strategy evidence.
- Do not alter signal eligibility, routing, sizing, risk, orders, or runtime state.
- Do not arm live execution while implementing or verifying this report-only path.
- This is an intentionally shared dirty worktree. Commit operations are deferred until the user explicitly requests a repository publication pass.

### Task 1: Define the metric accumulator contract

**Files:**

- Create: `src/hypervector/research/cohort_signal_metric_diagnostics.py`
- Test: `tests/test_cohort_signal_metric_diagnostics.py`

**Step 1: Write failing tests**

Cover these observable behaviors:

```python
def test_numeric_metric_separates_positive_and_nonpositive_paths() -> None:
    accumulator = MetricDiagnosticsAccumulator((5,))
    accumulator.observe_evaluation({"adx": 18.0})
    accumulator.observe_horizon(
        {"adx": 18.0},
        horizon_minutes=5,
        decision_time_ms=60_000,
        status="resolved",
        directional_return_bps=12.0,
    )
    assert accumulator.as_payload()["metrics"]["adx"]["horizons"]["5"][
        "positive_directional"
    ]["mean_metric"] == 18.0
```

Also cover categorical value outcomes, absent/null metrics, non-overlapping counts, unsupported values, and metric type drift.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_cohort_signal_metric_diagnostics.py -q
```

Expected: collection failure because the new accumulator module does not exist.

**Step 3: Implement the minimum accumulator**

Use online totals for numeric and categorical outcomes. Store only decision timestamps required for non-overlap counts; do not retain full candle paths or duplicate raw ledger rows.

**Step 4: Verify GREEN**

Run the same focused test and expect all cases to pass.

### Task 2: Connect exact metrics to causal forward outcomes

**Files:**

- Modify: `src/hypervector/research/cohort_signal_outcomes.py`
- Modify: `src/hypervector/research/cohort_live_audit_coverage.py`
- Modify: `tests/test_cohort_signal_outcomes.py`
- Modify: `tests/test_multi_asset_live_audit.py`

**Step 1: Write failing integration tests**

Require one audit report to expose:

```python
bucket = report["signal_outcomes"]["by_provider_symbol"][provider_key]
assert bucket["metric_diagnostics"]["metrics"]["adx"]["kind"] == "numeric"
assert report["signal_outcomes"]["coverage"]["metric_telemetry_complete"] is True
```

Add a second test where one later evaluation drops the declared metrics. It must retain the evaluation but report `provider_metric_telemetry_missing` as a technical coverage gap.

**Step 2: Verify RED**

Run the two focused test modules. Expected: missing `metric_diagnostics` and metric-coverage fields.

**Step 3: Implement integration**

- Parse the exact readiness `metrics` mapping into each causal candidate.
- Observe metrics once per deduplicated post-activation evaluation.
- Pair metrics with each horizon's existing resolved/censored/missing-data status.
- Publish metric coverage at the signal-outcome root and per provider.
- Add an overall technical gap only when post-activation evaluations exist and metric telemetry is incomplete.

**Step 4: Verify GREEN and refactor**

Run focused audit, signal-outcome, provider-readiness, signal-source, and telemetry tests. Keep every file under 500 lines and every function under 50 lines.

### Task 3: Reconcile operator contracts and verify the repository

**Files:**

- Modify: `HANDOFF.md`
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `docs/plans/2026-08-01-bidirectional-shared-live-cohort.md`

**Step 1: Document semantics**

State that metric-conditioned outcomes are descriptive measurement evidence, not an ML model, automatic threshold tuner, strategy gate, or fill/PnL claim.

**Step 2: Reproduce an immutable old-run audit**

Run the stopped-run audit against `bidirectional-live-1785638028253`. It must remain explicit that the old run has no provider evaluations and therefore no metric evidence.

**Step 3: Run complete verification**

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo fmt --all -- --check
uv run python -m hypervector status
git diff --check
```

Also run scoped Ruff and structural file/function checks. Do not claim completion unless every command exits successfully.

## Acceptance falsifiers

- A post-activation provider evaluation disappears because metrics are missing.
- Metrics are rounded display strings rather than exact backend values.
- A future candle changes the recorded decision metric.
- Censored or market-gap paths are pooled with resolved outcomes.
- Numeric/categorical type drift is silently coerced.
- Overlapping rows are presented as independent evidence.
- The audit changes runtime configuration or constructs execution authority.
