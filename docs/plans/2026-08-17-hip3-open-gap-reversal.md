# HIP-3 Cash-Open Gap Reversal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and evaluate a report-only, development-only SP500/SPCX cash-open gap-reversal hypothesis without accessing validation or holdout economics or changing v53.

**Architecture:** Add a causal 15-minute signal family that fades a fixed 20-bps U.S. cash-open gap after the first completed bar, targets the prior regular-session close, uses an 80-bps protective stop, and exits no later than the cash close. Reuse the existing audited SP500/SPCX archive, exact public-trade OHLC signal source, mark-risk path, BBO execution, funding, fee, and depth-cost inputs. Publish immutable per-symbol development artifacts and a decision journal; validation and holdout remain sealed unless development and technical checks pass.

**Tech Stack:** Python 3.12, pandas, DuckDB-backed HIP-3 archive inputs, shared exact-quote portfolio simulator, pytest, Ruff, immutable JSON evidence.

---

## Frozen research contract

- Symbols: `xyz:SP500`, `xyz:SPCX`, evaluated independently.
- Timeframe: completed 15-minute bars.
- Session calendar: `America/New_York`, weekdays, with the archive's predeclared 2026 closures.
- Event: cash-open gap from the prior eligible cash-session close to the current 09:30 open is at least `+20` or at most `-20` bps.
- Decision: wait through the first completed 09:30–09:45 bar. Enter only if its close remains on the gap side of the prior close.
- Direction: fade positive gaps with a short; fade negative gaps with a long.
- Fill: next-bar exact L2 ask/bid with nominal or stress latency and scaled-depth tail.
- Target: prior eligible cash-session close.
- Protection: fixed 80-bps stop, reduce-only in any future runtime design; research replay uses exact mark extrema and the shared maximum-stop clamp.
- Fallback exit: completed 15:45–16:00 cash-close bar, or 25 completed 15-minute holding intervals, whichever occurs first.
- Re-entry: at most one entry per cash session; one-bar cooldown and same-side episode reset.
- Sizing reference: $5,000 equity, $5,000 notional, 10x isolated leverage, 10% margin.
- Costs: exact current effective HIP-3 taker fee plus per-symbol p99 visible depth and frozen nominal/stress latency from the pre-PnL index cost contract.
- Selection: no parameter grid, no side selection, no symbol pooling, no validation or holdout access.
- Development checks: exact paths resolved, positive nominal and stress net/PF, positive stress net without largest winner, both directions observed, at least two positive stress folds, and no liquidations.
- Authority: report only; no live strategy, asset, risk, sizing, routing, process, or configuration change.

## Task 1: Freeze the preregistration

**Files:**
- Create: `docs/research-journal/v53-sp500-spcx-cash-open-gap-reversal-preregistration-v1.json`
- Test: `tests/test_hip3_cash_open_gap_reversal_script.py`

1. Write a failing test that requires the immutable preregistration path, exact hypothesis ID, fixed 20-bps gap, 80-bps stop, prior-close target, 25-bar ceiling, both symbols/sides, development-only access, and zero execution authority.
2. Run the exact test and verify it fails because the preregistration does not exist.
3. Add the preregistration with the two primary-paper URLs, exact local archive/cost references, assumptions, failure modes, and falsifiers.
4. Run the test and verify it passes.

## Task 2: Build causal signals

**Files:**
- Create: `src/hypervector/research/hip3_cash_open_gap_reversal_signals.py`
- Create: `tests/test_hip3_cash_open_gap_reversal_signals.py`

1. Write failing tests for positive-gap short, negative-gap long, sub-20-bps rejection, already-reverted first-bar rejection, prior-close target, 80-bps stop, one-entry-per-session behavior, session-close exit, holiday/weekend exclusion, source-gap reset, and no future-session leakage.
2. Run the signal tests and confirm import/behavior failures.
3. Implement the frozen dataclass, ordered finite 15-minute input validation, causal prior-session-close mapping, entry/target/stop columns, and exit columns. Keep every public function typed and documented.
4. Run the signal tests and verify green.

## Task 3: Add a DRY development evaluator

