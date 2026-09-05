# SP500 Breakout Cost-Clearance Diagnostic Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether a pre-PnL, cost-derived 17.5005328604182-bps breakout clearance materially improves the frozen SP500 32-bar pressure route without opening its sealed holdout or changing V58.

**Architecture:** Add one report-only research module that derives a fresh-onset signal only after price clears the frozen prior extreme by the declared clearance. Compare that challenger with the unchanged control on the original development and already-opened validation windows under nominal and stress friction; preserve the holdout as unread and retain full side attribution.

**Tech Stack:** Python 3.13, pandas, existing HIP-3 transfer simulator, pytest, Ruff, immutable JSON research journals.

---

### Task 1: Freeze the hypothesis and evidence boundary

**Files:**
- Create: `docs/research-journal/v58-sp500-breakout-cost-clearance-preregistration-20260821-v1.json`

**Step 1: Record the fixed challenger**

Freeze the 17.5005328604182-bps threshold from the existing $5,000 SP500 cost contract, the 32-bar/EMA21-55/imbalance-0.10/120-bps historical screening contract, the original development and validation timestamps, and the sealed holdout boundary.

**Step 2: Record non-negotiable interpretation limits**

State that this is an entry-mechanism screen under the historical transfer exit contract, not an exact V58 exit replay, not live authority, and not permission to open the sealed holdout.

**Step 3: Validate the preregistration**

Run: `jq -e '.' docs/research-journal/v58-sp500-breakout-cost-clearance-preregistration-20260821-v1.json`

Expected: exit 0.

### Task 2: Test the causal clearance signal

**Files:**
- Create: `tests/test_hip3_breakout_cost_clearance.py`
- Create: `src/hypervector/research/hip3_breakout_cost_clearance.py`

**Step 1: Write the failing signal tests**

Cover delayed fresh onset after a marginal base breakout, symmetric short clearance, gap-reset behavior, prefix invariance, invalid clearance, and mismatched input indices.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_hip3_breakout_cost_clearance.py -q`

Expected: collection failure because `hypervector.research.hip3_breakout_cost_clearance` does not exist.

**Step 3: Implement the minimal signal transformation**

Build candidate long and short raw states from causal close, frozen prior extreme, EMA alignment, pressure confirmation, and the fixed clearance. Apply fresh-onset logic within the existing source segment and recompute structural stops only at challenger onsets.

**Step 4: Run the focused tests to verify GREEN**

Run: `uv run pytest tests/test_hip3_breakout_cost_clearance.py -q`

Expected: all focused tests pass.

### Task 3: Test fixed-window control-versus-challenger evaluation

**Files:**
- Modify: `tests/test_hip3_breakout_cost_clearance.py`
- Modify: `src/hypervector/research/hip3_breakout_cost_clearance.py`

**Step 1: Write failing evaluation tests**

Require both arms, three chronological development folds, nominal and stress validation, side-separated outcomes, `execution_authority=none`, and `holdout_metrics_accessed=false`.

**Step 2: Run the tests to verify RED**

Run: `uv run pytest tests/test_hip3_breakout_cost_clearance.py -q`

Expected: failures for the missing evaluation/report API.

**Step 3: Implement the minimal evaluator**

Reuse `quote_aware_portfolio_config` and `evaluate_shared_bar_portfolio`; evaluate only the original development and validation windows. Never slice or evaluate at or after `validation_end_utc` for the sealed holdout.

**Step 4: Run the focused tests to verify GREEN**

Run: `uv run pytest tests/test_hip3_breakout_cost_clearance.py -q`

Expected: all focused tests pass.

### Task 4: Execute and journal the real SP500 diagnostic

**Files:**
- Create: `docs/research-journal/v58-sp500-breakout-cost-clearance-result-20260821-v1.json`

**Step 1: Run the frozen experiment**

Load the same HIP-3 archive/funding inputs as the original transfer report, evaluate the exact SP500 control and challenger, and print the complete result without writing or reading the sealed holdout.

**Step 2: Check the predeclared decision rule**

Reject the challenger unless validation is positive under nominal and stress friction, positive after removing its largest winner, represented on both sides, and not materially worse in chronological development stability than the control.

**Step 3: Journal every result**

Record development, folds, validation, side splits, largest-winner sensitivity, source/generator hashes, limitations, falsifiers, and explicit `runtime_strategy_changed=false`.

### Task 5: Verify without touching live execution

**Files:**
- Verify: `src/hypervector/research/hip3_breakout_cost_clearance.py`
- Verify: `tests/test_hip3_breakout_cost_clearance.py`
- Verify: both new research journals

**Step 1: Run focused tests and lint**

Run: `uv run pytest tests/test_hip3_breakout_cost_clearance.py tests/test_hip3_breakout_pressure_signals.py tests/test_hip3_breakout_pressure_transfer.py -q`

Run: `uv run ruff check src/hypervector/research/hip3_breakout_cost_clearance.py tests/test_hip3_breakout_cost_clearance.py`

Expected: exit 0 for both.

**Step 2: Verify artifacts and file limits**

Run `jq -e` on both journals, verify recorded hashes/byte counts, and require every touched source/test file to remain below 500 lines and every function below 50 lines.

**Step 3: Reconcile live isolation**

Confirm V58 retains the same run ID, profile fingerprint, backend process, open-position identity, and owned protective stop; confirm the experiment reports `execution_authority=none` and no runtime/configuration mutation.

