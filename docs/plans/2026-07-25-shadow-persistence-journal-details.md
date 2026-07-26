# Persistent Shadow Journal and Telemetry Implementation Plan

**Goal:** Preserve the Hypervelocity shadow portfolio across normal process restarts and make its historical trades, fees, regimes, timestamps, and full five-level L2 view inspectable from the read-only TUI.

**Architecture:** The append-only paper ledger remains the source of truth. A backend-only resume reader restores the latest Hypervelocity shadow run that contains real fills; the same run ID continues until the explicit recoverable reset truncates the ledger. The Rust TUI projects the complete continued run, adds independent journal selection/detail state, and never changes strategy or execution policy.

**Tech Stack:** Python 3.13, pytest, Rust 2024, Ratatui 0.29, Cargo tests, JSONL backend telemetry.

---

### Task 1: Restore the backend shadow portfolio on restart

**Files:**
- Create: `src/hypervector/paper/resume.py`
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/fills.py`
- Test: `tests/test_paper_session.py`
- Test: `tests/test_paper_resume.py`

**Step 1: Write the failing test**

Create a Hypervelocity shadow session, record an entry and realized/funding state, construct a second session against the same data root, and assert that it reuses the portfolio run ID and restores quantity, average price, realized PnL, initial cash, and last-exit cooldown state. Add a flat-after-close case and a no-fills case.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_session.py -q -k resume`

Expected: FAIL because the second session creates a new run ID and a flat `PaperPosition`.

**Step 3: Write minimal implementation**

Add a strict JSONL resume reader filtered to shadow execution, Hypervelocity strategy, symbol, and timeframe. Select the most recent run containing a non-skipped filled entry; restore the last authoritative position/equity row from that run. Add an explicit `ExplicitFillEngine.restore_position` boundary with finite-value and position consistency validation. Stamp resumed position/equity into each new `session_start` row.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_paper_session.py -q -k resume`

Expected: PASS.

### Task 2: Preserve and enrich backend trade records

**Files:**
- Modify: `crates/hypervector-tui/src/model.rs`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`

**Step 1: Write the failing test**

Parse a continued run containing entry regime telemetry, entry fee, funding, exit regime telemetry, exit fee, and exit timestamp. Assert the trade record exposes entry/exit timestamps, 1m/5m/15m states at both boundaries, entry fee, exit fee, funding cashflow, and total costs. Assert two closed trades survive a later `session_start` in the same run.

**Step 2: Run test to verify it fails**

Run: `cargo test -p hypervector-tui --test backend_telemetry_test continued_shadow_run_preserves_trade_details -- --exact`

Expected: FAIL because `PaperTradeRecord` lacks the fields.

**Step 3: Write minimal implementation**

Track the most recent causal regime observation at entry and exit, accumulate funding while the trade is open, and retain both fill fees. Use the newest `session_start` for current configuration while preserving the run's complete trading history.

**Step 4: Run tests to verify they pass**

Run the focused test, then `cargo test -p hypervector-tui --test backend_telemetry_test`.

Expected: PASS.

### Task 3: Add journal selection and trade detail modal

**Files:**
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `crates/hypervector-tui/src/main.rs`
- Modify: `crates/hypervector-tui/src/ui/mod.rs`
- Test: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

**Step 1: Write the failing tests**

Assert Dashboard Up/Down changes a journal-specific selection, Enter opens a trade detail modal, and the rendered modal includes entry/exit Eastern timestamps, entry/exit 1m/5m/15m regimes, entry/exit fees, funding, total costs, gross PnL, and net PnL. Assert Screen 2 retains independent regime-event navigation.

**Step 2: Run tests to verify they fail**

Run: `cargo test -p hypervector-tui --test regime_cockpit_test journal -- --nocapture`

Expected: FAIL because Dashboard currently drives regime-event selection.

**Step 3: Write minimal implementation**

Add `selected_trade_index` and `show_trade_detail_modal`. Route Dashboard Up/Down/Enter to trades, Screen 2 to regime events, and Screen 3 to configuration. Highlight the selected journal row and render a read-only detail modal.

**Step 4: Run tests to verify they pass**

Run the focused tests and the complete TUI test target.

Expected: PASS.

### Task 4: Show the full backend ladder and correct regime labels

**Files:**
- Modify: `crates/hypervector-tui/src/ui/mod.rs`
- Modify: `crates/hypervector-tui/src/hypervelocity.rs`
- Test: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

**Step 1: Write the failing render test**

Render five asks and five bids at the normal 180x50 size. Assert every level is visible, `5m PRIMARY` is present, `15m CONTEXT` is present, and `15m LOCK` is absent.

**Step 2: Run test to verify it fails**

Run: `cargo test -p hypervector-tui --test regime_cockpit_test dashboard_shows_full_ladder_and_truthful_regime_roles -- --exact`

Expected: FAIL because the ten-line panel clips the ladder and labels 15m as a lock.

**Step 3: Write minimal implementation**

Increase the dashboard position/ladder row to fourteen lines and reduce only flexible space. Relabel 5m as the primary strategy regime and 15m as contextual telemetry everywhere; do not alter backend entry logic.

**Step 4: Run tests to verify they pass**

Run the focused render test and complete TUI tests.

Expected: PASS.

### Task 5: Verify, document, and publish

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `HANDOFF.md` only if the current phase-status section requires the new operator behavior.

**Step 1: Document lifecycle behavior**

State that normal quit preserves and resumes the shadow portfolio, while `hypervelocity-shadow-reset --yes` is the only portfolio reset path and creates a backup.

**Step 2: Run full verification**

Run:

```bash
uv run pytest tests/ -q -m "not network"
cargo fmt --check
cargo test -p hypervector-tui
cargo build -p hypervector-tui --bin tui-regime-detector
git diff --check
```

Expected: all commands exit zero.

**Step 3: Inspect the real ledger without mutation**

Confirm run `7a7700e26672` projects two closed trades and one open position after restart logic is applied. Do not truncate or rewrite `data/paper/decisions/decisions.jsonl`.

**Step 4: Commit and push**

Commit only the scoped implementation and tests, push `main`, and report that the currently running old process must be restarted to load the new behavior.
