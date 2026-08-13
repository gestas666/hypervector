# Production-Queue Consolidation-Wick Screen Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether a causal, frozen pre-entry BBWP-consolidation high can reduce the current 12-bps source-follow lead's liquidation tail without destroying its target expectancy.

**Architecture:** First add auditable entry economics to the existing production-queue trade report without changing execution. Re-run the no-stop continuous control and require exact aggregate parity. Then apply the existing prefix-stable BBWP<25 consolidation-boundary implementation to those exact lifecycles as a fixed-lifecycle screen. A stateful mark-triggered Hyperliquid stop-market replay is a separate conditional task and is not implemented unless the screen improves net PnL and avoids at least one liquidation.

**Tech Stack:** Python 3.13, pandas, immutable JSON evidence, Hyperliquid venue candles, existing production shadow matcher, pytest, Ruff.

---

## Fixed assumptions and success criteria

- The no-stop control remains `source_follow_minrange12_continuous_v1`:
  $15,000, 50% isolated margin, 30x, 8% gross-margin target, 24-hour maximum
  hold, 60-second post-only entry, and observe-only ML.
- The stop is the maximum high of the most recent fully completed causal
  BBWP(20, 240)<25 episode. The boundary becomes available only after the
  compression episode ends and the final 1-minute bar completes.
- For a short, a stop is effective only when `entry < stop < isolated
  liquidation boundary`; missing or ineffective stops are reported, never
  substituted or clamped.
- Hyperliquid TP/SL orders trigger from mark price. The fixed-lifecycle screen
  uses completed 1-minute highs only as a conservative qualification screen;
  it is not presented as exact stop execution.
- Every valid lifecycle is retained. Performance cannot abort a trial.
- Qualification for stateful replay requires both positive counterfactual net
  PnL delta and at least one avoided liquidation. All target regrets remain
  explicit.
- The running faithful shadow backend is not stopped, reset, or reconfigured.

### Task 1: Add auditable production-replay lifecycle economics

**Files:**

- Modify: `tests/test_source_follow_portfolio_replay.py`
- Modify: `src/hypervector/research/source_follow_portfolio_models.py`
- Modify: `src/hypervector/research/source_follow_portfolio_replay.py`

**Step 1: Write the failing tests**

Add assertions that each resolved trade reports its originating signal time,
final entry average, maximum filled entry quantity, and isolated liquidation
boundary. Add a partial-entry test proving the fields update through the final
entry fill rather than freezing on the first fragment.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_source_follow_portfolio_replay.py -q
```

Expected: failure because `SourcePortfolioTrade` does not expose the new
fields.

**Step 3: Implement the minimum telemetry**

Associate each submitted entry command with the active immutable
`SourceSignal`. Capture entry economics from authoritative controller/port
state and serialize them on flat-to-flat completion. Do not change order
generation, sizing, matching, liquidation, funding, or exit behavior.

**Step 4: Verify GREEN**

Run the same focused test and Ruff on the two production modules. Expected:
all focused tests pass and Ruff reports no findings.

### Task 2: Make the existing wick evaluator accept the measured contract

**Files:**

- Modify: `tests/test_hypervelocity_stop_counterfactual.py`
- Modify: `src/hypervector/research/hypervelocity_stop_counterfactual.py`

**Step 1: Write the failing tests**

Add a test passing the current 15k/50%/30x `CandidateBarrierConfig` and an
explicit lifecycle liquidation boundary. Assert the evaluator uses the
measured boundary rather than recomputing the old 10k/70%/40x default.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_hypervelocity_stop_counterfactual.py -q
```

Expected: failure because the evaluator does not accept an explicit config or
measured lifecycle boundary.

**Step 3: Implement the minimum contract extension**

Add an optional config argument retaining the legacy default. Prefer an
explicit finite positive `liquidation_price` column when present. Preserve the
existing fixed-lifecycle limitations and output schema otherwise.

**Step 4: Verify GREEN**

Run the focused tests and Ruff. Expected: all pass.

### Task 3: Add the immutable current-lead wick screen

**Files:**

- Create: `tests/test_source_follow_wick_screen.py`
- Create: `scripts/hypervelocity_source_wick_screen.py`

**Step 1: Write the failing command-contract tests**

Require a continuous lead artifact, an uninterrupted venue candle file, and an
immutable output path. Assert the frozen BBWP and portfolio contract, source
artifact validation, report-only/no-authority fields, and qualification rule.

**Step 2: Verify RED**

Run:

```bash
uv run pytest tests/test_source_follow_wick_screen.py -q
```

Expected: failure because the command does not exist.

**Step 3: Implement the report-only screen**

Load the exact Hyperliquid candle bundle, compute BBWP(20, 240), use the
existing causal consolidation bounds, screen the enriched resolved
lifecycles, and write a single immutable report containing source/candle
hashes, every affected lifecycle, target regrets, avoided liquidations, PnL
delta, limitations, and the conditional next action.

**Step 4: Verify GREEN**

Run focused tests and Ruff. Expected: all pass.

### Task 4: Prove no-stop aggregate parity

**Files:**

- Evidence: `data/logs/research/hypervelocity_source_production_minrange12_continuous_dev_details_20250728_20260418_20260729.json`

Run the existing twelve-segment continuous replay with the same immutable
inputs and a new output identity. Machine-compare all prior aggregate fields:
final equity `$36,243.90819074817`, 114 trades, 100 targets, two time exits, 12
liquidations, 43 partial liquidations, PF `1.4276156524905022`, and drawdown
`-51.03289135831721%`. Any mismatch is a technical defect to diagnose before
using the enriched lifecycles.

### Task 5: Run the frozen wick screen and decide conditionally

**Files:**

- Evidence: `data/logs/research/hypervelocity_source_production_minrange12_wick_screen_20250728_20260418_20260729.json`

Run the screen on the parity-proven detailed control and the exact repaired
2025-07-28 through 2026-04-28 Hyperliquid 1-minute candles. The first filled
signal is 2025-07-31 18:00 UTC, so this supplies more than the required
260-minute BBWP warmup. Retain all results and report every explicit bounded
zero-volume `hl_gap_fill` row.

- If PnL delta is non-positive or zero liquidations are avoided: reject this
  wick definition and do not add stateful runtime behavior.
- If both criteria pass: write a separate TDD plan for mark-triggered,
  depth-aware, reduce-only stateful execution. Do not infer promotion from the
  screen.

### Task 6: Verify and document the decision

**Files:**

- Modify: `docs/reviews/2026-07-29-source-follow-production-queue-lead.md`
- Modify: `HANDOFF.md`

Run:

```bash
uv run pytest tests/ -q -m "not network"
uv run ruff check scripts/hypervelocity_source_wick_screen.py \
  src/hypervector/research/source_follow_portfolio_models.py \
  src/hypervector/research/source_follow_portfolio_replay.py \
  src/hypervector/research/hypervelocity_stop_counterfactual.py \
  tests/test_source_follow_wick_screen.py \
  tests/test_source_follow_portfolio_replay.py \
  tests/test_hypervelocity_stop_counterfactual.py
git diff --check
```

Record exact commands, counts, evidence hashes, confidence, limitations, and
falsifiers. Do not commit, push, restart, or reset the shared dirty worktree
without an explicit user request.
