# SP500 Short-Containment Successor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stage and validate an inactive eight-asset successor that preserves V58 exactly except that the SP500 fresh15 route observes both sides but may execute only shorts.

**Architecture:** Copy the authoritative V58 TOML into a new candidate identity, add one SP500 provider-level `execution_side_overrides` entry, and prove the parsed configuration differs only in profile identity and SP500-long execution authority. Keep the current live process, open SP500 short, orders, accounting epoch, and V58 configuration unchanged; deployment remains a separate explicit-approval operation at a verified flat and order-free boundary.

**Tech Stack:** Python 3.13, pytest, Hypervector typed live-profile parser, TOML configuration, report-only mainnet preflight, Rust TUI acceptance tests.

---

### Task 1: Freeze the evidence and intended delta

**Files:**
- Read: `configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml`
- Read: `docs/research-journal/v58-sp500-lineage-side-containment-audit-20260821-v1.json`
- Read: `data/logs/research/bidirectional_cohort/v58_sp500_long_resolution_short_open_20260822T0935Z.json`

**Step 1: Verify the resolved-long and open-short identities**

Run:

```bash
jq '{resolved: [.resolved_lifecycles[] | {lifecycle_id, side, exit_attribution, outcome}], open: [.open_lifecycles[] | {lifecycle_id, side, protection, exit_plan}]}' data/logs/research/bidirectional_cohort/v58_sp500_long_resolution_short_open_20260822T0935Z.json
```

Expected: one resolved SP500 long closed by `opposite_strategy_intent`, one protected unresolved SP500 short, and `live_change_supported=false`.

**Step 2: Verify the exact intended configuration delta**

Expected: new profile identity plus `execution_side_overrides = { "xyz:SP500" = ["short"] }` on the SP500 provider; no asset, route, risk, exit, sizing, leverage, timer, or portfolio-capacity change.

### Task 2: Write the failing exact-diff acceptance tests

**Files:**
- Create: `tests/test_v59_sp500_short_containment_config.py`
- Expected candidate: `configs/multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml`

**Step 1: Write the failing tests**

Test that:

```python
assert candidate.profile_id == (
    "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59"
)
assert candidate.assets == baseline.assets
assert candidate.providers_except_sp500 == baseline.providers_except_sp500
assert candidate_sp500.sides == baseline_sp500.sides == frozenset({"long", "short"})
assert candidate_sp500.execution_side_overrides == (
    ("xyz:SP500", frozenset({"short"})),
)
assert candidate_sp500.execution == baseline_sp500.execution
assert (SP500_ROUTE, "xyz:SP500", "long") not in candidate.executable_provider_directions
assert (SP500_ROUTE, "xyz:SP500", "short") in candidate.executable_provider_directions
```

Also assert that every non-SP500 executable provider direction is byte-for-byte equivalent after normalizing the profile ID.

**Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/test_v59_sp500_short_containment_config.py -q
```

Expected: FAIL because the candidate configuration does not yet exist.

### Task 3: Create the minimal inactive candidate

**Files:**
- Create: `configs/multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml`

**Step 1: Copy the exact V58 content into the new candidate**

Change only:

```toml
profile = "multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59"
```

and add to the SP500 provider:

```toml
execution_side_overrides = { "xyz:SP500" = ["short"] }
```

**Step 2: Run the exact-diff tests to verify GREEN**

Run:

```bash
uv run pytest tests/test_v59_sp500_short_containment_config.py -q
```

Expected: PASS.

**Step 3: Run focused parser, provider, routing, protection, and acceptance tests**

Run:

```bash
uv run pytest -q \
  tests/test_v59_sp500_short_containment_config.py \
  tests/test_multi_asset_live_config.py \
  tests/test_side_specific_cohort_providers.py \
  tests/test_v58_reused_provider_validation.py \
  tests/test_v58_poststart_acceptance.py
```

Expected: all pass with no network calls.

### Task 4: Produce a report-only transition preflight

**Files:**
- Create: `data/logs/research/bidirectional_cohort/v59_sp500_short_containment_interim_preflight_<UTCSTAMP>.json`

**Step 1: Run the candidate against the active V58 identity**

Run:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml \
  --active-config configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v59_sp500_short_containment_interim_preflight_<UTCSTAMP>.json
```

