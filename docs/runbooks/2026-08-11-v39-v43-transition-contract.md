# v39 to v43 transition contract

## Scope and identities

The active profile remains
`multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39`
until a flat and order-free boundary is observed. The proposed successor is
`multi_asset_bidirectional_btc_specialists_candidate_v43`, fingerprint
`3cb85383f63e346579bee66646d24c3808cbd49ec6d022f6ee51d0fa765340d7`.

This document is an operational safety contract. It is not a profitability
claim and it grants no execution authority. Switching still requires explicit live-risk authorization. There is no automatic restart or automatic profile
promotion.

## Why v39 is being replaced

The first exact v39 prefix closed five trades: one win and four losses, about
`-$2.21` net with profit factor near `0.008`. The loss sample is small, but the
routes that produced it were already contradicted by broader route evidence:

- generic HT-Onset on BTC, ETH, and SOL is removed;
- HIP-3 SNDK and SPCX are removed;
- ETH, SOL, SPCX, SNDK, and BRENTOIL leave the asset roster;
- prior Range Onset, Swing, GOLD, generic Source-Follow, and broad Hulk routes
  remain retired.

The successor does not reuse v39 performance as evidence for its new BTC
specialists. Prior history remains separately labeled.

## Exact v43 routes

The parsed candidate contains three assets, four provider-symbol routes, and
six exact directional scopes:

- `hulk_expansion_short_robust_v3|BTC|short`
- `liquidity_sweep_long_1h_stop60_v1|BTC|long`
- `hype_breakout_compression_pullback_bidirectional_v1|HYPE|long/short`
- `hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500|long/short`

BTC long and short share one asset slot; they cannot coexist. HYPE and SP500
each have one asset slot. The account retains 10-position capacity, but this
roster can occupy at most three simultaneous positions. Seven slots are
deliberately unused rather than filled with rejected routes.

All routes use isolated 5x leverage and taker IOC entry. Current mainnet
preflight resolved the account taker fee to 4.5 bps one way for BTC/HYPE and
0.864 bps one way for SP500. Fee and book evidence must be refreshed before
every start.

## Entry and exit behavior

### BTC robust short

- completed 30-minute Hulk expansion decision from causal 5-minute bars;
- short-only identity;
- structural stop clamped to 20–75 bps;
- provider-native target at 3R;
- 24-hour maximum-hold deadline;
- an authoritative opposite executable intent may close the shared BTC slot.

### BTC liquidity-sweep long

- completed 1-hour sweep/reclaim decision from causal 1-minute bars;
- long-only identity;
- exact readiness telemetry for sweep, reclaim, volume, and EMA55;
- 60 bps venue reduce-only stop;
- provider-native target at 26.6667 bps;
- 24-hour maximum-hold deadline;
- an authoritative opposite executable intent may close the shared BTC slot.

### HYPE compression

- retained exact v39 compression entry contract;
- 80 bps venue reduce-only stop;
- opposite executable intent exit;
- eight-hour soft maximum-hold deadline, extendable only while the canonical
  regime remains supportive, with a 24-hour hard ceiling.

### SP500 HIP-3 breakout

- retained exact completed-15-minute pressure breakout contract;
- 80 bps venue reduce-only stop;
- opposite executable intent exit;
- 24-hour maximum-hold deadline.

For the two routes without a target, the maximum-hold deadline is a terminal
strategy mechanism, not merely a fallback. Provider-native recipe exits remain
ignored unless a later profile explicitly changes that contract.

## Sizing and limitations

At the $500 scenario, maximum configured simultaneous margin is
`23.2036076893%` and gross notional is about `1.16018x` account equity. The
same percentage contract scales at $5,000 without editing the profile.

BTC short uses at most 13.3333% margin. At $5,000, its planned notional is
about $3,333, its modeled maximum-stop loss plus round-trip fees is about $28,
and its modeled 3R net target is about $72. BTC long uses at most 16.6667%
margin. Its planned notional is about $4,166, modeled stop plus fees is about
$28.75, and modeled net target is about $7.36.

Those figures exclude funding, gap-through-stop loss, latency, and realized
slippage. They are sizing arithmetic, not a loss guarantee.

Each BTC specialist has only one exact forward event; repeatability is not established. This is the primary economic uncertainty. The routes may trade
infrequently, and one clean event is sufficient only to validate plumbing.

Immutable risk evidence:

`data/logs/research/bidirectional_cohort/v43_btc_specialist_successor_risk_20260811_v1.json`

Preliminary current-account preflight:

`data/logs/research/bidirectional_cohort/v43_current_500_preflight_20260811_v1.json`

The preliminary preflight passed lot-size, current fee, visible depth, and
ledger reconciliation checks but correctly rejected transition because v39
still had protected positions and owned orders.

## Transition procedure

1. Keep v39 running while any v39 position remains open. Verify every open
   position has its owned venue reduce-only stop.
2. Reach a flat and order-free boundary across both the venue and all v39
   ledgers. Do not restart beneath an adopted v39 position.
3. Preserve the final v39 checkpoint, ledgers, profile, and the launcher's
   prestart backup.
4. Generate a fresh candidate preflight at the actual boundary:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 500 \
  --output data/logs/research/bidirectional_cohort/v43_final_flat_preflight.json
```

5. Require zero positions, zero owned orders, exact ledger reconciliation,
   current mainnet fees, and technically valid size/depth for all three assets.
6. Stop v39 normally. Confirm its process is gone and no backend writer is
   mutating the old run.
7. Start v43 only with both explicit live flags:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml \
  --enabled \
  --i-accept-live-risk
```

8. After all three asset ledgers advance, run the generic live audit and exact
   v43 technical acceptance:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v43_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v43_final_flat_preflight.json
```

9. Confirm the TUI shows the exact v43 run/profile/fingerprint, three assets,
   four routes, six side scopes, current fees/funding, and full venue-stop
   protection for every open position.

## Acceptance and falsifiers

Technical acceptance requires a fresh, healthy, identity-consistent backend;
exact route and side coverage; explicit readiness or non-action telemetry;
causal regime and HIP-3 pressure telemetry where applicable; fee/funding
fields; and complete stop protection.

The transition fails if any position or order remains, any ledger differs from
the venue, any provider gains an undeclared side, any current fee or minimum
lot invalidates sizing, any backend identity is stale, or any open position
lacks complete reduce-only stop coverage.

Economic confidence must be updated from exact v43 closes. Evidence that would
reject or revise the route choice includes persistent net losses after fees and
funding, negative results without the largest winner, materially worse
slippage than preflight, or signal cadence too sparse to satisfy the intended
portfolio use. These outcomes are reported evidence, not hidden execution
gates.
