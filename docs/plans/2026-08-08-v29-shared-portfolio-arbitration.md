# V29 Shared-Portfolio Arbitration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish one immutable, report-only diagnostic that passes all six inactive v29 routes through the same $500 account, configured priority order, five-position cap, and one-position-per-asset ownership contract.

**Architecture:** Normalize already-completed route lifecycles to v29's fixed per-asset notional and leverage contracts, then replay entry and exit events chronologically. A generic priority router accepts the first available lifecycle for an asset, records later occupied-asset or capacity conflicts, preserves realized shared equity, and exposes strategy/side attribution. The CLI runs nominal and HIP-3 stress scenarios from already-opened evidence only; it does not access sealed HIP-3 holdout rows or mutate live state.

**Tech Stack:** Python 3.13, dataclasses, pandas/Parquet, existing `CohortOutcome` adapters, immutable JSON evidence, pytest, Ruff.

---

## Empirical contract

- Source profile: `configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml`.
- Required executable scope: six exact provider-symbol mappings and no observe-only mappings.
- Initial account: $500; fixed notional caps: ETH $25, other selected assets $75; leverage 5x.
- Router: provider priority ascending, exits before entries at the same timestamp, one open lifecycle per asset, maximum five simultaneous assets.
- Inputs: ETH dual-MTF Range Onset continuous trades, SOL Range Onset event-replay trades, ETH precompression-pullback replay, and HIP-3 development plus validation sidecar rows for SPCX Swing/HA, SP500 breakout pressure, and GOLD Swing/HA.
- HIP-3 scenarios: nominal and stress. The sealed holdout is excluded and must remain absent from the sidecar phases.
- Authority: `execution_authority=none`, `report_only=true`, `automatic_promotion=false`, `runtime_strategy_changed=false`.
- Interpretation: capacity/conflict and realized-equity diagnostic only. Independent precomputed exits cannot reproduce opposite-intent early exits or private IOC fills.

### Task 1: Priority-aware shared-account router

**Files:**
- Create: `src/hypervector/research/evidence_selected_portfolio.py`
- Test: `tests/test_evidence_selected_portfolio.py`

1. Write failing tests for same-time priority, occupied-asset rejection, five-position capacity, exit-before-entry ordering, fixed-cap realized equity, and strategy/side attribution.
2. Run `uv run pytest tests/test_evidence_selected_portfolio.py -q` and verify failures are due to the missing module.
3. Implement typed router dataclasses and `replay_prioritized_outcomes()` without live imports or network calls.
4. Validate unique outcome IDs, complete priority coverage, positive account/capacity values, and finite economics.
5. Rerun the focused test and require all tests to pass.

### Task 2: Exact source adapters

**Files:**
- Modify: `src/hypervector/research/evidence_selected_portfolio.py`
- Modify: `tests/test_evidence_selected_portfolio.py`

1. Write failing tests for ETH context-candidate selection and HIP-3 sidecar route/phase/friction filtering.
2. Require every source to declare no execution authority and reject missing, duplicated, or unexpected candidate identities.
3. Normalize each lifecycle by its observed entry notional to the configured v29 cap while preserving after-cost return, direction, entry/exit timestamps, and exit reason.
4. Reject HIP-3 phases outside `development` and `validation`; reject sealed or unknown phases explicitly.
5. Rerun the focused tests.

### Task 3: Immutable v29 diagnostic command

**Files:**
- Create: `scripts/evidence_selected_portfolio_v29.py`
- Create: `tests/test_evidence_selected_portfolio_v29_script.py`

1. Write failing parser and artifact-contract tests.
2. Load the v29 config in observe mode and verify its exact profile fingerprint, six-route execution scope, sides, priorities, sizing, and zero observe-only routes.
3. Load and hash all local source files; build shared nominal and stress replays from the same crypto lifecycles and friction-specific HIP-3 rows.
4. Emit accepted/rejected counts, conflict reasons, concurrency, reserved margin, PnL/PF/drawdown, and strategy/side attribution.
5. Publish exclusively with `write_immutable_json`; an existing output path must fail rather than overwrite.
6. Run focused script tests and Ruff.

### Task 4: Execute, analyze, and journal

**Files:**
- Create: `data/logs/research/evidence_selected_portfolio_v29_shared_arbitration_<UTC>.json`
- Create if evidence changes the assessment: `docs/research-journal/evidence-selected-portfolio-v29-v4.json`
- Modify if revision 4 is appended: `docs/guides/cohort-live-transition-and-rollback-v29.md`
- Modify if revision 4 is appended: `tests/test_evidence_selected_portfolio_v29_transition_runbook.py`

1. Run the diagnostic once against immutable local inputs.
2. Verify no sealed HIP-3 holdout phase, live client, order adapter, or execution authority appears.
3. Compare nominal and stress results, both sides, winner concentration, accepted/rejected route counts, and same-asset ETH conflicts.
4. Append revision 4 only if the new diagnostic materially updates v29; preserve revision 3 otherwise.
5. If revision 4 exists, use test-first binding to update the transition runbook.
6. Run the focused Python suite, Ruff, JSON validation, DuckDB evidence-integrity report, and `git diff --check`.

## Success criteria

- Both scenarios reconcile shared equity exactly to accepted lifecycle PnL.
- No asset has overlapping accepted positions; simultaneous positions never exceed five.
- Every rejected lifecycle has an explicit reason and retains route attribution.
- All six v29 routes are represented in inputs and both directions remain measurable where source events exist.
- Sealed HIP-3 holdout rows remain unaccessed.
- Live v25 process, orders, positions, stops, route authority, and transition drain remain unchanged.

## Failure modes and falsifiers

- A source/config identity mismatch, missing evidence hash, duplicated lifecycle, unknown HIP-3 phase, unaccounted same-asset overlap, or equity reconciliation error invalidates the artifact.
- A positive aggregate with one losing component is not evidence that every route has edge.
- A negative diagnostic weakens v29 but is a reported research result, not an implicit runtime abort gate.
- Precomputed route lifecycles cannot establish private fill parity or counterfactual opposite-intent exit timing; fresh live telemetry remains the update path.

No commit, live transition, restart, drain, order, close, or sizing mutation is authorized by this plan.
