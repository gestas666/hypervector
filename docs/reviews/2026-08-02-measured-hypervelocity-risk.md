# Measured Hypervelocity exposure review

## Problem restatement

The experiment held the corrected bidirectional completed-5m source signal and
26.67-bps BTC target constant while reducing isolated margin allocation and
leverage. Success meant materially lower liquidation and drawdown risk without
silently changing signal selection, exit target, venue friction, or ML
authority.

## Evidence and assumptions

- Window: 2026-04-28 through 2026-07-28; initial equity: $15,000.
- Venue evidence: 12,202,083 Hyperliquid L2 snapshots, 36,931,672 public
  trades, mark/oracle prices, funding, maker/taker fees, and isolated
  liquidation accounting.
- Fill assumption: public trade-through. Private queue rank and cancellations
  are not observable.
- Corrected source clock: completed 5m signal range, not the superseded 1m
  range implementation.
- Immutable artifact:
  `data/logs/research/hypervelocity_measured_exposure_20260428_20260728_trade_through_v1.json`
  (`25f8b7c1aa1490ee6766e4f7d1e06089e54c9f833d4c617f64c7e8dad947220f`).

## Results

| Risk arm | Trades | Target / other exits | Net PnL | PF | Max drawdown | Liquidations |
|---|---:|---:|---:|---:|---:|---:|
| 35% margin / 30x / no stop | 55 | 50 / 1 time + 4 liquidation | -$4,175.63 | 0.800 | -59.43% | 4 |
| 5% / 3x / no stop | 72 | 66 / 6 time | -$20.71 | 0.945 | -1.28% | 0 |
| 5% / 3x / 60-bps stop | 76 | 55 / 21 stop | -$22.74 | 0.928 | -0.47% | 0 |
| 10% / 5x / no stop | 68 | 63 / 5 time | +$145.58 | 1.148 | -3.90% | 0 |
| 10% / 5x / 60-bps stop | 72 | 54 / 18 stop | +$54.18 | 1.059 | -1.41% | 0 |

The 10% / 5x / no-stop arm is the measured lead. It used 0.5x equity gross
notional and retained the 26.67-bps price target, which becomes a 1.333% gross
margin-return target at 5x. It produced 68 fills in 91 days, approximately 0.75
fills per day.

## Attribution

- **Signal:** identical corrected source decisions across arms.
- **Sizing:** reducing 30x/35% to 5x/10% eliminated observed liquidations and
  reduced maximum drawdown from 59.43% to 3.90%.
- **Stop:** the tested 60-bps stop reduced drawdown but cut net PnL from
  $145.58 to $54.18. Twelve of its 18 stopped signals later reached the same
  target in the no-stop arm; five became time exits. This stop was therefore
  too tight for this signal/hold contract.
- **Cadence:** the safer lead remains modest, not a solution to the larger
  portfolio-income objective by itself.

## Missing-book audit

The lead had two active missing-L2 windows, 2026-05-22 11:00-13:00 UTC, both
inside one short opened at 07:05 UTC and closed at its target at 13:33 UTC.
Independent venue price records during the missing hours showed:

- 11:00-12:00 UTC minimum mark/mid: $77,156.00 / $77,142.50.
- 12:00-13:00 UTC minimum mark/mid: $77,382.00 / $77,383.50.
- Trade target: $77,093.87.

The target was not reached during the missing-book interval. Under this
no-stop, target-or-24h-hold contract, the gap therefore does not appear to have
manufactured the exit. This narrows the failure concern but does not recover
private queue position or make execution economics conclusive.

## Impulse ML v1 challenger

Hypertrader's saved `ml_impulse_1m_long_mr_v1` and short bundle are range
mean-reversion fades, not Hypervelocity trend/breakout metalabels. Their saved
evaluation artifacts reported PF below 0.4 and strongly negative returns after
cost stress despite useful classifier AUC. The source and saved evaluation
contracts also disagree on barriers, hold time, and leverage. They remain an
observation-only RANGE challenger and are not allowed to filter or scale this
candidate.

## Confidence, failure modes, and falsifiers

- **High confidence on survivability improvement:** same decisions and price
  target, zero observed liquidations, and much lower drawdown. This would be
  falsified by an implementation-parity failure or a fresh shadow run showing
  materially different sizing/liquidation accounting.
- **Medium-low confidence on positive edge:** PF 1.148 and +0.97% over 91 days
  are development-selected and economically modest. A fresh forward window
  with PF below 1 after fees/funding, repeated time-exit losses, or materially
  worse maker fills would update the lead downward.
- **Execution uncertainty:** private maker queue rank remains unobserved. Live
  canary acknowledgement, fill latency, slippage, markout, fees, funding, and
  cancel/replace evidence are required before live promotion.
- **No implicit gate:** these are reported trial results under the project
  charter, not an automatic prohibition on further trials.

## Recommendation

Run the 10% / 5x / no-stop profile as a disarmed shadow candidate with ML in
annotation-only observe mode. Keep the other arms and Impulse ML v1 as
report-only challengers. Do not represent this as live-proven or as sufficient
portfolio profit; its current value is a much more survivable forward test of
the same source signal.