Expected while the SP500 short remains open: exit code 3, exact eight-asset reconciliation, `candidate_differs_from_active=true`, sizing technically ready, and transition blocked only by the current SP500 position/order. This blocked result validates mechanics but does not authorize deployment.

### Task 4A: Bind stress and post-start acceptance to the candidate identity

**Files:**
- Create: `src/hypervector/research/v59_poststart_acceptance.py`
- Create: `scripts/v59_poststart_acceptance.py`
- Create: `tests/test_v59_poststart_acceptance.py`
- Create: `tests/test_v59_poststart_acceptance_script.py`
- Create: `data/logs/research/bidirectional_cohort/v59_sp500_short_containment_growth_stress_<UTCSTAMP>.json`

**Step 1: Write failing candidate-acceptance tests**

Require the exact candidate profile fingerprint, all eight unchanged asset-sizing
contracts, all nine unchanged provider exit contracts, ten evaluated provider-symbol
routes, and thirteen executable directional scopes. Assert that restoring SP500-long
authority, changing any sizing or exit field, omitting route coverage, or binding stress
or preflight evidence from another profile rejects acceptance.

**Step 2: Implement the smallest candidate-specific acceptance module**

Reuse the established shared health, freshness, protection, execution-plan, sizing,
exit, and flat-preflight checks. Keep V58 acceptance behavior unchanged. The V59
publisher remains report-only and must hash every verdict-capable dependency.

**Step 3: Generate candidate-bound stress evidence**

Reuse the V58 eight-asset stress schema because the candidate removes one executable
direction while preserving every asset, position slot, leverage, margin fraction,
notional cap, stop, exit, and execution-cost assumption. Bind the generated report to
the V59 profile ID and fingerprint and record this exact directional-containment reuse
basis as a limitation; do not infer improved profitability from the reduced authority.

**Step 4: Verify RED then GREEN**

Run the new V59 acceptance tests first without the implementation and confirm failure,
then run them with the implementation and the existing V58 acceptance/stress suites to
prove the baseline remains unchanged.

### Task 5: Verify the complete staged source

**Files:**
- Verify: all current `src`, `scripts`, `tests`, Rust TUI, and the candidate TOML

**Step 1: Run complete verification**

Run:

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run ruff check src scripts tests
uv run ruff format --check \
  tests/test_v59_sp500_short_containment_config.py \
  tests/test_v59_poststart_acceptance.py \
  tests/test_v59_poststart_acceptance_script.py \
  src/hypervector/research/v59_poststart_acceptance.py \
  scripts/v59_poststart_acceptance.py
git diff --check
uv run python -m hypervector status
```

Expected: all functional gates pass. Report the existing unrelated repository-wide formatter backlog separately; do not bulk-rewrite unrelated dirty files.

### Task 6: Publish the approval-ready decision record

**Files:**
- Create: `docs/research-journal/v58-sp500-side-containment-after-first-long-20260822-v1.json`

**Step 1: Record exact evidence and alternatives**

Include the resolved long, two prior positive exact shorts, still-open third short, negative historical transfer evidence, largest-winner-removed dependency, unchanged four-non-crypto roster, exact candidate fingerprint, preflight blocker, uncertainty, success metrics, rollback triggers, and explicit non-authorization.

**Step 2: Append and verify the report-only hypothesis revision**

Run:

```bash
uv run python -m hypervector research-db-journal-append \
  --record docs/research-journal/v58-sp500-side-containment-after-first-long-20260822-v1.json
uv run python -m hypervector research-db-journal-report \
  --hypothesis-id v58-sp500-side-containment-after-first-long
```

Expected: inserted revision 1, all evidence matching, `execution_authority=none`, `automatic_promotion=false`, and `runtime_strategy_changed=false`.

### Task 7: Preserve the live boundary

**Files:**
- Read only: `data/runtime/bidirectional_cohort/latest_checkpoint.json`
- Read only: venue/ledger preflight evidence

**Step 1: Do not deploy from this plan**

Deployment remains prohibited until the SP500 short resolves, every asset and owned order reconciles flat/order-free, the latest short outcome is added to the decision, a fresh complete bundle verifies, and the operator provides exact operation-specific live-risk approval.

**Step 2: Define rollback before later approval**

If a later approved cutover changes any non-SP500 direction, route, exit, risk, sizing, leverage, accounting, checkpoint, protection, or TUI invariant, reject startup and restore only from a verified bundle at a flat/order-free boundary.
