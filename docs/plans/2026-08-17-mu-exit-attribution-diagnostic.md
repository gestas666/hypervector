# MU Exit Attribution Diagnostic Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a report-only measurement that attributes each resolved MU lifecycle exit against the first already-frozen 15/60/240-minute BBO horizon at or after that exit, without selecting or promoting an alternative exit.

**Architecture:** Add one typed research module that validates exact lifecycle/markout identity, joins nominal and stress lifecycles by `(decision_time_ms, side)`, and classifies only the first post-exit frozen horizon. Add a thin immutable command that hashes inputs and generator files before publication. The diagnostic remains authority-none, does not import live factories/configuration, and explicitly withholds any live recommendation because the sample is post-hoc and small.

**Tech Stack:** Python 3.13, typed mappings/dataclasses, pytest, Ruff, immutable JSON helpers from `hypervector.data.oxa_storage`.

---

### Task 1: Freeze the measurement contract

**Files:**
- Create: `tests/test_hip3_shadow_exit_attribution.py`
- Create: `src/hypervector/research/hip3_shadow_exit_attribution.py`

**Step 1: Write the failing identity and authority tests**

Create minimal lifecycle and markout fixtures. Require exact symbol/provider/profile identity, `execution_authority="none"`, report-only markouts, identical nominal/stress lifecycle keys, and unique horizon-path keys.

**Step 2: Run the tests and verify RED**

Run: `uv run pytest -q tests/test_hip3_shadow_exit_attribution.py`

Expected: collection fails because `hypervector.research.hip3_shadow_exit_attribution` does not exist.

**Step 3: Implement the minimal validator and join**

Expose a typed public `build_hip3_shadow_exit_attribution(lifecycle_report, markout_report)` function. Reject missing, duplicate, or contradictory evidence rather than defaulting values.

**Step 4: Run the tests and verify GREEN**

Run: `uv run pytest -q tests/test_hip3_shadow_exit_attribution.py`

Expected: all Task 1 tests pass.

### Task 2: Attribute exits without horizon selection

**Files:**
- Modify: `tests/test_hip3_shadow_exit_attribution.py`
- Modify: `src/hypervector/research/hip3_shadow_exit_attribution.py`

**Step 1: Write failing attribution tests**

Cover: choose the minimum frozen horizon greater than or equal to actual holding minutes; never inspect a later horizon after one qualifies; label lifecycles held beyond 240 minutes as `no_post_exit_frozen_horizon`; distinguish directional recovery, persistent loss, protected profit, and continued positive path; preserve actual nominal/stress economics separately from non-fill BBO markouts.

**Step 2: Verify RED**

Run: `uv run pytest -q tests/test_hip3_shadow_exit_attribution.py`

Expected: new classification assertions fail because attribution is absent.

**Step 3: Implement minimal attribution and aggregate counts**

Use gross directional signs for classification. Serialize actual nominal/stress net bps and the chosen horizon's gross/after-modeled-friction BBO bps without subtracting them, because lifecycle funding/depth/stress and markout assumptions are not execution-equivalent.

**Step 4: Verify GREEN and refactor**

Run: `uv run pytest -q tests/test_hip3_shadow_exit_attribution.py`

Expected: all module tests pass; no function exceeds 50 lines and the module remains at most 500 lines.

### Task 3: Publish immutable evidence

**Files:**
- Create: `tests/test_hip3_shadow_exit_attribution_script.py`
- Create: `scripts/hip3_shadow_exit_attribution.py`

**Step 1: Write failing command tests**

Require distinct input/output paths, unchanged SHA-256/byte evidence, generator identity, atomic immutable publication, no overwrite, and compact authority-none CLI output.

**Step 2: Verify RED**

Run: `uv run pytest -q tests/test_hip3_shadow_exit_attribution_script.py`

Expected: collection fails because the command module does not exist.

**Step 3: Implement the thin command**

Reuse `file_evidence` and `write_immutable_json`; do not add network, live configuration, execution, or signing imports.

**Step 4: Verify GREEN**

Run: `uv run pytest -q tests/test_hip3_shadow_exit_attribution.py tests/test_hip3_shadow_exit_attribution_script.py`

Expected: all focused tests pass.

### Task 4: Run the frozen MU measurement and journal it

**Files:**
- Create: `data/logs/research/xyz_mu_shadow_exit_attribution_20260817T065547Z_v1.json`
- Create: `docs/research-journal/v53-mu-shadow-exit-attribution-v1.json`

**Step 1: Run the immutable command**

Use the archive-repaired lifecycle v5 and fixed-horizon markout v5 artifacts. Do not read later observer rows or validation/holdout evidence.

**Step 2: Independently reconcile the output**

Recompute lifecycle keys, chosen horizons, classification counts, and SHA-256 hashes with a separate read-only script. Confirm execution authority is none and no live runtime/config file changed.

**Step 3: Record the hypothesis disposition**

Journal the result as diagnostic-only. State the effective sample size, largest-winner/side limitations, evidence that would falsify the exit-truncation hypothesis, and the minimum prospective sample required before considering a live proposal.

### Task 5: Full verification and live-state reconciliation

**Files:**
- Inspect only: `data/runtime/bidirectional_cohort/latest_checkpoint.json`
- Inspect only: `data/runtime/bidirectional_cohort/latest_v53_first_event_capture.json`
- Inspect only: `data/runtime/research/mu_transport_parity_status.json` or current equivalent

**Step 1: Run fresh verification**

Run focused pytest, Ruff check/format, `git diff --check`, file/function size checks, and import-surface search proving no live registration.

**Step 2: Reconcile active monitors**

Confirm v53 identity/heartbeat/config consistency and report whether a first eligible/resolved lifecycle occurred. Confirm the fixed MU parity window's latest observed/resolved count.

**Step 3: Do not commit yet**

This repository has a large shared dirty worktree. Preserve all concurrent changes and defer staging/committing until the explicit release manifest is reviewed; never use broad `git add`.
