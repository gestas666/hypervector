# Cohort v25 to evidence-routed v28 transition and rollback

V28 carries forward v27's HIP-3 telemetry repairs and explicit default-ignore
provider recipe exits. It changes one execution route: SOL remains observed by
`hype_breakout_onset_bidirectional_v1`, presented to operators as
`HT-Breakout`, but that exact provider-symbol pair has no automatic execution
authority. SOL retains automatic Hulk and Range Onset authority in both long
and short directions. Every other v27 route, side, priority, size, leverage,
stop, target, and maximum hold remains unchanged.

This is an inactive candidate. It does not authorize a restart or change the
running process. v25 remains active until the operator explicitly requests a
transition drain and the backend proves a flat, order-free boundary.

## Frozen contract

- active profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`
- active run: `bidirectional-live-1786137154835`
- inactive candidate: `multi_asset_bidirectional_complete_portfolio_canary_v28`
- v28 profile fingerprint:
  `90285e71220a7eca53e7791da9cb48ddcdc58e36a398c12a1485082c0f50f30f`
- verified report-only source bundle:
  `data/backups/bidirectional_cohort/prestart_20260808T052126.703591Z_90285e71220a`
- implementation identity:
  `e368fbf513cf51296b9ff7b7da18f621b4b9b0edc30d4d751f78b6c726f96138`
  across 1,247 files
- research revision:
  `8f0d4d52ed4d068dca222c1069b2b7cd5a3c27ea8b03259377cf8d44921f6561`

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "current_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "current_run_id": "bidirectional-live-1786137154835",
  "candidate_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v28.toml",
  "candidate_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v28",
  "candidate_profile_fingerprint": "90285e71220a7eca53e7791da9cb48ddcdc58e36a398c12a1485082c0f50f30f",
  "candidate_file_sha256": "7db6d87a87f3b69234421fa9b1838c6be18c5c162f1d76bd2e4ed7a7baa9f07e",
  "candidate_run_fingerprint_observe": "559eeb97f839421db937b018e479f35246ea7b91ae7d48330bcbe55fbf0ddfec",
  "prechange_bundle": "data/backups/bidirectional_cohort/prestart_20260808T052126.703591Z_90285e71220a",
  "prechange_manifest_sha256": "45e807298be4eb240683e593dc6fdff6cf7c5ae36706d50ae9ee61a3c930c2bf",
  "implementation_file_count": 1247,
  "implementation_sha256": "e368fbf513cf51296b9ff7b7da18f621b4b9b0edc30d4d751f78b6c726f96138",
  "research_record": "docs/research-journal/sol-ht-breakout-transfer-v2.json",
  "research_record_sha256": "5362e1b473fff4774bceff793def95516cff5c2330918b5f0f6a403a86846473",
  "research_revision_id": "8f0d4d52ed4d068dca222c1069b2b7cd5a3c27ea8b03259377cf8d44921f6561",
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
  "removed_execution_scope": [
    "hype_breakout_onset_bidirectional_v1|SOL"
  ],
  "observe_only_scope": [
    "hype_breakout_onset_bidirectional_v1|SOL"
  ],
  "maximum_positions": 9,
  "one_position_per_asset": true,
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed profile byte, execution source identity, route, risk setting,
research record, or backup invalidates this contract. Generate a new candidate
instead of launching a nearby profile.

## Evidence boundary

The route change is supported by three non-equivalent evidence layers:

1. The unchanged 365-day Hyperliquid SOL transfer produced 854 development
   trades, profit factor 0.8336, and -8,948.62 bps after modeled costs.
2. A post-hoc stop/hold winner reached development profit factor 1.0173, then
   failed the opened final block with 90 trades, profit factor 0.6714, and
   -2,056.33 bps.
3. The earlier live-ledger/BBO L2-aligned challenger resolved six SOL shorts at
   -16.21 bps mean after friction and profit factor 0.1507.

The current v25 SOL `HT-Breakout` lifecycle remains open and is not counted as
a resolved result. The route can be reconsidered under the falsifier in
`docs/research-journal/sol-ht-breakout-transfer-v2.json`. This is an explicit
profile selection, not an automatic performance gate. Results, drawdown, and
frequency remain reported trial outcomes under the project charter.

## 1. Verify active v25 ownership

Require a fresh checkpoint timestamp and this exact predicate:

```bash
jq -e '
  .lifecycle.state == "running_consistent" and
  .audit.health.faults == 0 and
  .audit.run.run_id == "bidirectional-live-1786137154835" and
  .audit.run.profile_id ==
    "multi_asset_bidirectional_complete_portfolio_canary_v25" and
  .audit.run.profile_fingerprint ==
    "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc" and
  .configuration_generation.matches_runtime == true and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Every open position must retain its exact venue-native stop and loaded v25
