# Cohort v25 to evidence-selected v29 transition and rollback

> **Retired transition target — do not execute this guide.** Append-only
> research revision 7 retired exact v29 after its route concentration,
> incomplete side evidence, negative components, fresh sparse live boundary,
> and frozen implementation identity were reconciled. Preserve this guide for
> audit and rollback history. A future transition requires a new candidate,
> new source baseline, new transition contract, and renewed explicit live-risk
> authorization.

V29 was an inactive five-asset live-research candidate. It narrows the complete
v25 portfolio to six explicitly selected provider-symbol routes while retaining
both long and short capability and one position per asset. It is not a
profitability-promoted portfolio.

The immutable checkpoint snapshot at `2026-08-08T16:27:10.446058+00:00`
showed v25 running consistently with zero faults. BTC, SOL, xyz:GOLD, and xyz:SPCX
were open and protected by venue-native stops. V29 does not hot-patch those
lifecycles and does not authorize a restart. v25 remains active until an
explicitly authorized transition drain reaches a verified flat, order-free
boundary.

## Frozen contract

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "current_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "current_run_id": "bidirectional-live-1786182011216",
  "checkpoint_snapshot_utc": "2026-08-08T16:27:10.446058+00:00",
  "checkpoint_snapshot_evidence": "data/logs/research/bidirectional_cohort/v25_transition_readiness_bidirectional-live-1786182011216_20260808T162644Z.json",
  "checkpoint_snapshot_evidence_sha256": "02f5baaf9292bf368aa6d5466cfc6082c2d24199bf9f05ad730f34bdb901ef82",
  "protected_open_assets_at_snapshot": [
    "BTC",
    "SOL",
    "xyz:GOLD",
    "xyz:SPCX"
  ],
  "candidate_path": "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml",
  "candidate_profile_id": "multi_asset_bidirectional_evidence_selected_portfolio_canary_v29",
  "candidate_profile_fingerprint": "d1f4cd3b03197e9e7a9899ab32e2b198fd4bd2a4117f1ea64261824fcdc4a393",
  "candidate_file_sha256": "bb62f0cd492bfeb332fd6e53cdd2a45205f3e7b6580fc5f18768ddecee3b40e1",
  "candidate_run_fingerprint_observe": "072bcf4d8a74d987ee2c9c8475029fe691d235b387aff70ac1eaefd399d8e976",
  "prechange_bundle": "data/backups/bidirectional_cohort/prestart_20260808T163708.093622Z_d1f4cd3b0319",
  "prechange_manifest_sha256": "ee60373354d57b28ac6507dcd559781e8aba673ee8f03ed1e919ead3d103793b",
  "implementation_file_count": 1257,
  "implementation_sha256": "914c62b7efaa5b8d18d6833c79299ecfb3a3f84f9f6000d23f129e34da5d068a",
  "research_record": "docs/research-journal/evidence-selected-portfolio-v29-v6.json",
  "research_record_sha256": "10a046b0f0e400a5386f498869d848066e2d30816eb7bee1bcdce1eeb33d6a1d",
  "research_revision_id": "48065e346de21ffb45e7d58de7e4c2de4173966755480214283e3db16805321e",
  "common_window_evidence": "data/logs/research/evidence_selected_portfolio_v29_common_window_20260808T080301Z.json",
  "common_window_evidence_sha256": "9a203016eafc66815a762396367929485f442413cac959852add6412a33bb763",
  "execution_scope": [
    "range_onset_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|SOL",
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
    "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:GOLD"
  ],
  "observe_only_scope": [],
  "maximum_positions": 5,
  "one_position_per_asset": true,
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed profile byte, route, side, risk parameter, research record, or
backup identity requires a new candidate and contract.

## Evidence boundary

V29 has six executable routes and no observe-only filler:

- ETH Range Onset uses the symmetric `dual_mtf_not_opposed` context policy,
  a 60-bps stop, and a 48-hour maximum hold.
- SOL Range Onset retains its 60-bps stop and 48-hour maximum hold.
- ETH precompression pullback uses a 60-bps stop and 12-hour maximum hold.
- SPCX Swing/HA, SP500 breakout pressure, and GOLD Swing/HA use fixed 80-bps
  stops and 24-hour maximum holds.

Every provider and asset retains both long and short. The ETH and SOL routes
have the stronger historical basis. HIP-3 remains contradictory live research:
the selected per-symbol validation/stress slices were positive, but development
or one directional slice was negative. V29 therefore has low-to-medium
economic confidence.

The append-only revision 3 records the first relevant v25 forward boundary:
one selected SPCX lifecycle closed at a loss, selected ETH and GOLD lifecycles
remain open with negative marked net PnL, and the other three selected routes
have no eligible event in that run. This sparse mixed evidence leaves v29
inactive and unchanged; it neither proves nor disproves portfolio edge.

The append-only revision 4 closes the missing shared-account diagnostic with
all six routes, configured provider priority, one position per asset, and the
five-position ceiling. Nominal modeled friction produced 560 accepted and 41
rejected lifecycles, +12.19% from $500, PF 1.51, and 2.00% realized-equity
drawdown. Stressed HIP-3 friction produced 562 accepted and 41 rejected
lifecycles, +11.06%, PF 1.45, and 2.51% drawdown. Every rejection was an ETH
same-asset conflict; concurrency peaked at four and there were no position-cap
or insufficient-capital rejections.

The aggregate is not broad proof of edge. SOL Range Onset supplied 65.76% of
positive nominal route PnL and 69.72% under stress, exceeding the recorded
winner concentration falsifier. SP500 breakout pressure and GOLD Swing/HA were
negative in both scenarios. The opened source windows differ by route, private
IOC fills remain unproven, and the sealed HIP-3 holdout was not accessed. V29
therefore remains inactive and unchanged pending explicit review; revision 4
does not authorize a drain, restart, route change, or order mutation.

