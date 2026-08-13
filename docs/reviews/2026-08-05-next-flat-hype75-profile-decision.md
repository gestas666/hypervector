# Next-flat HYPE allocation decision

**Decision timestamp:** 2026-08-05 13:43 EDT  
**Runtime authority:** none; this review does not stage, restart, arm, or mutate the live backend  
**Selected candidate:** `multi_asset_bidirectional_range_retired_hype75_v8`

## Problem and success criteria

The next live profile needs to collect more useful HYPE breakout evidence without
changing the currently open lifecycle or mixing allocation, entry, and exit
changes into one result. A successful candidate must:

1. preserve the current canonical HYPE entry and exit contract;
2. increase only canonical HYPE breakout exposure from `$25` to `$75` notional;
3. keep 5x isolated leverage and the venue-native 80-bps protective stop;
4. prevent the unproductive Range Onset route from opening new positions;
5. remain restart-only and inactive until the account is venue-flat; and
6. retain exact rollback and implementation evidence at the later live start.

## Evidence at the decision boundary

The immutable live audit contains 14 resolved lifecycles. Canonical HYPE has six
resolved closes: five wins, one loss, `$2.099489` after-cost net PnL, and profit
factor `10.3762`. The same strategy has one protected open lifecycle that is not
included in those closed results. Across all strategies the audit records 14
closes, `$2.164427` after-cost net PnL, profit factor `3.9198`, and maximum
observed portfolio drawdown `0.11995%`.

Observed execution friction across 30 fills was 4.0318 bps mean fee rate and
1.0630 bps mean slippage, with 1,189.8 ms mean acknowledgement latency. These
measurements support the execution plumbing, but six HYPE closes are not enough
to establish durable edge. The one-year HYPE control remained negative in both
development and the previously opened final block.

## Exact candidate delta

Relative to the active profile, the selected candidate changes:

- canonical HYPE breakout maximum notional: `$25` to `$75`;
- Range Onset execution symbols: `BTC/ETH/SOL/HYPE` to none;
- profile identity, as required for a restart-bound configuration.

It explicitly does not change:

- HYPE leverage: 5x isolated;
- HYPE stop: 80 bps;
- HYPE entry rule or bidirectional capability;
- HYPE eight-hour soft hold and regime-supported extension to a 24-hour hard
  limit;
- Hulk HYPE sizing, which remains pinned to `$25`;
- Hypervelocity source-follow execution or Hulk execution scope; or
- the four-position, one-position-per-coin portfolio contract.

At the audit's `$505.8873` final equity, `$75` notional uses at most `$15` margin,
or approximately `2.97%` of equity. An 80-bps move against the position is
`$0.60` before fees, slippage, funding, and any stop gap. Adding the research
model's 4.5-bps fee and 2-bps slippage on each side gives an illustrative
`$0.6975`, or `0.138%` of that equity. This is not a loss guarantee: a stop-market
fill can gap or slip beyond the modeled amount.

## Alternatives and trade-offs

| Option | Benefit | Cost / failure mode | Decision |
|---|---|---|---|
| Keep active `$25` profile | Maximum continuity | Slow dollar-scale learning; Range Onset remains executable | Continue only until the current lifecycle is flat |
| Fixed-eight-hour `$25` profile | Isolates the exit question | Does not test allocation; existing post-soft evidence is only `N=2` | Keep inactive |
| Evidence-routed `$75` plus fixed eight hours | Narrows routes and increases HYPE exposure | Confounds routing, allocation, and exit policy | Do not select |
| Range-retired `$75`, current HYPE exit | Increases HYPE information while preserving its lifecycle contract | Sparse live evidence may be a favorable cluster | Selected next-flat candidate |

## Confidence, failure modes, and falsifier

**Configuration-isolation confidence: high.** Contract tests prove that the
candidate preserves the range-retired baseline and changes only canonical HYPE
allocation, while provider-specific Hulk HYPE sizing stays `$25`. A different
loaded profile fingerprint, widened provider scope, changed HYPE hold policy, or
failed collector construction would falsify this claim.

**Strategy-edge confidence: low-to-medium.** The live HYPE sample is favorable
but sparse and contradicts the broader historical control. Twenty to thirty new
profile-matched HYPE closes with after-cost profit factor at or below one,
negative cumulative net PnL, material single-trade concentration, or materially
worse `$75` fill friction would falsify continued `$75` allocation.

Additional failure modes include canceling public depth, stop gaps, funding
changes, a market-regime shift, rate-limit interruption, and operational
recovery defects. The active open HYPE position must not be used as proof of the
candidate because it was entered under the `$25` profile.

## Validation and transition plan

1. Keep the active backend and its current HYPE protection unchanged.
2. Preserve the candidate as an inactive restart-only profile.
3. At a verified flat boundary, require zero signed venue positions and zero
   owned entry, stop, target, or close orders.
4. Create and independently verify the mandatory prestart backup bundle.
5. Activate only through a new explicit live command and matching profile
   fingerprint; do not hot-mutate the running backend.
6. Journal every `$75` lifecycle with fees, funding, slippage, latency, stop
   identity, exit reason, MFE/MAE, and regime context.
7. Reassess at 10 closes for an operational checkpoint and 20-30 closes for the
   stated allocation falsifier. Neither checkpoint is an automatic gate or
   promotion.

