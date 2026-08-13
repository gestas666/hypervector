# Cohort v25 to telemetry-repair v26 transition and rollback

This procedure assigns the already-staged HIP-3 causal-L2 and numeric-readiness
repairs to a distinct live generation. It does not change strategy, risk,
sizing, execution scope, leverage, stops, targets, or maximum holds. It does
not authorize a silent restart. V25 must first drain, reconcile flat and
order-free, and archive its transition marker.

## Frozen contract

- current profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`
- current run: `bidirectional-live-1786137154835`
- current fingerprint:
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`
- candidate profile: `multi_asset_bidirectional_complete_portfolio_canary_v26`
- candidate fingerprint:
  `2e5a46960175f90d41b9f415d3f10a49a46532d50e429581c1e4224bf8e4701c`
- verified credential-free source baseline:
  `data/backups/bidirectional_cohort/prestart_20260808T023732.159368Z_2e5a46960175`
- implementation identity:
  `0864f9a5c09b2d71462268c97e0fa01e8b5001147ce0573600bd9871c3527e09`
  across 1,243 implementation files

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
  "current_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
  "current_profile_fingerprint": "ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc",
  "current_file_sha256": "362763638541baf75d5121f0b59e1afc8091bda7aaa1aaea0f8b42aead3c3bdd",
  "current_run_id": "bidirectional-live-1786137154835",
  "candidate_path": "configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml",
  "candidate_profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v26",
  "candidate_profile_fingerprint": "2e5a46960175f90d41b9f415d3f10a49a46532d50e429581c1e4224bf8e4701c",
  "candidate_file_sha256": "e45dc9e686101debaaf7c2098887ed48cadf3091afa8fab14901211d51afbf0e",
  "candidate_run_fingerprint_observe": "3398faa2132d9c39eb3d4a8079a22a2a7cc791d395fbb713f4bb33b4dbf39000",
  "prechange_bundle": "data/backups/bidirectional_cohort/prestart_20260808T023732.159368Z_2e5a46960175",
  "prechange_manifest_sha256": "ad983fa184e91d8ef1b5a52822c5bd1d263b36a60a8aeef58ccb0efbf7bf2198",
  "implementation_file_count": 1243,
  "implementation_sha256": "0864f9a5c09b2d71462268c97e0fa01e8b5001147ce0573600bd9871c3527e09",
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

Any changed config byte, fingerprint, route, risk parameter, implementation
identity, or namespace invalidates this contract. Regenerate and review the
contract instead of launching a nearby profile.

## Repair boundary and economic claim

V26 contains two mechanical evidence repairs:

1. HIP-3 breakout-pressure providers select the newest exact-symbol L2 book at
   or before the causal cycle cutoff, while preserving the 30-second freshness
   limit and future-book rejection.
2. HIP-3 Swing/HA readiness accepts finite Python, NumPy, and Decimal numeric
   direction states, so the values used by eligibility are also serialized.

V25 and v26 parse identically after removing only the profile field. Every one
of the 24 provider-symbol routes remains bidirectional, every asset remains
isolated 5x, and all sizing and lifecycle policies remain unchanged. These
repairs improve telemetry correctness; they do not establish economic edge.

## 1. Verify current v25 ownership

Require a fresh checkpoint, exact v25 identity, zero faults, observed venue
state, and the recorded live run:

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

Also require a recent file timestamp relative to the wall clock. The JSON
predicate alone does not prove freshness.

## 2. Drain v25 without forcing an exit

Only after explicit operator authorization, use TUI screen 7 to select
`TRANSITION DRAIN`, inspect its exact v25 run binding, and confirm. The drain
withholds new entries while v25 continues to manage SOL, GOLD, or any later
open lifecycle through its original timers, funding, and venue-native orders.

If interrupted during an active drain, resume only the exact v25 profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml
```

## 3. Prove flat/order-free and archive v25

Wait for every asset to be terminal, flat, order-free, fault-free, and for the
drain to complete:

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

After normal v25 shutdown, preview and then confirm the recoverable archive
against the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786137154835

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id bidirectional-live-1786137154835 --yes
```

Do not delete or overwrite ledgers, journals, checkpoints, stops, orders, or
backups.

## 4. Reconcile v26 without placing

With no live owner, publish one report-only checkpoint using the exact staged
profile:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Require all nine assets, all 24 routes, both sides, nine shared slots, flat
venue positions, no owned orders, and no inherited exposure. This checkpoint
has no execution authority.

## 5. Explicitly launch v26

Only after approval at the verified boundary:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml \
  --enabled --i-accept-live-risk
```

Startup must acquire singleton ownership, reconcile venue state, and create a
new verified pre-start backup before constructing authenticated clients. Verify
the exact startup bundle printed by the backend:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-v26-path>
```

Attach a separate read-only cockpit only after v26 is active:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml
```

## Runtime acceptance

Before interpreting any v26 outcome, require:

- exact v26 identity in ledger, checkpoint, and TUI;
- `24/24` setup coverage, all nine assets, both sides, and the unchanged route
  and sizing maps;
- `running_consistent`, fresh heartbeat and venue samples, and zero faults;
- no inherited exposure, duplicate lifecycle, namespace drift, stale intent,
  or missing venue-native stop on an open position;
- the first completed HIP-3 breakout-pressure decision with a fresh causal exact-symbol book
  shows numeric `L2 IMB10`, not `N/A`;
- the first completed HIP-3 Swing/HA decision shows numeric `HA COLOR` and
  numeric `ORDER BLOCK` whenever those eligibility inputs are numeric;
- the same raw numeric values appear in ledger metrics and TUI indicators, and
  eligibility/blockers agree with those values;
- fills, fees, slippage, funding, liquidation price, MFE/MAE, exits, and missed
  opportunities remain backend-authored and journaled.

Missing source data may still correctly produce `N/A`; the repair is falsified
only when a fresh causal input exists but telemetry is unavailable or
contradictory. Performance and frequency remain trial results, not implicit
abort gates. Technical identity, authority, or protection failures remain
fail-closed.

## Rollback

There is no hot rollback. Preserve every v26 lifecycle under its recorded
contract. At a later verified flat/no-owned-order boundary, complete and
archive a v26 drain, create a fresh verified backup, and explicitly launch:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml \
  --enabled --i-accept-live-risk
```

Never restore older ledgers or journals over newer evidence.

## Confidence and falsifiers

- **High confidence — configuration isolation:** parsed v25/v26 parameters are
  identical except for profile identity, and the runbook test binds the exact
  file hashes and route map.
- **High confidence — unit-level repair behavior:** causal L2 cutoff/freshness
  and Decimal/NumPy telemetry paths have focused regression coverage.
- **Unverified end-to-end confidence:** the running v25 process predates these
  loaded-code repairs; the first completed v26 HIP-3 decisions are required.
- **Low strategy-economic confidence:** neither repair demonstrates positive
  after-friction return.

An early activation, profile drift, route/risk drift, duplicate exposure,
missing protection, causal-book telemetry remaining unavailable, eligibility
and display disagreement, or ledger/TUI identity mismatch falsifies the
corresponding acceptance claim.
