# Cohort v24 to complete-portfolio v25 transition and rollback

This procedure binds the candidate to the complete nine-asset, 24-setup
portfolio cockpit. It does not authorize a silent restart. Live mutation still
requires an explicit operator launch with both live-risk flags after v24 is
drained, flat, order-free, and archived.

## Frozen contract

- current profile: `multi_asset_bidirectional_eth_sol_full_observation_canary_v24`
- current fingerprint:
  `39697b04f758f62722fa16be49cce4d9462b087d44d4b08e05972015b664ee59`
- candidate profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`
- candidate fingerprint:
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`
- verified pre-change bundle:
  `data/backups/bidirectional_cohort/prestart_20260807T204004.937250Z_ec7715f671fa`
- implementation identity:
  `d859fcfe3d735959e98437490104cc86b4f25486a810fd536e1793bd6d0fc8e7`
  across 1,238 implementation files

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_eth_sol_full_observation_canary_v24.toml",
  "current_profile_id": "multi_asset_bidirectional_eth_sol_full_observation_canary_v24",
  "current_profile_fingerprint": "39697b04f758f62722fa16be49cce4d9462b087d44d4b08e05972015b664ee59",
  "current_file_sha256": "40671f17fcff7cb6ba2cf8f124929570dc2c5e91b4914bed745599ee27b00114",
  "candidate_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
  "candidate_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "candidate_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "candidate_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "candidate_run_fingerprint_observe": "af74bc13f346eb24138ed2568b829f0b01f5d57a95d5884de07ee4d276a1710d",
  "prechange_bundle": "data/backups/bidirectional_cohort/prestart_20260807T204004.937250Z_ec7715f671fa",
  "prechange_manifest_sha256": "06470acfdee66aba2cc91f7e27c49394ee7d5a8cdf9e91ae611ef8f9793276f6",
  "implementation_file_count": 1238,
  "implementation_sha256": "d859fcfe3d735959e98437490104cc86b4f25486a810fd536e1793bd6d0fc8e7",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hulk_expansion_bidirectional_tuned_v2|ETH",
    "hulk_expansion_bidirectional_tuned_v2|SOL",
    "hulk_expansion_bidirectional_tuned_v2|HYPE",
    "range_onset_bidirectional_v1|BTC",
    "range_onset_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|SOL",
    "range_onset_bidirectional_v1|HYPE",
    "hypervelocity_source_follow_bidirectional_5m_v1|BTC",
    "hype_breakout_onset_bidirectional_v1|BTC",
    "hype_breakout_onset_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|SOL",
    "hype_breakout_onset_bidirectional_v1|HYPE",
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SP500",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SPCX",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL"
  ],
  "observe_only_scope": [],
  "maximum_positions": 9,
  "one_position_per_asset": true,
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed config byte, fingerprint, execution pair, implementation identity,
or namespace invalidates this contract. Regenerate and review it rather than
launching a nearby profile.

## Candidate behavior and evidence boundary

- Core perps: BTC, ETH, SOL, and HYPE.
- HIP-3: `xyz:SP500`, `xyz:SPCX`, `xyz:SNDK`, `xyz:GOLD`, and
  `xyz:BRENTOIL`.
- All 24 provider-symbol setups declare long and short authority.
- Shared portfolio: nine slots, with one position per exact asset identity.
- All assets use isolated 5x. Core maximum notionals are $25 for BTC/ETH and
  $75 for SOL/HYPE; HIP-3 maximum notionals are $75.
- Venue stops and maximum holds remain provider-specific as frozen in the TOML.

Public mainnet observation produced 24/24 current setup evaluations, nine
candle streams, nine L2 books, zero actions, and zero withheld actions. That is
strong mechanical evidence for read-only completeness. Injected adapter tests
cover namespaced entry, stop, close, leverage, position, and order identities.
It is not an actual HIP-3 fill, so authenticated mutation and realized friction
remain unverified until a bounded canary lifecycle occurs. Prior offline index
Swing/HA results were negative; the route remains an explicitly requested,
ungated research trial rather than a claim of established edge.

## 1. Verify current v24 ownership

Require a fresh checkpoint, the exact v24 identity, zero faults, and observed
venue state:

```bash
jq -e '
  .lifecycle.state == "running_consistent" and
  .audit.health.faults == 0 and
  .audit.run.profile_id ==
    "multi_asset_bidirectional_eth_sol_full_observation_canary_v24" and
  .audit.run.profile_fingerprint ==
    "39697b04f758f62722fa16be49cce4d9462b087d44d4b08e05972015b664ee59" and
  .configuration_generation.matches_runtime == true and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

This proves only the sampled checkpoint. Staleness, a fault, identity drift, or
venue reconciliation failure stops the transition as a technical failure.

## 2. Drain v24 without forcing an exit

On TUI screen 7, select `TRANSITION DRAIN`, inspect its exact v24 run binding,
and confirm. It withholds new entries while the current owner continues to
manage open positions, timers, funding, and venue-native stops.

If interrupted while draining, resume only the exact v24 profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_eth_sol_full_observation_canary_v24.toml
```

## 3. Prove flat/order-free and archive v24

Wait for every asset to be terminal, flat, order-free, and drain-complete:

```bash
jq -e '
  .lifecycle.all_assets_terminal == true and
  .audit.health.faults == 0 and
  ([.audit.health.assets[] |
    (.final_state == "FLAT" or .final_state == "STOPPED") and
    .position_size_signed == 0 and
    (.open_order_ids | length) == 0] | all) and
  .transition_drain.status == "completed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

After the backend exits normally, preview and then confirm the recoverable
archive using the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

Do not delete or overwrite the ledgers, journal, checkpoint, transition marker,
stops, or backups.

## 4. Reconcile v25 without placing

With no live owner, generate one report-only checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Require the exact v25 identity, all nine exact asset identities, 24/24 setup
coverage, nine slots, flat venue state, no owned orders, and the frozen route
map above. This step has no execution authority.

## 5. Explicitly launch v25

Only after operator approval at the verified boundary:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --enabled --i-accept-live-risk
```

Startup must acquire singleton ownership, reconcile exact core and HIP-3 venue
state, and publish a new verified pre-start backup before constructing execution
clients. Verify the exact bundle reported at startup:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

A separate read-only TUI can attach without backend ownership:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml
```

## Runtime acceptance

- exact v25 identity in config, ledger, checkpoint, and TUI;
- `SETUPS 24/24 // COMPLETE` with every row selectable;
- all nine assets available across dashboard, charts, depth, regime, positions,
  strategy readiness, and trade history;
- `running_consistent`, zero faults, and fresh market/venue timestamps;
- only the 24 frozen routes executable, both directions;
- nine shared slots and at most one position per exact asset identity;
- every open position has exactly one nonzero reduce-only venue stop;
- causal signal, readiness blockers, entry, fill, fees, slippage, funding,
  liquidation price, MFE/MAE, exit attribution, and missed-opportunity records;
- no inherited exposure, duplicate lifecycle, namespace drift, stale intent, or
  display fallback represented as backend truth.

Performance, drawdown, or setup frequency are reported trial results rather
than implicit abort gates. Technical integrity failures remain fail-closed.

## Rollback

There is no hot rollback. Preserve any v25 lifecycle under its recorded
contract. At a later verified flat/no-owned-order boundary, complete and archive
a v25 drain, then explicitly launch the exact frozen v24 config or another
approved generation with a newly verified backup. Never replace newer ledger or
journal bytes with an older backup.

## Confidence and falsifiers

- **High mechanical confidence for staged observation:** supported by 24/24
  public evaluations, 9/9 candles/L2, exact parser/render tests, and full Python
  and Rust test passes.
- **Medium confidence for authenticated HIP-3 execution:** payload identity is
  tested, but no real namespaced fill/stop/close lifecycle has yet occurred.
- **Low and strategy-specific economic confidence:** the candidate is a live
  research portfolio, not a validated profitability claim.

Any missing setup, wrong namespace, stale feed, reconciliation fault, duplicate
position, missing owned stop, or ledger/TUI disagreement falsifies mechanical
acceptance. Realized live fills that materially diverge from the expected fee,
slippage, or stop behavior update the execution-friction model and strategy
assessment.
