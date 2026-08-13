# Canonical Recovery Long Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Economically replay the already-defined Recipe C long hypothesis: a fresh 1m `TREND_UP` onset while the canonical 5m state remains `TREND_DOWN`.

**Architecture:** Keep signal construction in `hypervelocity_selective_recipe.py` and add the missing recovery arm to its report-only replay grid. Add a small command that classifies immutable Hyperliquid candles, selects that arm, and replays it through verified L2, public trades, mark prices, and funding. Run touch, book-through, and public-trade-through separately; no result changes runtime authority.

**Tech Stack:** Python 3.13, pandas, DuckDB-backed replay evidence, pytest, Ruff.

---

### Task 1: Freeze the missing recovery replay arm

**Files:**
- Modify: `tests/test_hypervelocity_selective_recipe.py`
- Modify: `src/hypervector/research/hypervelocity_selective_recipe.py`

1. Extend the existing replay-grid test to require `c_1m_recovery_in_5m_down`.
2. Run the focused test and observe failure because the arm is absent.
3. Map `c_1m_trend_up_recovery_in_5m_down` events to a 24-hour maximum hold without changing the existing arms.
4. Re-run the focused tests and require green.

### Task 2: Add a report-only authentic replay command

**Files:**
- Create: `tests/test_hypervelocity_selective_recovery_replay_script.py`
- Create: `scripts/hypervelocity_selective_recovery_replay.py`

1. Write failing command-contract tests for explicit UTC bounds, fill rule, config, candle evidence, verified context, and immutable output.
2. Observe the tests fail because the command does not exist.
3. Implement the smallest command that builds canonical decisions, selects only the recovery arm, uses `verified_archive_bundles`, and runs `replay_maker_order_chunks` with 70% allocation, 40x leverage, 8% gross-margin TP, no stop, five-minute maker eligibility, isolated liquidation, authentic context, and ML observe authority.
4. Require the report to state `report_only=true` and `runtime_strategy_changed=false`.
5. Re-run focused tests and require green.

### Task 3: Run the frozen experiment

**Files:**
- Create: `data/logs/research/hypervelocity_canonical_recovery_long_*_20260729.json`
- Modify: `docs/reviews/2026-07-29-canonical-recovery-long.md`
- Modify: `HANDOFF.md`

1. Replay development plus July 27 under touch, book-through, and public-trade-through fills using the verified research database and matching mark/funding context.
2. Replay the available July 28 forward window separately if complete venue evidence and context cover the requested bounds; otherwise record the exact missing evidence.
3. Report event counts, submissions, fills, targets, liquidations, expiries, final equity, maximum drawdown, fees, funding, and chronological slices.
4. Compare against the frozen short-only leader without combining the arms.
5. Reject generalization if performance depends on one fill assumption, one time slice, or selected screenshot winners.

### Task 4: Verify without runtime promotion

**Files:**
- Verify all files touched above.

1. Run focused tests.
2. Run Ruff and format checks on touched Python files.
3. Run the non-network Python suite.
4. Confirm the shadow backend PID and fresh ledger after replay.
5. Confirm no runtime/config/model-authority file changed as part of this experiment.

No commit, push, live execution, runtime promotion, or ML authority change is part of this plan.

## Execution result

- Tasks 1-2 completed under TDD with a dedicated immutable replay command.
- Full development failed all fill assumptions with final equity between
  $138.37 and $207.52 and maximum drawdown below -99.44%.
- The retrospectively selected July 1-27 fresh-equity slice was profitable:
  strict $20,370.28 final equity, 26 targets, one liquidation, and -48.66%
  drawdown.
- July 27 and July 28 each produced one strict fill and one target from three
  events.
- The candidate does not align to the six new creator timestamps and remains
  annotation-only. See
  `docs/reviews/2026-07-29-canonical-recovery-long.md`.
