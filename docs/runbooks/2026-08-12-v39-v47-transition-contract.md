# v39 to v47 repaired-growth transition contract

## Purpose, authority, and exact identity

This runbook moves the live research portfolio from the active v39 profile to
the repaired v47 candidate without mixing strategy identities or leaving an
existing position unmanaged. The active owner remains
`multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39`
until its venue positions and owned orders are both empty.

The proposed successor is
`multi_asset_growth_first_5000_repaired_candidate_v47`, fingerprint
`cb1482029e230069bb6615cb5232975728602c3c14b925ef7f0c734a90b1bc0f`.
The exact sizing evidence is
`data/logs/research/bidirectional_cohort/v47_growth_sizing_stress_20260812_v3.json`.

This document grants no execution authority. It does not automatically stop,
start, promote, resize, or route a strategy. Live execution still requires the
operator's explicit decision and both live-risk flags.
No report-only observer substitutes for the live trial; report-only evidence
can validate wiring but cannot establish real fill quality or profitability.

## Strategy repairs and retained contracts

v47 contains five assets, six provider-symbol routes, and ten bidirectional
side scopes. It retains strategies only under their exact provider identity:

- BTC Hulk short: robust 30-minute setup, structural 20--75 bps stop, 3R
  target, and 24-hour terminal fallback;
- BTC liquidity-sweep long: hourly setup, 60 bps stop and target, and 24-hour
  terminal fallback;
- ETH and SOL Range: one-minute decisions derived from completed five-minute
  structure and hourly context, 60 bps stop, strategy/opposite exit, and
  48-hour terminal fallback;
- HYPE compression: one-minute entry, 80 bps stop, strategy exit, 8-hour soft
  hold with regime extension, and 24-hour hard fallback;
- SP500 HIP-3 pressure: completed 15-minute bars, 80 bps stop, strategy exit,
  and 24-hour fallback. Its provider must be the repaired
  `fresh15s_bidirectional_v2` identity.

The transfer-tested HT onset ETH/SOL routes are removed because their tested
economics were negative. HIP-3 Swing is removed because commodity/index
results were negative or dependent on a small number of winners. Legacy
HIP-3 pressure v1 is not evidence for v2: v1 admitted a 30-second book age
while the archive contract required 15 seconds. Range remains because its low
frequency is statistically plausible under its signal contract; its forward
results remain a measured hypothesis rather than a promised edge.

## Portfolio sizing and stress interpretation

At a $5,000 sizing reference, each configured asset receives 12% isolated margin
with fixed 10x leverage and a $6,000 per-asset notional cap. One
position per asset means five simultaneous positions even though the account
capacity is ten positions. If all five assets enter, configured isolated
margin totals 60% of equity.

The v3 evidence models a marginal stacked p99 stop wave of 5.73877% of the
$5,000 sizing reference, approximately $286.94. This is a deterministic stress
scenario, not a joint-event probability, expected loss, worst-case ceiling,
or proof of profitability. Gaps, latency, liquidation mechanics, correlation,
or venue behavior outside sampled evidence can produce a larger realized
loss. Fixed leverage is intentional; exposure changes through notional size,
not by silently changing liquidation geometry.

## Flat-boundary transition procedure

1. Keep v39 and its checkpoint writer running while any lifecycle remains
   open. Confirm every open position has an owned reduce-only venue stop and a
   persisted exit deadline. Do not rebind the active checkpoint writer to v47.
2. Wait for zero venue positions and zero owned orders across every v39
   ledger. If venue state and ledger state disagree, stop the transition and
   reconcile the discrepancy without creating a new order.
3. Stop v39 normally only after the flat/order-free condition is observed.
   Preserve the final checkpoint, ledger prefix, execution/reflection archive,
   and a prestart backup. Confirm both the backend and checkpoint writer exit.
4. Generate a fresh exact-boundary $5,000 preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v47.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v47_final_flat_preflight.json
```

5. Require the exact v47 profile and fingerprint, a reconciled ledger, zero
   positions, zero orders, current mainnet fee evidence, per-symbol venue
   leverage compatibility, minimum-order readiness, and complete visible depth
   for each configured $6,000 notional. Any mismatch aborts this attempt.
6. After the old writer exits, inspect the staged transition in the read-only
   cockpit:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_growth_first_5000_repaired_candidate_v47.toml \
  --growth-preflight data/logs/research/bidirectional_cohort/v47_final_flat_preflight.json
```

7. Require the cockpit to show v39 as the completed active identity and v47 as
   staged, with five assets, six routes, ten side scopes, fixed 10x leverage,
   12% margin per asset, and no unexplained missing telemetry.
8. Start v47 only after a new explicit operator authorization:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v47.toml \
  --enabled \
  --i-accept-live-risk
```

9. After all five asset ledgers advance, publish the generic live audit and
   exact technical acceptance:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v47_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v47_final_flat_preflight.json
```

10. Confirm every provider evaluation has an action or explicit non-action
    reason; every open lifecycle has correct provider identity, fees, funding,
    entry/exit regime telemetry, deadline, and owned venue stop. Confirm HIP-3
    pressure age is at most 15 seconds and no legacy v1 row is counted as v2.

## Acceptance, monitoring, and rollback

Technical acceptance proves identity, causal telemetry, accounting, routing,
and protection—not economic edge. Track per-provider net PnL, return on margin,
profit factor, maximum drawdown, fees, funding, largest-winner removal, missed
eligible opportunities, exit reasons, and regime alignment. A strategy change
requires a new versioned identity and a preserved prior configuration.

Rollback is permitted only when v47 is flat and order-free. Never replace an
active provider configuration while it owns a position. Reject or stop the
transition for stale checkpoints, profile/fingerprint drift, missing route
accounting, a position without protection/deadline, pressure older than the
frozen contract, unexpected leverage/margin, venue/ledger disagreement, or a
failed post-start verifier. Economic outcomes remain reported trial results;
only technical failure aborts under the project charter unless the operator
explicitly configures a performance gate.

## Confidence and falsifiers

Confidence is high that this procedure prevents mixed-profile execution and
checks the known HIP-3 freshness defect, because those conditions are bound to
exact identities and machine-tested artifacts. Confidence is medium that v47
will produce improved live economics: retained strategies have uneven and in
some cases sparse evidence, and the larger $5,000 sizing has not yet produced
compatible live closes. This assessment is falsified or updated by a fresh
preflight mismatch, post-start identity/protection failure, continued
provider-level negative expectancy under compatible v47 lifecycles, or live
friction materially exceeding the modeled evidence.
