# ETH/SOL Bidirectional Low-Timeframe Tuning Plan

> Status: implementation plan. Research and observation only; this plan grants no live execution authority.

## Objective

Produce separate ETH and SOL 5-minute execution / 15-minute context candidates that support long and short entries, map exactly to the cohort's fixed execution contracts, and are reproducibly evaluated on Hyperliquid bars and funding. Preserve every trial, including losing trials. Do not change or restart the active HYPE lifecycle.

## Known evidence and constraints

- Venue inputs: `data/cache/{ETH,SOL}_1m_365d.parquet` and matching Hyperliquid funding parquet files.
- Frozen windows: development `2025-07-28..2026-01-28`, validation `2026-01-28..2026-04-28`, pseudo-holdout `2026-04-28..2026-07-28`.
- The pseudo-holdout has already been inspected by prior research, so it is a chronological challenge, not a pristine holdout.
- Existing baseline uses 5-minute completed decisions, completed 15-minute context, one-minute path replay, 13 bps nominal / 20 bps stress friction, funding, isolated liquidation, and one-position-per-symbol semantics.
- Entry tuning must be separate by asset and side. A bidirectional runtime can therefore use different long and short parameters without pretending one symmetric rule fits both.
- Runtime parity requires fixed/clamped stops, fixed reward-risk targets, and fixed maximum holds. The research winner cannot depend on an exit unavailable to the live cohort.

## Success measurements

The artifact must report, not hide or abort on:

- trades, entries per 30 days, long/short split, wins/losses, net USD, PF, maximum drawdown, fees, funding, liquidations, and rejection reasons;
- nominal and 20 bps stress results;
- development month stability, validation, and pseudo-holdout results;
- parameter-neighbor sensitivity and source/config hashes;
- an explicit qualification state: `research_only`, `forward_observe`, or `canary_candidate`. This state is descriptive and grants no execution authority.

## Task 1: Define the immutable tuning contract

Files:

- Create `src/hypervector/research/low_tf_asset_tuning_models.py`
- Create `tests/test_low_tf_asset_tuning_models.py`

Steps:

1. Write failing tests for parameter validation, stable trial IDs, asset/side identity, frozen windows, and nominal/stress scenarios.
2. Run `uv run pytest tests/test_low_tf_asset_tuning_models.py -q` and confirm the expected import/behavior failures.
3. Add typed dataclasses for entry shape, exit shape, trial identity, segment/scenario result, and summary.
4. Keep the initial surface bounded: causal 5m breakout lookbacks, 5m/15m EMA pairs, BBWP release thresholds, clearance, fixed stop distance, reward multiple, and maximum hold.
5. Re-run the focused test.

## Task 2: Build causal signals and runtime-mappable exits

Files:

- Create `src/hypervector/research/low_tf_asset_tuning_signals.py`
- Create `tests/test_low_tf_asset_tuning_signals.py`
- Reuse `src/hypervector/research/low_tf_multi_asset_features.py`

Steps:

1. Write failing append-invariance and no-lookahead tests using synthetic bars.
2. Require a completed 15m directional context, completed 5m BBWP release, EMA direction/slope, and a completed-prior breakout boundary.
3. Emit long and short signals independently with stable reasons and readiness metrics.
4. Bind fixed/clamped stop, reward-risk target, and maximum hold anchors at decision time so the final replay and live execution contract express the same mechanics.
5. Verify no future bar changes an already emitted decision.

## Task 3: Implement bounded development selection and complete reporting

Files:

- Create `src/hypervector/research/low_tf_asset_tuning.py`
- Create `src/hypervector/research/low_tf_asset_tuning_reporting.py`
- Create `tests/test_low_tf_asset_tuning.py`

Steps:

1. Write failing tests that every declared trial is retained, zero-trade trials remain visible, side metrics are separate, and ranking is deterministic.
2. Broad-screen the entry surface on development data with the existing isolated, fee/funding-aware bar portfolio.
3. Rank within each asset/side by temporal stability, return-to-drawdown, PF, and useful frequency. Rankings do not delete or abort losing trials.
4. Run the selected candidates through the one-minute path replay at nominal and stress friction.
5. Include monthly results and local-neighbor sensitivity so a single brittle optimum is visible rather than silently promoted.

## Task 4: Add a report-only CLI and durable journal

Files:

