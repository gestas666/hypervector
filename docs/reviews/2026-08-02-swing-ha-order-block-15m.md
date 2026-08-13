# Swing + Heikin-Ashi + Order-Block 15m Review

## Chart-domain correction

The initial artifact below did not exactly reproduce the user's TradingView
workflow. It calculated Swing Auto pivots, EMA state, BUY, and SELL from raw
OHLC and used Heikin-Ashi only for candle color. On a TradingView Heikin-Ashi
chart, the Pine indicator receives Heikin-Ashi OHLC. The initial artifact is
therefore retained as a superseded reconstruction, not evidence for the exact
requested rule.

`build_swing_ha_chart_signals` now computes pivots, EMA 9/21, BUY/SELL state,
order-block context, and candle color in the Heikin-Ashi chart domain while
retaining raw Hyperliquid prices for fills. A position exists only while both
BUY+green or SELL+red remain true and closes when either condition fails.

The corrected requested 9/21, pivot-5 rule was still broadly negative in a
bounded diagnostic: 4,212 development trades and about -$31,114 across four
independent asset accounts; downstream validation and pseudo-holdout were about
-$18,929 and -$19,436. All 18 predeclared EMA/pivot combinations lost on every
asset. The least-bad 50/200, pivot-5 cell still lost about -$21,619 on 2,415
development trades, with asset profit factors from 0.453 to 0.632. Trend-level,
Krown, Cipher, order-block, BTC/SOL L2-imbalance, and microprice entry contexts
did not make an asset positive.

Three deterministic tests bind the corrected chart domain, exact dual-state
hold rule, and separation of signal prices from raw execution prices. The
corrected diagnostic was not promoted into an immutable replay artifact, so its
rounded totals should be treated as rejection support rather than a new
performance benchmark. Reproducing a materially positive corrected run from
the same frozen bars and friction would falsify this correction.

## Superseded initial reconstruction outcome

The exact reconstructed strategy is rejected as a runtime provider. It should
not replace an incumbent or be added to the automatic cohort. Every asset lost
in development, validation, and pseudo-holdout after realistic friction; most
asset-periods also lost before fees. Both long and short sides traded densely,
so this is not a sparse-sample conclusion.

This is a report-only result. No runtime adapter, TUI strategy tile, model,
order client, or execution authority was created.

## Source reconstruction

`swing-auto.pine` is a repeated breakout-state indicator, not a one-shot
reversal strategy. A BUY remains true on every bar above the latest confirmed
pivot high with bullish EMA alignment; SELL is symmetric. Its pivot label is
drawn backward even though the pivot requires future right-hand bars before it
is knowable. The implementation exposes pivots only at confirmation time and
converts repeated states into explicit state/onset alternatives.

`order-block-finder.pine` also back-plots its source candle. Its default 0%
displacement threshold admits weak blocks, and its own alerts say a block is
not a trade signal. The experiment therefore tested it as agreement or a
structural stop, never as hidden historical knowledge.

Heikin-Ashi values were recursive signal features only. All entries, exits,
fees, liquidation checks, and PnL used raw Hyperliquid prices at the next
15-minute open.

## Data and execution contract

- BTC, ETH, SOL, and HYPE native Hyperliquid perpetual candles.
- 525,600 one-minute rows and 35,040 complete 15-minute bars per asset from
  2025-07-28 through 2026-07-28.
- Authentic funding: 8,760 hourly observations per asset.
- Development/validation/pseudo-holdout: 184/90/91 calendar days.
- Independent $15,000 asset screens, 10% isolated margin, 5x leverage.
- Taker fee 4.5 bps and adverse slippage 2 bps per market side: 13 bps nominal
  round trip. Stress is 20 bps round trip.
- One position per coin, next-bar execution, authentic funding, isolated
  liquidation, and liquidation-first native-bar ambiguity ordering.

The pseudo-holdout is not globally sealed because earlier project research
inspected the period. It is still chronologically downstream from this frozen
development selection.

## Development tuning

The base grid retained all 72 combinations of six EMA pairs, three pivot
lengths, state/onset entry, and two mismatch exits. The best requested 9/21
shape was `pivot=8, onset, HA-flip`; it still lost on all four assets and all 12
asset-fold cells:

