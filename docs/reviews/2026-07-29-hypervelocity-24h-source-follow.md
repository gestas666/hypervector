# Hypervelocity 24-Hour Source-Follow Review

Date: 2026-07-29

## Question

Does the current pinned Hypertrader `TREND_DOWN` onset retain edge when it is
allowed to trade continuously, and do adjacent clock windows support or reject
the previously profitable 07:00-16:00 UTC result?

The creator's observed hours were availability hours, not an original market
condition. The 24-hour replay is therefore the primary fidelity test. Session
windows are report-only sensitivity experiments and are not presented as the
original strategy.

## Frozen execution contract

- current pinned source revision `ad15f2bdc949619be495a5f516babd08f7f52a90`;
- confirmed `TREND_DOWN` onset, short direction;
- label available five minutes after the completed 5-minute source bar;
- signal eligibility 60 seconds;
- completed source-bar range no greater than 100 bps;
- post-only maker entry with public trade-through admission;
- one BTC position at a time;
- 70% isolated margin, 40x leverage, and an 8% gross margin target;
- no stop and a 24-hour maximum hold;
- causal Hyperliquid mark liquidation, adverse-BBO liquidation execution,
  authentic fees, and official hourly funding;
- runtime configuration and ML observe-only authority unchanged.

The development interval is 2026-04-28 through 2026-07-27 UTC. July 27 is
reported separately as a fresh one-day sensitivity. It contains only one fill
and cannot estimate tail risk.

## Measured results

| Candidate | Fills | Targets | Liquidations | Final equity | Maximum drawdown |
|---|---:|---:|---:|---:|---:|
| 24 hours | 72 | 65 | 7 | $4,653.99 | -89.17% |
| 06:00-15:00 UTC | 21 | 21 | 0 | $26,843.05 | -32.50% |
| 07:00-16:00 UTC | 20 | 20 | 0 | $25,600.17 | -32.50% |
| 08:00-17:00 UTC | 20 | 20 | 0 | $25,626.10 | -32.50% |

All three session candidates also reproduced the single July 27 target and
ended that one-day replay at $10,476.87. The adjacent results show that the
observed profit is not caused by one exact hour boundary. They do not prove a
session effect because all three reuse the same 90-day evidence and the clock
hypothesis was motivated by that evidence.

The 24-hour target rate was 90.3%, close to the creator screenshot's observed
90.7% win rate. This numerical similarity is not sufficient edge: seven full
isolated liquidations outweighed 65 targets. Mean net PnL was approximately
+$302.69 for targets and -$3,574.40 for liquidations.

The 24-hour results were not stable by broad time partition:

| Partition | Fills | Targets | Liquidations | Net result |
|---|---:|---:|---:|---:|
| Asia-side hours | 22 | 18 | 4 | -$6,403.12 |
| 07:00-16:00 UTC | 32 | 32 | 0 | +$9,532.12 |
| US-side hours | 18 | 15 | 3 | -$8,475.01 |

These partition values are attribution totals from the 24-hour chronology,
not independent portfolio replays. The stateful session rows in the first
table are the authoritative portfolio comparisons.

## Exit and stop challengers

An opposite-source-regime exit closed shorts only after a causally available
confirmed `TREND_UP` or upward breakout. It reduced liquidations from seven to
four, but chronology changed 65 target outcomes to 56 targets, five regime
exits, and four liquidations. Final equity fell to $3,372.00 with -86.91%
drawdown. It is rejected.

A predeclared 6%, 10%, 14%, and 18% gross-margin stop grid removed full
liquidations but over-stopped the path:

| Stop | Fills | Targets | Stops | Final equity | Maximum drawdown |
|---|---:|---:|---:|---:|---:|
| None | 72 | 65 | 0 | $4,653.99 | -89.17% |
| 6% | 89 | 32 | 57 | $1,204.66 | -88.54% |
| 10% | 84 | 41 | 43 | $1,219.07 | -90.09% |
| 14% | 83 | 47 | 36 | $965.07 | -93.17% |
| 18% | 83 | 53 | 30 | $1,059.38 | -93.28% |

The 6% and 10% variants also stopped the sole fresh winner. This fixed-stop
family is rejected; fewer liquidations did not improve expectancy.

## Data and causal validation

The label input named `data/cache/BTC_1m_90d.parquet` is venue-matched. It
contains 129,532 `hl` bars that match the immutable 0xArchive Hyperliquid
candle bundle exactly on timestamps and OHLC values, plus 68 explicit
zero-volume `hl_gap_fill` minutes. No Binance bar is present in this input.

The live-replay adapter additionally validated the post-22:00 UTC forward
window with 2,513 L2 observations, 52,898 public trades, 13,215 causal context
updates, a 5.604-second maximum L2 gap, a 2.475-second maximum context gap, and
three funding observations. The strict source detector emitted no eligible
entry in that short window; no synthetic trade was created.

## Decision and confidence

The 24-hour source-follow candidate is rejected on the current window. The
three adjacent daytime candidates survive only as one frozen annotation
hypothesis pending a longer venue-matched challenge. No clock gate, exit gate,
stop, runtime strategy change, or model-authority change is authorized by this
review.

Confidence is high that the measured 90-day replay economics and causal
ordering are reproduced by the stored artifacts. Confidence is low-to-medium
that the daytime result is a durable edge because the same evidence motivated
and evaluated the hypothesis. A profitable multi-slice 24-hour result, or a
stable broader session result on the newly acquired pre-window history, would
increase confidence. Any materially negative expanded slice or new forward
liquidation would falsify the current session hypothesis.

## Artifact identities

- 24-hour replay: `b7d8b7a574cf463117b9488172e098f7bd3a461cb2452733a3267bb039efeb17`
- 06:00-15:00 replay: `524af7fc1f384117b369cff2fbe41699d0f5da490ddf753c8a3c179e1c48ae1b`
- 07:00-16:00 replay: `551b8ed6ba32eb1273398f6331b51f8e7d89b5d0efbd2955472322fe181cfe46`
- 08:00-17:00 replay: `39d0f9bd763c470078d819b431bf999cc22731bb188a8d8ced579fc6bdcace79`
- opposite-regime exit: `e80bb1f787fd1e1ee53b5572139c6b90c696a8d7752ea6a8ccf170ab0374ea20`
- fixed-stop grid: `8dd83fa602edc3f6e50cdfbc90bc422d61fab9da4521165e03b2631df5c8d8ed`

The expanded one-year 0xArchive acquisition is intentionally not claimed
complete here. Its final manifest and integrity audit must be recorded before
the longer-window comparison is treated as evidence.
