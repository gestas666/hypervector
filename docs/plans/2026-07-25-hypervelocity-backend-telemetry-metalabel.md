# Hypervelocity Backend Telemetry and Metalabel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Python shadow backend authoritative for Hypervelocity decisions and LightGBM annotations while the Rust TUI renders the backend ledger without creating local trades.

**Architecture:** Research commands continue to produce immutable strategy exports and versioned model candidates. `paper-run` owns signals, model inference, sizing, fills, positions, and the append-only shadow ledger. The TUI reads that ledger as telemetry, reports connection/error state, and never falls back to local execution or simulation.

**Tech Stack:** Python 3.13, pandas, LightGBM, pytest, Rust 2021, serde/serde_json, Ratatui, Cargo tests.

---

### Task 1: Add an explicit observation-only metalabel policy

**Files:**
- Modify: `src/hypervector/paper/conviction.py`
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/runner.py`
- Modify: `src/hypervector/cli.py`
- Test: `tests/test_paper_conviction.py`
- Test: `tests/test_paper_cli.py`

**Step 1: Write the failing provider test**

Add a test whose fake model returns `p=0.2`, fixed conviction is `0.5`, and policy is `observe`. Assert `metalabel_p == 0.2`, `conviction == 0.5`, `allow_entry is True`, and `source == "metalabel_observe"`.

**Step 2: Run the test to verify RED**

Run: `uv run pytest tests/test_paper_conviction.py -q`

Expected: failure because observation-only behavior is not implemented.

**Step 3: Implement the minimal policy**

Represent policy with the validated strings `off`, `observe`, `scale`, and `filter`. In `observe`, calculate and ledger the probability but preserve fixed conviction and entry eligibility. Prediction failure must preserve fixed conviction and report `fallback_fixed`; it must not create a success-shaped probability.

Keep `--metalabel` and `--metalabel-filter` backward compatible, and add `--metalabel-mode`. Reject contradictory combinations with an actionable error. Default remains `off`.

**Step 4: Add CLI wiring tests and run GREEN**

Run: `uv run pytest tests/test_paper_conviction.py tests/test_paper_cli.py -q`

Expected: all selected tests pass.

### Task 2: Stamp authoritative backend identity and effective policy

**Files:**
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_paper_session.py`

**Step 1: Write a failing session-identity test**

Assert the `session_start` ledger record includes `strategy_name`, `export_id`, `execution_mode`, `metalabel_mode`, model bundle ID when loadable, and the effective fixed conviction. Secret values must never be present.

**Step 2: Run RED**

Run: `uv run pytest tests/test_paper_session.py -q`

Expected: failure on missing effective-policy fields.

**Step 3: Implement and run GREEN**

Emit the immutable session identity once per run and include the same run ID on subsequent decisions. Do not alter live arming or paper no-submit behavior.

Run: `uv run pytest tests/test_paper_session.py tests/test_paper_acceptance_matrix.py -q`

Expected: all selected tests pass.

### Task 3: Parse backend shadow telemetry in Rust

**Files:**
- Create: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/src/lib.rs`
- Modify: `crates/hypervector-tui/src/model.rs`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`

**Step 1: Write failing parser tests**

Cover:
- pairing `enter_long`/`close` rows into one displayed trade;
- reconstructing the latest open position;
- computing equity, realized/unrealized PnL, wins, losses, and drawdown from ledger truth;
- retaining `metalabel_p`, source, bundle ID, strategy, run ID, and execution mode;
- isolating the latest run instead of mixing historical runs;
- returning an explicit disconnected/error state for missing or malformed ledgers.

**Step 2: Run RED**

Run: `cargo test -p hypervector-tui --test backend_telemetry_test`

Expected: compile failure because the module does not exist.

**Step 3: Implement the parser and source**

Use typed serde structures with optional fields for backward-compatible ledger rows. A file source checks metadata and reparses only when the file changes. Malformed nonblank JSON is an error; it is not silently skipped. Never write to the ledger.

**Step 4: Run GREEN**

Run: `cargo test -p hypervector-tui --test backend_telemetry_test`

Expected: all parser tests pass.

### Task 4: Replace TUI-local paper simulation with backend telemetry

**Files:**
- Modify: `crates/hypervector-tui/src/main.rs`
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `crates/hypervector-tui/src/hypervelocity.rs`
- Modify: `crates/hypervector-tui/src/ui/mod.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

**Step 1: Replace simulator expectations with failing read-only expectations**

Assert that snapshot playback alone never creates paper trades. Applying a backend telemetry snapshot must populate the journal, position, statistics, and model annotation exactly. Configuration keys must not mutate backend-derived outcomes.

**Step 2: Run RED**

Run: `cargo test -p hypervector-tui --test regime_cockpit_test`

Expected: old local simulation tests fail the new requirements.

**Step 3: Implement minimal consumption**

Remove calls that rebuild paper trades from regime snapshots. Refresh the ledger source from the event loop and apply its typed snapshot to `App`. Show `CONNECTED`, `STALE`, `DISCONNECTED`, or `ERROR`, plus run ID, strategy, metalabel mode, probability, and source. On loss of telemetry retain the last confirmed snapshot as stale; never generate replacement trades.

Make the configuration screen explicitly read-only until a separate acknowledged backend command protocol exists.

**Step 4: Run GREEN**

Run: `cargo test -p hypervector-tui`

Expected: all Rust tests pass.

### Task 5: Produce a versioned Hypervelocity candidate without promotion

**Files:**
- Create runtime artifact only: `data/models/metalabel/candidates/hypervelocity-long-<timestamp>/`
- Do not overwrite: `data/models/metalabel/metalabel_lgbm.txt`

**Step 1: Create a strict Hypervelocity-long export**

Use cached 180-day BTC 1-minute data and the backend-compatible long strategy. Validate the export strictly before training.

**Step 2: Train and evaluate**

Run `metalabel-train` without `--install`. Record sample count, temporal folds, OOS log loss, baseline log loss, AUC, Brier score, class balance, and feature importance.

**Step 3: Apply the promotion rule**

Do not promote unless chronological OOS log loss beats its baseline and the feature/label audit passes. A failed candidate remains inspectable and has no runtime effect.

### Task 6: Verify safety, parity, and rollback

**Files:**
- Modify if needed: `docs/guides/acceptance-visual-and-holistic.md`
- Update: `HANDOFF.md`

**Step 1: Run full offline verification**

Run:

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run python -m hypervector status
uv run python -m hypervector paper-check
```

Expected: zero test failures; paper/shadow still reports no-submit; live remains unarmed.

**Step 2: Run ledger-to-TUI parity acceptance**

Start a bounded offline shadow run, load its ledger in the TUI telemetry parser, and assert identical trade count, latest position quantity, equity, realized PnL, model probability, run ID, and strategy ID.

**Step 3: Verify rollback**

Starting the backend with metalabel mode `off` must reproduce fixed-conviction behavior. Selecting the previous immutable export/model references must require no TUI change.

**Step 4: Report evidence and residual uncertainty**

Report observed commands and outputs. Do not describe a model as useful merely because training completed.
