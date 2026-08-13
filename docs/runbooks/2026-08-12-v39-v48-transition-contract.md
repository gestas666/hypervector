# v39 to v48 evidence-pruned growth transition contract

## Authority and exact successor

This runbook prepares a flat-boundary transition from the active v39 research
profile to `multi_asset_growth_first_5000_repaired_candidate_v48`, fingerprint
`badda60d549db4fcce9c6a6883198dd71a22f91b58a8073fa5f502c459716f22`.
The exact stress input is
`data/logs/research/bidirectional_cohort/v48_growth_sizing_stress_20260812_v1.json`.

This document and its acceptance command are report-only. They cannot stop,
start, trade, resize, or promote a strategy. Live execution still requires a
separate operator decision and both explicit risk flags.

## What v48 changes and what it does not claim

v48 has four assets, five provider-symbol routes, and eight directional scopes:

- BTC Hulk short retains its completed 30-minute setup, structural 20--75 bps
  stop, 3R target, and 24-hour terminal fallback.
- BTC liquidity-sweep long retains its hourly setup, 60 bps stop and target,
  and 24-hour terminal fallback.
- ETH and SOL Range retain their one-minute decisions derived from completed
  five-minute structure and hourly context, 60 bps stop, strategy/opposite
  exit, and 48-hour terminal fallback. ETH retains the explicit
  `dual_mtf_not_opposed` context selected for prospective testing.
- HYPE compression retains its one-minute entry, 80 bps stop, strategy exit,
  8-hour soft hold with regime extension, and 24-hour hard fallback.

SP500 pressure is removed. The repaired 15-second freshness implementation
fixed a real research/live timing defect, but the exact common-window route was
still net negative and PF below 1 under nominal and stress friction. It returns
to report-only redesign rather than consuming live growth capital. HIP-3 Swing
also remains retired because its tested validation economics were negative.

The retained routes are forward experiments, not proven edges. Review found no
current research/live signal mismatch in Range or HYPE. Their lack of recent
entries is consistent with sparse signal contracts, subject to continued live
measurement. Hulk's historical `2R` label is naming debt; the stored target
price and current runtime both implement 3R. Sweep evidence was corrected to
separate four resolved development wins, one resolved loss, one unresolved
apparent win, and one resolved forward win. That correction lowers confidence
but does not alter the runtime rule.

## Growth sizing and stress meaning

Each asset uses 15% isolated margin at fixed 10x leverage. A $5,000 reference
therefore assigns at most $750 margin and $7,500 notional per active asset. One
position per asset allows four simultaneous positions, although account
capacity remains ten. Fully occupied configured margin is 60% of equity.

The exact modeled p99 stop wave is approximately $294.70, or 5.89408% of the
$5,000 reference. This is a deterministic sampled-friction scenario, not a
probability, expected loss, maximum loss, liquidation ceiling, or profitability
claim. Correlated gaps, latency, stop overrun, and unobserved venue conditions
can produce a larger loss. Variable leverage remains telemetry-only because a
calibrated readiness-to-win mapping has not been established.

## Flat-boundary transition

1. Keep v39 managing its current positions and orders. Verify each open
   lifecycle has an owned reduce-only stop and persisted deadline.
2. Wait for zero venue positions and zero owned orders across every v39 ledger.
   Any venue/ledger disagreement aborts the transition for reconciliation.
3. Stop v39 normally only at that boundary. Preserve the final checkpoint,
   ledgers, execution/reflection archive, and a prestart backup. Confirm both
   backend and checkpoint writer have exited.
4. Generate a fresh boundary preflight:

```bash
uv run python scripts/multi_asset_bidirectional_preflight.py \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml \
  --active-config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --checkpoint data/runtime/bidirectional_cohort/latest_checkpoint.json \
  --sizing-equity-usd 5000 \
  --output data/logs/research/bidirectional_cohort/v48_final_flat_preflight.json
```

5. Require the exact v48 identity, current mainnet fee and leverage evidence,
   complete candidate-notional depth evidence, reconciled ledgers, and zero
   positions/orders. A stale or mismatched preflight is unusable.
6. Inspect the staged identity through the attach-only cockpit:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml \
  --staged-config configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml \
  --growth-preflight data/logs/research/bidirectional_cohort/v48_final_flat_preflight.json
```

7. Require four assets, five routes, eight side scopes, fixed 10x leverage,
   15% margin per asset, exact active/staged identities, and no unexplained
   missing cockpit telemetry.
8. Only after a new explicit operator authorization may v48 start:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live \
  --config configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml \
  --enabled \
  --i-accept-live-risk
```

9. After all four ledgers advance, publish the generic live audit and exact
   report-only technical acceptance:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort

uv run python scripts/v48_poststart_acceptance.py \
  --preflight data/logs/research/bidirectional_cohort/v48_final_flat_preflight.json
```

## Monitoring, rollback, and falsifiers

Track provider-level net PnL, return on margin, PF, drawdown, fees, funding,
largest-winner removal, eligible-but-missed opportunities, exit reasons, and
regime alignment. Preserve each strategy version before any mechanism change.
Rollback only while v48 is flat and order-free.

Confidence is high that exact-profile tests prevent removed SP500/Swing routes
or old five-slot friction from masquerading as v48. Confidence in profitability
is low-to-medium because all retained routes have sparse, unstable, or limited
forward evidence. Update or falsify this plan if the final preflight changes
venue constraints, post-start identity/protection fails, realized friction
exceeds the sampled model, a retained strategy remains negative across a
compatible forward sample, or a removed mechanism succeeds under a genuinely
new causal design.
