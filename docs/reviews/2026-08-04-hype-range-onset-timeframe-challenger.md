# HYPE range-onset timeframe challenger — 2026-08-04

## Decision

Do not replace the current 1h range-onset cross with the tested 5m, 15m, or
30m form. Faster crosses increased trade count, but 5m and 15m became
after-cost churn and 30m did not survive all chronological segments. No live
entry, exit, sizing, routing, or model authority changed.

Confidence is high that the fixed 5m and 15m variants are unsuitable under the
measured bar-execution contract because both sides lost in development,
validation, pseudo-holdout, and the continuous year. Confidence is medium that
30m is unsuitable: its validation and pseudo-holdout were positive, but
development and the continuous year were negative. Confidence is low in the
apparent positive continuous 1h baseline because two paths crossing synthetic
continuity bars contributed more than its entire net gain.

## Frozen experiment

- Artifact:
  `data/logs/research/range_onset_timeframe_challenger_HYPE_20260804T1527Z_v2.json`
- SHA-256:
  `bb4a3b83e826ce01b3c6345d3e36c965045c8698f808f14c5a4a92e0f667ed13`
- Venue: Hyperliquid HYPE one-minute candles and exact hourly funding history.
- Window: 2025-07-28 through 2026-07-28; 525,600 minute rows and 8,760 funding
  events.
- Chronology: development through 2026-01-28, validation through 2026-05-28,
  and explicitly non-pristine pseudo-holdout through 2026-07-28.
- One changed variable: completed SMA10/30 cross timeframe (`5min`, `15min`,
  `30min`, or the `1h` baseline).
- Fixed admission: completed canonical 5m `RANGE` or `BREAKOUT`.
- Fixed risk: $15,000 initial equity, 10% isolated margin, 5x leverage,
  60-bps price stop, 48-hour maximum hold, and one position.
- Fixed friction: 4.5-bps entry fee, 4.5-bps market-exit fee, 2-bps adverse
  entry slippage, 2-bps adverse market-exit slippage, and supplied hourly
  funding. No target was used.
- Causality: a source cross becomes visible only on the final minute of the
  fully completed source bar; the simulated order fills at the next minute
  open.

## Results

### Continuous year

| Cross | Trades/30d | Trades | Net PnL | PF | Max DD | Long net | Short net |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5m | 90.7 | 1,104 | -$8,585.26 | 0.639 | -60.29% | -$5,117.62 | -$3,467.65 |
| 15m | 31.7 | 386 | -$4,076.01 | 0.682 | -30.19% | -$2,697.60 | -$1,378.41 |
| 30m | 7.5 | 91 | -$207.29 | 0.945 | -8.58% | +$182.81 | -$390.10 |
| 1h | 4.6 | 56 | +$260.15 | 1.094 | -7.14% | -$1,156.32 | +$1,416.47 |

### Chronological net PnL

| Cross | Development | Validation | Pseudo-holdout |
|---|---:|---:|---:|
| 5m | -$5,771.87 | -$3,854.28 | -$967.35 |
| 15m | -$3,184.02 | -$990.72 | -$151.66 |
| 30m | -$361.71 | +$38.20 | +$119.72 |
| 1h | +$189.96 | +$190.02 | -$119.19 |

The 5m and 15m candidates supplied the desired frequency but not the edge.
Fees alone were $4,808.68 and $2,126.39 respectively in the continuous
portfolio. Both directional legs lost, so the result is not caused by omitting
longs or shorts.

The 30m candidate is the least-bad faster form. Its clean pseudo-holdout had 13
trades, +$119.72, PF 1.223, and -4.43% maximum drawdown, but the long leg made
the pseudo-holdout gain while the short leg lost; the side relationship was
different in other segments. This is instability, not a repeatable
bidirectional result.

## Gap-path correction

The archive contains 183 explicit `hl_gap_fill` rows. These are labeled,
zero-volume prior-close continuity bars rather than observed venue candles.
The artifact reports every completed trade whose signal-to-exit path touches
one.

The continuous 1h portfolio has two gap-touched paths contributing +$695.11,
while total net PnL is only +$260.15. Therefore the positive continuous result
cannot support an edge claim. This corrects any interpretation that treated
the raw +$260.15 as clean evidence. The 1h pseudo-holdout contains no
gap-touched trades and loses $119.19.

The 30m pseudo-holdout also contains no gap-touched trades. Its small positive
result is authentic to the supplied bars, but development failure and only 13
pseudo-holdout trades keep confidence low.

## Missed-opportunity interpretation

Raw crosses were much more common than admitted crosses. In the continuous
year, 5m emitted 4,198 raw directional crosses but only 1,108 admitted events;
30m emitted 689 raw crosses but admitted 91. This does not prove the regime
filter discarded profitable trades. Removing the filter from hindsight would
mix causal blockers and overlapping positions.

The live checkpoint now evaluates eligible paths and exact one-blocker near
misses separately, after fixed 13-bps estimated round-trip friction and a
26-bps robust gross-move hurdle. That is the appropriate forward evidence for
whether a specific blocker prevented a capturable move. Multi-blocker rows are
not credited to every failed condition.

## Failure modes and falsifiers

- Bar simulation cannot reproduce IOC latency, spread at order time, queue
  position, depth impact, websocket loss, or rate limiting.
- The pseudo-holdout has been reused by prior project research and is not
  pristine out-of-sample evidence.
- A materially cheaper executable fill path could improve the high-turnover
  variants, but it would need to overcome multi-thousand-dollar losses, not a
  marginal cost difference.
- The 30m decision should be updated if a fresh venue-native forward window
  produces both long and short cost-clearing results with stable drawdown and
  enough independent trades. Repeating the current 13-trade outcome alone is
  insufficient.
- Any prefix non-invariance or signal before the completed source-bar endpoint
  would invalidate the experiment.

## Recommendation

Retain all four results and stop the simple timeframe-substitution branch. Do
not hot-mutate the running live cohort. Continue measuring the current live
strategies using accepted-trade MFE/MAE, exit capture, post-exit continuation,
and exact one-blocker opportunity paths. The next strategy change should be
supported by those causal diagnostics or a genuinely different entry
hypothesis, not another faster version of the same SMA cross.

