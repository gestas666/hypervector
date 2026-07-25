# Shadow/Real Log Reconciliation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collect clean Hyperliquid shadow observations and compare their entries, regimes, maker timing, and exits with a real-strategy log from the same UTC window.

**Architecture:** The live daemon will seed indicators from historical bars without simulating historical orders, then emit report-only regime observations during the live phase. A research comparator will select explicit backend run IDs, restrict both sources to their overlapping UTC window, match same-side entries one-to-one within a configurable tolerance, and report every match and mismatch without gating execution.

**Tech Stack:** Python 3.13, pandas, JSONL ledgers, argparse CLI, pytest, Ruff.

---

### Task 1: Make daemon warm-up observation-only

**Files:**
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/runner.py`
- Test: `tests/test_paper_cli.py`

**Step 1: Write the failing test**

Add a daemon test whose historical warm-up contains Hypervelocity entry/target signals and assert that only post-warm live bars can create order events.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_cli.py::test_hypervelocity_daemon_warmup_seeds_without_historical_orders -q`

Expected: FAIL because the current runner processes warm-up through normal execution.

**Step 3: Write minimal implementation**

Add `PaperSession.warm_up()` to validate and retain the bounded indicator buffer and last timestamp without calling `_process_intent()`. Use it only in `start_paper_daemon()`; keep offline paper replay behavior unchanged.

**Step 4: Run test to verify it passes**

Run the test from Step 2 and expect PASS.

### Task 2: Record causal live regime observations

**Files:**
- Modify: `src/hypervector/strategies/hypervelocity.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_hypervelocity.py`
- Test: `tests/test_paper_session.py`

**Step 1: Write failing tests**

Specify a typed latest-regime observation containing primary regime, breakout direction, requested direction, and entry eligibility. Assert live Hypervelocity bars append `regime_observation` rows with the run ID and no submit attempt.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hypervelocity.py tests/test_paper_session.py -q`

Expected: FAIL because no public observation API or ledger event exists.

**Step 3: Write minimal implementation**

Add the observation API, enable it only after daemon warm-up, and append report-only decision rows before processing live intent. Do not change entry eligibility or sizing.

**Step 4: Run tests to verify they pass**

Run the tests from Step 2 and expect PASS.

### Task 3: Compare shadow and real-strategy logs

**Files:**
- Create: `src/hypervector/research/shadow_compare.py`
- Create: `tests/test_shadow_compare.py`
- Modify: `src/hypervector/cli.py`
- Modify: `tests/test_cli_help.py`

**Step 1: Write failing domain tests**

Cover exact matches, same-side timing matches, direction mismatches, unmatched shadow entries, unmatched real entries, no-overlap errors, and selection by explicit run ID.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_shadow_compare.py -q`

Expected: FAIL because the comparison module does not exist.

**Step 3: Write minimal implementation**

Parse JSONL and CSV inputs, validate required columns, normalize UTC timestamps and sides, compute the overlap window, greedily match nearest same-side entries without reuse, and return report-only metrics plus detailed discrepancy records.

**Step 4: Add CLI test and implementation**

Add `hypervelocity-shadow-compare --shadow-ledger --positions --run-id --entry-tolerance-seconds --out`. The command prints/writes JSON and never changes execution state.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_shadow_compare.py tests/test_cli_help.py -q`

Expected: PASS.

### Task 4: Collect and validate the first fresh window

**Files:**
- Create at runtime: `data/cache/book/BTC_l2_<UTC date>.jsonl`
- Create at runtime: `data/paper/decisions/decisions.jsonl`
- Create after real log arrives: `data/logs/research/hypervelocity_shadow_compare_<UTC timestamp>.json`

**Step 1: Verify safety identity**

Run: `uv run python -m hypervector paper-check`

Expected: `mode=shadow`, `network=mainnet`, `no_submit=true`.

**Step 2: Run bounded collection**

Record Hyperliquid BTC L2 and run bounded long/short shadow daemons with `--metalabel-mode observe`. Preserve each returned run ID.

**Step 3: Reconcile when the same-window real log is available**

Run the comparison command once per run ID. Report timing distributions, direction agreement, false RANGE states at real entries, unmatched entries, target timing, and fill-price differences. Do not convert any metric into an execution gate.

### Task 5: Verify, document, and publish

**Files:**
- Modify: `HANDOFF.md`

**Step 1: Run focused verification**

Run: `uv run pytest tests/test_hypervelocity.py tests/test_paper_session.py tests/test_paper_cli.py tests/test_shadow_compare.py tests/test_cli_help.py -q`

Run: `uv run ruff check <changed Python files>`

Run: `cargo test -p hypervector-tui --test backend_telemetry_test`

**Step 2: Record evidence and limitations**

Document run IDs, exact UTC observation window, venue provenance, comparison availability, tests, risks, and falsifiers in `HANDOFF.md`.

**Step 3: Commit and push**

Commit the implementation intentionally, push it, and verify local `HEAD` equals `origin/main` with a clean worktree.
