# Hypervelocity Archive Parameter Comparison Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether the original Pareto-60 regime contract, the full BBWP blueprint, or a one-/two-parameter hybrid produces the strongest reproducible Hypervelocity behavior on the complete 90-day Hyperliquid archive.

**Architecture:** Add explicit, serializable regime-filter variants so the removed Choppiness configuration remains reproducible as a research challenger while the runtime default stays BBWP. Screen the complete baseline/single-change/pair-change/full matrix with causal regime metrics, independent next-bar entry barrier outcomes, and a serial one-position portfolio diagnostic, then run the baseline, full BBWP, best non-duplicate single, and best non-duplicate pair through the verified L2/trade archive. Every result is retained and configuration-stamped; rankings are report-only and never abort a trial.

**Tech Stack:** Python 3.13, pandas, dataclasses, pytest, existing Hyperliquid regime classifier, 0xArchive streaming maker replay.

---

## Assumptions and measurable success criteria

- Baseline groups are EMA 20/50, Choppiness(14) threshold 85, 5 bps breakout clearance, and 2.0x volume.
- Challenger groups are EMA 21/55, BBWP(20/240) below 25%, 8 bps clearance, and 2.5x volume.
- The matrix retains baseline, every one-group change, every two-group change, and the full challenger: 12 candidates total.
- The 15m state remains non-veto and the 5m state remains authoritative.
- Independent barrier evaluation enters at the next completed 1m bar open, uses the existing 8% margin target (0.2% price at 40x), the official BTC isolated-maintenance formula, and a conservative liquidation-first result when both barriers occur inside one OHLC bar.
- Independent barrier outcomes are fixed-stake diagnostics, not a portfolio equity curve or executable fills.
- The serial bar diagnostic enforces one position, next-bar entry, one-bar cooldown, same-direction structural reset, TP-only holding through RANGE, compounding, close-mark drawdown, and full closure at the isolated liquidation boundary. It cannot reproduce partial liquidation or depth-aware liquidation execution.
- The L2 replay remains the maker execution-assumption comparison and currently reports liquidation and drawdown as unavailable.
- A successful report contains exact configuration identity, all 12 screening results, all shortlisted L2 results, selection rationale, unresolved/open outcomes, and limitations.
- Historical funding is reported unavailable unless a complete venue funding series is supplied; no zero-funding result may be labeled funding-adjusted.

### Task 1: Reproducible regime candidates

**Files:**
- Create: `src/hypervector/regime/hypervelocity_candidates.py`
- Modify: `src/hypervector/regime/classifier.py`
- Modify: `src/hypervector/strategies/hypervelocity_contract.py`
- Test: `tests/test_hypervelocity_candidates.py`
- Test: `tests/test_regime_classifier.py`

1. Write a failing test proving the baseline candidate reproduces the saved Pareto-60 parameters and the runtime candidate explicitly selects BBWP.
2. Run the focused test and confirm it fails because filter selection and candidate identity do not exist.
3. Add an explicit `range_filter` selector plus Choppiness challenger settings without changing the faithful runtime default.
4. Generate baseline, four single-change, six pair-change, and full-BBWP candidates with deterministic SHA-256 fingerprints.
5. Run the focused tests until green.

### Task 2: Independent trade-outcome screening

**Files:**
- Create: `src/hypervector/research/hypervelocity_candidate_eval.py`
- Test: `tests/test_hypervelocity_candidate_eval.py`

1. Write failing tests for next-bar entry, long/short target completion, isolated liquidation, unresolved right-censoring, same-bar ambiguity, and fees.
2. Run the focused tests and verify the expected missing-feature failures.
3. Implement causal independent-signal barrier evaluation using canonical entry-direction episode starts.
4. Emit fixed-stake counts, win/loss/unresolved rates, net PnL, liquidation count, median holding time, and adverse excursion.
5. Run the focused tests until green.

### Task 2B: Serial portfolio screening

**Files:**
- Create: `src/hypervector/research/hypervelocity_portfolio_eval.py`
- Test: `tests/test_hypervelocity_portfolio_eval.py`

1. Write failing tests for one-position enforcement, compounding, same-direction structural reset, one-bar cooldown, range-hold behavior, liquidation equity, and bounded drawdown.
2. Implement a next-bar-open serial portfolio diagnostic using the same 70% margin, 40x leverage, 8% target, maker entry/target fees, and taker liquidation fee.
3. Label liquidation as a full-close boundary approximation; do not claim partial-liquidation or order-book execution fidelity.
4. Rank screening candidates by the serial result while retaining every trial.
5. Exclude decision-identical pairs from the expensive shortlist without dropping them from the report.

### Task 3: Configuration-stamped maker replay

**Files:**
- Modify: `src/hypervector/cli.py`
- Create: `src/hypervector/research/hypervelocity_archive_compare.py`
- Test: `tests/test_hypervelocity_maker_replay.py`
- Test: `tests/test_hypervelocity_archive_compare.py`

1. Write a failing CLI test proving replay output includes candidate ID, exact parameters, fingerprint, and archive identity.
2. Write a failing comparison test proving all 12 screenings are retained and shortlist selection is deterministic without rejecting weak trials.
3. Add a report-only `hypervelocity-archive-compare` command that loads bars/archive once per phase and writes one comparison artifact.
4. Shortlist baseline, full BBWP, best single, and best pair for the expensive L2 phase.
5. Run focused CLI/comparison tests until green.

### Task 4: Full 90-day experiment

**Files:**
- Create: `data/logs/research/hypervelocity_archive_parameter_comparison_20260727.json`

1. Verify the 2,160 archive bundles and checksums before evaluation.
2. Run all 12 candidates over the 129,600 strict Hyperliquid bars.
3. Run shortlisted candidates through touch, one-tick-through, and public-trade-through archive replay.
4. Preserve all candidate results, including sparse, losing, liquidated, or unresolved outcomes.
5. Compare the recommendation with the saved Pareto-60 and full-BBWP reports.

### Task 5: Verification and handoff

**Files:**
- Modify: `HANDOFF.md`
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `skills/hypervector-regime-detector/SKILL.md`

1. Run focused candidate, classifier, evaluator, replay, and CLI tests.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Run changed-file Ruff, `git diff --check`, and archive-report schema checks.
4. Document which candidate was better or worse, exact trade/outcome metrics, execution disagreement, funding limitations, confidence, and falsifiers.
5. Defer commit/push because the working tree already contains open user-approved chart/BBWP changes and no commit was requested in this turn.

## Measured result

- Completed artifact: `data/logs/research/hypervelocity_archive_parameter_comparison_20260727.json`.
- Archive: 2,160 checksum-verified hourly bundles; 12,013,542 L2 snapshots; 36,591,762 deduplicated public trades.
- All 12 bar screenings and all four shortlisted three-rule L2 replays completed.
- Every shortlisted candidate lost at least 98.18% in the serial bar diagnostic and more than 99.91% in every L2 result; maximum drawdown was worse than -99.95% in every L2 result.
- EMA21/55-only retained the most equity under trade-through ($8.84); EMA21/55+8 bps clearance led touch ($2.98) and through ($2.84). The full BBWP blueprint did not dominate.
- BBWP25 alone was decision-identical to the original Choppiness85 candidate on this window.
- No promotion or runtime change was made. Historical funding, authentic mark price, queue rank, and depth-aware liquidation execution remain explicit limitations.
