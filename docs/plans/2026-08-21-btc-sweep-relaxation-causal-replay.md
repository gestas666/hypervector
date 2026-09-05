# BTC Sweep-Relaxation Causal Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether removing only V58 BTC long's downside-sweep predicate creates a repeatable, after-cost trend-capable long route without changing live execution.

**Architecture:** Freeze an authority-none preregistration before opening the historical comparison. Build causal hourly control and sweep-relaxed entry pulses from uninterrupted BTC minute bars, replay both through the existing shared bar portfolio with V58's exact 60/60 exit shape and realistic costs, and publish an immutable report with chronological partitions, stress, largest-winner removal, and a prospective cutoff.

**Tech Stack:** Python 3.13, pandas, existing Hypervector shared-bar replay, pytest, immutable JSON research artifacts.

---

### Task 1: Freeze the experiment contract

**Files:**
- Create: `docs/research-journal/v58-btc-sweep-primary-relaxation-causal-replay-preregistration-20260821-v1.json`

**Step 1: Record the prior rejection and changed evidence**

Record the four adverse V52/V53 episodes, the V58 five-episode `TREND_UP` mismatch, and the prior alternative reopen condition requiring either twelve episodes or a separately preregistered causal replay.

**Step 2: Freeze the comparison**

Freeze control, candidate, partitions, nominal/stress friction, V58 60-bps stop and target, 24-hour hold, $5,000 equity, 10% margin, 10x leverage, acceptance rules, bias controls, and no live authority.

**Step 3: Hash the preregistration**

Run: `shasum -a 256 docs/research-journal/v58-btc-sweep-primary-relaxation-causal-replay-preregistration-20260821-v1.json`

Expected: one stable SHA-256 recorded before any economic replay is run.

### Task 2: Specify causal control and candidate signals

**Files:**
- Create: `tests/test_btc_sweep_primary_relaxation.py`
- Create: `src/hypervector/research/btc_sweep_primary_relaxation.py`

**Step 1: Write failing signal tests**

Test that the control requires all four current predicates, the candidate removes only `low < prior20h_low * 0.9998`, both routes retain volume `>=1.2x`, reclaim, and EMA55, consecutive true bars emit one onset, incomplete cadence fails closed, and appended future rows cannot alter prior signal bytes.

**Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation.py -q`

Expected: collection failure because the new module does not exist.

**Step 3: Implement the minimal signal module**

Create a frozen dataclass and a builder returning aligned control and candidate minute-decision frames. Aggregate only complete 60-row hours and project decisions to the completed hour's final minute.

**Step 4: Run the tests and verify GREEN**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation.py -q`

Expected: all signal-contract tests pass.

### Task 3: Replay exact V58 economics

**Files:**
- Create: `tests/test_btc_sweep_primary_relaxation_replay.py`
- Create: `src/hypervector/research/btc_sweep_primary_relaxation_replay.py`

**Step 1: Write failing replay tests**

Test next-minute entry, 10% margin at 10x, 60-bps price stop and target, maker target fee, taker entry/stop fees, 24-hour fallback, nominal-versus-stress monotonicity, and explicit same-bar ambiguity.

**Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation_replay.py -q`

Expected: collection failure because the replay module does not exist.

**Step 3: Implement the minimal replay wrapper**

Reuse `evaluate_shared_bar_portfolio`; do not create a second execution engine. Configure initial equity `$5,000`, margin fraction `0.10`, leverage `10`, target and stop margin percentages `6`, entry and market-exit taker fees `4.5 bps`, target maker fee `1.5 bps`, and nominal/stress residual slippage `2/5 bps`.

**Step 4: Run the tests and verify GREEN**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation_replay.py -q`

Expected: all replay-contract tests pass.

### Task 4: Build chronological experiment reporting

**Files:**
- Create: `tests/test_btc_sweep_primary_relaxation_experiment.py`
- Create: `src/hypervector/research/btc_sweep_primary_relaxation_experiment.py`

**Step 1: Write failing reporting tests**

Test immutable partition bounds, control/candidate/scenario completeness, profit factor, drawdown, trade cadence, largest-winner removal, no-action comparison, acceptance evaluation, source hashes, prospective cutoff, and authority-none fields.

**Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation_experiment.py -q`

Expected: collection failure because the experiment module does not exist.

**Step 3: Implement the report builder**

Use development `2025-07-28..2026-01-28`, validation `2026-01-28..2026-04-28`, and pseudo-holdout `2026-04-28..2026-07-28`. Disclose that all historical partitions were previously opened and that only post-preregistration collection is truly prospective.

**Step 4: Run the tests and verify GREEN**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation_experiment.py -q`

Expected: all experiment tests pass.

### Task 5: Publish the immutable result

**Files:**
- Create: `tests/test_btc_sweep_primary_relaxation_script.py`
- Create: `scripts/btc_sweep_primary_relaxation_replay.py`
- Create after execution: `data/logs/research/v58_btc_sweep_primary_relaxation_causal_replay_20260821_v1/`
- Create after review: `docs/research-journal/v58-btc-sweep-primary-relaxation-causal-replay-result-20260821-v1.json`

**Step 1: Write the failing command test**

Test fail-closed missing inputs, immutable output refusal, manifest hashes, and execution authority `none`.

**Step 2: Run the command test and verify RED**

Run: `uv run pytest tests/test_btc_sweep_primary_relaxation_script.py -q`

Expected: collection failure because the command does not exist.

**Step 3: Implement and run the report-only command**

Run: `uv run python scripts/btc_sweep_primary_relaxation_replay.py --out-dir data/logs/research/v58_btc_sweep_primary_relaxation_causal_replay_20260821_v1`

Expected: immutable `report.json`, `trades.parquet`, and `manifest.json`; no live files or processes change.

**Step 4: Apply the preregistered decision rule**

Accept only if validation and pseudo-holdout are positive after nominal and stress costs, profit factor exceeds one, largest-winner removal remains positive, minimum trade coverage is met, and drawdown/portfolio competition are acceptable. Otherwise reject or defer without retuning.

### Task 6: Verify and integrate research telemetry

**Files:**
- Modify only if the experiment is valid: `configs/research/v58_active_route_lifecycle_collectors.json`
- Modify only if needed for hypothesis visibility: `src/hypervector/research/v58_continuous_improvement.py`
- Test: relevant V58 continuous-improvement tests

**Step 1: Add failing telemetry coverage tests if integration is needed**

Expected: the canonical ledger initially lacks the new authority-none experiment.

**Step 2: Add the minimal report-only integration**

Expose status, evidence hashes, result, confidence, and next action without execution authority.

**Step 3: Run focused and broad verification**

Run:

```bash
uv run pytest tests/test_btc_sweep_primary_relaxation*.py -q
uv run pytest tests/ -q -m "not network"
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
```

Expected: all checks pass, no live configuration fingerprint changes, and venue positions/orders remain unchanged.
