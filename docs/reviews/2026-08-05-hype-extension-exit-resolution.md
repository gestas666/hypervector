# HYPE extension exit resolution

**Decision timestamp:** 2026-08-05 08:09 EDT  
**Evidence source:** `data/runtime/bidirectional_cohort/latest_checkpoint.json`  
**Execution authority:** report-only analysis; no order, position, or running
strategy was changed.

## Problem and success criterion

The deployed canonical HYPE provider held beyond its 28,800-second soft
boundary while its regime remained supportive, subject to an 86,400-second hard
boundary. The decision is whether the next separately staged profile should
retain that extension, use the fixed boundary, or introduce a post-boundary
trailing exit. A candidate must improve reconciled after-cost outcomes without
changing entry logic, size, leverage, or another provider at the same time.

## Observed terminal evidence

Two long-side extension lifecycles are resolved:

| Lifecycle | Actual net | Estimated 8h net | Actual minus 8h | 20bps trail net |
|---|---:|---:|---:|---:|
| `HYPE:509351044526` | `$0.096600` | `$0.248189` | `-$0.151589` | `$0.200382` |
| `HYPE:510231967855` | `$0.864788` | `$1.001600` | `-$0.136812` | `$1.213007` |
| Aggregate | `$0.961388` | `$1.249790` | `-$0.288402` | `$1.413389` |

The fixed eight-hour estimate beat the actual extended exit in both lifecycles.
The 20-bps trail beat the actual exit in both but beat the fixed boundary in
only the second lifecycle. Aggregate 30-bps and 40-bps trail estimates were
`$1.363808` and `$1.312744`, respectively.

Canonical HYPE's complete reconciled live history is six closes, `5W/1L`,
`+$2.099489`, PF `10.3762`, including both sides. The exit-policy comparison,
however, is only the two long lifecycles that actually extended; the broader
history does not increase the comparison sample.

## Assumptions and limitations

- The eight-hour and trail exits are counterfactual estimates, not submitted
  orders. They reuse the actual later exit's fill/reference ratio and fee rate.
- Completed one-minute bars do not identify private queue position or exact
  intrabar ordering.
- Both eligible paths are long. There is no short-side extension evidence.
- Two outcomes can be dominated by market path and do not establish a durable
  statistical edge.
- The latest lifecycle did not reach the hard 24-hour boundary; regime support
  disappeared about 3 hours 40 minutes after the soft boundary.

## Decision

Stage
`configs/multi_asset_bidirectional_range_retired_hype_fixed8_candidate.toml`
for the next verified flat/no-owned-orders start. It changes only canonical
HYPE's maximum-hold policy from regime-supported extension to a fixed 28,800
seconds. HYPE remains both-sided, `$25` maximum notional, 5x isolated. Range
onset remains observe-only and all other provider contracts remain unchanged.

The 20-bps post-boundary trail remains report-only. Its aggregate estimate is
higher, but one of two trail outcomes is below the fixed boundary and the rule
adds state, restart, and intrabar execution assumptions that have not been
validated live.

**Confidence: medium-low.** The direction of evidence is consistent across two
eligible paths, but `N=2`, one side, and counterfactual fills are substantial
limitations.

## Validation and falsification

Activation remains blocked until every asset is venue-flat with zero owned
orders and the fail-closed pre-start backup independently verifies. After
activation, record for every canonical HYPE lifecycle:

1. actual fixed-boundary fill, fee, funding, acknowledgement latency, and
   slippage;
2. the same frozen 20/30/40-bps trail counterfactuals;
3. post-exit MFE/MAE and whether continuation would have cleared all costs; and
4. results split by long/short and entry regime.

Repeated after-cost continuation beyond eight hours that exceeds the realized
fixed exit would falsify this candidate. A post-boundary trail that repeatedly
beats fixed eight hours per lifecycle, not merely in aggregate, would justify a
separate trail candidate. Any profile/fingerprint mismatch, missing backup
implementation identity, open position/order at transition, or first-position
protection fault invalidates activation regardless of performance.
