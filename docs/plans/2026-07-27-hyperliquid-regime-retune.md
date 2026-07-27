# Hyperliquid-Native Regime Retune Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Evaluate, retune, compare, and—only when supported—apply the Hypervelocity regime detector using the strict 90-day Hyperliquid candle cache and recorded real-strategy entries.

**Architecture:** Preserve the canonical causal 1m/5m/15m classifier and change only its faithful threshold configuration if a train-selected candidate is non-inferior on the scoring-excluded chronological holdout without adding execution gates. Save complete baseline, tuning-board, comparison, and review evidence; keep every valid trial regardless of performance.

**Tech Stack:** Python 3.13, Pandas, deterministic chronological tuning, Pytest, Rust/Ratatui, TOML, Hyperliquid-native 1m cache.

---

### Task 1: Freeze inputs and baseline

**Files:**
- Read: `data/cache/BTC_1m_90d.parquet`
- Read: `docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv`
- Create: `data/logs/research/hypervelocity_regime_eval_hl90d_baseline_20260727.json`

1. Verify the cache has 129,600 bars and only `hl`/`hl_gap_fill` provenance.
2. Verify the positions file has the required timestamp, symbol, and side fields.
3. Run the faithful baseline evaluation with `--strict-hl-only --lookback 90`.
4. Record range errors, direction alignment, transition delay, breakout quality, churn, and source provenance.

### Task 2: Run chronological tuning

**Files:**
- Create: `data/logs/research/hypervelocity_regime_tuning_hl90d_20260727.json`

1. Run 100 deterministic trials with seed 42 and the existing chronological 70/30 split.
2. Confirm every trial is retained and only technical failures are errors.
3. Confirm `selection_basis=train_only`; do not inspect holdout to select the winner.

### Task 3: Compare baseline and selected candidate

**Files:**
- Create: `data/logs/research/hypervelocity_regime_comparison_hl90d_20260727.json`
- Create: `docs/reviews/2026-07-27-hyperliquid-regime-retune-review.md`

1. Extract the current faithful-config trial and the train-selected trial.
2. Compare train and scoring-excluded holdout direction match, false range/no-entry states, breakout misses, range expansion errors, transition latency, and churn.
3. Reject an apparent gain caused only by training fit, future leakage, or materially worse holdout behavior.
4. State limitations from 35 unique entry decisions and the absence of independently labeled range intervals.

### Task 4: Apply the supported configuration

**Files:**
- Modify only if supported: `src/hypervector/strategies/hypervelocity_contract.py`
- Modify only if supported: `configs/hypervelocity_faithful.toml`
- Test: `tests/test_regime_classifier.py`
- Test: `tests/test_hypervelocity_profile.py`

1. Add a failing contract/profile assertion for the selected threshold values.
2. Update both authoritative defaults and the operator-visible TOML atomically.
3. Re-run the focused tests and confirm no 1m override, 15m veto, confidence gate, or non-causal timing is introduced.
4. If the candidate is not supported, retain the baseline and document that empirical result instead of forcing a change.

### Task 5: Full acceptance and clean shadow boundary

**Files:**
- Update: `HANDOFF.md`
- Update: `skills/hypervector-regime-detector/SKILL.md`

1. Run focused regime/evaluation/profile tests and prefix-invariance checks.
2. Run all offline Python tests, all Rust TUI tests, changed-file Ruff/format, Cargo format, CLI status, profile parsing, and no-submit checks.
3. Run a unified bounded live-feed shadow smoke, verify regime/L2 telemetry and zero venue place attempts, then quit normally.
4. Run reset dry-run and confirmed reset; verify backup paths, zero-byte active state, unchanged cache checksum, and no background process.
5. Commit, push, fast-forward `main`, delete the merged branch, and finish on clean synchronized `main`.

## Success criteria and falsifiers

- Input provenance is strict Hyperliquid except explicit zero-volume `hl_gap_fill` minutes.
- Candidate selection uses training diagnostics only; holdout metrics do not inform selection and are inspected only after the candidate choice.
- Any applied candidate is at least non-inferior on holdout direction alignment and false-range behavior; breakout quality, churn, and transition delay are explicitly measured, with any accepted trade-off documented and falsifiable in shadow.
- No confidence threshold, model score, or performance metric becomes an execution gate.
- Prefix mutation cannot alter earlier states; 5m remains authoritative and 15m remains non-veto context.
- Shadow creates no live execution client or venue place attempt.
