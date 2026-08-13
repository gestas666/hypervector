# SOL range-onset clean venue extension

Date: 2026-07-31

## 1. Problem restatement

The report-only SOL challenger enters on a causal completed-one-hour 10/30 SMA
cross only when the completed five-minute canonical state is `RANGE` or
`BREAKOUT`. It exits on an opposite/signal event, a 60/80-bps stop, or a
48-hour maximum hold. The question is whether the next available signal and
the joined clean January-February path survive authentic Hyperliquid depth,
public trades, fees, funding, and portfolio compounding.

This experiment has no execution or model authority. It does not modify the
running BTC shadow strategy.

## 2. Inputs and validation boundary

- Signal bars are Hyperliquid one-minute candles, not Binance candles. The
  January 24-February 26 slice contains seven venue REST gap-fill minutes.
  Two occur roughly 24 hours before the February 22 entry; neither replaces
  its one-hour closing bar.
- DuckDB imported 335 new checksum-verified SOL hourly pairs and skipped one
  already-identical pair for February 12-26.
- The joined January 24-February 26 window contains 5,378,682 L2 snapshots,
  4,668,480 deduplicated public trades, and zero empty-book hours.
- Every fill walks the first fresh finite L2 snapshot. Stops are conservatively
  bounded by the first public-trade crossing. Funding uses the archived
  Hyperliquid series. SOL leverage stays at or below its 20x venue maximum.
- Sampled mark/oracle partitions are not yet present for this window. The
  event replay therefore reports realized-equity drawdown and explicit
  isolated-liquidation prices, but not continuous mark-to-market drawdown.

## 3. New signal result

The February 22 07:00 UTC short entered at $85.243 and reached its 48-hour
exit on February 24 07:00 UTC. Neither the 60-bps nor 80-bps public-trade stop
crossed.

| Exposure | Net PnL | Return on $15,000 | Fees | Funding | Exit impact | Liquidation |
|---:|---:|---:|---:|---:|---:|---:|
| 0.5x | +$751.39 | +5.01% | $6.41 | -$7.14 | 0.74 bps | none modeled |
| 3.0x | +$4,505.71 | +30.04% | $38.45 | -$42.85 | 1.39 bps | none modeled |

The public-trade tape never crossed even the tighter stop, which lies well
inside the modeled liquidation boundary. A mark-only excursion without a
corresponding public trade remains possible and is the reason sampled-mark
validation is still required.

## 4. Joined clean path

| Stop / exposure | Trades | W/L | PF | Final equity | Return | Realized DD | Liquidations |
|---|---:|---:|---:|---:|---:|---:|---:|
| 60 bps / 0.5x | 3 | 2/1 | 33.48 | $16,814.20 | +12.09% | -0.37% | 0 |
| 80 bps / 0.5x | 3 | 2/1 | 26.86 | $16,799.76 | +12.00% | -0.46% | 0 |
| 60 bps / 3.0x | 3 | 2/1 | 28.43 | $27,253.22 | +81.69% | -2.22% | 0 |
| 80 bps / 3.0x | 3 | 2/1 | 22.25 | $27,094.08 | +80.63% | -2.79% | 0 |

The 0.5x 60-bps event result is within $6.19 of the matching 2-bps-per-side
bar replay. At 20 bps per side, the bar stress still returns +11.62% at 0.5x
and +77.90% at 3x. That supports entry/exit execution parity for these three
trades; it does not establish intratrade mark-path safety.

Across the two independent clean event blocks, November 26-January 10 and
January 24-February 26, the 60-bps 0.5x arm has 12 trades, five wins, seven
losses, zero liquidations, combined PF 8.38, and a product-of-block return of
+21.15% ($18,173.11 from $15,000). Both blocks are positive. The 3x arm has
the same 12 outcomes, combined PF 6.49, and a product-of-block return of
+171.25%, but its prior block's realized drawdown was -10.19% and the bar-wick
drawdown reached approximately -30%. It is not a prudent promotion candidate
without sampled marks and forward evidence.

## 5. Capacity correction and later clean block

Correction: the earlier recommendation to retain 0.5x as the lead was too
early. The next clean February 26-May 1 block completed nine trades at 0.5x
before failing closed at an entry where 29.56 SOL was visible versus 92.59 SOL
required. Its positive partial PnL is censored and cannot count as a completed
block. The 3x arm failed finite depth on its first exit.

A frozen 60-bps capacity ladder held the signal and stop constant while testing
0.10x, 0.15x, 0.25x, and 0.50x total-account notional. The two smaller arms
completed all 12 trades; the two larger arms failed the same thin-book entry.

| Exposure | Status | Trades | W/L | PF | Final equity | Return | Liquidations |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.10x | complete | 12 | 3/9 | 2.43 | $15,134.66 | +0.90% | 0 |
| 0.15x | complete | 12 | 3/9 | 2.42 | $15,201.46 | +1.34% | 0 |
| 0.25x | depth failure | 9 | 3/6 | censored | $15,412.71 | censored | 0 |
| 0.50x | depth failure | 9 | 3/6 | censored | $15,823.60 | censored | 0 |