| Shape | Trades | Net across independent asset screens | Positive assets/folds | Worst asset DD |
|---|---:|---:|---:|---:|
| Best 9/21 | 3,836 | -$29,867.66 | 0/4, 0/12 | 70.52% |
| Selected base 50/200, pivot 8, onset/alignment-loss | 2,454 | -$21,055.73 | 0/4, 0/12 | 56.69% |
| Selected OB agreement, 3 bars, 0.50% move | 1,997 | -$18,251.95 | 0/4, 0/12 | 48.01% |

The order-block agreement reduced turnover and loss relative to the base but
did not create positive economics. Structural-stop variants did not improve
the selected control materially.

## Frozen downstream results

Nominal results for the development-selected 50/200, pivot-8,
onset/alignment-loss, three-bar/0.50% order-block-agreement configuration:

| Segment | Asset | Trades | Gross PnL | Net PnL | PF | Max DD | Long/Short |
|---|---|---:|---:|---:|---:|---:|---:|
| Validation | BTC | 219 | -$904.64 | -$2,264.69 | 0.541 | 16.72% | 96/123 |
| Validation | ETH | 219 | -$649.00 | -$2,015.18 | 0.686 | 15.83% | 92/127 |
| Validation | SOL | 249 | +$140.72 | -$1,495.70 | 0.761 | 11.62% | 96/153 |
| Validation | HYPE | 263 | -$1,802.57 | -$3,379.38 | 0.605 | 24.14% | 138/125 |
| Pseudo-holdout | BTC | 233 | -$1,049.68 | -$2,492.51 | 0.395 | 16.62% | 110/123 |
| Pseudo-holdout | ETH | 192 | -$1,120.64 | -$2,328.51 | 0.453 | 15.52% | 85/107 |
| Pseudo-holdout | SOL | 253 | -$1,175.59 | -$2,746.27 | 0.537 | 19.04% | 125/128 |
| Pseudo-holdout | HYPE | 299 | -$1,205.92 | -$3,063.41 | 0.646 | 21.15% | 160/139 |

Validation nominal was -$9,154.96 across four independent $15,000 screens;
pseudo-holdout nominal was -$10,630.69. The 20-bps stress results were
-$13,207.63 and -$14,663.05. One-bar delayed entry was -$10,878.49 and
-$13,429.09. All variants had zero liquidations, which validates the restrained
risk assumptions but does not rescue the negative signal.

Median nominal hold was 45 minutes. Validation long trades averaged +0.74 bps
gross but -8.31 bps net; shorts averaged -9.12 bps gross and -18.17 bps net.
Pseudo-holdout long/short gross means were -4.10/-9.43 bps. This is primarily a
signal/turnover failure, not merely an overly punitive fee model.

Only zero or one trade per asset/scenario touched an explicit continuity-filled
bar. Losses were broad, so gap reconstruction is not a plausible explanation.

## Recommendation

Keep the Pine components available as chart annotations, especially confirmed
swing structure and active order-block zones. Do not route this exact strategy,
replace a provider with it, or add it as an automatic provider. A more selective
future strategy may reuse a feature, but that would be a different mechanism
requiring a newly frozen experiment—not a neighboring EMA/pivot resweep on the
same year.

## Integrity evidence

- JSON: `data/logs/research/swing_ha_order_block_15m_all_assets_v1.json`
- Trades: `data/logs/research/swing_ha_order_block_15m_all_assets_v1.trades.parquet`
- JSON SHA-256:
  `1a8353020bd32b14cef4618ce740b3b0b7317aa72bfee203703667ae37543078`
- Parquet SHA-256:
  `f8f4fc63079766ed6e1a6fd20127ceba5710b8a507a27ac599b6089b5ed22215`
- Independent validator: 72 base trials, 13 order-block trials, six downstream
  scenarios, 6,054 trade rows, all authority `none`, exact source/generator
  hashes, causal timing, and PnL/equity arithmetic valid.

## Confidence and falsifier

**Confidence: high for rejecting this exact strategy contract.** The conclusion
is supported by thousands of bidirectional trades, every coin, downstream
periods, delayed entry, stressed friction, and predominantly negative pre-cost
returns. A material bug in confirmed-pivot timing, raw-price execution,
funding/fee arithmetic, or source identity would invalidate the artifact. A
separately frozen lower-turnover mechanism with positive gross and net outcomes
across coins/folds would update the broader view; additional tuning of this same
negative family would not.