The append-only revision 5 removes the unequal-calendar comparison by applying
all six routes to one 22.36-day common entry window before priority
arbitration. Nominal friction produced 97 accepted and three rejected
lifecycles, +3.30% from $500, PF 1.52, and 1.50% realized-equity drawdown.
Stressed friction produced 98 accepted and three rejected lifecycles, +2.73%,
PF 1.40, and 1.59% drawdown. The one additional stressed SPCX short is an
explicit friction-path effect: changed lifecycle timing freed the symbol for a
later entry; it is not hidden source drift.

The common-window aggregate remains concentrated rather than broad. SPCX
Swing/HA supplies 65.48% of positive nominal route PnL and 62.34% under stress;
its long side is strongly positive while its short side is negative. ETH
precompression pullback and SP500 breakout pressure are negative in both
scenarios. The overlap contains only two SOL Range Onset longs and no SOL Range Onset shorts.
Revision 5 therefore leaves v29 inactive and unchanged:
it supports a narrower SPCX-long mechanism investigation, not automatic
promotion of the complete six-route portfolio.

The append-only revision 6 refreshes the inactive candidate's implementation
baseline around the tested pressure-clock ordering repair. It leaves revision
5's economic decision, six-route scope, risk, and inactive status unchanged.
The current v25 process predates the repair and remains untouched. Its 244
historical pressure metric-value gaps are preserved as evidence; revision 6
does not backfill historical gaps or infer pressure after the fact. A future
process must establish live parity from new causal observations.

## 1. Verify active v25 ownership and protection

Use a fresh checkpoint. Do not rely on the frozen snapshot alone:

```bash
jq -e '
  .lifecycle.state == "running_consistent" and
  .audit.health.faults == 0 and
  .audit.run.run_id == "bidirectional-live-1786182011216" and
  .audit.run.profile_id ==
    "multi_asset_bidirectional_complete_portfolio_canary_v25" and
  .audit.run.profile_fingerprint ==
    "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc" and
  .configuration_generation.matches_runtime == true and
  ([.audit.health.assets[] |
    (.final_state != "OPEN") or .protected_if_open == true] | all)
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

Staging v29 cannot replace BTC, SOL, xyz:GOLD, or xyz:SPCX execution plans,
stops, or maximum-hold ownership while those v25 lifecycles remain open.

## 2. Request TRANSITION DRAIN only with explicit authority

On TUI screen 7, select `TRANSITION DRAIN`, inspect the exact v25 binding, and
confirm only after explicit operator authorization. The drain withholds new
entries while v25 continues its existing exits and protection.

If the backend is interrupted during an active drain, recover only the same
v25 profile:

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

After normal shutdown, preview and explicitly archive the completed drain:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786182011216

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786182011216 --yes
```

Never delete or overwrite the ledger, checkpoint, journal, or backup.

## 4. Reconcile v29 without placing orders

With no live owner, publish one report-only checkpoint:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Require five assets, six executable routes, zero observe-only routes, both
directions on every provider, five slots, no inherited exposure, and no owned
open orders.

## 5. Archived launch procedure — not authorized

Do not execute this procedure under revision 7. It is retained solely to prove
what the retired contract would have launched. A new candidate requires its
own guide and renewed authorization at a verified flat boundary.

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml \
  --enabled --i-accept-live-risk
```

The archived procedure required verifying the startup bundle printed by the
backend with
`scripts/cohort_prestart_backup_verify.py`. The pre-change bundle in this guide
does not replace the mandatory startup backup.

## Runtime acceptance

- Ledger, checkpoint, and TUI identities match exact v29 bytes.
- Coverage is 6/6 executable routes with zero observation-only routes.
- Every route accepts both long and short; each asset permits one position.
- Every open position has a venue-native stop and its exact provider exit plan.
- Heartbeats, venue reads, L2, fills, fees, funding, slippage, liquidation,
  MFE/MAE, and missed opportunities remain backend-authored.
- A fresh new-run audit does not report `provider_metric_telemetry_missing`
  for an applicable HIP-3 evaluation when a causal in-window book exists.
- That applicable evaluation records numeric pressure_age_seconds and numeric imbalance_10
  from the causal in-window book; it does not backfill historical gaps.
- Performance remains a performance result rather than an implicit abort condition;
  drawdown, cadence, and regime alignment are likewise reported evidence.

Technical identity, source-causality, ownership, or protection failures remain
fail-closed. Economic losses are journaled and reviewed; they do not silently
rewrite the running strategy.

## Rollback

No hot rollback is permitted. Preserve every v29 lifecycle under its recorded
contract. At a later explicitly authorized, drained, flat and order-free
boundary, archive v29, create and verify a new backup, then launch a separately
approved prior or successor profile with renewed live-risk flags. Never restore
an older ledger over newer evidence.

## Confidence and falsifiers

- High confidence: profile, route, side, risk, and backup identities are
  machine-verifiable.
- Medium confidence: v29 removes mappings with the clearest negative evidence
  while retaining bidirectional and multi-market research coverage, and its
  fixed-cap arbitration is feasible in the opened sample.
- Low-to-medium confidence: the portfolio will be profitable; HIP-3 lacks live
  parity, two common-window routes are negative, SOL direction coverage is
  incomplete, and the positive common-window replay is materially concentrated
  in SPCX Swing/HA longs.

The transition is falsified by identity drift, an unexpected route or side,
unprotected or duplicated exposure, inherited orders, source staleness, or
reconciliation disagreement. The economic hypothesis is updated by fresh
after-cost live evidence through a new journal revision.
