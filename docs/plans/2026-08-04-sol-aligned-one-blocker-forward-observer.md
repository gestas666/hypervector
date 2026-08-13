# SOL Aligned One-Blocker Forward Observer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one execution-incapable, future-cutoff SOL observer that tests whether side-aligned order-book pressure identifies useful hourly-cross near misses on a currently flat portfolio symbol.

**Architecture:** Extend the immutable forward-experiment registry with one SOL, both-direction contract and reuse the existing causal routing-publication/BBO/funding/portfolio-compatibility pipeline. Admit the exact identity through the strict Rust checkpoint projection, render it as a distinct research line, and attach its atomic output as a supplemental matrix through a durable report-only launchd process. The armed backend, active configuration, positions, orders, and next-flat range-retirement candidate remain unchanged.

**Tech Stack:** Python 3.13, pytest, Rust/Serde/Ratatui, Cargo tests/Clippy, Hyperliquid immutable ledgers, DuckDB funding evidence, launchd.

---

## Frozen experiment contract

- Name: `v8-sol-aligned-range-fixed`
- Candidate: `sol_aligned_range_relaxed_fixed60_bidirectional_v1`
- Source: `range_onset_bidirectional_v1`
- Symbol: `SOL`
- Exact blocker: `awaiting_hourly_sma_cross`
- OPI cohort: side-adjusted `aligned` (`directional_opi > 0`)
- Cutoff: `2026-08-05T03:45:00Z` / `1785901500000` ms
- Horizon: fixed 60 minutes, non-overlapping accepted entries
- Stop proxy: adverse-side BBO crossing at 60 bps
- Size: `$75` hypothetical notional, matching the active SOL range-onset
  provider-symbol override, with full top-level capacity required
- Costs: observed `4.32 bps` taker fee per side plus official funding
- Direction: both long and short are eligible; results remain separated
- Authority: report-only, no order/sizing/exit/promotion/portfolio-PnL authority

Discovery evidence used a generic `$25` feasibility size and is N5, 4W/1L,
`+49.7410 bps`, PF `1.7646`, but every example is long and mean net is only
`+9.95 bps`. The forward observer deliberately raises the capacity requirement
to the actual `$75` source mapping; failure at that size is counterevidence, not
permission to fall back to `$25`. This is weak discovery evidence, not a live
strategy result. A first fresh resolved PF at or below one, tail slippage
consuming the modeled edge, no short examples, one path dominating absolute
return, or portfolio incompatibility weakens or falsifies the idea.

### Task 1: Freeze and validate the Python experiment identity

**Files:**
- Modify: `src/hypervector/research/cohort_forward_experiments.py`
- Modify: `tests/test_cohort_forward_one_blocker_script.py`

1. Add a failing test asserting the exact v8 identity, SOL symbol, both-side
   source contract, aligned OPI cohort, fixed cutoff, 60-bps proxy, and no target.
2. Run the focused test and confirm it fails because v8 is unknown.
3. Add the frozen registry row and make the registry explicitly bind the
   provider-symbol notional; do not add a runtime provider.
4. Run the focused Python tests and Ruff.

### Task 2: Admit the exact report-only identity in the TUI projection

**Files:**
- Modify: `crates/hypervector-tui/src/backend_cohort_candidate_portfolio.rs`
- Modify: `crates/hypervector-tui/src/backend_cohort_execution_opportunity_matrix.rs`
- Modify: `crates/hypervector-tui/src/cohort_research_opportunity_matrix.rs`
- Modify: `crates/hypervector-tui/src/cohort_research_opportunity_matrix_tests.rs`
- Modify: `crates/hypervector-tui/tests/cohort_execution_opportunity_matrix_checkpoint_test.rs`
- Modify: `crates/hypervector-tui/tests/support/cohort_execution_opportunity_matrix_checkpoint_fixtures.rs`

1. Add a failing checkpoint fixture for the exact SOL candidate/source/symbol.
2. Confirm the strict parser rejects it before the allowlist change.
3. Add the exact identity to both forward and portfolio validators.
4. Add the compact labels `FROZEN FWD SOL ALIGN60` and
   `FROZEN SOL ALIGNED-BOOK RANGE RELAXATION 60M`.
5. Assert the summary exposes all-path and deployable-only economics separately.
6. Run the focused Rust tests, Rustfmt, and strict Clippy.

### Task 3: Publish and attach the observer durably

**Files:**
- Create at runtime: `data/runtime/bidirectional_cohort/latest_sol_aligned_range_challenger.json`
- Update externally: launchd submitted jobs only

1. Run the observer once and validate schema, cutoff exclusion, funding bounds,
   both-side contract, `execution_authority=none`, and deployable summary.
2. Submit exactly one durable launchd observer using the frozen v8 command.
3. Replace only the report-only checkpoint publisher so it includes the SOL
   supplemental matrix; preserve its config and all existing supplemental paths.
4. Verify one writer per output, fresh atomic timestamps, and no backend PID change.

### Task 4: Journal and visually verify the operator projection

**Files:**
- Modify: `docs/reviews/2026-08-04-live-forward-portfolio-journal.md`
- Modify: `HANDOFF.md`

1. Record the discovery/forward boundary, fixed contract, limitations, and
   falsifiers before interpreting any post-cutoff outcome.
2. Build the optimized TUI and render Screen 6 at 190x52 against the live
   checkpoint.
3. Verify the SOL line says report-only, shows all/deployable scopes, and does
   not alter the trade journal or portfolio PnL.
4. Revalidate the backend as `running_consistent`, all open positions protected,
   zero asset faults, and unchanged execution PIDs.

### Task 5: Final verification

1. Run `uv run pytest` for forward experiment, script, checkpoint, and portfolio
   journal coverage.
2. Run `cargo test -p hypervector-tui`, strict Clippy, Rustfmt, and release build.
3. Run Ruff, whitespace checks, `git diff --check`, and file-size checks.
4. Preserve the dirty worktree and do not commit unrelated changes. Commit only
   if the user separately requests repository publication.
