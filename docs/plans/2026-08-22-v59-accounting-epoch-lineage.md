# V59 Accounting Epoch Lineage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve the existing `$5k` accounting start across the V58-to-V59 profile transition while keeping V59 live startup fail-closed on an exact, immutable accounting bundle.

**Architecture:** Extend `CohortAccountingEpoch` with an optional ordered set of included profile fingerprints while retaining the existing single-profile JSON shape for old bundles. Add an immutable continuation publisher that validates the stopped V58 boundary, the exact V59 successor, the parent V58 epoch, and all preserved evidence before emitting a V59-bound bundle. Propagate the lineage through the isolated research worker, checkpoint cache, post-start acceptance, and Rust TUI projection.

**Tech Stack:** Python 3.13 dataclasses and argparse, immutable JSON evidence bundles, DuckDB reporting projection, pytest, Rust/Serde TUI models, Cargo tests.

---

### Task 1: Specify the multi-profile epoch model

**Files:**
- Modify: `tests/test_cohort_accounting_epoch_archive.py`
- Modify: `src/hypervector/research/cohort_live_portfolio_archive.py`

**Step 1: Write the failing tests**

Add tests proving that an epoch with current fingerprint `V59` and included fingerprints `(V58, V59)` selects both profiles after the original start timestamp, serializes the ordered lineage, rejects duplicates, rejects malformed fingerprints, and requires the current fingerprint to be included.

**Step 2: Run the focused tests and verify RED**

Run: `uv run pytest -q tests/test_cohort_accounting_epoch_archive.py`

Expected: failure because `CohortAccountingEpoch` does not accept or apply an included-profile lineage.

**Step 3: Implement the minimal epoch extension**

Add an optional typed `included_profile_fingerprints: tuple[str, ...]` field. Preserve the legacy three-field `to_dict()` output when the tuple is empty. Filter archive rows against the exact effective fingerprint tuple rather than one fingerprint.

**Step 4: Run the focused tests and verify GREEN**

Run: `uv run pytest -q tests/test_cohort_accounting_epoch_archive.py`

Expected: all tests pass.

### Task 2: Propagate the lineage through the isolated research worker

**Files:**
- Modify: `tests/test_cohort_accounting_epoch_checkpoint.py`
- Modify: `tests/test_multi_asset_bidirectional_research_import_script.py`
- Modify: `src/hypervector/research/cohort_checkpoint_accounting.py`
- Modify: `scripts/multi_asset_bidirectional_research_import.py`

**Step 1: Write the failing serialization and parsing tests**

Require one repeated `--accounting-epoch-included-profile-fingerprint` argument per lineage member and exact reconstruction by the isolated worker. Retain compatibility with the legacy single-profile argument set.

**Step 2: Run the tests and verify RED**

Run: `uv run pytest -q tests/test_cohort_accounting_epoch_checkpoint.py tests/test_multi_asset_bidirectional_research_import_script.py`

Expected: failure because the new argument is not defined or forwarded.

**Step 3: Implement minimal CLI propagation**

Add the repeatable argument, construct the typed tuple, and emit it only for lineage epochs.

**Step 4: Run the tests and verify GREEN**

Run the same command and require all tests to pass.

### Task 3: Publish and load an immutable V58-to-V59 continuation bundle

**Files:**
- Create: `src/hypervector/live/cohort_accounting_continuation.py`
- Create: `tests/test_cohort_accounting_continuation.py`
- Modify: `src/hypervector/live/cohort_accounting_rollover.py`
- Modify: `scripts/cohort_accounting_rollover.py`
- Modify: `tests/test_cohort_accounting_rollover_script.py`

**Step 1: Write failing bundle tests**

Require the continuation builder to preserve the parent start timestamp, include exactly the parent scope plus V59, bind the current fingerprint to V59, preserve final checkpoint/preflight/prestart evidence, and reject an open lifecycle, non-flat venue state, identity mismatch, changed parent manifest, duplicate lineage, or non-adjacent parent successor.

**Step 2: Run the tests and verify RED**

Run: `uv run pytest -q tests/test_cohort_accounting_continuation.py tests/test_cohort_accounting_rollover_script.py`

