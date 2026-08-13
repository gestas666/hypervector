# V29 Common-Window Arbitration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish an immutable, report-only v29 shared-account replay that restricts all six selected routes to one exact UTC entry window and compares it with the frozen full-window diagnostic.

**Architecture:** Preserve the revision-4 runner, router, adapters, profile, and artifact byte-for-byte. Add a separate companion command that imports the frozen runner, reconstructs its raw nominal and stress outcomes, filters them before priority arbitration by a predeclared half-open entry interval, and then delegates to the frozen `build_artifact` implementation. Bind the output to exact source hashes and the frozen full-window artifact; journal the result without changing live authority.

**Tech Stack:** Python 3.13, pandas/Parquet, Hypervector report-only research adapters, pytest, JSON evidence, DuckDB research journal.

---

## Systems Contract

- Fixed window: `[2026-06-13T03:15:00Z, 2026-07-05T12:00:00Z)`.
- The start is the latest first selected-route entry in revision 4 (`SPCX Swing/HA`).
- The end is the first 15-minute boundary after the earliest last selected-route entry (`GOLD Swing/HA` at `11:45Z`).
- Filter raw `CohortOutcome` inputs by entry timestamp before shared-account arbitration.
- Retain nominal and stress scenarios, exact v29 priority, one position per asset, five-position ceiling, fixed notional caps, and frozen friction behavior.
- Require every selected route to have at least one input in both scenarios.
- Report route-side gaps as evidence; do not convert missing sides, sparse counts, PnL, drawdown, or concentration into a technical abort or runtime gate.
- Require `execution_authority=none`, `report_only=true`, `automatic_promotion=false`, and `runtime_strategy_changed=false`.
- Do not read the sealed HIP-3 holdout and do not mutate the running v25 process, checkpoint, profile, orders, positions, protection, or transition drain.

## Predeclared Interpretation

- Aggregate nonpositive net PnL or profit factor at or below one in either scenario weakens the v29 portfolio hypothesis.
- A route supplying more than 50% of positive route PnL, any negative route, or missing route-side coverage remains evidence against broad portfolio promotion.
- Positive nominal and stress aggregates are supportive only if described with route concentration, route-side coverage, drawdown, and source limitations.
- Even a fully supportive result authorizes only review; it never promotes or starts v29 automatically.

### Task 1: Freeze and Test the Window Contract

**Files:**
- Create: `tests/test_evidence_selected_portfolio_v29_common_window_script.py`
- Reference without modifying: `scripts/evidence_selected_portfolio_v29.py`

**Step 1: Write the failing tests**

Test a wished-for companion module with these behaviors:

```python
def test_fixed_window_is_half_open_and_filters_before_arbitration() -> None:
    module = _load()
    rows = (
        _outcome(START_MS - 1),
        _outcome(START_MS),
        _outcome(END_MS - 1),
        _outcome(END_MS),
    )
    assert module.filter_entry_window(rows) == (rows[1], rows[2])


def test_coverage_reports_missing_route_sides_without_rejecting_trial() -> None:
    coverage = module.route_side_coverage(_scenario_with_long_only_sol(), ROUTES)
    assert coverage["all_routes_present"] is True
    assert coverage["all_route_sides_present"] is False
    assert coverage["missing_route_sides"] == [
        "range_onset_bidirectional_v1|SOL|short"
    ]
```

Also test invalid bounds, an absent route, exact parser defaults, immutable output refusal, report-only authority, source-hash binding, and full-window comparison reconciliation.

**Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/test_evidence_selected_portfolio_v29_common_window_script.py -q
```

Expected: FAIL because `scripts/evidence_selected_portfolio_v29_common_window.py` does not exist.

### Task 2: Implement the Separate Companion Runner

**Files:**
- Create: `scripts/evidence_selected_portfolio_v29_common_window.py`
- Do not modify: `scripts/evidence_selected_portfolio_v29.py`
- Do not modify: `src/hypervector/research/evidence_selected_portfolio.py`
- Do not modify: `src/hypervector/research/evidence_selected_portfolio_inputs.py`

**Step 1: Implement the minimal window functions**

```python
WINDOW_START_MS = 1_781_320_500_000
WINDOW_END_MS = 1_783_252_800_000


def filter_entry_window(rows: tuple[CohortOutcome, ...]) -> tuple[CohortOutcome, ...]:
    return tuple(
        row
        for row in rows
        if WINDOW_START_MS <= row.outcome.entry_time_ms < WINDOW_END_MS
    )
