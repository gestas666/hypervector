# Frequency and non-crypto expansion implementation plan

**Goal:** Repair the mismatch between V88's sparse, concentrated results and the requested active growth portfolio, and add SPCX plus two non-crypto candidates to a concrete, testable successor.

**Architecture:** Reuse existing causal providers, replay engines, source provenance, and shared-account configuration. Run research in this isolated checkout, keeping the operator's current process and configuration intact. New hypotheses are exploratory on previously examined history; recent data is an evaluation extension only when exposure provenance supports that description.

**Tech stack:** Python, pandas, DuckDB, immutable JSON/Parquet evidence, pytest, existing Hypervector CLI and Ratatui TUI.

## Requirements and acceptance

- Report calendar and active-session trade frequency, net win rate, average win/loss, cost sensitivity, loss concentration, and chronological slices for every tested candidate. Frequency alone is not an edge claim.
- Include SPCX and screen non-crypto alternatives using exact mainnet metadata, current liquidity, historical coverage, and prior hypothesis dispositions. Select up to three non-crypto additions total.
- Preserve baseline and failed candidates. No performance metric implicitly aborts a technically valid trial. No automatic promotion or order authority.
- The completed deliverable includes reproducible experiments, tested candidate configuration/provider integration where supported, TUI visibility, explicit readiness limitations, and rollback to the unchanged V88 profile.
- Success is a technically correct, reviewable replacement and an honest measured comparison. Positive future returns or a majority of large winners cannot be an engineering guarantee.

## Task 1: Pin root cause and experiment inputs

Read the existing research journals and generators; reuse rejection dispositions rather than rerunning identical ideas. Freeze V88's 351-day baseline and the new evaluation protocol. Run public `scripts/hip3_market_qualification.py` for SPCX, SP500, SNDK, GOLD, and BRENTOIL. Inventory exact cached bar, L2, funding, and prospective sources. Record the selected three assets and the changed assumption behind every reopened hypothesis.

Files: this plan; `docs/research-journal/frequency-noncrypto-repair-20260907-v1.json`; immutable artifacts under the original workspace's `data/logs/research/bidirectional_cohort/`.

## Task 2: Run bounded causal comparisons

Reuse `src/hypervector/research/shared_bar_portfolio.py` and existing HIP-3/core provider signal builders. Prefer small, predeclared mechanism comparisons to broad parameter search. Preserve funding, spread/slippage, gaps, terminal censoring, and same-bar ambiguity. Report chronological partitions without relabeling repeatedly inspected data as untouched holdout. Write a reproducible script if no existing command performs the necessary comparison.

For any new calculation, first add an offline test using hand-computable trades covering frequency, wins/losses, costs and largest-winner removal; run it and observe failure before implementation. Verify truncating future inputs preserves prior signals. Tests must not make network calls.

## Task 3: Implement the successor and visibility

After evidence resolves asset/route selection, create the next unused successor profile under `configs/` and tests under `tests/`. Reuse existing supported providers and backend-authored TUI projections. Implement a provider only when a validated mechanism requires one. Test exact symbols, sides, execution contracts, no-submit construction, and profile identity. Add a concise review with observed activity and readiness for each asset; no invented performance or hidden safety gate.

## Task 4: Verify and deliver

Run focused pytest/Ruff checks, then the affected integration suite. Run Rust tests and terminal visual acceptance if TUI code or the asset projection changes. Verify original V88 configuration hash and active runtime identity were not changed by this work. Append the research decision with evidence hashes; preserve rejected results and next validation requirements. Commit only this task's files and provide the exact candidate, measured comparison, and any remaining approval-dependent activation step.

## Risks and falsifiers

Sparse current behavior can be intentional signal logic rather than a defect; more trades can increase costs and losses. Historical selection bias, cash-session calendar errors, stale midpoint bars, absent funding, native mark differences, and correlated equity exposure can invalidate apparent gains. A timestamp/side/source mismatch invalidates an experiment; a negative result changes the recommendation without suppressing the report.

## Execution disposition

The bounded research, tested seven-asset candidate, backend evidence integration, terminal review and source-backed decision are complete. SPCX, SNDK and BRENTOIL were selected for the staged profile; SP500 and GOLD were not added. All 216 experiment cells remain retained. See [the review](../reviews/2026-09-07-frequency-and-noncrypto-expansion.md) for observed cadence, costs and explicit economic limitations.

Live activation was not performed. Full seven-asset joint-account validation and prospective execution economics remain unproven. The final independent runtime check found V88 stopped with `operator_stop` records, which supersedes the initial running-state observation. The expansion is a reviewable implementation, not a claim that the operating portfolio is now trading or profitable.