Expected: failure because the continuation module and parent-epoch publisher input do not exist.

**Step 3: Implement the report-only publisher and loader**

Reuse the existing public rollover boundary validator, then replace only the new epoch boundary with the verified parent start and exact two-profile lineage. Extend the existing publisher with one optional exact parent-epoch bundle rather than duplicating its locks and immutable publication logic. Preserve dry-run by default and require `--yes` for the immutable directory. Extend the runtime loader to validate continuation evidence before returning the epoch.

**Step 4: Run the tests and verify GREEN**

Run the same command and require all tests to pass.

### Task 4: Make V59 require its exact accounting bundle

**Files:**
- Modify: `tests/test_cohort_accounting_epoch_live_boundary.py`
- Modify: `src/hypervector/live/cohort_accounting_rollover.py`

**Step 1: Write the failing V59 boundary test**

Load the exact candidate config and assert that live construction without a bundle raises an actionable error.

**Step 2: Verify RED**

Run: `uv run pytest -q tests/test_cohort_accounting_epoch_live_boundary.py`

Expected: V59 currently accepts a missing bundle.

**Step 3: Add the exact V59 fingerprint to the mandatory set**

Do not generalize to unrelated profiles.

**Step 4: Verify GREEN**

Run the same test file and require all tests to pass.

### Task 5: Bind V59 post-start acceptance to the lineage

**Files:**
- Modify: `tests/test_v59_poststart_acceptance.py`
- Modify: `src/hypervector/research/v59_poststart_acceptance.py`

**Step 1: Write failing acceptance tests**

Require checkpoint accounting evidence to identify V59 as current, retain the original V58 `$5k` start timestamp, and include exactly V58 plus V59. Reject a missing epoch, fresh reset, unrelated profile, reordered duplicate, or omitted V58 scope.

**Step 2: Verify RED**

Run: `uv run pytest -q tests/test_v59_poststart_acceptance.py`

Expected: failure because V59 acceptance does not inspect the accounting lineage.

**Step 3: Implement the minimal acceptance check**

Add a report-only verdict component without changing routing, sizing, exits, or execution.

**Step 4: Verify GREEN**

Run the same test file and require all tests to pass.

### Task 6: Validate the TUI projection

**Files:**
- Modify: `crates/hypervector-tui/src/backend_cohort_portfolio_archive.rs`
- Modify: `crates/hypervector-tui/tests/cohort_all_time_selection_test.rs`
- Modify: `crates/hypervector-tui/tests/support/cohort_checkpoint_portfolio.rs`

**Step 1: Write the failing Rust tests**

Require a valid lineage to parse and remain attached to the portfolio archive. Reject duplicate, malformed, or current-profile-omitting lineages while continuing to accept legacy epochs.

**Step 2: Verify RED**

Run: `cargo test -p hypervector-tui accounting_epoch`

Expected: failure because the Rust epoch model has no lineage field or validation.

**Step 3: Implement the Serde-compatible optional lineage**

Use a default empty vector for old checkpoints and validate the exact non-empty lineage contract.

**Step 4: Verify GREEN**

Run the same command and require all tests to pass.

### Task 7: Verify the complete cutover implementation

**Files:**
- Verify all modified Python, scripts, tests, Rust TUI, and V59 candidate files.

**Step 1: Run focused verification**

Run all accounting, V59, live-start, checkpoint-worker, and TUI lineage tests plus targeted Ruff checks and `git diff --check`.

**Step 2: Run complete non-network verification**

Run:

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run ruff check src scripts tests
uv run python -m hypervector status
```

Expected: zero failures, live remains fail-closed, secrets remain unprinted, and V58 keeps running unchanged until its drain completes.

**Step 3: Execute the stopped-boundary bundle flow only after drain completion**

Archive the completed drain, generate a fresh V59 preflight and prestart backup, dry-run and publish the exact continuation bundle, start V59 with that bundle and both live-risk flags, start one V59 checkpoint writer, and require the immutable V59 post-start acceptance report to pass.

No commit or push is authorized by this plan; preserve the dirty worktree and request separate authority before repository publication.