```

Implement `route_side_coverage` with exact route and side counts, missing routes, and missing sides. Empty routes are technical source failures; one-sided route samples remain publishable limitations.

**Step 2: Reconstruct and filter raw scenarios**

Load the exact profile and source paths through the frozen runner. Reuse its route specs, crypto adapters, and HIP-3 sidecar adapter, then filter nominal and stress tuples before calling frozen `build_artifact`.

**Step 3: Bind comparison evidence**

Require the frozen full-window artifact at:

```text
data/logs/research/evidence_selected_portfolio_v29_shared_arbitration_20260808T070837Z.json
```

Validate its schema, report-only authority, profile fingerprint, scenario names, and file identity. Add comparison fields for completed trades, net PnL, return, profit factor, maximum realized drawdown, negative routes, largest positive-route share, and side coverage.

**Step 4: Publish immutable output**

Set a new schema and mode:

```python
artifact["schema_version"] = "evidence_selected_portfolio_v29_common_window_v1"
artifact["mode"] = "report_only_fixed_common_window_shared_priority_diagnostic"
artifact["common_window"] = window_contract
artifact["full_window_comparison"] = comparison
```

Use `write_immutable_json`; never overwrite a prior artifact.

**Step 5: Run tests to verify GREEN**

Run:

```bash
uv run pytest tests/test_evidence_selected_portfolio_v29_common_window_script.py -q
```

Expected: all tests PASS.

### Task 3: Execute Nominal and Stress Common-Window Replay

**Files:**
- Create: `data/logs/research/evidence_selected_portfolio_v29_common_window_<UTC>.json`

**Step 1: Run the immutable report-only command**

```bash
uv run python scripts/evidence_selected_portfolio_v29_common_window.py \
  --out data/logs/research/evidence_selected_portfolio_v29_common_window_<UTC>.json
```

**Step 2: Validate artifact invariants**

Verify exact profile fingerprint, six routes, both scenarios, source hashes, fixed window, route counts, route-side gaps, equity reconciliation, one-position-per-asset rejection reasons, maximum concurrency, report-only authority, and no sealed holdout access.

**Step 3: Compare with revision 4**

Report both absolute common-window economics and changes from the full-window replay. Do not annualize, compound beyond the fixed notional simulation, or call the result a forecast.

### Task 4: Append Journal Revision 5

**Files:**
- Create: `docs/research-journal/evidence-selected-portfolio-v29-v5.json`
- Modify only if required by the new conclusion: `docs/guides/cohort-live-transition-and-rollback-v29.md`
- Test: `tests/test_evidence_selected_portfolio_v29_transition_runbook.py`

**Step 1: Write a failing runbook/journal assertion if the conclusion changes**

Bind revision 5, the new revision ID, exact artifact hash, common-window result, side-coverage limitation, and unchanged runtime authority.

**Step 2: Verify RED**

```bash
uv run pytest tests/test_evidence_selected_portfolio_v29_transition_runbook.py -q
```

Expected: FAIL on the old revision-4 identity.

**Step 3: Create and append revision 5**

```bash
uv run python -m hypervector --data-root data \
  research-db-journal-append \
  --record docs/research-journal/evidence-selected-portfolio-v29-v5.json
```

Retry only a transient DuckDB writer lock; never bypass revision-chain or evidence-integrity failures.

**Step 4: Verify journal integrity**

```bash
uv run python -m hypervector --data-root data \
  research-db-journal-report \
  --hypothesis-id evidence-selected-portfolio-v29
```

Require revision 5 current, all evidence matching, and `runtime_strategy_changed=false`.

### Task 5: Verification and Live Boundary Recheck

**Files:**
- Verify only; do not modify live state.

**Step 1: Run focused tests and lint**

```bash
uv run pytest \
  tests/test_evidence_selected_portfolio.py \
  tests/test_evidence_selected_portfolio_v29_script.py \
  tests/test_evidence_selected_portfolio_v29_common_window_script.py \
  tests/test_evidence_selected_portfolio_v29_transition_runbook.py -q
uv run ruff check \
  scripts/evidence_selected_portfolio_v29_common_window.py \
  tests/test_evidence_selected_portfolio_v29_common_window_script.py
```

**Step 2: Recheck frozen implementation hashes**

Require the revision-4 runner, router, adapters, and profile hashes to remain unchanged.

**Step 3: Recheck live v25 without mutation**

Read the latest stable ledger/checkpoint and confirm active profile identity, run health, open lifecycle protection, and transition-drain state. Do not restart, drain, place, close, resize, or alter any live lifecycle.

**Step 4: Commit only with explicit operator instruction**

The repository has a large pre-existing dirty worktree. Preserve all unrelated changes and do not create a commit, merge, or push unless the operator explicitly requests it after reviewing the result.
