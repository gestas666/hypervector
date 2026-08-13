# Cohort live transition and rollback — inactive v32 candidate

This document is a fail-closed transition contract. It does not authorize a
restart, a drain, an order, a profile switch, or live execution. V25 remains
active. V31 is superseded as the proposed successor but remains immutable
historical evidence.

Contract shorthand: v25 remains active; v31 is superseded.

<!-- cohort-transition-contract:start -->
```json
{
  "schema_version": 1,
  "report_only": true,
  "execution_authority": "none",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "candidate_profile_id": "multi_asset_bidirectional_commodity_swing_retired_candidate_v32",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "candidate_profile_fingerprint": "6c14d3a11e55f2e63175036e4f50cfa4c1404d570fe2e37558084affb6785cf3",
  "candidate_run_fingerprint_observe": "610bebe7c03afe8f3f24d6d73fffa8d833c25942bcef77fb1bceee1fccc79e9f",
  "current_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "candidate_file_sha256": "df1cd68c8e8c86a635e5c6763eb0231b6e40156b8d0eb86f855bd2b88a4546cb",
  "research_revision_id": "482feff06a142dcd4a906c58be1f49b0e42df3f71cd1469838c6fe56fedec2a5",
  "research_record_sha256": "5630aefd980fdef8984d7a49ca9ed1b85a694370b69a7f14f1ef0c1d8e8a98f5",
  "candidate_active": false,
  "transition_authorized": false,
  "flat_and_order_free_verified": false,
  "transition_readiness_snapshot": null,
  "prechange_bundle": null,
  "maximum_positions": 9,
  "post_start_acceptance_ready": true,
  "route_forward_tracking_ready": true,
  "route_forward_tracker_active": false,
  "route_forward_baseline_phase": "pretransition_v25_baseline",
  "route_forward_snapshot": "data/runtime/bidirectional_cohort/latest_v32_route_forward.json",
  "route_forward_change_journal": "data/logs/research/bidirectional_cohort/v32_route_material_changes.jsonl",
  "execution_scope": [
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SPCX",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SP500",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "hulk_expansion_bidirectional_tuned_v2|ETH",
    "hulk_expansion_bidirectional_tuned_v2|HYPE",
    "hulk_expansion_bidirectional_tuned_v2|SOL",
    "hype_breakout_onset_bidirectional_v1|BTC",
    "hype_breakout_onset_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|HYPE",
    "hype_breakout_onset_bidirectional_v1|SOL",
    "hypervelocity_source_follow_bidirectional_5m_v1|BTC",
    "range_onset_bidirectional_v1|BTC",
    "range_onset_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|HYPE",
    "range_onset_bidirectional_v1|SOL"
  ],
  "observe_only_scope": [
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:BRENTOIL",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:GOLD",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK"
  ],
  "readiness_blockers": [
    "current v25 portfolio is not flat",
    "fresh flat and order-free snapshot is absent",
    "prechange backup is absent",
    "continuous v32 route-forward tracker is not active",
    "explicit v32 live-risk authorization is absent"
  ]
}
```
<!-- cohort-transition-contract:end -->

## Current authority boundary

V25 remains active and owns its current positions and venue-native protection.
The v32 file is only an inactive profile description. The v31 report-only
tracker remains attached to v31 and is not evidence that v32 is ready.

V32 observes every commodity Swing symbol in both long and short directions,
but that provider has no execution symbols. All other route authority remains
exactly as listed in the machine-readable contract. The portfolio still allows
one position per asset and up to nine different assets concurrently.

## Required pre-transition evidence

No transition may begin until all of the following are true in one fresh,
identity-bound snapshot:

1. Every configured asset is flat and no owned entry, stop, target, or close
   order remains at the venue.
2. The active ledger reports `transition_drain.status == "completed"` for the
   exact v25 run and profile fingerprint.
3. `scripts/cohort_transition_drain_archive.py` publishes the immutable drain
   archive and its hashes reconcile to the stopped v25 ledger.
4. `scripts/cohort_prestart_backup_verify.py` validates a recoverable,
   immutable prechange bundle containing the v25 config, ledgers, checkpoint,
   launch definition, environment-key names without values, and rollback
   instructions.
5. Placement-free reconciliation succeeds under the candidate identity before
   any live arm. If a drain process is interrupted, only
   `--resume-transition-drain` may resume its exact identity.
6. The operator separately supplies both `--enabled --i-accept-live-risk` for
   the exact v32 command after reviewing the new readiness artifact.

This document records requirements; it does not authorize a restart.

## Post-start technical acceptance

The first completed HIP-3 breakout-pressure evaluation must prove causal,
finite depth-ten imbalance, book age within the declared 30-second maximum,
and funding-cursor continuity. Historical v25 metric gaps remain attributed to
v25 and cannot be relabeled as complete.

The v31 identity remains isolated: its validators continue rejecting v32 by
design. The combined v32 verifier is now implemented at
`scripts/v32_acceptance.py`. It binds the checkpoint to the exact v32 profile
and fingerprint, the 21 executable and three observe-only route scopes, the
exact journal SHA-256, protected open positions, complete provider metrics,
causal pressure books, and contiguous funding cursors.

Run it only after the first completed v32 HIP-3 breakout-pressure evaluation:

```bash
uv run python scripts/v32_acceptance.py
```

The immutable bundle contains separate `v32_poststart_acceptance_v1` and
`v32_raw_ledger_acceptance_v1` decisions. An exit status 2 is returned when either
component rejects. The command is report-only, imports no order client, and
has no execution or transition authority. `post_start_acceptance_ready: true`
means the exact verifier path exists and its isolation tests pass; it does not
mean v32 has started, its future evidence has accepted, or transition is
authorized.

## Route-forward tracking readiness

The v32 tracker has a separate bounded snapshot and hash-chained material
journal. The first report-only baseline was captured against active v25 as
`pretransition_v25_baseline`; it does not claim v32 fills or counterfactual
execution. Refresh the exact baseline without starting a persistent service:

```bash
uv run python scripts/v32_route_forward_monitor.py --once
```

Material changes append to
`data/logs/research/bidirectional_cohort/v32_route_material_changes.jsonl`;
timestamp-only and evaluation-count-only refreshes are deduplicated. The v31
tracker and journal remain separate. `route_forward_tracking_ready: true`
means the v32 publisher, monitor, and chain validator exist and pass tests.
`route_forward_tracker_active: false` records that no new continuous process
has been started; the existing v31 and live processes were not restarted.

## Rollback

No hot rollback is permitted. If v32 later starts and must be rolled back, stop
new entries, retain venue-native protection, drain the exact v32 run, prove all
assets flat and order-free, archive the drain, verify the v25 backup, reconcile
without placement, and require fresh explicit live-risk authorization before
starting v25 or another profile. Both long and short observation history and
the one position per asset invariant must survive the rollback boundary.
