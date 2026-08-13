# Cohort v14 to v21 live transition and rollback

This procedure prepares an inactive evidence-routed generation. It does not
authorize a current transition. v21 keeps three executable mappings and adds the
bounded breakout retest on all four assets strictly as prospective observation.
It does not establish edge.

## Frozen contract

- current profile: `multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14`
- current fingerprint:
  `e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900`
- candidate profile:
  `multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21`
- candidate fingerprint:
  `0b0d4a841241f60814eef68fb52adcf93fb323744978f7427ec8372a819518a0`

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml",
  "current_profile_id": "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14",
  "current_profile_fingerprint": "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900",
  "current_file_sha256": "f6098f1f553a81b6731eb5d5e0897c96b7da8c3bc25295a276d9cbed44c2e007",
  "candidate_path": "configs/multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21.toml",
  "candidate_profile_id": "multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21",
  "candidate_profile_fingerprint": "0b0d4a841241f60814eef68fb52adcf93fb323744978f7427ec8372a819518a0",
  "candidate_file_sha256": "4c84d6f3b1c29c5d188342572ae056527e8cce1234a8c8906a121d40e98a7995",
  "v1_source_sha256": "3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d",
  "v2_source_sha256": "3f02ae7051ebcc3791e97b155d7f0ea4df77870eab2ccc84c087994b60027121",
  "v2_policy_sha256": "cf0edd6d96fd06fc39db7e9db3d9eab80564f38f5f75976f0703a9a4207fc189",
  "eth_source_sha256": "11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497",
  "execution_scope": [
    "hulk_expansion_bidirectional_tuned_v2|BTC",
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "hype_breakout_onset_bidirectional_v1|HYPE"
  ],
  "retest_observe_only_scope": ["BTC", "ETH", "SOL", "HYPE"],
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed byte, fingerprint, source hash, execution route, or retest execution
symbol invalidates this generation. Regenerate and review it rather than using a
nearby profile.

## 1. Verify current v14 ownership

Require a fresh checkpoint, exact v14 identity, zero faults, and observed venue
portfolio:

```bash
jq -e '
  .lifecycle.state == "running_consistent" and
  .audit.health.faults == 0 and
  .audit.run.profile_id ==
    "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14" and
  .audit.run.profile_fingerprint ==
    "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900" and
  .configuration_generation.matches_runtime == true and
  .venue_portfolio.status == "observed"
' data/runtime/bidirectional_cohort/latest_checkpoint.json
```

A successful query proves only that snapshot. Staleness, a fault, an identity
mismatch, or venue reconciliation failure stops the procedure.

## 2. Drain v14 only after explicit approval

On TUI screen 7, select `TRANSITION DRAIN`, inspect the exact run/profile
binding, and confirm only after current operator authorization. The drain
withholds new entries while the existing v14 process manages normal exits,
funding, timers, and venue-native stops. It must not force-close a position.

If the owning process is interrupted during an authorized drain, resume only
the frozen v14 generation:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml
```

## 3. Prove flat and archive the completed generation

Wait until every asset is terminal, position-free, order-free, and the drain is
complete:

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

After the owning backend and checkpoint writer exit normally, preview and then
confirm the recoverable archive with the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

Do not delete the marker, ledger, checkpoint, stops, journal, or backup.

## 4. Reconcile v21 without execution authority

With no live owner, generate one report-only checkpoint for the exact candidate:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --eligible-policy-forward --once
```

Require the exact v21 fingerprint, no exposure, no owned orders, observed venue
state, four asset slots, and one position per coin. Retest v2 remains
observe-only for BTC, ETH, SOL, and HYPE; its `execution_symbols` must remain
empty.

## 5. Start only after a new explicit authorization

The exact unified live command is recorded here for a future approved, verified
flat boundary. Do not run it merely because the file exists:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21.toml \
  --enabled --i-accept-live-risk
```

The launcher must acquire singleton ownership, reconcile the venue, and create a
new pre-start backup before constructing live clients. Verify the emitted bundle:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

An additional display attaches without backend ownership or execution authority:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21.toml
```

## Runtime acceptance

Before calling the deployment mechanically correct, require:

- exact v21 identity in ledger and checkpoint;
- `running_consistent`, zero faults, and fresh venue reconciliation;
- only Hulk/BTC, ETH-pullback/ETH, and v1-breakout/HYPE executable;
- Retest v2 remains observe-only on all four assets;
- both directions on all executable routes, isolated 5x, and recorded caps;
- four shared portfolio slots and one position per coin;
- every open position has one nonzero reduce-only stop OID;
- causal entry attribution, fill price, slippage, fees, funding, liquidation
  telemetry, MFE/MAE, exit attribution, and missed-opportunity records;
- v1 onset and v2 arm/pending/confirmation/expiration decisions in the same
  completed-bar timeline;
- no inherited exposure, stale intent, duplicate coin position, or route drift.

No economic result automatically changes live authority. Performance is a trial
result, not an implicit abort or promotion gate.

## Rollback

There is no hot rollback. Open v21 lifecycles retain their recorded execution
contracts. At a later verified flat/no-owned-order boundary, complete and archive
a v21 drain, then launch a separately approved frozen generation with a new
verified backup. Never overwrite newer ledger or journal bytes with an older
backup.

## Confidence and falsifiers

**Mechanical confidence: high** for the tested profile bytes and route
separation. **Economic confidence: low** because the executable mechanisms lack
stable prospective after-friction evidence.

The procedure is falsified by identity drift, incomplete drain, inherited venue
state, missing stop protection, duplicate coin exposure, retest execution
authority, missing observer events, or a backup mismatch. The economic
hypothesis is weakened by continued route losses or confirmed retests that
underperform expired v1 paths after attainable friction; it is strengthened only
by independent bidirectional outcomes with complete attribution.
