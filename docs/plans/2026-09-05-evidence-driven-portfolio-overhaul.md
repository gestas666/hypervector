# Evidence-driven Portfolio Overhaul Implementation Plan

> Execute the full objective in the attached September 5 mandate; this plan does not redefine completion as diagnostics alone.

**Goal:** Deliver a validated, maintainable portfolio revision with a working continuous improvement pipeline, accurate TUI, explicit executable strategy coverage for each retained asset, and a verified live transition under the operator's authorization.

**Architecture:** Start from preserved V86 commit `fac0369` in an isolated worktree. Use immutable ledger prefixes and venue observations as execution truth, DuckDB and source-backed experiment records as research evidence, and exact profile/provider/side contracts as comparison boundaries. Preserve the current deployment and evidence until a reviewable successor and rollback exist.

**Tech stack:** Python 3.13, DuckDB, Parquet/0xArchive, existing strategy/event replay and journal modules, pytest, Rust/Ratatui.

## Requirements and completion evidence

| ID | Requirement | Required evidence | Status |
|---|---|---|---|
| R1 | Inspect actual current system, logs, all trades and anomalies | Exact source/run/profile inventory; venue positions/orders; ledger-source reconciliation; current and historical lifecycle audit | In progress |
| R2 | Diagnose entry/exit quality, costs, timing, stops, regimes, portfolio interactions and mismatch with research | Per provider/asset/side/time/regime outcomes, realistic fees/funding/slippage/latency, sample counts/uncertainty, concentration/correlation and marked drawdown | In progress: exact executable capacity and static adverse-cost sensitivities verified |
| R3 | Active, nonrepeating research pipeline | Source-backed ledger with proposed/testing/accepted/rejected/deferred/superseded states; ranked opportunities and one next investigation per review | In progress: two new canonical revisions; ZEC/GOLD prior decisions reconciled |
| R4 | Evidence-backed improvements and complete executable asset/strategy coverage | Frozen candidate hypotheses; causal production-provider replay; chronological out-of-sample/walk-forward/stress and bias audit; exact final route matrix | In progress: 71-day core extraction and sampled parity complete; SNDK current onset mismatch confirmed, correction pending |
| R5 | Reliable implementation and execution | Failing regressions before fixes, meaningful focused/full offline tests; venue constraints; protection/adoption/partial-fill/rejection/restart checks; no-submit observer parity | In progress: lifecycle and bootstrap fixes; 7,929 full-suite tests then 193 related bootstrap tests passed |
| R6 | Updated TUI | Backend parity on every screen and retained asset/route; explicit missing/stale evidence; build, rendering and interactive PTY verification | In progress: terminal-state rendering fixed, Rust checks and recorded-fixture PTY verified |
| R7 | Reviewable changes and rollback | Proposal includes every requested field; immutable previous source/config backup; measurable success and rollback triggers; explicit scope of live authorization | Pending |
| R8 | Live operation and continuing research | Authorized exact launch; fresh venue reconciliation; process handles; post-start acceptance; ongoing ledger/monitor coverage; entry/protection/exit evidence as available | Pending |

Optional: up to three additional non-crypto Hyperliquid perp assets, only with sufficient native history, feasible current liquidity/costs, and portfolio contribution evidence. ML and external feeds are alternatives to evaluate where the evidence supports them, not deliverables to fabricate.

## Task 1: Freeze and reconcile current evidence

- Inspect `data/runtime/bidirectional_cohort/latest_checkpoint.json`, newest immutable audits, `data/live/bidirectional_cohort/`, database source tables, and `docs/research-journal/`.
- Record hashes for bounded source artifacts and run/profile identity. Verify source-prefix consistency before trusting projected counts.
- Use `create_multi_asset_read_only_readers` for a fresh public-wallet-only venue check. Missing provider dependencies are distinct from venue flatness.
- Inventory source journal revisions absent from DuckDB; preserve rejected hypotheses and opened historical windows.
- Publish an immutable diagnostic artifact and a concise source-backed review.

## Task 2: Repair demonstrated lifecycle telemetry defects

Files: `src/hypervector/research/cohort_live_lifecycle.py`, `tests/test_cohort_live_checkpoint_liveness.py`, relevant Rust lifecycle projection/tests.

1. Reproduce terminal asset engines classified as healthy solely from the last running heartbeat.
2. Add regression cases for fresh/stale terminal evidence, degraded status, missing evidence and faults. Run them before changing the classifier.
3. Classify terminal control state independently of process liveness; do not infer flat positions from STOPPED workers.
4. Verify active healthy and protected-open stopped cases remain distinguishable in Python and TUI projections.
5. Reproject the immutable V86 evidence to a new artifact; preserve the original checkpoint.

## Task 3: Audit economic diagnosis and experiment governance

- Reuse `cohort_live_audit`, `cohort_continuous_improvement`, `cohort_successor_triage`, `portfolio_research_journal`, and existing route-specific replay utilities before adding helpers.
- Check triage against the exact executable directions: a long-only or short-only contract must not inherit an implicit both-side research requirement.
- Separate normal variance, rare intended signals, deliberate observe-only routes, technical outages, implementation defects, changed costs, and unsupported edge claims.
- Verify each source-backed journal revision; enumerate missing/changed evidence without pretending the entire database is current.
- Rank proposals by expected value evidence, confidence, downside, complexity and validation priority. Retain do-nothing/current-contract and simpler alternatives.

