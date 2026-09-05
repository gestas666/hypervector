# SNDK Pressure-Short Exit Validation and Live Successor Plan

> Execution note: this plan is being executed in the existing working tree because the project is already running a live backend and the worktree contains extensive user-owned changes. Commits are intentionally deferred to avoid mixing unrelated work.

**Goal:** Determine whether a causal, SNDK-short-only exit overlay improves the exact V60 pressure route after costs and, only if it passes frozen robustness criteria, deploy it through a fail-closed successor profile without changing the other seven assets.

**Current contract:** `xyz:SNDK` executes only short signals from `hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2`, with an 80 bps fixed stop, no target, no recipe exit, no profit lock, and a 24-hour maximum-hold fallback. The shared provider also serves BRENTOIL, so any accepted change must use the existing symbol/side override mechanism.

**Evidence limits:** Historical SNDK replay uses causal 15-minute midpoint bars rather than exact one-minute venue mark candles. The current fresh-15-second route has no resolved attributable forward lifecycle. Therefore historical selection can justify a bounded candidate, but not a guarantee of live profitability. A candidate is rejected if its benefit depends on one winner, one fold, omitted costs, or a shared-provider behavior change.

## Executed outcome

No fixed-target or completed-bar trailing candidate passed the frozen development robustness criteria. The exit overlay was therefore rejected. The exact current SNDK identity subsequently closed its first live short at +$24.544682 net after recorded fees and funding through an operator-requested manual close. That is contradictory but single-trade evidence: it does not establish expectancy, yet it makes route disablement an unsupported inference from the exit experiment.

The selected successor disposition is consequently conservative about strategy drift rather than capital conservation: V61 preserves V60's SNDK short-only 80-bps stop, no-target/no-profit-lock contract and 24-hour fallback. It also preserves every other V60 execution and sizing contract. Only the profile identity changes so the stopped V60 run can receive an auditable successor lineage. The immutable evidence record is `docs/research-journal/sndk-pressure-short-exit-disposition-20260824-v1.json`.

Correction to the initial Task 4 premise: no accepted policy exists to bind, so the route guard was not widened and no directional profit-lock override was added. The successor acceptance test instead proves zero normalized strategy drift. Route disablement remains an update option only if additional exact-identity evidence falsifies the retained-route hypothesis.

## Task 1: Freeze the comparison contract

**Files:**
- Read: `configs/multi_asset_growth_first_5000_eight_asset_btc_hulk_smart_exit_candidate_v60.toml`
- Read: `data/logs/research/hip3_breakout_pressure_transfer_sndk_gold_disabled_brent_v1.json`
- Read: `src/hypervector/research/hip3_deployed_lifecycle.py`
- Read: `src/hypervector/research/hip3_lifecycle_inputs.py`

1. Record the V60 SNDK direction, stop, hold, exit, sizing, and entry-freshness settings.
2. Freeze SNDK short entries and the existing 80-bps-stop/24-hour/no-target exit as the control.
3. Freeze development folds for selection and use validation exactly once after selection.

## Task 2: Add a report-only bounded exit experiment using TDD

**Files:**
- Create: `src/hypervector/research/sndk_pressure_short_exit.py`
- Create: `scripts/sndk_pressure_short_exit_experiment.py`
- Create: `tests/test_sndk_pressure_short_exit.py`
- Create: `tests/test_sndk_pressure_short_exit_script.py`

1. Write failing tests for short-only filtering, causal completed-bar lock behavior, fixed candidate declarations, cost-stress reporting, and promotion rejection when robustness conditions fail.
2. Confirm the tests fail for the missing implementation.
3. Implement the smallest typed report-only evaluator, reusing the shared profit-lock policy and existing HIP-3 lifecycle loaders.
4. Bound the family before reading candidate validation results: control, a small fixed-target grid, and a small completed-bar trailing grid. Do not add staggered partial exits because live execution has no validated partial-ladder primitive.
5. Emit source hashes, phase boundaries, trial count, limitations, nominal/stress metrics, fold metrics, largest-winner removal, and the deterministic selection decision.

## Task 3: Select on development and confirm on validation

**Files:**
- Create: `data/logs/research/sndk_pressure_short_exit_development_20260824.json`
- Create only after selection freeze: `data/logs/research/sndk_pressure_short_exit_validation_20260824.json`

1. Run the experiment on the development folds only.
2. Select at most one candidate using predeclared criteria: positive nominal and stress net, improvement over control in both, nonnegative worst fold, positive net without the largest winner, and no increase in maximum drawdown.
3. Freeze the selected parameters and run validation once.
4. Accept only if validation nominal and stress net are positive, both improve over control, net excluding the largest winner remains positive, and no execution-data censoring invalidates the comparison.
5. If no candidate passes, leave V60 unchanged and report that exit optimization did not repair the route.

## Task 4: Bind an accepted policy only to SNDK short

**Files:**
- Modify: `src/hypervector/live/multi_asset_route_contract_validation.py`
- Create: `configs/multi_asset_growth_first_5000_eight_asset_sndk_exit_candidate_v61.toml`
- Create: `tests/test_v61_sndk_exit_config.py`

1. Write failing configuration tests proving the successor changes only `xyz:SNDK` short and preserves all other V60 route, sizing, and exit contracts byte-for-byte at their normalized payload level.
2. Narrow the commodity route guard to permit only the exact accepted SNDK-short override while continuing to reject BRENTOIL, long-side, and arbitrary policy drift.
3. Add the exact `profit_lock_overrides` declaration to the successor profile.
4. Verify provider payload, runtime contract selection, history warmup, open-exit telemetry, and TUI configuration identity.

## Task 5: Verify and cut over fail-closed

**Files:**
- Verify: targeted SNDK research/config/live tests
- Verify: `tests/ -q -m "not network"`
- Verify: Rust TUI tests

1. Run targeted tests and static/config validation.
2. Run the non-network Python suite and `cargo test -p hypervector-tui`.
3. Run the live preflight command for the successor without arming it.
4. Query direct venue state; require zero positions and zero open orders before transition. If not flat/order-free, do not cut over.
5. Stop only the old V60 backend after reconciliation, arm V61 with both explicit live-risk flags, and verify one backend, one run identity, eight configured assets, fresh heartbeats, ledger writes, and TUI parity.
6. Preserve V60 as the rollback profile. Roll back if startup verification, venue reconciliation, strategy contract identity, or telemetry freshness fails.

## Success and falsification criteria

- **Research success:** one frozen candidate passes every development and validation criterion after nominal and stressed costs.
- **Deployment success:** only the SNDK-short exit contract changes; the successor starts healthy and remains reconciled with venue state.
- **Falsifiers:** negative validation stress net, dependence on the largest winner, a negative worst development fold, missing causal bar coverage, change leakage into BRENTOIL/other assets, or any non-flat/non-order-free transition state.
- **Good enough:** no claim of optimality beyond the tested family; the accepted policy must be materially better than the control under the stated data limits and technically safe to bind directionally.
