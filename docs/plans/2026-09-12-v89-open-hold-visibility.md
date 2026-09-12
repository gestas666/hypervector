# Open hold visibility implementation plan

> Apply the writing-plans, executing-plans, systematic-debugging, test-driven-development and verification-before-completion workflows locally in this isolated worktree.

**Goal:** Show bound position timer clocks, stale evidence and absent local exit management accurately in the existing nine-screen TUI, without execution authority.

**Architecture:** Reuse Python's existing open-reflection observation clock and persisted timer origin. Preserve and validate them in the Rust projection. Derive informational wall-clock notices that distinguish observed expiry from conditional expiry if a stale position remains open. Add one compact shared-header warning and label static timer values as snapshot values; preserve existing panels and operator controls.

**Tech stack:** Existing Python source-backed JSON, Rust/Serde/Chrono/Ratatui, pytest, Cargo tests and native terminal playback.

## Evidence and assumptions

The prior turn is progress: source commit e8464c4 and publication f30986b independently reconcile all 32 unchanged SNDK intents, 12 cases and 30 reproduced files. Central revision 2313f72ad39f094c7429cb05c687e06c25a4e50a4fdac1dafa8eea3b136f28f3 binds 3,620 references.

The September 12 19:05 UTC unsigned account still has the original −0.306 SNDK short and full-size stop. Its protected ledger ended September 11 15:37 UTC, operator_stop, with no recorded last fault. The 24-hour persisted decision-clock hold had passed. No local execution runner was identified at 19:16 UTC. These observations do not identify who stopped it or establish current account state or an active-runner timer bug.

Root cause of the display gap: `cohort_open_trade_reflections.py` emits `as_of_timestamp_ms`; `cohort_open_exit_plan.py` emits `opened_at_ms` and `timer_origin`. Rust's raw models discard these fields. `cohort_regime_open.rs` displays frozen `remaining_time_ms` as LEFT without its observation clock. Existing backend heartbeat and STOPPED labels work and must be reused.

No account request, signer, order submission, live runtime restart, parameter change or performance gate belongs in this fix. An old open reflection cannot prove a current open position or currently live stop. Missing clock/policy evidence remains explicit, not fabricated fresh evidence. The existing 60-second heartbeat inactivity threshold is reused only as a display-age threshold. TUI authority checks remain unchanged.

## Task 1: Preserve and validate backend timer clocks

Files: `backend_cohort_exit_plan.rs`, new `backend_cohort_exit_plan_clocks.rs`, `backend_cohort_trade_reflections.rs`, `backend_cohort_trade_reflections_projection.rs`, focused checkpoint tests under `crates/hypervector-tui/tests/support/`.

1. Add failing parsing tests to an existing source-backed open-reflection fixture: retain section as-of, runtime opened clock and labeled legacy fill fallback; reject unsupported policy/origin, mismatched deadlines/remaining, overflow and partial origin fields. Retain explicit absent evidence for older documents.
2. Run `cargo test -p hypervector-tui --release --test cohort_checkpoint_test open_hold_clock` and inspect expected failures.
3. Add optional provenance fields to the projected timer, bind the enclosing observation clock, and validate arithmetic using checked operations. Preserve the two supported policies exactly; hard/soft deadlines must agree with supplied timer origin and durations. Move a small projection helper if needed to retain 500-line files and 50-line functions.
4. Repeat focused tests and relevant existing timer/checkpoint tests. Commit after passing evidence.

## Task 2: Informational overdue/stale diagnostics and shared display

Files: new `cohort_open_hold.rs`, `cohort_view.rs`, `cohort_regime_open.rs`, `backend_source.rs`, `lib.rs`, new tests and support fixtures.

1. Add failing deterministic-clock tests for fixed before/due/overdue, stopped exposure, fresh versus stale observation, future/missing clock, legacy origin, supported extension before soft/between soft-hard/after hard, and conflicting/missing position evidence. No false current expiry or extension grant from stale regime support.
2. Implement a pure diagnostic using existing bound clocks, backend status and observed assets. Reuse the existing freshness constant. Current wall-clock expiry of stale exposure is explicitly conditional: IF STILL OPEN. Distinguish stopped local exits from unknown heartbeat health. Do not claim a fresh stop from an old stop ID.
3. Add a compact shared warning before screen content when exposure evidence needs attention, including last open symbol/count, evidence age and timer state. Label remaining time in the open-regime panel as snapshot evidence and expose timer origin. Keep nine screens, all existing controls and no request/strategy changes.
4. Add rendering assertions at 100x28, 120x36 and 190x52 for all nine views; verify warnings fit, stopped authority remains correct, flat/missing/conflicting states are explicit and account/stop values are not synthesized.
5. Run focused and affected Rust tests, lint, formatting, then full required checks appropriate to this Rust-only change. Reuse unchanged Python contract tests and an actual saved open-reflection/ledger pair for source parity.

## Task 3: Source-bound acceptance and publication

1. Build the separate candidate binary. Generate immutable replay inputs from the authenticated stopped snapshot using actual backend projections; retain source clock/quantity/order/deadline comparisons, including the 22.977-second decision/fill offset.
2. Exercise the candidate in a pseudo-terminal with harmless monitor/file playback only. Capture rendered cells at the three acceptance sizes; do not retry denied Terminal.app automation. Distinguish native PTY evidence from a human Terminal inspection.
3. Archive source, tests and binary with hashes and reproduce focused tests/fixtures. Record discrepancies and repairs. ROOT HEAD, existing dirty work, configuration, runtime ledger and 102 protected hashes remain unchanged during development.
4. Publish an approval-ready review and central research revision with exact validation scope and rollback. A deployed runtime/configuration change requires the active mandate's explicit human approval; no live execution action is part of this change.

## Trade-offs, validation standard and falsifier

Doing nothing leaves the user to reconcile frozen countdowns against a stopped runner. Recomputing an unconditional live countdown from old data would misrepresent position/extension state. The chosen diagnostic keeps the bound clock and evidence age together, uses conditional elapsed deadlines, and costs one warning row only when needed. It is good enough when source-backed and synthetic fixed/extended/stale/conflicting cases parse and render correctly without lost required controls or execution-side changes.

Failure means a forged fresh clock, malformed timer accepted as authoritative, stale position labeled current, stale support granting extension, wrong expired arithmetic, or clipped critical warning at supported sizes. Code/tests and measured acceptance can falsify those claims; actual future trade outcomes are unrelated to this informational improvement. Any rollback is replacement by the preserved prior binary/source; journal corrections append superseding evidence rather than deleting records. Prospective September 22/23 outcome seals stay unopened.

## Validation-driven layout correction

The initial shared-header row passed the new warning tests but failed 21 existing compact rendering checks because it reduced body height. Preserve the original four-row header and body geometry, and place the same warning in the footer's previously unused bottom border. Existing controls and research-sync title remain present. This replaces the planned header insertion based on observed clipping, not a weaker acceptance standard.
