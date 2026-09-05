# V85 Route Bleeding Audit and V86 Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Continuously reconcile every V85 strategy's entries, protection, exits, and after-cost outcomes; identify demonstrated negative mechanisms; and replace or repair those mechanisms without removing any of the seven requested assets.

**Architecture:** Treat the append-only live ledgers and immutable portfolio archive as execution truth, and the active V85 config as authority truth. Produce a report-only, run/profile-bound route audit that separates technical defects from statistical losses and decomposes each closed lifecycle into entry quality, execution drag, adverse excursion, favorable excursion surrendered, exit reason, fees, and funding. Any V86 change must retain `BTC`, `ETH`, `SOL`, `HYPE`, `ZEC`, `xyz:SPCX`, and `xyz:SNDK`, remain disarmed until a separately authorized transition, and replace a losing route with independently validated same-asset logic rather than silently deleting the asset.

**Tech Stack:** Python 3.13, pytest, JSONL ledgers, DuckDB/Parquet research data, existing cohort checkpoint/audit contracts, TOML live profiles, Rust Ratatui projection tests.

---

### Task 1: Freeze the V85 evidence boundary

**Files:**
- Read: `configs/multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85.toml`
- Read: `data/runtime/bidirectional_cohort/latest_checkpoint.json`
- Read: `data/live/bidirectional_cohort/decisions.jsonl`
- Create: `docs/research-journal/v85-route-bleeding-audit-preregistration-v1.json`

1. Record the exact run ID, profile fingerprint, seven symbols, nine monitored provider-symbol pairs, eight executable pairs, configured directions, entry IOC caps, stop/target recipes, maximum holds, and accounting epoch.
2. Freeze the audit cutoff at a complete cohort-ledger prefix and hash that prefix.
3. Declare the minimum 13-bps round-trip comparison hurdle where exact route-specific live costs are unavailable; retain exact realized costs where available.
4. Declare that trade count and cadence are reported usefulness criteria, not technical abort gates.
5. Validate the JSON preregistration and confirm it contains `execution_authority=none` and no automatic strategy mutation.

### Task 2: Reconcile every entry and exit lifecycle

**Files:**
- Create: `src/hypervector/research/v85_route_bleeding_audit.py`
- Create: `scripts/v85_route_bleeding_audit.py`
- Create: `tests/test_v85_route_bleeding_audit.py`
- Create: `tests/test_v85_route_bleeding_audit_script.py`

1. Write failing tests for exact V85 identity, all nine monitored routes, all eight execution scopes, namespaced HIP-3 lifecycle IDs, partial fills, rejected entries, protective-stop coverage, mixed exits, fees, funding, MFE, MAE, and peak giveback.
2. Run the focused tests and record the expected failures.
3. Implement immutable-prefix loading and exact lifecycle reconciliation by reusing existing cohort audit/reflection helpers.
4. Classify each route as `technical_fault`, `negative_signal`, `exit_leakage`, `execution_drag`, `insufficient_evidence`, or `no_observed_issue`; allow multiple evidence-backed diagnoses.
5. Refuse missing routes, identity drift, malformed lifecycles, incomplete costs, or an in-progress trailing JSONL record instead of producing a success-shaped report.
6. Run focused tests until green.

### Task 3: Run the current V85 audit and isolate root causes

**Files:**
- Create: `data/logs/research/bidirectional_cohort/v85_route_bleeding_audit_<UTC>.json`
- Update: `docs/research-journal/v85-route-bleeding-audit-preregistration-v1.json`

1. Snapshot the current run without stopping, signaling, restarting, or mutating the live backend.
2. Reconcile every current and archived lifecycle against its exact provider-symbol-side contract.
3. Report route-level closed count, wins/losses/breakeven, gross and net PnL, fees, funding, slippage, maximum drawdown, leave-largest result, cadence, and adverse/favorable excursion coverage.
4. Separate `different outputs on identical inputs` technical failures from `same outputs with poor net returns` statistical failures.
5. Identify the earliest causal layer that explains each negative route: signal, entry, execution, protection, maximum hold, or exit.

### Task 4: Test one repair per demonstrated loss mechanism

**Files:**
- Create: `docs/research-journal/v86-<asset>-<mechanism>-preregistration-v1.json`
- Create or modify only the route-specific research signal/replay files selected by Task 3.
- Create matching focused tests under `tests/`.

1. Preserve the five scoping invariants: point-in-time decision data, exact universe, label/horizon, cost model, and walk-forward protocol.
2. Write a failing parity or replay test before changing strategy code.
3. Change one causal mechanism at a time; do not combine entry, stop, target, and sizing changes in one trial.
4. Apply `shift(1)` between signal and executable bar, purge overlapping labels by the exit horizon, and fit learned transforms inside each fold.
5. Report every explored variant, every fold, gross and net results, worst fold, leave-largest result, break-even cost, and effective sample size.
6. Reject a replacement whose edge disappears after costs, in the worst fold, or after removing its largest winner.

### Task 5: Build a complete disarmed V86 successor only from passing repairs

**Files:**
- Create: `configs/multi_asset_growth_first_5000_seven_asset_route_repaired_v86.toml`
- Create: `tests/test_v86_route_repaired_config.py`
- Create: `docs/guides/cohort-live-transition-and-rollback-v86.md`

1. Write a failing config test requiring the exact seven-asset roster and at least one executable route for every asset.
2. Preserve venue leverage ceilings, one-position-per-symbol ownership, explicit entry/close IOC caps, and venue-native reduce-only protection.
3. Replace only routes that Task 3 classifies as demonstrably broken or negative and Task 4 supplies with a validated alternative.
4. Load V86 in observe mode and run a bounded production-provider parity observer in an isolated ledger root.
5. Validate all TUI screens, exact route coverage, and fresh 0/0 display history without granting execution authority.
6. Do not stop V85 or start V86. A live transition requires a later flat/order-free boundary, verified backup, post-start acceptance, rollback evidence, and fresh explicit live-risk authorization.

### Task 6: Verify and hand off

**Files:**
- Verify all files changed by Tasks 1-5.

1. Run focused audit and strategy tests.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Run `cargo fmt --all -- --check` and `cargo test -p hypervector-tui`.
4. Run the explicit V86 current/observe runtime TUI acceptance test.
5. Recheck that the active V85 backend was not signaled or restarted and that its latest checkpoint remains technically accepted.
6. Do not create a commit while the shared worktree contains unrelated user changes unless the user explicitly requests one.
