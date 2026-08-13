# Cohort v25 to telemetry repair v27 transition and rollback

V27 supersedes the inactive v26 candidate. It carries forward v26's HIP-3
telemetry repairs and makes provider-recipe exit authority explicit. Every v27
provider has `provider_recipe_exit_policy=ignore`; typed HIP-3 Swing/HA exit
signals remain report-only and cannot close a position. The codebase contains
a durable `honor` mechanism for a separately reviewed future profile, but
direct `honor` execution remains rejected by the current economic evidence.
V27 does not change entry rules, route priority, execution scope, sizing,
leverage, stops, targets, or maximum holds. It does not authorize a restart.
V25 remains active until an explicitly authorized drain reaches a verified
flat and order-free boundary.

## Frozen contract

- active profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`
- active run: `bidirectional-live-1786137154835`
- inactive candidate: `multi_asset_bidirectional_complete_portfolio_canary_v27`
- v27 profile fingerprint:
  `c671c7aaedbd357d44b935eec8f725235d6751521ab53d6d4e04f63f55665a33`
- verified report-only source bundle:
  `data/backups/bidirectional_cohort/prestart_20260808T042806.773285Z_c671c7aaedbd`
- implementation identity:
  `e368fbf513cf51296b9ff7b7da18f621b4b9b0edc30d4d751f78b6c726f96138`
  across 1,247 files

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "current_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "current_run_id": "bidirectional-live-1786137154835",
  "candidate_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml",
  "candidate_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v27",
  "candidate_profile_fingerprint": "c671c7aaedbd357d44b935eec8f725235d6751521ab53d6d4e04f63f55665a33",
  "candidate_file_sha256": "bc8997972d07daf0a44c722d5c1800e00e802e271e84d3e8b06f2a7e10093698",
  "candidate_run_fingerprint_observe": "1d338071b1b01005afc5abf8095023db4aad65fd15d2487d165355a381efc67f",
  "prechange_bundle": "data/backups/bidirectional_cohort/prestart_20260808T042806.773285Z_c671c7aaedbd",
  "prechange_manifest_sha256": "40c64167bbac8a6f5742e14aea5a6e1136064eaa71026b25a1a53da2a52f7fa3",
  "implementation_file_count": 1247,
  "implementation_sha256": "e368fbf513cf51296b9ff7b7da18f621b4b9b0edc30d4d751f78b6c726f96138",
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
  "provider_recipe_exit_policies": {
    "hulk_expansion_bidirectional_tuned_v2": "ignore",
    "range_onset_bidirectional_v1": "ignore",
    "hypervelocity_source_follow_bidirectional_5m_v1": "ignore",
    "hype_breakout_onset_bidirectional_v1": "ignore",
    "eth_breakout_precompression_pullback_bidirectional_v1": "ignore",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2": "ignore",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1": "ignore",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1": "ignore",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1": "ignore"
  },
  "observe_only_scope": [],
  "maximum_positions": 9,
  "one_position_per_asset": true,
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed config byte, source identity, route, risk setting, bundle, or
namespace invalidates this contract. Generate a new candidate instead of
launching a nearby profile.

## Repair boundary

V27 contains four mechanical repairs relative to the running v25 process:

1. HIP-3 breakout-pressure providers select the newest exact-symbol L2 book at
   or before the causal cutoff, retain the 30-second freshness limit, and
   reject future books.
2. HIP-3 Swing/HA readiness serializes the finite numeric direction states
   actually consumed by entry eligibility.
3. HIP-3 Swing/HA provider evaluations retain typed `exit_sides` and
   `exit_reason` values for `hip3_swing_ha_flip`,
   `hip3_swing_alignment_loss`, and `hip3_swing_gap_recovery`. Under v27's
   explicit `ignore` policy, these values remain telemetry and do not alter the
   timer, venue stop, target, manual-command, or selected-opposite-entry paths.
4. The bound execution plan, configuration-generation evidence, open-trade
   reflection, friction-parity contract, and TUI all publish the exact
   `provider_recipe_exit_policy`. Missing legacy fields resolve to `ignore`;
   unknown values fail closed.

The dormant `honor` implementation is lifecycle-bound and durable so it can be
tested without silently changing the selected strategy. Only a future profile
that explicitly declares `honor` may append a `provider_exit_decision`; the
decision is bound to the same entry OID, provider, symbol, and side. A stale
pre-entry event, future event, different provider, different side, or different
lifecycle cannot close the position. V27 must not append a
`provider_exit_decision` from a report-only one-bar exit.

V26 and v27 parse identically after removing only the profile field. Their
configured economic strategy is unchanged because both resolve recipe exits to
`ignore`. The new mechanism improves telemetry fidelity and makes future
authority explicit; it does not establish profitability or promote `honor`.
The bounded challenger in
`docs/research-journal/hip3-signal-exit-lifecycle-v1.json` materially degraded
both Swing routes and the index Breakout route after modeled friction, so direct
execution remains rejected pending contradictory forward evidence.

## 1. Verify active v25 ownership

Require a fresh file timestamp plus this exact predicate:

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

Open v25 lifecycles remain governed by their loaded v25 code. Their
venue-native stops and targets must remain present. Do not infer that staging
v27 hot-patched them.

## 2. Drain without forcing an exit

Only after explicit operator authorization, select `TRANSITION DRAIN` on TUI
screen 7 and confirm the exact v25 binding. It withholds new entries while v25
continues managing open positions.

If the process is interrupted during the active drain, resume only v25:

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

After normal shutdown, preview and confirm the recoverable archive:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786137154835

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786137154835 --yes
```