Normalizing all three independent clean blocks to the same size gives 24
trades, 8W/16L, zero liquidations, and three positive block results. At 0.15x,
combined PF is 5.26 and product-of-block equity is $16,123.61 (+7.49%). At
0.10x, combined PF is 5.29 and equity is $15,742.78 (+4.95%). The 0.15x arm is
the largest tested size that completes every block, but it requires a live
capacity buffer because observed depth can still be lower in forward trading.

May added 17 declared empty-book hours. Three signal lifecycles are censored:
an open stop needed a fill during the May 8 outage, another entry arrived before
books resumed promptly after that outage, and later entries intersected the May
17/20 outages. They are excluded rather than imputed. An explicit causal candle
warm-up now preserves the prior 30-hour SMA state while execution resets only
after each gap.

Three additional gap-safe blocks completed at 0.15x. The first returned
$15,062.06 with 1W/5L and PF 2.00; the next two returned $14,983.92 and
$14,979.31 with three combined losses. Across all six complete clean blocks,
the lead has 33 trades, 9W/24L, zero liquidations, combined PF 4.15, four
positive blocks, two negative blocks, and product-of-block equity of
$16,150.65 (+7.67%). May therefore preserved positive aggregate expectancy but
added only about 0.17 percentage points to the prior product return.

The clean June 14 10:00-June 25 block added two long trades: one 48-hour winner
of $131.17 and one stopped loss of $15.93 at 0.15x. It returned +0.77% with PF
8.23, zero liquidation, zero measured impact, 1,245,669 L2 snapshots, and
1,042,450 public trades. Across seven clean blocks the lead now has 35 trades,
10W/25L, zero liquidations, combined PF 4.33, five positive blocks, two negative
blocks, and product-of-block equity of $16,274.73 (+8.50%).

The first July signal was a short stopped for $15.71 at 0.15x, with 0.02 bps
measured exit impact and no liquidation. The next clean block added a $63.85
short winner at its 48-hour exit. The following block contained a stopped long
and a signal-exited short, losing $30.21 combined after $4.05 of fees and
$0.02 of adverse funding cash flow.

The July 21 short stopped for $15.74. The resolved July 27 block then added a
$61.29 signal-exited short and a $15.76 stopped short, netting $45.52. A long
entered on July 30 remains open at the evidence boundary and is excluded rather
than force-closed.

Across 12 complete clean blocks the lead has 42 trades, 12W/30L, zero
public-trade liquidations, combined PF 3.86, seven positive blocks, five
negative blocks, and product-of-block equity of $16,326.30 (+8.84%). Total
modeled fees are $85.49 and funding cash flow is -$12.09. This remains a block
product, not a continuous backtest across provider gaps.

## 6. Sampled mark-price challenge

All 368 UTC-day price partitions passed manifest, checksum, identity, and row-
count validation, providing 524,596 mark/oracle observations. The global series
contains 129 gaps above the preregistered two-minute active-position limit. The
largest is an 18.53-hour January 19 outage outside the included clean trade
paths. Seven of the 42 public-trade lifecycles intersect shorter 2.77-3.48
minute mark gaps. The limit was not relaxed after inspecting these gaps.

Query-scoped validation ignores gaps while flat but censors a block when an
active position crosses one. Seven blocks pass strictly; five blocks are
explicitly mark-censored. The fully mark-observed subset is:

| Exposure | Blocks | Trades | W/L | PF | Product equity | Return | Worst block mark DD | Liquidations |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.10x | 7 | 18 | 7/11 | 6.43 | $15,646.50 | +4.31% | -0.52% | 0 |
| 0.15x | 7 | 18 | 7/11 | 6.41 | $15,976.83 | +6.51% | -0.79% | 0 |

The same seven-block public-trade surface returned $15,975.40 (+6.50%, PF
6.36). Sampled marks therefore changed product equity by only +$1.42 in this
strict subset, although individual stop timing changed. This supports, but does
not prove, the absence of mark-triggered tail loss. The other 24 trades retain
public-trade economics; seven specifically lack continuous two-minute mark
coverage, so the full 42-trade headline is not fully mark-validated.

## 7. Uncertainties and failure modes

- The rule was selected after inspecting the full-year bar surface. Neither
  clean block is a pristine strategy-discovery holdout.
- The top three winners produce 48.4% of gross profit and the top five produce
  69.8%. The observed 28.6% win rate is economically viable only if rare trend
  payoffs continue to dominate frequent small losses.
- Declared provider gaps divide the evidence into blocks. Product-of-block
  compounding does not claim a continuous executable tape across those gaps.
- Public trades are a conservative stop proxy in many paths but cannot prove
  the venue mark never crossed and recovered between observations.
- Five blocks remain mark-censored. The observed -0.79% worst block mark
  drawdown applies only to the seven strictly covered blocks.
