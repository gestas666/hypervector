# v39 to v45 growth-sizing transition contract

## Authority and exact identities

The active owner remains
`multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39`
until it is flat and order-free. The proposed successor is
`multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45`,
fingerprint
`e1b46ba749a46cc2966f0b4629bfd487c3d6dfe1a29de745d9f9eb7c8e22c6f5`.

This runbook grants no execution authority. There is no automatic restart,
promotion, resizing, or variable-size execution. A future live start still
requires an explicit operator decision plus both live-risk flags.

## Strategy and sizing delta

v45 preserves all v44 provider, entry, stop, target, and maximum-hold
contracts. It changes only base sizing for HYPE and SP500:

- BTC short: 13.3333% margin override, isolated 5x;
- BTC long: 16.6667% margin override, isolated 5x;
- HYPE: 7% margin, isolated 5x;
- SP500: 7% margin, isolated 5x.

BTC directions share one asset slot. The exact three-asset roster therefore
has at most three simultaneous positions despite account capacity of ten.
Variable 0.75x/1.00x/1.25x notional tiers are telemetry-only and cannot affect
orders until separately implemented, calibrated, and authorized.

## Forward observer while v39 remains active

The v45 signal contract may run concurrently only through the isolated
zero-authority observer:

```bash
uv run python scripts/multi_asset_bidirectional_observe.py \
  --config configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml \
  --ledger-root data/observe/v45_candidate_shadow
```

Its checkpoint is
`data/runtime/research/v45_candidate_shadow_latest.json`. Because the observer
rebinds every ledger and stop-file path, its operational fingerprint is
`b8ba030a964ed2c109346641e9d91534ada73ec851ae191a318cf3f8bac2bb90`;
this is intentionally different from the deployable v45 fingerprint above.
The observer has execution authority `none`, cannot place orders, and its
readiness fractions are prerequisite telemetry rather than sizing inputs or
win probabilities.

The exact candidate-notional stress artifact is
`data/logs/research/bidirectional_cohort/v45_growth_sizing_stress_20260812_v2.json`.
It estimates a simultaneous p99 stop wave of 1.39364% of equity: about $6.97
at $500 and $69.68 at $5,000. This is not a joint probability or loss ceiling.

## Transition procedure

1. While any v39 lifecycle is open, keep its backend and checkpoint writer
   running. Verify every position has an owned venue reduce-only stop and a
   persisted exit deadline. Do not rebind the checkpoint writer merely to
   preview v45.
2. Wait for zero venue positions and zero owned orders across all v39 ledgers.
3. Stop v39 normally. Confirm the v39 backend and checkpoint writer exited,
   then preserve the final checkpoint, ledger prefix, and prestart backup.
4. Generate a fresh $500 v45 preflight at that exact boundary:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 500 \
  --output data/logs/research/bidirectional_cohort/v45_final_flat_preflight.json
```

5. Require exact v45 identity, zero positions, zero orders, ledger
   reconciliation, current mainnet fees, minimum-lot readiness, and complete
   visible depth at every configured size.
6. Preview the active-to-staged identity in the read-only cockpit only after
   the old checkpoint writer has exited:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml \
  --growth-preflight data/logs/research/bidirectional_cohort/v45_final_flat_preflight.json
```

7. Start v45 only after a new explicit authorization:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml \
  --enabled \
  --i-accept-live-risk
```

8. After all three ledgers advance, publish the generic live audit and exact
   v45 technical acceptance:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v45_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v45_final_flat_preflight.json
```

9. Confirm the cockpit shows the exact v45 profile/fingerprint, BTC/HYPE/SP500,
   four provider-symbol routes, six directional scopes, 30.6667% maximum
   margin, fixed 5x leverage, current fee/funding telemetry, and venue-stop
   protection for every open position.

## Acceptance, rollback, and falsifiers

Technical acceptance requires a fresh healthy v45 checkpoint, exact route and
direction identity, explicit action or non-action telemetry for every provider,
causal regime/pressure evidence, fee/funding accounting, and protected open
positions. Rollback is permitted only when v45 is again flat and order-free.

Reject the transition if any exposure or owned order remains, venue and ledger
state differ, a route gains an undeclared side, sizing/depth/fees fail current
preflight, the checkpoint identity is stale, or any position lacks its stop or
deadline. Economic results remain reported trial outcomes rather than hidden
activation gates.
