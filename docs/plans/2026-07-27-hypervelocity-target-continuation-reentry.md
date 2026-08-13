# Hypervelocity Target-Continuation Re-entry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether same-side re-entry only after a successful target and fresh directional price continuation can recover original strategy cadence and produce profitable venue-matched execution.

**Architecture:** Extend research replay state with the last completed outcome and target price. A `target_continuation` policy allows same-side re-entry after cooldown only when the previous outcome was a target and the current causal maker price has moved beyond that target by a configured clearance. Liquidations and expired maker attempts remain consumed until structural regime reset; production defaults remain unchanged.

**Tech Stack:** Python 3.13, pandas, typed dataclasses, pytest, Hyperliquid 0xArchive public L2/trades.

---

## Predeclared Matrix and Frozen Contract

- Control: `regime_reset`, 60-second cooldown.
- Challengers: `target_continuation`, 60-second cooldown, additional continuation clearance of 0, 1, and 3 bps.
- The 0/1/3-bps values bracket the source distribution: 12/15 known re-entries continued beyond the prior exit; first quartile 0.85 bps, median 2.34 bps.
- Preserve one position, 70% allocation, 40x isolated leverage, 8% target, maker execution, and current liquidation fees.
- Do not allow same-side target-continuation re-entry after liquidation.
- Do not change expired-entry regime-reset semantics.
- Do not change runtime config or metalabel observe policy.

## Task 1: Add Outcome-Aware Research State

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay_risk.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write a failing test proving target-continuation waits for both cooldown and causal price clearance.
2. Write a failing test proving liquidation cannot re-arm target-continuation inside the same regime.
3. Add typed completed-outcome/reference-price state and validated continuation clearance.
4. Implement point-in-time long/short clearance checks using the maker limit price at submission.
5. Keep default and cooldown-only behavior unchanged.

## Task 2: Mirror the Mechanism in Serial Screening

**Files:**
- Modify: `src/hypervector/research/hypervelocity_portfolio_eval.py`
- Test: `tests/test_hypervelocity_portfolio_eval.py`

1. Write failing tests for target-only continuation, clearance, and liquidation blocking.
2. Store the last completed target price/outcome in serial state.
3. Check current decision-bar close against the causal continuation boundary before scheduling the next-bar maker approximation.
4. Preserve compounding, one-position enforcement, and drawdown accounting.

## Task 3: Screen and Retain the Fixed Matrix

**Files:**
- Modify: `src/hypervector/research/hypervelocity_reentry_compare.py`
- Modify: `tests/test_hypervelocity_reentry_compare.py`

1. Add the 0/1/3-bps target-continuation candidates without adding thresholds after results are visible.
2. Report profit, drawdown, liquidation count, cadence distance from the source, and original re-entry coverage.
3. Retain all trial results and select any event candidates using joint performance/cadence evidence.

## Task 4: Run Event Replay if the Mechanism Survives

**Files:**
- Create if selected: `data/logs/research/hypervelocity_target_continuation_20260727.json`

1. If at least one challenger improves serial equity over the control and stays within 0.5x–2x the source cadence, run it through the complete checksum-verified public trade-through archive.
2. A final event result must exceed $10,000 after modeled costs to establish profitability; merely losing less is not success.
3. If no challenger survives, record the falsification and advance to the next source-grounded entry mechanism without modifying runtime.

## Verification

```bash
uv run pytest tests/test_hypervelocity_maker_replay.py \
  tests/test_hypervelocity_portfolio_eval.py \
  tests/test_hypervelocity_reentry_compare.py -q
ruff check src/hypervector/research/maker_replay_models.py \
  src/hypervector/research/maker_replay.py \
  src/hypervector/research/maker_replay_risk.py \
  src/hypervector/research/hypervelocity_portfolio_eval.py \
  src/hypervector/research/hypervelocity_reentry_compare.py
```

## Execution Note

Completed and falsified at the predeclared serial gate. The control completed 328
trades at 3.64/day with 39 liquidations and $173.00 final marked equity. The
0/1/3-bps challengers completed 845-878 trades at 9.39-9.76/day, incurred
118-129 liquidations, and ended below $0.00004. No challenger beat the control or
fell inside the source-cadence band, so full L2 event replay was correctly
skipped. Evidence is retained in
`data/logs/research/hypervelocity_target_continuation_20260727.json`.

Runtime strategy configuration and metalabel observe policy were not changed.
The active goal continues with a discrete re-entry event rather than another
continuously true price condition. Commit/push remains deferred until requested.
