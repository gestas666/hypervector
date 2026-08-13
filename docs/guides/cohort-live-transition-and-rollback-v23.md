# Cohort v14 to v23 live transition and rollback

This procedure binds the authorized replacement to one exact ETH/SOL canary.
It permits a live launch only after v14 has completed a normal transition drain,
the venue is flat and order-free, the existing generation is archived, and a
fresh pre-start backup passes verification. The replay is encouraging evidence;
it does not establish durable edge.

## Frozen contract

- current profile: `multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14`
- current fingerprint:
  `e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900`
- candidate profile: `multi_asset_bidirectional_eth_sol_canary_v23`
- candidate fingerprint:
  `a5d3619c80a875a205afafef6263985f9a0b3a23061d2dc34468751acd5fe453`

<!-- cohort-transition-contract:start -->
```json
{
  "current_path": "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml",
  "current_profile_id": "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14",
  "current_profile_fingerprint": "e27a8cb63b1713e68e8bdafc3d09f4c4cbabfc27cb1af11db673f7ad18df8900",
  "current_file_sha256": "f6098f1f553a81b6731eb5d5e0897c96b7da8c3bc25295a276d9cbed44c2e007",
  "candidate_path": "configs/multi_asset_bidirectional_eth_sol_canary_v23.toml",
  "candidate_profile_id": "multi_asset_bidirectional_eth_sol_canary_v23",
  "candidate_profile_fingerprint": "a5d3619c80a875a205afafef6263985f9a0b3a23061d2dc34468751acd5fe453",
  "candidate_file_sha256": "4f335e94e6977a2a2445a93594fa584a170a3e2cfbd69db4d2387696bb918322",
  "replay_path": "data/logs/research/eth_sol_shared_canary_falsification_20260807_v1.json",
  "replay_file_sha256": "7944dd2611c3b22307b718e9dd35c9aab03831018cf6c01613c53811c381c1b0",
  "eth_source_sha256": "11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497",
  "sol_source_sha256": "2d94ee6a757a8997e2bfc0a59de14bc2324872e3b31b16fe9b89d26db73ef0e2",
  "execution_scope": [
    "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "range_onset_bidirectional_v1|SOL"
  ],
  "observe_only_scope": [],
  "requires_completed_transition_drain": true,
  "requires_flat_no_orders": true,
  "automatic_restart": false
}
```
<!-- cohort-transition-contract:end -->

Any changed byte, fingerprint, source hash, evidence hash, execution route, or
risk contract invalidates this generation. Regenerate and review the contract;
do not launch a nearby profile.

## Candidate behavior

- ETH: precompression pullback, long and short, $25 maximum notional, isolated
  5x, fixed 60-bps venue stop, no profit target, 12-hour maximum hold.
- SOL: range onset, long and short, $75 maximum notional, isolated 5x, fixed
  60-bps venue stop, no profit target, 48-hour maximum hold.
- Shared account: at most two positions, one position per symbol.
- No observer provider and no BTC or HYPE execution route exists in v23.

The immutable shared replay used $500 initial equity and fixed live-sized caps.
Development contained 312 trades, +$42.21 net, PF 1.87, and 1.20% realized
drawdown. The opened final 60 days contained 66 trades, +$6.07 net, PF 1.61,
and 0.52% realized drawdown. These figures include the replay's taker fees,
slippage, and funding but omit concurrent intratrade mark-to-market drawdown.
SOL history is twelve measured blocks with gaps, and the final ETH short slice
was approximately flat. Those limits make economic confidence medium at most.

## 1. Verify current v14 ownership

Require a fresh checkpoint, exact v14 identity, zero faults, and observed venue
portfolio before initiating a drain:

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

A successful query proves only that checkpoint. Staleness, a fault, an identity
mismatch, or venue reconciliation failure stops the procedure.

## 2. Drain v14

On TUI screen 7, select `TRANSITION DRAIN`, inspect the exact run/profile
binding, and confirm. The drain withholds new entries while v14 manages existing
positions, timers, funding, and venue-native stops. It must not force-close.

If the owner is interrupted during the drain, resume only the exact v14 profile:

```bash
uv run python -m hypervector cohort-tui \
  --mode live --enabled --i-accept-live-risk \
  --resume-transition-drain \
  --config configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml
```

## 3. Prove flat and archive v14

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

After the backend and checkpoint writer exit normally, preview and confirm the
recoverable archive using the exact drained run ID:

```bash
uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id>

uv run python scripts/cohort_transition_drain_archive.py \
  --expected-run-id <exact-drained-run-id> --yes
```

Do not delete the marker, ledger, checkpoint, stops, journal, or backup.

## 4. Reconcile v23 without placing

With no live owner, create one report-only checkpoint for the exact candidate:

```bash
uv run python scripts/multi_asset_bidirectional_live_checkpoint.py \
  --ledger-root data/live/bidirectional_cohort \
  --out data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --config configs/multi_asset_bidirectional_eth_sol_canary_v23.toml \
  --research-database data/research/market.duckdb \
  --venue-portfolio --once
```

Require the v23 fingerprint, observed flat venue state, no owned orders, two
asset slots, one position per symbol, and exactly the ETH and SOL execution
routes above. This reconciliation has no live order authority.

## 5. Launch the authorized v23 live canary

At the verified boundary, use the unified launcher. The explicit flags are
required even though this runbook records user authorization:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_eth_sol_canary_v23.toml \
  --enabled --i-accept-live-risk
```

The launcher must acquire singleton ownership, reconcile venue state, and write
a fresh pre-start backup before constructing execution clients. Verify its exact
bundle path from startup output:

```bash
uv run python scripts/cohort_prestart_backup_verify.py \
  --bundle data/backups/bidirectional_cohort/prestart_<exact-path>
```

An additional terminal may attach read-only without backend ownership:

```bash
uv run python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_bidirectional_eth_sol_canary_v23.toml
```

## Runtime acceptance

Before calling the launch mechanically correct, require:

- exact v23 identity in ledger, checkpoint, selected config, and TUI;
- `running_consistent`, zero faults, and fresh venue reconciliation;
- only ETH pullback/ETH and range onset/SOL executable, both directions;
- isolated 5x and the exact $25/$75 notional and 60-bps stop contracts;
- two shared portfolio slots and one position per symbol;
- every open position has exactly one nonzero reduce-only stop OID;
- causal entry attribution, fill, slippage, fees, funding, liquidation price,
  MFE/MAE, exit attribution, and missed-opportunity records;
- no inherited exposure, stale intent, duplicate symbol position, or route drift.

No economic result automatically changes live authority. Performance is a trial
result and must remain visible in the journal rather than becoming an implicit
abort gate.

## Rollback

There is no hot rollback. Open v23 lifecycles retain their recorded contracts.
At a later verified flat/no-owned-order boundary, complete and archive a v23
drain, then launch a separately approved frozen generation with a new verified
backup. Never replace newer ledger or journal bytes with an older backup.

## Confidence and falsifiers

Mechanical confidence is high only after all acceptance checks pass. Economic
confidence is medium for this bounded trial and lower for persistence. Identity
drift, incomplete drain, inherited venue state, missing stop protection,
duplicate exposure, TUI/config mismatch, or backup mismatch falsifies mechanical
readiness. Sustained negative after-friction live outcomes, material replay/live
fill divergence, or a loss of positive contribution from either mechanism would
weaken the economic hypothesis and require a recorded revision.
