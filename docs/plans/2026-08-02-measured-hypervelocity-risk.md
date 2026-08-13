# Measured Hypervelocity exposure experiment — 2026-08-02

## 1. Problem restatement

Test whether the frozen source-follow Hypervelocity short entries remain useful
when leverage and isolated margin exposure are reduced substantially. The
experiment must keep the BTC target move, signal timestamps, maker-order rules,
fees, funding, liquidation model, and maximum hold unchanged so position sizing
is not confused with a different trade.

This is report-only research. It has no execution authority and does not alter
the running observer, live configuration, regime detector, or ML authority.

## 2. Known facts and assumptions

- The source-follow selector currently emits only short decisions.
- The existing 35% margin / 30x control targets an 8% margin return, equal to a
  26.6667 bps favorable BTC price move before fees.
- Earlier lower-leverage comparisons incorrectly retained an 8% margin target.
  They therefore changed both leverage and target distance.
- Exact recent Hyperliquid replay includes public trade-through maker fills,
  recorded L2, maker/taker fees, funding, mark/oracle context, isolated
  liquidation, and a 24-hour maximum hold.
- The authoritative corrected 24/7 control uses completed five-minute signal
  ranges: 102 signals, 55 fills, and 50 targets. The older 33-signal artifact
  applied that range rule to one-minute bars and is explicitly superseded.
- A fixed stop can reduce tail loss but may stop trades that later reach target.
  Prior 15–45 bps price-space stops were harmful on related evidence; the new
  60 bps stop is a hypothesis, not an assumed improvement.

## 3. Frozen development matrix

All arms use the same 26.6667 bps target, 60-second maker-entry lifetime,
60-second regime-reset re-entry policy, 24-hour maximum hold, and exact entry
decision stream.

| Arm | Margin | Leverage | Gross notional | Price stop | Planned stop loss before friction | Maximum isolated margin exposure |
|---|---:|---:|---:|---:|---:|---:|
| Control | 35% | 30x | 10.50x equity | none | unbounded before liquidation | 35% |
| Minimal exposure | 5% | 3x | 0.15x equity | none | unbounded before liquidation | 5% |
| Minimal exposure + stop | 5% | 3x | 0.15x equity | 60 bps | 0.09% equity | 5% |
| Measured exposure | 10% | 5x | 0.50x equity | none | unbounded before liquidation | 10% |
| Measured exposure + stop | 10% | 5x | 0.50x equity | 60 bps | 0.30% equity | 10% |

The planned stop loss excludes fees, slippage beyond the trigger, funding, and
gap risk. The maximum isolated margin exposure is reported separately because
a stop is not a guarantee of execution price.

## 4. Measurements and attribution

For every arm report completed trades, targets, stops, time exits,
liquidations, partial liquidations, net PnL, profit factor, maximum drawdown,
fees, funding, and replay-data uncertainty annotations.

Attribution is pairwise:

1. Control versus no-stop low-exposure arms estimates exposure and target-
   invariance effects.
2. Each no-stop arm versus its identical stopped arm estimates the incremental
   stop effect.
3. Signal-level target/time-exit/liquidation paths remain visible so reduced
   dollars are not misreported as improved signal quality.

## 5. Validation and falsification

The 2026-04-28 through 2026-07-28 exact venue interval is development evidence
because prior losses motivated the experiment. All predeclared arms will be
reported; performance is not a technical abort gate.

Control parity is pinned to
`hypervelocity_source_all_day_strict_tuned_20260428_20260728_trade_through_hv35x30_v2.json`
with SHA-256
`9c6f769f178cbbabf425ee9fc5ff429e67107e0e533636ae9821a410aacd15d8`.

Evidence against the measured approach includes profit factor at or below one,
stops preventing more eventual targets than tail losses avoided, material data
gaps overlapping decisive trades, or an accounting/parity mismatch. Evidence
for further testing requires positive net performance, materially smaller
drawdown and liquidation loss, and no unexplained replay mismatch. Promotion
would still require a frozen older block or fresh forward venue-matched window.

## 6. Separate 1m impulse ML track

Hypertrader's `ml_impulse_1m_*_mr_v1` models are range mean-reversion fades,
not Hypervelocity trend/breakout entries. Their saved evaluation reports show
classifier AUC without net economic edge after costs. They remain a separate,
low-leverage annotation/challenger track. They will not be merged into this
sizing experiment or granted execution authority.

## 7. Confidence and update conditions

Confidence is high that this matrix cleanly separates leverage, target
distance, and stop effects in the existing replay implementation. Confidence
is low that the 60 bps stop is profitable before the replay is run. A contract
calculation error, target-price mismatch, or replay parity failure would update
the first assessment immediately.
