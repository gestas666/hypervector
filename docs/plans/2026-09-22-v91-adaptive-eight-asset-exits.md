# V91 Adaptive Eight-Asset Exits Implementation Plan

**Goal:** Deploy a verified live eight-asset successor to V90 with aggressive
entry/allocation behavior, causal market-aware exits, measurable profit
retention, durable recovery, and working monitoring.

**Architecture:** Reuse the existing venue execution and lifecycle ownership
boundaries. Bind a versioned adaptive exit contract at entry; evaluate completed
regime/volatility evidence and fresh order-book corroboration during each open
lifecycle. Evaluate ML continuation estimates against deterministic baselines
with chronological, cost-aware validation before assigning model authority.

**Tech Stack:** Python, existing pandas/NumPy/ML dependencies, Hyperliquid
mainnet adapters, JSONL lifecycle journals, pytest, existing Rust TUI, launchd.

## Authority and boundaries

The user explicitly requests research, trading skills, ML consideration,
implementation, and the new eight-asset profile live and trading. The universe is
BTC, ETH, SOL, HYPE, xyz:SPCX, xyz:SNDK, xyz:BRENTOIL, xyz:TSLA, all eligible to
execute. Do not substitute the old five-executable/three-observation profile.
Preserve native protection, isolated margin, reduce-only closes, and exact
restart identities. Technical validity is required; research results remain
reported evidence rather than invented performance gates or profit guarantees.

Worktree: `/Users/gestas/Prototypes/hypervector-v91-adaptive-exits-20260922`.
The current dirty work was copied intact; `.codex-v91-baseline.json` identifies
the starting files. Main live checkout source remains unchanged during work.
Shared data is existing evidence; new artifacts use dedicated V91 paths.

## Success evidence

- All eight current assets have executable membership in the successor profile.
- Exits explicitly respond to favorable excursion, volatility, confirmed regime
  deterioration, and fresh corroborating book conditions; every action states why.
- ML is researched and empirically compared using causal features, purged labels,
  training-only transformations and held-out time blocks. Report the measured
  result and actual authority, including a negative outcome if applicable.
- Healthy trends retain room to run; the new profile is not a disguised blanket
  tight scalp or reduced-capital substitute. Compare net returns, profit retained,
  cut winners, loss tails, turnover and execution costs, not just win rate.
- Missing/stale/future/duplicate inputs cannot fabricate confidence or loosen an
  established profit floor. Restart preserves lifecycle state and pending exits.
- The three reproduced review failures pass regression tests; loaded services
  contain the repaired code and intended graceful shutdown configuration.
- Fresh independent venue checks, approved exact config/source identity,
  authenticated backup, live armed process, all-eight fresh telemetry, and
  monitoring/restart evidence demonstrate deployment. No manual trade is required
  merely to manufacture an apparent fill.

## Task 1 — Research, evidence and frozen exit specification

Read the ML4T, algo-trading and project regime/CLI skills. Use Exa primary sources
(Parallel refused for insufficient credit). Inspect actual regime, book, model,
cost and replay paths. Save sources and a research report under
`data/logs/research/bidirectional_cohort/v91_adaptive_exits_20260922/` and
`docs/reviews/2026-09-22-v91-adaptive-exit-research.md`.

Before evaluating candidate results, freeze a small comparison matrix and causal
input/label/horizon/cost definitions in that report. Derive concrete parameters
from the stated exit behavior and volatility/cost units, not a search for the
best historical PnL. Distinguish existing historical screens from new held-out
tests. Do not invent historical order flow from candles or spaced L2 snapshots.

## Task 2 — Repair known execution/supervisor failure paths

Files: `src/hypervector/live/sol_range_onset_engine.py`,
`src/hypervector/live/multi_asset_live_runner.py`, `scripts/cohort_supervisor_*.py`.
Promote the three offline review probes into focused regression tests, run them
red, repair the underlying boundaries, and run relevant existing suites.
Handle mutation-capable reconciliation errors distinctly from read-only failures;
preserve fault visibility if event/alert storage fails; retain unpersisted stops
without allowing restart. Test subsequent supervisor lifetimes and receipt-bound
partial-close recovery. Keep each new module under 500 lines and functions under
50 where feasible without rewriting unrelated baseline code.

