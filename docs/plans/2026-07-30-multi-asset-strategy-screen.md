# Multi-Asset Strategy Screen Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce causally aligned ETH, SOL, and HYPE strategy-screen artifacts whose asset identity is explicit and whose results can feed a later one-portfolio comparison.

**Architecture:** Extend the existing single-asset screen with an explicit symbol input and immutable asset provenance while preserving its fixed candidate cohorts, $15,000 simulation, funding accounting, and report-only authority. Run each asset and chronological segment independently before any cross-asset allocator is introduced, so weak signals cannot be hidden by pooled results.

**Tech Stack:** Python 3.13, pandas, pytest, Hypervector shared-portfolio simulator, 0xArchive Hyperliquid candles, official Hyperliquid funding history.

---

### Task 1: Make asset identity explicit

**Files:**
- Modify: `tests/test_shared_strategy_screen_script.py`
- Modify: `scripts/shared_strategy_screen.py`

**Step 1: Write the failing test**

Add a test that parses `--symbol ETH`, invokes `run_screen` with a minimal causal fixture, and requires `symbol == "ETH"`, an ETH position contract, and matching data provenance.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shared_strategy_screen_script.py -q`

Expected: FAIL because the parser and report do not yet carry symbol identity.

**Step 3: Write minimal implementation**

Add a required/explicit symbol parameter with a BTC default for backward compatibility. Normalize it to uppercase, include it in the report and data evidence, and construct the portfolio contract from that symbol. Forward the parsed value from `main()`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shared_strategy_screen_script.py -q`

Expected: PASS.

**Step 5: Commit**

Do not commit from the current dirty shared worktree without a separate user request. Preserve the scoped diff for later intentional publication.

### Task 2: Run fixed chronological screens

**Files:**
- Create: `data/logs/research/multi_asset_screen_<asset>_<segment>_<timeframe>_v1.json`

**Step 1: Run development screens**

Run the fixed `legacy`, `source`, and relevant isolated cohorts over 2025-07-28 through 2026-01-28 at 5m, 15m, and 1h using each asset's immutable one-minute bars and complete funding series.

**Step 2: Run validation screens**

Repeat unchanged over 2026-01-28 through 2026-04-28.

**Step 3: Run pseudo-holdout screens**

Evaluate only predeclared candidates over 2026-04-28 through 2026-07-28. Do not tune after observing this segment.

**Step 4: Verify artifacts**

Check that every artifact has `mode=bar_screen_only_not_executable_evidence`, the expected symbol, full funding coverage, complete one-minute cadence, a SHA-256 for every input, and every trial retained.

### Task 3: Select L2 backfill candidates without hiding failures

**Files:**
- Create: `docs/reviews/2026-07-30-multi-asset-strategy-screen.md`

**Step 1: Build the cross-segment table**

Report trade count, wins/losses, net PnL, profit factor, drawdown, fees, funding, liquidations, and monthly dispersion for every asset/candidate/timeframe.

**Step 2: Apply the predeclared feasibility interpretation**

Identify candidates with positive net performance and profit factor above one in development and validation. Keep pseudo-holdout results separate and report all failures rather than aborting them.

**Step 3: Name L2 finalists**

Request expensive book/trade history only for asset-strategy pairs that remain economically plausible after the unfavorable chronological segment. This shortlist has no runtime or model authority.

**Step 4: Validate the active runtime remains untouched**

Confirm the BTC shadow process identity and zero live order authority after the research work.