execution plan. Staging v28 does not hot-patch any lifecycle.

## 2. Drain without forcing an exit

Only after explicit operator authorization, select `TRANSITION DRAIN` on TUI
screen 7 and confirm the exact v25 binding. Flat symbols stop opening while v25
continues its original exits and protection.

If the owner is interrupted during the active drain, resume only v25:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml
```

## 3. Prove flat/order-free and archive v25

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

After normal shutdown, preview and then explicitly archive the drain:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786137154835

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786137154835 --yes
```

Do not delete or overwrite ledgers, journals, checkpoints, orders, or backups.

## 4. Reconcile v28 without placing orders

With no live owner, publish one report-only checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v28.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Require all nine assets, 24/24 observed provider-symbol rows, 23 executable
provider-symbol rows, one explicit observe-only SOL `HT-Breakout` row, both
sides on every executable provider, nine slots, no inherited exposure, and no
owned open orders.

## 5. Explicitly launch v28

Only after renewed approval at the verified flat boundary:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v28.toml \
  --enabled --i-accept-live-risk
```

Verify the new startup bundle printed by the backend:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-v28-path>
```

## Runtime acceptance

- The ledger, checkpoint, and TUI report the exact v28 identity.
- Coverage is 24/24 observed, 23 executable, and one observe-only route.
- SOL Hulk and Range Onset retain both long and short automatic authority.
- SOL `HT-Breakout` remains visible but any routed SOL action from it is an
  authority defect.
- All nine assets remain eligible for at most one position per asset.
- Provider recipe exits remain `ignore`; no report-only recipe signal closes a
  lifecycle.
- Heartbeats, venue reads, L2, fills, fees, funding, slippage, liquidation,
  stop ownership, MFE/MAE, and missed opportunities remain backend-authored.
- Performance, drawdown, and frequency are a performance result rather than an implicit abort condition.

Technical identity, ownership, source-causality, or protection failures remain
fail-closed. Poor economic results remain evidence and do not silently mutate
the runtime strategy.

## Rollback

No hot rollback is permitted. Preserve every v28 lifecycle under its recorded
contract. At a later explicitly authorized, drained, verified flat/order-free
boundary, archive v28, create a fresh backup, and launch v25 only with renewed
authority:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --enabled --i-accept-live-risk
```

Never restore older ledgers or journals over newer evidence.

## Confidence and falsifiers

- High confidence: v28 changes only the SOL `HT-Breakout` execution scope from
  v27; the typed config contract verifies every other route and risk field.
- Medium confidence: the SOL rejection combines broad historical, failed tuned
  holdout, and sparse prospective evidence, but historical replay does not
  reproduce private live fills.
- Low portfolio-economic confidence: the current v25 run has only two resolved
  trades and cannot establish profitability.

The transition contract is falsified by any changed identity, unprotected or
duplicated lifecycle, inherited exposure, unexpected SOL `HT-Breakout` route,
missing observed setup, side restriction, or risk drift. The route decision is
updated by the journal's declared prospective live falsifier, not by one open
mark or one favorable short window.
