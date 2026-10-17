# Unified CLI and repository cleanup implementation plan

**Goal:** Retain VectorBT, NautilusTrader, paper/shadow, Karpathy autotuning,
Hyperliquid and 0xArchive through one installable CLI; remove terminal rendering
and fix the measured recovery-memory and startup issues.

**Architecture:** Focused argparse command groups share the existing tested
services. Legacy non-visual commands remain aliases. Command registration and
dispatch load engines only when used. Installed commands use packaged Python
entry points rather than repository-relative scripts. Live authorization,
profile identity, accounting epochs and STOP boundaries remain explicit.

**Tech stack:** Python 3.13, argparse, pytest, VectorBT, NautilusTrader, DuckDB,
Hyperliquid SDK, Parquet. No replacement GUI or Rust workspace is required.

## Constraints and acceptance

- Implement in `codex/unified-cli-cleanup`, an isolated checkout and venv.
  Preserve all pre-existing changes in the original checkout. Do not merge
  execution changes into that checkout or restart/arm any backend.
- Preserve frozen evidence and historical approvals byte-for-byte. Missing
  local historical artifacts require explicit integration-test selection and
  actionable diagnostics; do not manufacture evidence or re-sign approvals.
- Unit tests use temporary data and mocks, with network access forbidden.
- CLI help must cover every retained workflow; inventory must match parsers.
  Help/status must neither instantiate execution clients nor create data roots.
- Recovery memory must be bounded by one ledger row, independent of ledger
  size; validate malformed/truncated/incomplete rows and incremental offsets.
- Build/install a wheel outside the source tree and exercise retained command
  help and fail-closed boundaries. Measure startup and recovery before/after.

## Sequence

1. Add failing regression tests for grouped CLI discovery, lazy imports,
   installed cohort commands, status isolation and streaming ledger recovery.
2. Split CLI registration/handlers into focused modules; introduce data,
   archive, research, nautilus, paper, live, cohort, regime and model groups.
   Preserve compatible flat commands with one authoritative inventory.
3. Package operational entry points and replace native replay's script import.
   Retain headless observe/checkpoint/audit and manual operator requests with
   strict run/profile binding. Extract shared lifecycle/accounting utilities
   before retiring TUI launchers and Rust crates.
4. Stream candidate-entry recovery; enforce explicit model-root scoping and
   explicit optional-sampler requirements. Default autotuning to Karpathy.
5. Remove unused Backtrader and broad VectorBT integrations from required
   dependencies while retaining TA-Lib as required; declare directly imported runtime dependencies and optional
   research integrations. Refresh the lock and verify installation.
6. Repair test data isolation and offline execution. Separate historical
   evidence, native replay performance, and Ray integration checks from unit
   tests with documented opt-in markers and prerequisites. Retain negative
   tests for genuine runtime errors and approvals.
7. Consolidate current operator documentation/skills; retain historical
   journals and shelved D1 research. Add reproducible verification/profiling
   commands and a disposition record for every audit finding.
8. Run focused regressions, offline unit suite, install smoke checks, lint,
   coverage of changed critical logic and performance measurements. Record
   actual results and remaining externally gated validation explicitly.

## Rollback and falsifiers

Git history retains removed tracked files; the original checkout is untouched.
Revert this isolated branch to roll back. A failed existing safety test,
changed replay output, missing retained command, cross-root model selection,
unbounded recovery read, real network in unit tests or missing wheel entry
point falsifies the corresponding acceptance claim and requires repair.

## Implementation record

The workflow, pruning, packaging and bounded-memory changes are implemented in
this isolated branch. See `docs/reviews/2026-10-17-unified-cli-cleanup.md` for
observed validation and the decisions retained as legacy/evidence debt. The
full artifact-dependent test list is in
`docs/reviews/2026-10-17-test-disposition.md`. Do not treat software validation
as approval to merge or relaunch an armed checkout.