## Task 3 — Implement the frozen adaptive exit contract and controller

Expected files: new `src/hypervector/live/cohort_adaptive_exit_*.py`,
`cohort_execution_plan.py`, `cohort_execution_plan_validation.py`,
`cohort_route_cycle.py`, `multi_asset_live_runner.py`, telemetry/protocol/history
modules, and dedicated tests. Search/reuse existing causal book and regime
parsers before adding helpers. Preserve old fingerprints by omitting inactive
new contract fields from legacy payloads where required.

Write failing long/short policy tests first: supported trend, deteriorating
regime, corroborating/persistent opposing book, profit-floor crossing, costs,
stale/unknown evidence, gaps, no future access, duplicate observations,
restart/pending close, partial close and same-cycle re-entry suppression.
Implement the smallest explicit state machine that satisfies the frozen policy.
Expose the actual decision evidence in durable telemetry and the TUI's existing
exit-plan projection. No LLM sits in the signed-order path.

## Task 4 — ML and replay evaluation

Expected files: dedicated `src/hypervector/research/v91_*` and `scripts/v91_*`
research modules, small auditable model artifact/schema if justified, tests.
Use a regularized baseline and one bounded nonlinear comparator, no unbounded
hyperparameter search. Report fold-level behavior, effective sample limitations,
calibration, net execution outcomes and failure cases. Run the production policy
function on identical causal replay inputs. Compare against original exits and
fixed protection at actual allocation and normalized notionals.

## Task 5 — Eight-asset package and review

Create `configs/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml`, a
new V90-to-V91 approval record containing the actual user instruction, and a
deployment/rollback runbook. Retain V90 as rollback evidence. Test all eight
resolved entry/exit contracts, venue leverage/precision, fingerprint round-trip,
bound lifecycle policy and source hashes. Review the completed diff, correct
the obsolete status claims without corrupting historical approval hashes, and
run the project Python/Rust checks plus focused critical-path coverage.

## Task 6 — Controlled deployment and live acceptance

Use the existing transition-drain inbox. Verify completion and fresh venue
flat/order-free truth; archive the exact completed drain through its existing
recoverable command. Retain installed service definitions, durable restart
journal, source/config and accounting evidence. Deploy only the reviewed changes
against unchanged baseline hashes. Install the intended supervisor/checkpoint
definitions and launch the new profile with both explicit live flags using the
existing credential path without printing secrets. Verify the actual loaded
timeouts, no competing owner, authenticated startup backup, new implementation
hash, all eight executable scopes, fresh market/exit/ML telemetry and healthy
monitoring. Validate induced failure/restart with isolated acceptance stubs; do
not kill a live position-holding backend to demonstrate restart.

## Current progress — complete at 11:03:58 UTC

Research, implementation, review, exact approval, controlled deployment and live
acceptance are complete. V91 is live and armed as
`bidirectional-live-1790073983560`, with all eight executable scopes, fresh
canonical/book telemetry, 8/8 setup coverage and a matching healthy checkpoint.
The cohort is flat and awaiting normal entry signals; no order was manufactured.

Validation: full Python suite 10,169 passed; full Rust suite and Clippy passed;
136 final changed-area tests, 83 corrected supervisor tests and 46 deployed
critical-path tests passed. Actual V91 cockpit projection and disposable launchd
shutdown acceptance passed. Whole-repository formatting retains four unrelated
pre-existing findings, documented in the acceptance report.

The host capped the proposed 180-second launchd timeout at 60. Deployment revision
2 corrects the child wait to 30 seconds and persists stop before waiting. Its
exact approval and loaded service state were validated. Original source, plists,
journals and authenticated startup backup remain available for recovery.

No validated ML exit advantage was found. Prospective Ridge telemetry has no order
authority; real captured startup inference succeeds on all eight assets. Profit
improvement remains an empirical forward hypothesis, not a completion claim.
See `docs/reviews/2026-09-22-v91-code-review-and-acceptance.md` for exact evidence,
limits, source identities and the current deployment/rollback procedure.