Do not delete or overwrite ledgers, journals, checkpoints, orders, or backups.

## 4. Reconcile v27 without placing orders

With no live owner, publish one report-only checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Require all nine assets, `24/24` provider-symbol coverage, both sides, nine
slots, no inherited exposure, no open owned orders, and exact v27 identity.
This command has no execution authority.

## 5. Explicitly launch v27

Only after renewed approval at the verified flat boundary:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml \
  --enabled --i-accept-live-risk
```

Verify the exact new startup bundle printed by the backend:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-v27-path>
```

Attach another read-only cockpit only after v27 owns the backend:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml
```

## Runtime acceptance

Before interpreting economic outcomes, require:

- exact v27 identity in ledger, checkpoint, and TUI;
- `24/24` setup coverage, all nine assets, both sides, and unchanged routes;
- `running_consistent`, fresh heartbeat/venue reads, and zero faults;
- no inherited exposure, duplicate lifecycle, stale intent, namespace drift, or
  missing venue-native stop;
- numeric HIP-3 L2/readiness inputs when their causal sources are present;
- a completed HIP-3 Swing/HA exit publishes the exact typed `exit_sides`,
  `exit_reason`, provider, symbol, side, and decision time as report-only
  telemetry;
- configuration, bound open plan, friction parity, and TUI all report
  `provider_recipe_exit_policy=ignore` for every v27 provider;
- an ignored recipe exit leaves the lifecycle open under its existing exit
  contract and must not append a `provider_exit_decision`;
- focused dormant-mechanism tests prove that an explicit `honor` contract would
  append once, replay the one-bar exit after restart using a fresh mark, and
  reject a mismatched provider/entry/side with no cross-provider close;
- fills, fees, funding, slippage, acknowledgement latency, liquidation price,
  MFE/MAE, exits, and missed opportunities remain backend-authored.

Missing source data can correctly produce unavailable telemetry. Performance,
drawdown, and frequency are reported trial results rather than implicit gates.
Technical identity, authority, source causality, ownership, or protection
failures remain fail-closed.

## Rollback

There is no hot rollback. Preserve every v27 lifecycle under its recorded
contract. At a later explicit, drained, verified flat/order-free boundary,
archive v27, create a fresh backup, and launch v25 only with renewed authority:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --enabled --i-accept-live-risk
```

Never restore older ledgers or journals over newer evidence.

## Confidence and falsifiers

- High confidence — config isolation: v26/v27 differ only in profile identity,
  all nine provider policies resolve to `ignore`, and the runbook binds routes,
  files, and source bytes.
- High confidence — dormant mechanism behavior: lifecycle binding, durable
  replay, idempotence, and conflict rejection have focused tests. This proves
  mechanism safety, not permission to use it.
- Unverified end-to-end confidence: v25 has not loaded these telemetry changes.
  A real v27 HIP-3 signal is required to validate that `ignore` is displayed and
  honored without a close.
- Medium-high rejection confidence — direct `honor`: validation-stress
  challengers materially worsened both Swing routes and index Breakout. A
  shared-account, profile-matched forward sample with better after-cost profit
  factor and drawdown would update that rejection.
- Low strategy-economic confidence: these repairs do not establish edge.

The v27 contract is falsified by any recipe-signal close or
`provider_exit_decision` under `ignore`, missing policy telemetry, cross-provider
close, missing protection, or config/risk drift. Dormant mechanism safety is
falsified by a duplicate decision, stale/future execution, wrong exit reason,
or loss of an explicitly honored one-bar exit after restart. Economic
confidence updates only from profile-matched forward outcomes after actual
fees, funding, slippage, and missed-opportunity accounting.
