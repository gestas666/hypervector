# Range Impulse ML Experiment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add auditable BTC 1-minute range-only impulse strategy variants, autotune both directions, and train unpromoted annotation-only model candidates.

**Architecture:** The existing impulse signal remains unchanged by default. Dedicated range variants apply the point-in-time EMA regime detector and admit entries only when its label is `range`; long and short remain separate because the current metrics engine is single-direction. Autotune and LightGBM artifacts remain isolated research outputs and are never installed automatically.

**Tech Stack:** Python 3.13, pandas, VectorBT metrics, LightGBM, pytest, Hypervector CLI.

---

### Task 1: Add range-only impulse signal behavior

**Files:**
- Modify: `src/hypervector/strategies/impulse_1m.py`
- Test: `tests/test_impulse_1m.py`

1. Write a failing test proving `range_only=True` removes every entry outside point-in-time `range` labels.
2. Run the focused test and confirm it fails because the option is absent or ignored.
3. Add the minimal regime mask using `detect_regime_ema` with explicit fast, slow, and band parameters.
4. Run the focused test and existing impulse tests.

### Task 2: Register explicit range variants

**Files:**
- Modify: `src/hypervector/strategies/impulse_1m.py`
- Test: `tests/test_impulse_1m.py`

1. Write a failing registry test for `impulse_1m_range_long` and `impulse_1m_range_short` with role `regime`.
2. Register builders that force `range_only=True` and expose threshold/regime grids.
3. Verify registry idempotence and native long/short direction labels.

### Task 3: Autotune and validate both range directions

**Runtime artifacts:**
- `data/logs/research/autotune_impulse_1m_range_{long,short}_1m_<timestamp>.json`
- `data/exports/exp_impulse_1m_range_{long,short}_1m_<timestamp>/`

1. Run 100 seeded Karpathy-adaptive trials per direction on cached BTC 1-minute, 180-day data with costs.
2. Strictly validate both exports.
3. Audit all sampled types, range-only flags, and venue leverage bounds.
4. Report results without promotion gates.

### Task 4: Train isolated LightGBM candidates

**Runtime artifacts:**
- `data/models/metalabel/candidates/impulse-range-long-v001-20260725/`
- `data/models/metalabel/candidates/impulse-range-short-v001-20260725/`

1. Train walk-forward candidates without `--install`.
2. Compare chronological OOS log loss with the constant-probability baseline.
3. Retain candidates for observation only; do not promote unless they beat baseline and the native lifecycle label audit passes.

### Task 5: Verify and document

**Files:**
- Update: `HANDOFF.md`

1. Run focused strategy/autotune tests, full offline pytest, Ruff, and `git diff --check`.
2. Record Hypervelocity and range-impulse metrics, artifact paths, invalid diagnostic board timestamps, model decisions, and remaining same-bar execution limitations.
