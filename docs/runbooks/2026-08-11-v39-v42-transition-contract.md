# Inactive v39-to-v42 transition and rollback contract

## Decision

V39 remains the live owner until every open lifecycle and owned venue order is
resolved. V42 is an inactive `$5,000` successor candidate. This document does
not authorize a close, restart, route change, or live launch.

Confidence is high that the v42 profile is internally sizeable and materially
reduces exposure to routes falsified by current evidence. Confidence is low to
medium that its three retained routes have durable economic edge. A fresh
flat-boundary preflight, post-start technical acceptance, and forward outcomes
are required to update that assessment.

## Frozen identities

- Active profile: `multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39`
- Active fingerprint: `8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5`
- Candidate profile: `multi_asset_bidirectional_focused_growth_5000_candidate_v42`
- Candidate fingerprint: `c691ee99f6f450990b9c2e25059fba8b5f266f8d6caff33900fc8a259b003097`
- Candidate config SHA-256: `825cbfc1be69ff4dd38528ef7939f7216be3092999bb93400c26b7acd30e78c9`
- Candidate design artifact SHA-256: `608f8f5e41c5643786d1b2a115c70baa133e85587905d2407e42d9a6a3238cc4`
- Current rejected preflight SHA-256: `fc1531f58196e70761d367f2d0be15fb8979162c5c54d54719fd56a293809aa1`

The candidate has three executable provider-symbol routes and six explicit
long/short scopes:

- BTC Hulk Expansion;
- HYPE Compression Pullback with the unchanged 8h-to-24h exit contract; and
- `xyz:SP500` HIP-3 Breakout Pressure.

All positions use isolated 5x leverage. The account cap remains ten, but one
position per configured asset limits this profile to three simultaneous
positions. Seven slots and the removed routes' risk remain unused.

At `$5,000`, configured initial margin is `$483.51`, gross notional is
`$2,417.54`, and gross account exposure is approximately `0.484x`. The modeled
`$21.80` p99 stop wave is a deterministic visible-depth sensitivity. It is not
a worst-case loss ceiling and excludes gap-through-stop uncertainty.

The 22:46 UTC public-wallet preflight reconciled all venue and ledger state,
current fee inputs, leverage limits, and planned visible depth. It correctly
returned a technical rejection with four positions and four owned stops on
BTC, ETH, SOL, and SP500. It is evidence that the candidate can be sized, not
permission to transition. The flat-boundary preflight must be generated again.

## Current no-go conditions

Do not transition while any of these conditions holds:

- v39 reports an open or protecting lifecycle;
- the venue or any ledger reports a nonzero position;
- any v39-owned entry, stop, target, or close order remains;
- the transition drain is incomplete or unarchived;
- the latest checkpoint is stale, faulted, or mismatched to v39;
- a fresh v42 public-wallet preflight is absent or unreconciled;
- the v42 implementation/config hash differs from the frozen review; or
- the operator has not supplied a new explicit live-risk authorization.

## Monitor v39 and stage v42 read-only

The staged monitor is execution-incapable. It must report active v39 and next
v42 separately, `14 -> 3` routes, six bidirectional scopes, no automatic
restart, and the exact open-position/order blockers:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml \
  --growth-preflight data/runtime/bidirectional_cohort/latest_growth_5000_v42_preflight.json
```

This command may start a report-only checkpoint writer when no compatible
writer exists. It does not start, stop, or replace the v39 backend. A writer
with unprovable active/staged identity causes the launcher to fail closed.

## Flat-boundary transition sequence

1. Request a v39 transition drain only after explicit operator authorization.
2. Wait for every configured asset to be flat and for all owned order lists to
   be empty. Preserve provider exits, maximum holds, and venue-native stops
   during the drain.
3. Stop v39 normally. Do not kill or overlap the account owner.
4. Preview and then explicitly archive the completed drain using
   `scripts/cohort_transition_drain_archive.py` with the exact run ID.
5. Generate a fresh public-wallet-only v42 preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/runtime/bidirectional_cohort/latest_growth_5000_v42_preflight.json
```

6. Require exact venue/ledger flatness, zero owned orders, current account
   value, current fee inputs, current leverage limits, current executable book
   depth, three assets, three routes, six sides, and the frozen sizing weights.
7. Create and independently verify a fresh v42 prechange bundle. The armed
   launcher must create and verify its own mandatory prestart bundle again.
8. Render every TUI screen at the acceptance size and reconcile run/profile,
   route scope, sizing, fees, funding, positions, orders, and protection.

## Future launch template

This template is not current authorization. It may be used only after all
flat-boundary conditions pass and the user provides a new explicit live-risk
approval:

```bash
uv run python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml \
  --enabled --i-accept-live-risk
```

## Post-start acceptance

Before describing v42 as technically accepted, require:

- exact v42 run/profile/config/prestart identities;
- all three ledgers advancing and all three provider routes evaluated;
- six explicit long/short execution scopes and no observe-only route;
- no unexpected order, position, duplicate owner, or startup adoption;
- venue-native reduce-only protection for every open lifecycle;
- exact entry/exit fee, funding, slippage, and acknowledgement telemetry;
- fresh canonical regime telemetry and HIP-3 pressure provenance;
- Screen 1 through Screen 9 populated without mixed-generation claims; and
- an immutable post-start technical report with execution authority `none`.

Technical acceptance does not establish profitability. Route edge remains a
forward measurement and cannot be inferred from sizing or clean execution.

## Rollback

Rollback is allowed only from a verified flat and order-free boundary. Do not
restart v39 to adopt v42 positions or orders. Preserve the v42 ledgers and
prestart bundle, publish the stopped-run audit, record the exact incident or
economic reason, and require another explicit authorization for any later
profile.

Falsifiers include any active/staged identity mismatch, a route count other
than `14 -> 3`, a side-scope count other than six, risk redistribution to
removed assets, a missing protective order, realized friction outside the
preflight model, or a later forward sample showing the retained routes remain
net negative after costs and largest-winner sensitivity.
