# SOL Route-Priority Interaction Review

Status: reject static-priority change  
Execution authority: none  
Runtime strategy changed: false

## Problem and result

The experiment tested whether the v25 static SOL provider order was suppressing
the historically stronger but sparse canonical Range Onset route. It compared
exactly two predeclared arms under one SOL slot:

1. current fallback: HT-Breakout, Range Onset, Hulk;
2. challenger: Range Onset, HT-Breakout, Hulk.

The arms produced identical accepted lifecycles and identical economics in both
the development and already-opened final blocks. There were zero entry
timestamps shared by HT-Breakout and Range Onset and zero accepted-trade
symmetric differences between arms. Static provider priority therefore did not
affect this historical path.

This rejects the proposed priority-only change. It does not establish that the
current SOL route set has positive aggregate edge.

## Frozen contract and sources

- Profile identity: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Profile fingerprint:
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- Initial account: $500.
- SOL notional: $75 per accepted lifecycle.
- Leverage: 5x.
- Crypto entry-fee identity: 4.5 bps.
- Shared ownership: one position in SOL, with no lifecycle eviction.
- HT-Breakout replay: 80-bps stop, eight-hour initial maximum hold, causal
  regime-supported extension to a 24-hour hard maximum, 4.5-bps fees per side,
  and 2-bps modeled slippage per side.
- Inputs: three frozen Hulk artifacts, one year of Hyperliquid SOL one-minute
  bars and funding, and twelve frozen canonical SOL Range Onset artifacts.

The opened final block had already been inspected. It is descriptive and was
not used to select the decision.

## Development evidence

The development phase contained 933 fully resolved input lifecycles. Both arms
accepted 832 and rejected 101 because SOL was already occupied.

| Route | Accepted | Net USD | PF | Long net | Short net |
|---|---:|---:|---:|---:|---:|
| HT-Breakout | 781 | -79.39 | 0.78 | -54.07 | -25.32 |
| Range Onset | 19 | +24.11 | 4.80 | +0.19 | +23.93 |
| Hulk | 32 | -9.00 | 0.35 | -8.22 | -0.78 |
| Shared SOL path | 832 | -64.28 | 0.83 | n/a | n/a |

Shared-path maximum drawdown was 15.57%. Net result excluding the largest
winner was -$74.81. Canonical Range Onset remained positive in aggregate, but
its long side was nearly flat and the result remained winner-concentrated.

## Descriptive opened-final evidence

The final phase contained 178 fully resolved input lifecycles. Both arms
accepted the same 149 trades.

| Route | Accepted | Net USD | PF | Long net | Short net |
|---|---:|---:|---:|---:|---:|
| HT-Breakout | 135 | -24.97 | 0.58 | -11.30 | -13.66 |
| Range Onset | 7 | +4.07 | 2.88 | +2.43 | +1.63 |
| Hulk | 7 | +1.07 | 1.51 | -0.18 | +1.24 |
| Shared SOL path | 149 | -19.83 | 0.69 | n/a | n/a |

Shared-path maximum drawdown was 5.14%. Net result excluding the largest winner
was -$24.03. The final block contradicts any claim that the reconstructed SOL
HT-Breakout route was profitable under this friction contract.

## Interpretation

High confidence: static priority was not the limiting mechanism in these exact
historical paths. The two arms accepted identical trade IDs, and no
HT-Breakout/Range Onset entries shared a timestamp.

Medium confidence: the next SOL problem is component quality rather than route
ordering. The source data are venue-matched and include fees, slippage, and
funding, but one-minute bars cannot reproduce private IOC queue position, stop
gaps, or every live routing decision.

Low confidence: the current optimal executable SOL mix is known. Range Onset is
supportive but too sparse to carry the portfolio, while the dense reconstructed
HT-Breakout path is negative on both sides and Hulk evidence is unstable.

## Recommendation

1. Do not change v25 provider priorities from this experiment.
2. Do not evict an open lifecycle or reserve the SOL slot for an anticipated
   Range Onset signal; that would be a new gate and was not tested here.
3. Keep the protected live v25 process unchanged while positions are open.
4. Make the next bounded strategy experiment a SOL HT-Breakout parity and
   mechanism audit: first prove that historical decisions match the exact live
   provider contract, then compare only the frozen control with a minimal causal
   entry-timing challenger under the same exits and costs.
5. Preserve Range Onset as the sparse canonical challenger and continue
   separately attributed forward measurement. Do not relax it solely to create
   cadence.
6. Do not increase leverage, notional, or hold duration to compensate for the
   negative dense route.

If historical/live decision parity fails, fix the reconstruction before any
strategy inference. If parity holds and the minimal challenger remains negative
on both development and prospective evidence, the exact SOL HT-Breakout
contract should not be included in a newly generated successor profile. That
decision would require a new source-bound profile and explicit authorization;
this review has no execution authority.

## Falsifiers and limitations

The no-priority-effect conclusion is falsified by a missing input lifecycle, a
source hash mismatch, or a live router interpretation in which a higher static
priority may evict or reserve capacity against an already-open position. The
component-quality diagnosis weakens if exact live-parity HT-Breakout decisions
produce materially different lifecycles or if a sufficiently sized,
after-cost forward sample becomes positive on both sides without
largest-winner dependence.

The replay does not reproduce live regime-aware arbitration, order-book queue
position, every IOC fill, stop gaps, or mark-to-market drawdown between bar
observations. Its final block is descriptive because it was previously opened.
No live process, configuration, signal, order, position, stop, target, size,
leverage, allocation, priority, or protection changed in this experiment.

## Evidence

- Immutable artifact:
  `data/logs/research/sol_route_priority_interaction_20260809T152921Z.json`.
- Implementation plan:
  `docs/plans/2026-08-09-sol-route-priority-interaction.md`.