## Task 4: Validate the actual successor

- Choose the highest-value untested hypothesis from Task 3; preregister its mechanism, costs, splits, candidate count, leakage checks, and falsifiers before viewing new outcomes.
- Run production-compatible historical tests for every retained route, realistic execution replay where native L2/trades exist, and documented uncertainty where they do not.
- Report every valid trial, including losses and sparse cadence. Performance results are not implicit technical abort gates.
- Test delayed entry, wider costs, funding, adverse intrabar ordering, market gaps, and concurrent portfolio margin/exposure. Fit transforms/models within chronological folds and purge overlapping labels.
- Do not relabel already-opened partitions as untouched holdouts. Validate any changed contract against newly reserved evidence or explicitly label the limit.
- Construct the concrete candidate configuration and named replacements needed for complete retained-asset coverage. No silent retirement or unsupported profitability claim.

## Task 5: Implementation, TUI and transition

- Implement only validated changes with focused regression/parity tests, explicit types and errors; retain venue-native protection and one-position-per-symbol ownership.
- Update effective configuration, route state, research evidence and lifecycle presentation in the TUI. Test all retained rows at 120x36 and wide layouts, then inspect a real PTY session.
- Run `uv run pytest tests/ -q -m "not network"`, `cargo fmt --all -- --check`, `cargo clippy -p hypervector-tui --all-targets -- -D warnings`, `cargo test -p hypervector-tui`, release build and CLI status.
- Deliver the full proposal fields from the mandate, including remaining validation and confidence, with a complete rollback package before any final approval request.
- Establish a fresh flat/order-free or verified protected-position adoption boundary, resolve dependencies and exact authorization, launch the validated profile, and verify fresh post-start telemetry and continuing research processes.

## Initial evidence and falsifiers

High confidence: root `main` is July commit `4fae13c`; preserved September V86 source is `fac0369`. The latest V86 run is `bidirectional-live-1788585501070`, with 1,255 routing cycles, zero intents/fills/closes and reported unchanged collateral $4,857.58724349. These are local report observations, not fresh venue observations or proof of economic fitness.

High confidence: primary DuckDB contains September 5 live-event imports but its portfolio journal revisions stop August 22. Source records may use different schemas; inventory and checksum comparison are required before describing this as lost research.

Falsifiers: a different current owner/run, source-prefix mismatch, unresolved venue exposure, incomplete exact route coverage, inconsistent costs/attribution, look-ahead or opened-holdout reuse, and TUI/backend disagreement invalidate the corresponding readiness claim.

## Continuation record

Initial turn: progress — located preserved current implementation, isolated it without changing the original branch, inspected current run and database schemas, and identified concrete validation targets. No live strategy or deployment change has been made. All eight requirements remain open until independently verified.

September 5 continuation: progress — source integrity and all-live archive reconstruction completed; terminal health and TUI fixes verified; exact capped executable capacity published and journaled; prior ZEC exact replay found and retained rather than repeated; GOLD reopening condition remains unestablished. Fresh SPCX observation reproduced and repaired empty-journal bootstrap. See `docs/reviews/2026-09-05-portfolio-overhaul-foundation.md` for evidence, confidence, corrections and limits. The next economic experiment is the six-route shared-account marked-path replay at current caps; the old `current_cohort_shared_portfolio.py` is a V11-specific predecessor and must not be relabeled as V86 parity. The primary two archive registries contain BTC/SOL and SPCX/SNDK; ETH/HYPE candle sources and native-path availability require explicit binding. The full requested outcome remains unfinished.

The verified foundation is committed as `effb9f1`; the joint replay preregistration is committed as `60124e5` and indexed with revision `390908a621847e64a3fae1f5fbe0689c27d9a7cb630b53ec18dd199547d9c404`. Fresh clean observer `bidirectional-observe-1788628609645` passed a four-poll, nine-route technical audit after SPCX's first prospective boundary. All nine TUI tabs were opened against that current disarmed checkpoint and exited normally. These are bounded startup/rendering checks; R1–R8 remain open at the full mandate scope. No live strategy/configuration/deployment was changed.

Provider-parity continuation: progress — the four current crypto providers produced a 71-day immutable decision panel with 20 eligible entries and 66 exit evaluations. All 364 sampled rolling comparisons matched. Forty focused/integration tests passed, and the extractor has 100% statement coverage. ETH/HYPE native candle rows were bound exactly to their observed cache rows; selected native book files were verified separately. No joint returns or private fills are inferred. A deterministic current SNDK v3 reproduction found four repeated-onset discrepancies across two scenarios. The immediate next step is a durable prior-pressure corrective adapter using existing repaired index code, with frozen SNDK strategy/risk settings and restart/source-boundary validation. See shared-replay revision v2 and SNDK-onset-fidelity v1. This changes investigation priority on new defect evidence; the full goal remains active and unfinished.
