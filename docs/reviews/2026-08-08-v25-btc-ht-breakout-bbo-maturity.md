# V25 BTC HT-Breakout executable-BBO maturity

## Problem and success criteria

The live audit needed to distinguish a real closed trade from a report-only
signal path, retain exact run and decision identity, and measure whether a new
BTC HT-Breakout episode cleared the configured execution-friction model as its
15-, 30-, and 60-minute horizons matured.

Acceptance required:

1. the same run and profile on both audit prefixes;
2. one provider-cadence episode onset with causal entry and exit BBOs;
3. complete source-run and decision-time identity;
4. explicit fee and residual-slippage assumptions; and
5. zero execution, routing, sizing, or runtime authority.

## Observed result

The immutable after-prefix contains one eligible BTC HT-Breakout long episode.
It was published at decision time `1786239000000`, first matched an executable
BBO at `64849`, had aligned order pressure, and neutral 5m and 15m context.

| Horizon | Gross BBO | After fees | After modeled friction |
|---:|---:|---:|---:|
| 15m | +1.3878 bps | -7.6128 bps | -11.6131 bps |
| 30m | -2.6215 bps | -11.6203 bps | -15.6198 bps |
| 60m | -6.0140 bps | -15.0113 bps | -19.0101 bps |

The model deducts 4.5 bps per side in taker fees and 2.0 bps per side in
residual slippage. This one episode failed to clear modeled costs at all three
horizons. It is not a fill, owned PnL, funding result, or authorization change.

## Portfolio delta

Across the 49.9-minute same-run delta, no live lifecycle resolved: closed
trades, fills, fees, funding, and realized net PnL were unchanged. The audit
retained three provisional open lifecycles. The provider stream added 498
evaluations, 491 directional evaluations, and zero eligible evaluations.

The broader deduplicated opportunity audit added 208 unique directional paths.
Only one or two independent paths per horizon cleared the fixed modeled cost
hurdle, while 50, 19, 8, and 2 independent paths failed at 5, 15, 30, and 60
minutes respectively. These counts describe newly matured annotations, not
independent strategy trials or portfolio PnL.

## Uncertainty, risks, and falsifiers

Economic confidence is low because the BTC evidence is one long episode from
one intraday window, with no short replication or regime diversity. Aligned
pressure did not rescue this path, but one observation cannot establish that
pressure is unhelpful generally.

The conclusion would be updated by materially more independent, venue-matched
BTC episodes on both sides. Positive after-friction median and leave-largest
results that agree with resolved live lifecycles would weaken the current
entry-quality concern. The technical result is falsified by cross-run mixing,
pre-publication books, changed artifact bytes, incomplete path identity, or any
report-only code changing live execution.

## Recommendation

Keep the armed v25 runtime unchanged. Continue collecting causal BBO episodes
and resolved live lifecycles. Do not loosen or add a gate, resize a route, or
change an exit from this single episode.

