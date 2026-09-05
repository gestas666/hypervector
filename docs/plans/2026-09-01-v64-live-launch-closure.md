# V64 Live Launch Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion task-by-task.

**Goal:** Start the exact V64 cohort successfully, without restarting V63 or weakening the transition, retired-asset, live-authority, or TUI contracts.

**Architecture:** Recover the already-stopped V63 transition evidence by validating its final existing cohort snapshot while holding the shared live-account lock, then publish the same strict immutable legacy-flat archive accepted by startup. Extend changed-profile startup to reconcile every retired symbol through an Info-only reader after the authenticated candidate adapters are constructed and before any engine or runner exists. Start the required report-only HIP-3 observer supervisor, regenerate the V64 mainnet preflight, launch the unified live TUI, and validate the exact runtime/checkpoint/screens.

**Tech Stack:** Python 3.13, pytest, Hyperliquid Info SDK, append-only JSONL ledgers, file locks, Rust/Ratatui, Cargo.

---

### Task 1: Recover final V63 transition evidence without restarting it

**Files:**
- Modify: `tests/test_cohort_legacy_flat_stop.py`
- Modify: `tests/test_cohort_legacy_flat_stop_script.py`
- Modify: `src/hypervector/live/cohort_legacy_flat_stop.py`
- Modify: `scripts/cohort_legacy_flat_stop.py`

1. Write tests requiring an offline archive mode to select the latest exact armed run, validate its final cohort snapshot, reject a different latest run, reject non-flat evidence, and publish exclusively.
2. Run the focused tests and confirm they fail because offline archival is absent.
3. Implement a stable streaming scan of the existing ledger and an `--archive-existing-final-snapshot` output option guarded by `bidirectional_live_runtime_lock`.
4. Run focused tests and confirm the strict legacy watcher behavior remains unchanged.

### Task 2: Reconcile retired GOLD during changed-profile startup

**Files:**
- Create: `tests/test_cohort_profile_transition_venue.py`
- Create: `src/hypervector/live/multi_asset_read_only_factory.py`
- Create: `src/hypervector/live/cohort_profile_transition_venue.py`
- Modify: `src/hypervector/live/cohort_profile_change_approval.py`
- Modify: `scripts/multi_asset_bidirectional_preflight.py`
- Modify: `scripts/multi_asset_bidirectional_live.py`

1. Write tests proving retained and retired symbols are both reconciled, retired open exposure/orders fail, and retired readers are Info-only.
2. Run the tests and confirm failure because startup currently iterates only candidate symbols.
3. Extract the existing multi-symbol Info-only reader construction from the preflight script.
4. Expose the exact prior config already authenticated by the pre-start backup.
5. Replace the candidate-only startup check with one boundary that checks candidate adapters and read-only retired readers before engine construction.
6. Run focused live-start, approval, preflight, and factory tests.

### Task 3: Produce fresh transition evidence and archive V63

**Files:**
- Create: `data/backups/bidirectional_cohort/legacy_STOP_v63_bidirectional-live-1788233180107.json`
- Create: a timestamped V64 preflight below `data/logs/research/bidirectional_cohort/`
- Modify: `skills/hypervector-cli/SKILL.md`

1. Start the report-only SP500/SPCX observer supervisor and wait on its validated readiness condition.
2. Run the exact V64 preflight against V63 and require eight retained assets plus retired GOLD all flat, order-free, ledger-reconciled, and technically ready.
3. Run offline V63 archival under the shared account lock and independently reload/verify the immutable archive.
4. Document the exact V64 transition and launch sequence in the CLI runbook.

### Task 4: Full regression and TUI acceptance

**Files:**
- Modify as required by failing acceptance tests only.

1. Run the full non-network Python suite.
2. Run Rust formatting, production Clippy, complete TUI tests, and the exact V64 nine-screen artifact test.
3. Render/inspect all nine screens at 120x36, 160x50, and 190x52.
4. Run `git diff --check` and verify no unrelated user changes were reverted.

### Task 5: Authorized live start and post-start acceptance

**Files:**
- Runtime artifacts only; no secret values are printed or persisted.

1. Dry-resolve the exact V64 unified launcher with credential-presence booleans only.
2. Start `cohort-tui --mode live` with the exact V64 config and both explicit live-risk flags.
3. Wait for the new armed V64 configuration identity, verified pre-start backup, fresh checkpoint, and running-consistent lifecycle.
4. Verify the runtime has eight assets, 23 executable direction scopes, no GOLD route, no startup faults, and the retired-GOLD venue boundary passed.
5. Run the nine-screen TUI acceptance against the active V64 runtime and leave the authorized live owner plus required report-only observer supervisor running.

## Failure modes and rollback

- Any identity, archive, venue, ledger, approval, observer, credential, backup, or TUI mismatch aborts the launch.
- A retired GOLD position or order blocks V64 before engines exist.
- A concurrent account owner blocks offline archival and live startup.
- V63 remains the immutable rollback config, but it must not be restarted merely to manufacture a new flat snapshot.
- If V64 starts and faults, preserve its ledger, protection, STOP state, pre-start bundle, and exact error; do not force-kill an open lifecycle.
