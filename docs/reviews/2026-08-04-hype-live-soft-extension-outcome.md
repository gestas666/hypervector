# HYPE Live Soft-Extension Outcome — 2026-08-04

## Problem restatement

Determine whether extending the HYPE long beyond its configured eight-hour
soft maximum hold added or destroyed value. This is a causal, report-only
execution review. It does not change strategy eligibility, sizing, balance
handling, or live authority.

## Authoritative inputs

- Lifecycle: `HYPE:509351044526`
- Strategy: `hype_breakout_onset_bidirectional_v1`
- Side: long
- Entry: `53.891` at `1785793512230 ms`, size `0.46`
- Runtime timer origin: `1785793500000 ms`
- Soft boundary: `1785822300000 ms`
- Last fully completed candle at the boundary: `1785822240000 ms`, close
  `54.481`
- Exit: `54.153` at `1785825622862 ms`
- Runtime timer duration: `32,122,862 ms` (`8h55m22.862s`)
- Fill-to-fill holding time: `32,110,632 ms` (`8h55m10.632s`)
- Exact lifecycle fees: `$0.021470`
- Exact lifecycle funding: `-$0.002450`
- Exact realized net PnL: `+$0.096600`

The entry/exit and costs come from reconciled Hyperliquid fills. The boundary
path comes only from completed one-minute candles persisted by the backend.

## Causal post-soft path

The first eligible post-boundary candle begins at `1785822300000 ms`; the last
fully completed candle before the exit begins at `1785825540000 ms`. There are
55 completed bars.

| Metric | Result |
|---|---:|
| Boundary baseline | `54.481` |
| Post-soft high | `54.486` |
| Post-soft low | `54.152` |
| Exit versus boundary | `-60.20 bps` |
| Post-soft MFE | `+0.92 bps` |
| Post-soft MAE | `60.39 bps` |
| Actual-minus-soft estimated gross | `-$0.151343` |

Price exceeded the completed-candle boundary close by less than one basis
point, then moved against the position. The policy retained the position until
structure support degraded from `+0.8333`
(`directionally_supported`) to `+0.0833` (`mixed_or_transition`).

## Executable counterfactual

A taker close at the boundary is estimated using the actual later
fill/reference ratio and its exact observed fee rate:

`(54.482006075 - 53.891) * 0.46 - 0.010709 entry fee - 0.010826378 estimated exit fee - 0.002138 funding through soft boundary = +$0.248189416`

Compared with the exact realized `+$0.096600`, the extension reduced the
counterfactual result by approximately `$0.151589`. The extension itself paid
an additional `$0.000312` funding. The counterfactual still cannot reproduce
the private order book or queue at the soft boundary; its actual later
fill/reference ratio is an explicitly labeled friction proxy.

## Evidence update

The prior report-only supported-extension challenger contributed approximately
`+$0.156960` gross at 60 minutes. This direct live extension contributed
`-$0.151343` estimated gross over about 55 minutes. Combined gross evidence is
therefore approximately `+$0.005617` before incremental funding and execution
effects.

Confidence is **high for the recorded lifecycle and arithmetic** because the
runtime timer, venue fills, funding rows, candle boundary, and cost ledger
reconcile. Confidence is **medium for the estimated soft fill** because it
reuses later observed friction rather than an order submitted at the boundary.
Confidence is **low for the general exit policy** because only one direct live
extension and one earlier compatible challenger exist.

## Recommendation and falsification

Keep the current bounded extension temporarily while the newly activated
first-class `maximum_hold_decision` journal collects direct events. Do not treat
the current result as a promotion, rejection, or balance gate. Evaluate fixed
eight-hour exit, supported extension, and a post-soft protective-trail
challenger from the same future lifecycles.

The extension hypothesis gains support if direct events produce positive
aggregate incremental after-cost PnL without materially worse adverse
excursion. It is weakened if additional direct extensions repeat this
near-zero-MFE/giveback pattern or remain negative after costs. A mismatch between
the persisted candle baseline and an independently reconstructed Hyperliquid
candle snapshot would invalidate this calculation and require rebuilding the
path evidence.
