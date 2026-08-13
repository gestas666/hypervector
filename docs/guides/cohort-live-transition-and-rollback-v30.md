# Inactive v25-to-v30 transition and rollback contract

This guide prepares the lean v30 candidate without activating or staging it.
v25 remains active and owns every current lifecycle and venue protection. This
document does not authorize a restart, drain, order, close, profile switch, or
live execution.

<!-- cohort-transition-contract:start -->
```json
{
  "current_run_id": "bidirectional-live-1786182011216",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "candidate_profile_id": "multi_asset_bidirectional_lean_successor_canary_v30",
  "candidate_profile_fingerprint": "4cb3ca7905b8d5817066cc7f4cdb5e28f04f93ce298c55fe34d96d5065eecf54",
  "candidate_run_fingerprint_observe": "eee2b798be090ebfa99a21df2d2430925d3bb5906216f850e20f1b7ae237dbc7",
  "candidate_file": "configs/multi_asset_bidirectional_lean_successor_canary_v30.toml",
  "candidate_file_sha256": "303c8e9ae1c8947481ab64e2894cffb964c9de4b17811bb44ae6d8ce9dd3d81c",
  "execution_scope": [
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
    "range_onset_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|SOL"
  ],
  "maximum_positions": 3,
  "research_revision_id": "a97034d76756d80a7ae18e6765ea2e91b2d828f331ec4ea962c5d6ed9e39c9ef",
  "research_record": "docs/research-journal/lean-successor-portfolio-v1.json",
  "research_record_sha256": "088f49e6271b7e8a6fc74f852d119f08305fda307d39dfccede5dc0722e2860d",
  "comparison_artifact": "data/logs/research/lean_successor_portfolio_comparison_20260809T161609Z.json",
  "comparison_artifact_sha256": "a507537566cacb1a256e61f5f70abc8a5f0212514787e93367a8ef5727127bee",
  "candidate_active": false,
  "transition_authorized": false,
  "flat_and_order_free_verified": false,
  "transition_readiness_snapshot": null,
  "prechange_bundle": null
}
```
<!-- cohort-transition-contract:end -->

## Candidate scope

V30 contains three executable mappings and no execution filler:

- SOL Range Onset, long and short;
- ETH Range Onset with `dual_mtf_not_opposed`, long and short;
- SPCX Swing/HA, long and short.

It uses one position per asset, three portfolio slots, 5x isolated leverage,
fixed `$75/$25/$75` notionals, venue-native protective stops, and the existing
provider-exit `ignore` policy. Strategy performance remains a reported
performance result rather than an implicit abort condition.

## Why the candidate is inactive

The full opened stressed comparison produced 171 trades, `+$58.62`, PF `2.02`,
and 2.35% realized-equity drawdown. The shorter stressed development and opened
final windows were also positive, but both became slightly negative after
removing their largest winner. Confidence is therefore low-medium: sufficient
for a bounded next live-research canary, insufficient for an established-edge
claim or automatic promotion.

## 1. Preserve active v25

Until every v25 lifecycle resolves, do not stage v30, replace the profile file,
restart the backend, or adopt positions under another generation. A fresh
checkpoint must show that every open position remains protected and that the
runtime identity is still v25.

## 2. Request transition drain only after explicit authorization

The transition drain withholds new entries but preserves existing exits and
venue stops. If an authorized drain is interrupted, resume only the same v25
profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml
```

## 3. Require a new verified flat-and-order-free boundary

Before v30 can be considered for launch, a fresh checkpoint must prove:

- every asset is flat or stopped;
- every signed position size is zero;
- every owned open-order list is empty;
- no source-health fault exists;
- the completed v25 drain is archived without deleting its ledger; and
- the live venue agrees with the local ledger.

The current contract intentionally leaves `transition_readiness_snapshot` and
`prechange_bundle` null. They must be created at that future boundary rather
than copied from an older profile transition.

## 4. Verify v30 without live authority

With no live owner, publish a report-only candidate checkpoint and require the
exact profile fingerprint, three routes, both long and short authority, three
slots, zero inherited positions, and zero owned orders:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_lean_successor_canary_v30.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Create and verify a new prestart backup with the existing backup utilities.
The configuration, implementation bundle, research revision, comparison
artifact, flat checkpoint, and venue reconciliation must all be bound into the
future transition revision.

## 5. Launch template requiring renewed authority

The following is a template, not current authorization. Execute it only after
the preceding evidence exists and the operator again explicitly accepts live
risk:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_lean_successor_canary_v30.toml \
  --enabled --i-accept-live-risk
```

Verify the printed startup backup before accepting any new entry.

## Rollback

No hot rollback is permitted while v30 owns a position or protective order.
If v30 later runs and a rollback is requested:

1. activate a generation-bound transition drain;
2. retain every venue stop while positions resolve;
3. prove verified flat-and-order-free venue and ledger state;
4. archive the completed v30 run and create another prechange backup;
5. select a preserved profile explicitly; and
6. require fresh `--enabled --i-accept-live-risk` authority.

Do not copy an old staged profile, position checkpoint, order identity, or
implementation hash into the rollback generation.