- Visible depth can disappear before an IOC reaches the venue. Private queue
  state and live latency remain unobserved.

## 8. Recommendation

Keep the 60-bps 0.15x arm as the provisional report-only SOL challenger. Reject
0.25x, 0.50x, and 3x as conservative finite-depth sizes on the current tape.
Promote it from isolated report-only replay to a no-submit, one-position shared-
portfolio forward observer, while keeping it out of live execution. The
observer must retain the 0.15x cap, finite-depth failure, two-minute mark-gap
telemetry, funding, and isolated-margin accounting. The unresolved July 30
long remains forward evidence rather than a fabricated historical close.

Confidence is medium that the candidate has positive historical economics on
the 12 public-trade blocks and seven strictly mark-observed blocks, low-to-
medium that the edge will persist, and low that the observed return cadence is
repeatable. A recovered mark path showing liquidation, repeated 0.15x depth
failure, an accounting correction reducing aggregate PF to one or below, or a
fresh forward PF at or below one would materially weaken or falsify the lead.

## 9. Verification and evidence identity

- 26 focused event, drawdown, risk, and friction tests passed.
- Focused Ruff checks passed.
- Extended event artifact SHA-256:
  `39d92326ca6e36a95c3510227dafbdb2d4eb570825bfbf2f446022c75f0c3925`.
- Extended friction artifact SHA-256:
  `e6b356b3d6f2309d160d00dd589602815d266d76189697619ecbfa5e9ee1859f`.
- Incremental February 12-26 event artifact SHA-256:
  `df64a6c01fa7246ab155023a3db9ae22e96a70b7fa3503668862faa901d05c44`.
- Capacity artifacts for November 26-January 10, January 24-February 26, and
  February 26-May 1 SHA-256:
  `98e94fd6fd63ec0495d4af196ff95635cd5595c1302aba4c556c66a903b915cc`,
  `98b14a847dfe08e1951df5d1e55af86e9b7900c519b5b28b2109bf19e2e624d5`,
  and `5f94db0b0ebf3f8e51b054998aa90bfa06812dd0167e01647ac664b4c8fd53fd`.
- Gap-safe May block SHA-256:
  `cf917657264acc987b203ad4ec596846af141858f9bd27fd3f3324ac0bf49b7b`,
  `67eeb2e0f81a507b23c195500802191606bcdd1f2fd330579fb6d73535e9b100`,
  and `16281f18f6484660ad4196325b4efe62156792f87143fb941b8d403e8e9c6054`.
- Clean June block SHA-256:
  `18181747bb0d23ae779bf5e1828449b62496e7bd39a17cfe0c399f96c5603acc`.
- First clean July block SHA-256:
  `308e03d71104300d22d0eb1fd3277073f17d7c9c2dca0b51d1b9f334f279e0c4`.
- Second and third clean July block SHA-256:
  `d037056b2573048e0b528fb4fa6587b5f1871602d227b129b0fed75227a182fb`
  and `eb70cd33d48e0df77f95c80eeb06c14ab09325de3a901b8eab868d559ba0b07b`.
- July 21 and resolved July 27 public artifacts SHA-256:
  `71aed07ad24b4e39acc3e4c5cbc54a8e987bfa2a317f20d37ddd6a0f5486cde5`
  and `fa853bed20ff1195e5c0596b022b6f5e11625feb3463af625bad47ee35de3180`.
- Strict mark artifacts for the seven passing blocks SHA-256:
  `c770ac312ce172a1e823ebfffd70c7ab52249f087037eec0f29357bb082f8968`,
  `a1a719f8713f29d66a4f600f6352c57e13bb8945aaeed1b3bfde20673eb223af`,
  `8e14c153b8a8f3472734a4c571893b34d2c2e21489f4026889993b97c4d9ecd1`,
  `303bdb6b5b0181d1e20b0d6f75b84edc1124c7962758e3e5c804e8ba7740bc8c`,
  `172296cc2f206448deffe1cc267656fd8c356207cf068aa84518d14a04f476b6`,
  `135370ec1875cfd022ffcc572157ed9ba2dbae95023ea049b1e0340cf38eba0c`,
  and `0545357d9bdc17f5fba6bd94072aadfe8066e819c9817c48a2476696af4880a8`.
- Mark-censored artifacts for the other five blocks SHA-256:
  `bd41503a0be1cd844e9e4c2034259f93e0687805f5e279b575c484a6bafaefc9`,
  `498c27cfc5aaf1540828f4d8916d2464cae428ffdd99debc6ebf7232acc4eae4`,
  `84f9bb8a0facf5b59cb4edbbcd6dafa6514052cc1a0ef4a6c0c71b8c4ee8d740`,
  `f82338372cfa8359cf0eb7ad39a2247804cae6edf6732a9651ea1d90a2adb68e`,
  and `baf9e1af0a6f961d116f02479e164a0986612436e58aa6958cc8bbb3b9df5411`.