**Files:**
- Create: `src/hypervector/research/hip3_development_partitions.py`
- Create: `tests/test_hip3_development_partitions.py`
- Modify: `src/hypervector/research/hip3_opening_range_breakout_candidate.py`
- Modify: `src/hypervector/research/hip3_oil_shock_reversion_candidate.py`
- Modify: `src/hypervector/research/hip3_krown_trend_resumption_candidate.py`

1. Write a failing unit test for a generic half-open development/fold evaluator that receives bars, signals, windows, and nominal/stress portfolio builders.
2. Run it and verify the missing helper fails.
3. Implement the smallest typed helper around `evaluate_shared_bar_portfolio`.
4. Refactor the three existing duplicated partition evaluators to call the helper without changing outputs.
5. Run all four candidate suites and compare existing outputs.

## Task 4: Add the gap-reversal candidate and report

**Files:**
- Create: `src/hypervector/research/hip3_cash_open_gap_reversal_candidate.py`
- Create: `src/hypervector/research/hip3_cash_open_gap_reversal_reporting.py`
- Create: `tests/test_hip3_cash_open_gap_reversal_candidate.py`
- Create: `tests/test_hip3_cash_open_gap_reversal_reporting.py`

1. Write failing candidate tests for exact SP500/SPCX identity, $5,000 notional, 10x leverage, 80-bps stop, 25-bar ceiling, next-bar BBO fills, exact risk columns, chronological development/folds, and withheld OOS.
2. Write failing reporting tests for nominal/stress economics, side/fold breakdown, largest-winner sensitivity, technical path status, and fail-closed disposition.
3. Run both suites and verify they fail because the modules are absent.
4. Implement the candidate using the shared development-partition helper and the frozen cost/execution contract.
5. Implement the report with explicit report-only authority and no promotion path.
6. Run both suites and verify green.

## Task 5: Add an immutable local-only command

**Files:**
- Create: `scripts/hip3_cash_open_gap_reversal_development.py`
- Modify: `tests/test_hip3_cash_open_gap_reversal_script.py`

1. Add failing command tests for explicit local database/funding/audit/qualification/fee/liquidity/cost inputs, source rehashing, fresh output requirement, report-only contract enforcement, and no network fallback.
2. Run the command tests and confirm behavior failures.
3. Implement a thin command that reuses the existing archive loader, attaches official funding, builds exact venue paths, evaluates only development, and writes atomically after source/generator rechecks.
4. Run command tests and verify green.

## Task 6: Execute the frozen development replay

**Files:**
- Create: `data/logs/research/xyz_sp500_cash_open_gap_reversal_development_20260817_v1.json`
- Create: `data/logs/research/xyz_spcx_cash_open_gap_reversal_development_20260817_v1.json`

1. Run SP500 with the exact audited June 8–August 6 archive, funding, qualification, fee, liquidity, and frozen cost inputs.
2. Verify output hashes, source reconciliation, no OOS access, zero live authority, and development/fold/path arithmetic.
3. Run SPCX with the same frozen contract and its exact symbol inputs.
4. Verify the same invariants.

## Task 7: Journal and disposition the result

**Files:**
- Create: `docs/research-journal/v53-sp500-spcx-cash-open-gap-reversal-development-result-v1.json`
- Modify: `configs/research/cohort_improvement_decision_overrides_v53.json`
- Modify: `tests/test_v53_continuous_improvement_profile.py`

1. Write a failing ledger test requiring the new hypothesis state, exact evidence hashes, minimum update evidence, and no live proposal.
2. Run it and verify red.
3. Add the result journal with the 15-field recommendation, confidence, risks, alternatives, falsifiers, and the single highest-value next investigation.
4. Update the research-only decision ledger without changing v53.
5. Run the ledger and improvement-monitor suites and verify green.

## Task 8: Final verification

1. Run all new and affected candidate/script/reporting tests with network tests excluded.
2. Run Ruff check and format check on every touched Python file.
3. Run JSON parsing, `git diff --check`, source/output SHA-256 reconciliation, <=500 lines/file, <=50 lines/function, and live-PID/profile/fingerprint invariance checks.
4. Re-read the preregistration and verify every frozen requirement against the produced artifacts.
5. Report the actual disposition; do not describe a failed or unresolved development result as a live candidate.
6. Do not commit or push this slice until it is added to the separately reviewed release manifest for the existing dirty worktree.

