# V58 Observer Epoch Rotation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow the authority-none V58 research pipeline to rotate to a clean, non-pooled observer epoch while preserving exact strategy identity, lifecycle attribution, and the live backend boundary.

**Architecture:** Keep the live V58 process unchanged. Derive an isolated observer's expected profile and run fingerprints from the frozen base V58 configuration plus its ledger root, rather than accepting arbitrary hashes or pinning one obsolete root. Bind fresh BTC, ETH, and HYPE lifecycle watchers and the continuous consolidator to the new observer identity and separate output paths.

**Tech Stack:** Python 3.13, pytest, Hypervector TOML configuration loader, report-only JSONL checkpoints, tmux process supervision.

---

### Task 1: Reproduce the identity-rotation failure

**Files:**
- Modify: `tests/test_cohort_successor_observer_status.py`
- Test: `tests/test_cohort_successor_observer_status.py`

**Step 1: Write the failing tests**

Add a test that loads the frozen V58 config, rebinds it to a temporary observer root, writes a checkpoint using the derived isolated profile/run fingerprints, and calls:

```python
status.load_v58_successor_observer_status(
    source,
    observed_at=_NOW,
    maximum_age_seconds=300.0,
    config_path=_V58_CONFIG,
)
```

Require the derived identity to be accepted. Add a paired negative test that changes the derived run fingerprint and requires `ValueError("successor observer run identity is invalid")`.

**Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/test_cohort_successor_observer_status.py -q
```

Expected: the new tests fail because `config_path` is not yet accepted.

### Task 2: Derive the isolated identity without weakening validation

**Files:**
- Modify: `src/hypervector/research/cohort_successor_observer_status.py`
- Modify: `scripts/v58_continuous_improvement.py`
- Test: `tests/test_cohort_successor_observer_status.py`
- Test: `tests/test_v58_continuous_improvement_script.py`

**Step 1: Implement the minimal identity resolver**

Extend `load_v58_successor_observer_status` with optional `config_path: Path | None = None`. Preserve the existing frozen original identity when it is omitted. When supplied:

```python
base = load_multi_asset_live_config(config_path, mode="observe")
isolated = with_observer_ledger_root(base, ledger_path.parent)
```

Require the base profile ID/fingerprint to equal exact V58, require the evidence path to equal `isolated.cohort_ledger`, and require the checkpoint profile/run fingerprints to equal the derived isolated fingerprints. Do not accept a caller-provided fingerprint list or a success-shaped fallback.

Pass `config_path=args.config` from the continuous consolidator.

**Step 2: Run focused tests and verify GREEN**

```bash
uv run pytest tests/test_cohort_successor_observer_status.py tests/test_v58_continuous_improvement_script.py -q
```

Expected: all focused tests pass, including the drift rejection.

### Task 3: Freeze the successor lifecycle contracts

**Files:**
- Create: `docs/research-journal/v58-btc-liquidity-sweep-exact-mark-lifecycle-preregistration-20260821-v5.json`
- Create: `docs/research-journal/eth-breakout-precompression-pullback-v21.json`
- Create: `docs/research-journal/v58-hype-alignment-exact-depth-shadow-lifecycle-preregistration-20260821-v5.json`

**Step 1: Bind each preregistration**

Use observer run `bidirectional-observe-1787339261510`, isolated profile fingerprint `a779d40ff77909b42d0359668087aad77a74cd8209c936d88d253062a2ddba17`, isolated run fingerprint `950a71d22a1b94292d3fbdd674ace4b92d0ac1d506f7f3a1700d806b68462ea8`, and prospective start `1787339280000`.

Preserve each route's existing entry, stop, target, maximum-hold, fee, funding, and authority-none contract. Set `pool_with_predecessor_epoch=false` and bind the exact new ledger prefix hash/bytes.

**Step 2: Validate JSON and source identities**

```bash
jq empty docs/research-journal/*v5.json docs/research-journal/eth-breakout-precompression-pullback-v21.json
shasum -a 256 docs/research-journal/*v5.json docs/research-journal/eth-breakout-precompression-pullback-v21.json
```

Expected: valid JSON and stable SHA-256 identities.

### Task 4: Attach fresh authority-none lifecycle watchers

**Files:**
- Runtime output: `data/runtime/research/v58_btc_sweep_lifecycle_v2_latest.json`
- Runtime output: `data/runtime/research/v58_eth_pullback_first_lifecycle_v2_latest.json`
- Runtime output: `data/runtime/research/v58_hype_alignment_shadow_lifecycle_v2_latest.json`
- Runtime output: `data/live/research/v58_btc_sweep_marks_epoch_v2.jsonl`

**Step 1: Start each watcher in a retained tmux pane**

Use the exact new preregistration SHA-256 and observer run ID. Each process must remain report-only and use separate status/output files.

**Step 2: Verify initial watcher state**

Require all three status documents to match the new run/profile identity, report zero pending/resolved before a qualifying signal, and declare `execution_authority=none`.

### Task 5: Restore and verify continuous consolidation

**Files:**
- Runtime output: `data/runtime/research/v58_continuous_improvement_latest.json`
- Create: `docs/research-journal/v58-cached-observer-successor-acceptance-20260821-v1.json`

**Step 1: Run one bounded consolidation cycle**

Supply the new observer checkpoint and the new BTC/ETH/HYPE status paths explicitly. Keep the existing SP500, BRENTOIL, live checkpoint, venue preflight, and active-route sources.

**Step 2: Verify the bounded report**

Require fresh new observer identity, complete 10-route coverage, zero execution authority, no automatic live change, and an unchanged healthy/protected live backend.

**Step 3: Start the continuous report-only loop**

Run the same exact arguments at a 120-second interval in a retained tmux pane.

**Step 4: Run regression verification**

```bash
uv run pytest tests/test_cohort_successor_observer_status.py tests/test_v58_continuous_improvement.py tests/test_v58_continuous_improvement_script.py tests/test_v58_continuous_improvement_monitor.py -q
uv run ruff check src/hypervector/research/cohort_successor_observer_status.py scripts/v58_continuous_improvement.py tests/test_cohort_successor_observer_status.py
```

Expected: all focused tests and lint pass; the live backend remains untouched.

### Task 6: Record acceptance and continue the evidence window

**Files:**
- Create: `docs/research-journal/v58-cached-observer-successor-acceptance-20260821-v1.json`

**Step 1: Record exact evidence**

Bind the successor ledger, checkpoint, parity report, lifecycle statuses, continuous report, config, and implementation hashes. State that the 24-hour gate remains collecting and that no profitability or live-equivalence claim is established by the initial prefix.

**Step 2: Preserve the shared dirty worktree**

Do not commit, push, clean, revert, or modify unrelated user changes in this session.
