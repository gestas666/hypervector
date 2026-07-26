# Shadow Restart Fidelity Implementation Plan

**Goal:** Make Hypervelocity shadow restarts preserve the correct portfolio and pending-order lifecycle, reconcile missed venue bars and funding deterministically, and expose data-root-safe operator commands.

**Architecture:** The append-only backend ledger remains authoritative. Session identity gains a deterministic execution-spec fingerprint and resolved data root; resume validates the latest portfolio epoch before restoring it. Missed completed Hyperliquid bars are replayed only for an already-open target or already-pending maker entry—never to create new entries—and hourly funding uses public historical Hyperliquid rates. The TUI remains read-only and renders a complete reset command for the active backend root.

**Tech Stack:** Python 3.13, pandas, requests, pytest, Rust 2024, Ratatui, Cargo tests, JSONL telemetry.

---

### Task 1: Bind operator commands to the active data root

**Files:**
- Modify: `src/hypervector/paper/session.py`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/src/config_view.rs`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Test: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Add failing telemetry and rendering tests requiring the resolved backend data root and a full reset command containing that exact root.
2. Run the focused Rust tests and verify the expected missing-field/command failures.
3. Stamp `data_root` in `session_start`, project it through Rust telemetry, POSIX-quote it for display, and remove the rootless reset hint.
4. Re-run the focused tests to green.

### Task 2: Validate the persistent portfolio execution specification

**Files:**
- Modify: `src/hypervector/paper/resume.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_paper_resume.py`
- Test: `tests/test_paper_session.py`

1. Add failing tests for matching legacy session specifications, an incompatible open position, an incompatible flat portfolio, repeated restart timestamps, and inconsistent equity.
2. Verify each test fails for missing compatibility validation.
3. Canonically hash execution-affecting identity, strategy, risk, exit, order, and position-policy fields. Fail closed on an incompatible open position; retain a flat portfolio while explicitly stamping the profile change. Preserve the original market `state_asof` through repeated `session_start` rows and validate the equity identity within a numeric tolerance.
4. Run the focused Python tests to green.

### Task 3: Restore and reconcile pending maker entries

**Files:**
- Modify: `src/hypervector/paper/resume.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_paper_resume.py`
- Test: `tests/test_paper_session.py`

1. Add failing tests proving the latest unmatched `submit_entry` is restored with direction, quantity, limit, timestamp, TTL, and model annotations, while later cancel/fill events clear it.
2. Verify red failures.
3. Restore `PendingMakerEntry` into the backend. During missed-bar replay, apply the existing expiry, regime-change, and one-tick-through rules; never create a brand-new entry during downtime.
4. Re-run focused tests to green.

### Task 4: Reconcile open targets and historical funding across downtime

**Files:**
- Modify: `src/hypervector/data/hl.py`
- Modify: `src/hypervector/paper/fills.py`
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/runner.py`
- Test: `tests/test_fetchers.py`
- Test: `tests/test_paper_fills.py`
- Test: `tests/test_paper_session.py`
- Test: `tests/test_paper_cli.py`

1. Add failing parser/transport tests for Hyperliquid `fundingHistory` and failing session/runner tests for venue-only missed bars, hourly funding, target crossing, insufficient funding evidence, and no offline new entries.
2. Verify red failures independently.
3. Fetch public historical funding rates, normalize them to UTC settlement hours, and allow the fill engine to apply an explicit historical rate. Split warm history at the persisted market timestamp; seed older bars normally, replay later completed HL bars through the restricted reconciliation path, then continue live processing. Abort on non-HL replay bars or missing required funding evidence.
4. Re-run focused tests to green.

### Task 5: Document, verify, and publish

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `skills/hypervector-regime-detector/SKILL.md`
- Modify: `HANDOFF.md`

1. Document the canonical default `data` root, full same-root reset command, compatibility behavior, and restricted downtime replay semantics.
2. Run `uv run pytest tests/ -q -m "not network"`, targeted Ruff, `cargo fmt --check`, `cargo test -p hypervector-tui`, `cargo build -p hypervector-tui --bin tui-regime-detector`, and `git diff --check`.
3. Read-only validate the current ledger and configuration without starting the backend or appending records.
4. Review the final diff, commit the scoped files, push `main`, and confirm a clean synchronized worktree.