- Create `scripts/low_tf_asset_tuning.py`
- Create `tests/test_low_tf_asset_tuning_script.py`
- Create `src/hypervector/research/low_tf_asset_tuning_journal.py`
- Create `tests/test_low_tf_asset_tuning_journal.py`

Steps:

1. Write failing CLI tests for explicit ETH/SOL paths, immutable output behavior, and `execution_authority=none`.
2. Load each one-year venue dataset once, evaluate the complete development surface, then validation and pseudo-holdout for every selected candidate.
3. Persist full trials and trades to `data/research/strategy_trials.duckdb`; write a compact immutable JSON artifact under `data/logs/research/`.
4. Refuse overwrite and include file/config hashes, run ID, generated time, and known limitations.

## Task 5: Run the tuning experiment

Commands:

```bash
uv run python scripts/low_tf_asset_tuning.py \
  --symbol ETH --symbol SOL \
  --data-root data \
  --run-id eth_sol_bidirectional_5m15m_tuning_v1_20260805 \
  --journal data/research/strategy_trials.duckdb \
  --output data/logs/research/eth_sol_bidirectional_5m15m_tuning_v1_20260805.json
```

Validation:

- Independently recalculate headline metrics from the persisted trade rows.
- Compare nominal versus 20 bps stress and parameter neighbors.
- Report ETH long, ETH short, SOL long, and SOL short separately, including negative outcomes.
- Compare selected trials against the untouched baseline artifacts from all three chronological windows.

## Task 6: Add observe-only cohort providers for selected identities

Files:

- Create `src/hypervector/live/low_tf_trend_profile.py`
- Create `src/hypervector/live/low_tf_trend_provider.py`
- Create `tests/test_low_tf_trend_profile.py`
- Create `tests/test_low_tf_trend_provider.py`
- Modify `src/hypervector/live/multi_asset_intent_poller.py`
- Modify `src/hypervector/live/multi_asset_live_config.py`
- Modify focused config/poller tests

Steps:

1. Write failing tests for exact asset/side profile resolution, completed-bar causality, readiness/blockers, and stable profile identity.
2. Implement the selected ETH/SOL profiles as a new versioned strategy identity; do not overwrite Hulk, HYPE breakout, or Range Onset identities.
3. Emit backend evaluations for every completed 5m decision and intents only on actual selected signals.
4. Map stop/target/hold values to an existing `ProviderExecutionContract` with exact telemetry.
5. Keep `execution_symbols = []`; observation must work without live order authority.

## Task 7: Stage configuration, telemetry, and rollback

Files:

- Create `configs/multi_asset_bidirectional_eth_sol_tuned_observe_candidate.toml`
- Create `tests/test_eth_sol_tuned_observe_candidate_config.py`
- Create `docs/guides/eth-sol-tuned-observer-and-canary.md`
- Modify TUI tests only if the generic provider projection does not already render the new readiness fields.

Steps:

1. Add ETH and SOL providers with both declared sides and no execution symbols.
2. Prove the config cannot place orders even when the main process is live-enabled.
3. Verify TUI strategy, symbol, side, readiness, blocker, regime context, and profile identity projections.
4. Document an explicit later canary procedure that requires a new user authorization and a new fingerprint.
5. Rollback is removal of the observe-only provider config and restoration of the prior config path; no existing strategy file is overwritten.

## Task 8: Verification

Commands:

```bash
uv run pytest tests/test_low_tf_asset_tuning_models.py \
  tests/test_low_tf_asset_tuning_signals.py \
  tests/test_low_tf_asset_tuning.py \
  tests/test_low_tf_asset_tuning_script.py \
  tests/test_low_tf_asset_tuning_journal.py \
  tests/test_low_tf_trend_profile.py \
  tests/test_low_tf_trend_provider.py \
  tests/test_eth_sol_tuned_observe_candidate_config.py -q
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
```

Acceptance requires zero failing tests, immutable artifacts, independently reconciled metrics, observe-only runtime authority, and no mutation or restart of the active HYPE lifecycle.

## Risks and falsifiers

- If the selected shape is negative under stress or unstable across later windows, it remains a `research_only` or `forward_observe` challenger; this falsifies promotion, not the experiment.
- If long or short frequency is below the requested operating tempo, report that directly and retain the other side rather than fabricating symmetry.
- If one-minute replay materially disagrees with the broad 5m screen, trust the one-minute replay and revise the screen.
- Fresh forward observation with materially worse fills, missed signals, or sign-reversed outcomes would reduce confidence and require retuning or retirement.
