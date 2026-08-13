# v39 to v44 transition contract

## Scope and identities

The active profile remains
`multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39`
while its forward window remains open. The corrected successor is
`multi_asset_bidirectional_btc_specialists_corrected_candidate_v44`, fingerprint
`a947c234d900f01ba993358e75ef44589a3262e000d0a67070c94c353dc1249a`.

This contract grants no execution authority. There is no automatic restart,
promotion, resizing, or strategy substitution. Starting v44 requires a fresh
flat and order-free boundary plus explicit live-risk authorization.

## What the poor v39 prefix changed

The reviewed v39 prefix closed six trades: one win and five losses, net about
`-$2.28` after recorded costs. The sample is too small to estimate stable
expectancy, but the same routes were already contradicted by broader evidence.
The successor therefore removes those routes instead of hiding their losses
with more leverage or a larger account:

- generic HT-Onset on BTC, ETH, and SOL is removed;
- HIP-3 SNDK and SPCX are removed;
- ETH, SOL, SPCX, SNDK, and BRENTOIL leave the roster;
- Range Onset, both HIP-3 Swing providers, GOLD, generic Source-Follow, and
  broad multi-asset Hulk routes remain retired.

A report-only profit-lock sensitivity reduced the six-trade v39 loss but
remained net negative. Consequently v44 adds no profit-lock rule. That decision
would be revised only by a predeclared forward sample showing positive
after-cost expectancy and improved loss concentration.

## Exact v44 routes

The candidate has three assets, four provider-symbol routes, and six exact
directional scopes:

- `hulk_expansion_short_robust_v3|BTC|short`
- `liquidity_sweep_long_1h_stop60_target60_v2|BTC|long`
- `hype_breakout_compression_pullback_bidirectional_v1|HYPE|long/short`
- `hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500|long/short`

BTC long and short share one asset slot and cannot coexist. HYPE and SP500 each
have one slot. The account retains 10-position capacity, but the exact roster
can hold only three simultaneous positions. Seven slots remain intentionally
unused rather than being filled with negative or unverifiable routes.

All routes use isolated 5x leverage and taker IOC entry. Current evidence uses
4.5 bps one-way taker fees for BTC/HYPE and 0.864 bps for SP500; fee and book
evidence must be refreshed at the actual start boundary.

## Entry and exit contracts

### BTC robust short

- completed 30-minute Hulk expansion decision from causal 5-minute inputs;
- short-only identity;
- structural venue reduce-only stop clamped to 20–75 bps;
- provider-native 3R target;
- 24-hour maximum-hold deadline;
- an authoritative opposite executable intent may close the shared BTC slot.

### BTC corrected liquidity-sweep long

- completed 1-hour sweep/reclaim decision from causal 1-minute inputs;
- long-only identity and maximum 30-second entry delay;
- exact sweep, reclaim, volume, and EMA55 readiness telemetry;
- fixed 60 bps venue reduce-only stop;
- fixed 60 bps provider-native target;
- 24-hour maximum-hold deadline;
- an authoritative opposite executable intent may close the shared BTC slot.

The long is the v44 correction. Its observed path is a taker-parity challenger,
not the maker-derived v43 identity. Development was 5W/1L and the one-event
forward slice was 1W/0L, but one development lifecycle has unresolved mark-path
evidence; repeatability is not established, and this is not a profitability
claim.

### HYPE compression

- exact retained v39 compression entry contract;
- fixed 80 bps venue reduce-only stop;
- opposite executable intent exit;
- eight-hour soft hold, extendable only with supportive canonical regime;
- 24-hour hard maximum-hold deadline.

### SP500 HIP-3 breakout

- exact completed-15-minute pressure-breakout contract;
- fixed 80 bps venue reduce-only stop;
- opposite executable intent exit;
- 24-hour maximum-hold deadline.

For HYPE and SP500, the hold deadline is a terminal strategy mechanism because
their current provider contract has no price target. It is not described as a
secondary fallback.

## Percent sizing and friction evidence

At both `$500` and `$5,000`, route-aware maximum configured margin is
`23.2036076893%`. Gross exposure scales from the same percentages; the profile
does not require a sizing edit between those account values.

The current friction-stress artifact estimates a simultaneous three-slot p99
stop wave of about `$5.14` at `$500` and `$51.38` at `$5,000`, or `1.0276%` of
equity. These are deterministic visible-depth stress estimates, not a loss
ceiling or probability. Gaps, stop slippage, latency, and mark-path uncertainty
can make realized loss larger.

At `$5,000`, BTC short has planned notional near `$3,333`; its modeled p99 stop
loss is `$33.38` and friction-adjusted target net is `$70.55`. BTC long has
planned notional near `$4,167`; its modeled p99 stop loss is `$35.48` and
friction-adjusted target net is `$19.44`. The long needs a win rate above about
`64.61%` under this stress model, which is a material economic risk.

Frozen report-only evidence:

- `data/logs/research/bidirectional_cohort/v44_btc_specialist_successor_risk_20260811_v1.json`
- `data/logs/research/bidirectional_cohort/v44_portfolio_friction_stress_20260811_v1.json`
- `data/logs/research/bidirectional_cohort/v44_current_500_preflight_20260811_v1.json`

The preliminary preflight passed fee, visible-depth, lot-size, and ledger
reconciliation checks, but correctly rejected transition while v39 positions
and orders remained open.

## Controlled transition

1. Keep v39 running during the requested observation window. Verify every open
   position retains its owned venue reduce-only stop and deadline.
2. Wait for a flat and order-free boundary across the venue and all v39
   ledgers. Do not restart under an adopted v39 position.
3. Preserve the final v39 checkpoint, ledger prefix, config, and prestart
   backup.
4. Generate a fresh v44 preflight at that exact boundary:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 500 \
  --output data/logs/research/bidirectional_cohort/v44_final_flat_preflight.json
```

5. Require zero positions, zero owned orders, exact ledger reconciliation,
   current mainnet fees, and valid size/depth for all three assets.
6. Stop v39 normally and confirm both its backend and checkpoint writer exit.
7. Start v44 only after a new explicit decision, with both live flags:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml \
  --enabled \
  --i-accept-live-risk
```

8. After all three ledgers advance, run the generic live audit and exact v44
   post-start verifier:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v44_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v44_final_flat_preflight.json
```

9. Confirm the TUI shows exact v44 run/profile/fingerprint, BTC/HYPE/SP500,
   four routes, six directional scopes, current fees/funding, and complete stop
   protection for every open position.

## Acceptance and falsifiers

Technical acceptance requires a fresh healthy backend, exact route/scope
identity, readiness or explicit non-action telemetry for every provider,
causal regime and HIP-3 pressure evidence, fee/funding accounting, and owned
reduce-only protection for every open position.

Transition is rejected if exposure or owned orders remain, venue and ledgers
disagree, a provider gains an undeclared side, current size/fee/depth invalidates
the profile, backend identity is stale, or an open position lacks protection.

Economic confidence remains low. It is reduced further by repeated exact v44
losses after all costs, negative net without the largest winner, materially
worse slippage than the stress artifact, or cadence too sparse for the intended
portfolio role. It increases only through a predeclared compatible forward
window. Those outcomes are reported trial results, not hidden execution gates.
