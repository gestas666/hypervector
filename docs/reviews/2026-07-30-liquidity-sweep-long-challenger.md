# Liquidity-sweep long challenger review — 2026-07-30

## 1. Problem restatement

The running source-follow shadow candidate is deliberately short-only. The
requested system still needs a long arm, but a symmetric long mirror previously
failed. This review tests a distinct long hypothesis while leaving backend
runtime authority unchanged.

Success for this research stage means:

- one causal BTC long signal with no short arm;
- one shared $15,000 portfolio and at most one open BTC position;
- Hyperliquid fees, funding, isolated liquidation, and chronological execution;
- positive behavior across fixed chronological bar windows;
- survival of strict public-trade-through maker replay before any shadow wiring.

## 2. Assumptions and known facts

- The signal is the pre-existing default `liquidity_sweep_long` strategy on
  completed 1-hour bars: a downside range sweep, close reclaim, volume
  confirmation, and close at or above EMA-55.
- A 10:00–10:59 signal bar becomes actionable at 11:00. Focused tests lock this
  boundary so the replay cannot trade from an incomplete hour.
- The low-risk reference uses 10% allocation, 5x leverage, a 60 bps stop,
  signal exits, and a 48-hour hold.
- The aggressive challenge uses 35% allocation, 30x leverage, an 8% gross
  margin target, a 60 bps stop (18% leveraged margin loss before costs), and a
  24-hour hold.
- The exact replay uses a 60-second post-only order lifetime, maker target,
  taker stop, authentic funding, mark/oracle context, and public
  trade-through entry evidence.
- No ML model filters or sizes these trials. Metalabel authority remains
  observe-only.
- The active backend remains the separate short-only source-follow shadow
  candidate. No long runtime path was enabled.

## 3. Analysis and evidence

### Low-risk isolation

The long side was first isolated so paired short signals could not block it.
The unchanged low-risk reference was positive in all three chronological
windows:

| Window | Trades | W/L | PF | Net PnL | Max DD | Liquidations |
|---|---:|---:|---:|---:|---:|---:|
| 2025-07-28 to 2026-01-28 | 10 | 5/5 | 1.22 | +$60.47 | -1.33% | 0 |
| 2026-01-28 to 2026-04-28 | 6 | 2/4 | 1.02 | +$4.33 | -1.52% | 0 |
| 2026-04-28 to 2026-07-28 | 6 | 2/4 | 1.64 | +$139.89 | -1.41% | 0 |

This supports continued research but not deployment: 22 trades are sparse and
the total dollar return is too small for the stated objective.

### Broader long isolation

A subsequent bounded screen isolated all five registered source-derived long
arms under the same low-risk managed profile. This removed short-side capital
conflicts that could have distorted the earlier paired screen.

| One-hour long | Development PF | Validation PF | Latest PF |
|---|---:|---:|---:|
| Donchian trend | 0.59 | 0.75 | 0.35 |
| Squeeze breakout | 0.84 | 0.93 | 0.04 |
| Liquidity sweep | 1.22 | 1.02 | 1.64 |
| Zero-lag reclaim | 0.88 | 0.75 | 0.75 |
| Regime trend router | 1.26 | 0.86 | 0.17 |

Liquidity sweep was the only one-hour long with PF above one in all three bar
windows. Moving the same five candidates to 15-minute execution did not create
a higher-frequency solution: every validation and latest-window PF was below
one. The regime router's 24-trade development result was separately isolated,
then failed with PF 0.86 and 0.17 in the next two windows. It is rejected
without exact order-book replay.

This comparison strengthens the relative case for retaining liquidity sweep,
but it is still exploratory and does not turn its sparse exact result into a
proven edge.

### Aggressive no-stop challenge

Applying the current 35%/30x/8%/24-hour shape without a stop produced 10/10
and 6/6 targets in the first two windows, then five targets and one liquidation
in the latest window. The latest result was -$1,885.73 with PF 0.51 and
-22.61% drawdown. One liquidation erased the preceding winners. This contract
is rejected.

### Signal-wick stop

A retrospective stop at the completed bullish sweep-bar low removed
liquidations but was negative in every window: PF 0.49, 0.87, and 0.64. It
stopped too many eventual targets and is rejected.

### Fixed 60 bps stop

The pre-existing 60 bps stop was combined with the aggressive contract without
searching neighboring stop values:

| Window | Targets/stops | PF | Net PnL | Max DD | Liquidations |
|---|---:|---:|---:|---:|---:|
| 2025-07-28 to 2026-01-28 | 7/3 | 0.76 | -$772.97 | -9.81% | 0 |
| 2026-01-28 to 2026-04-28 | 5/1 | 1.69 | +$742.72 | -7.68% | 0 |
| 2026-04-28 to 2026-07-28 | 5/1 | 1.61 | +$734.64 | -7.15% | 0 |

The combined retrospective result is approximately +$704.39. The first window
fails, so this is not a stable proven edge; the two latest windows justify an
exact execution challenge.

### Exact 91-day Hyperliquid trade-through replay

The fixed-stop candidate was replayed over 12,202,083 canonical L2 snapshots
and 36,931,672 deduplicated public trades:

- six signals and six maker submissions;
- five fills and one 60-second expiration;
- four targets and one stop;
- zero liquidations, zero time exits, and zero open positions at the end;
- $15,376.31 final equity from $15,000, or +$376.31;
- filled-trade PF 1.3225;
- -7.39% maximum drawdown;
- -$4.02 funding cashflow.

The stricter fill model removed one winner assumed by the bar screen, reducing
latest-window PnL from +$734.64 to +$376.31. That degradation is plausible and
material.

The archive contains 21 declared empty-book hours, so the replay conservatively
reports `execution_economics_conclusive=false`. A direct interval join found
zero overlap between those gaps and any of the six pending/open lifecycles;
the replay also reports `active_book_gap_windows=0`. This lowers but does not
eliminate evidence risk.

## 4. Uncertainties, risks, and failure modes

- **Sparse outcomes:** Five exact fills cannot estimate a dependable win rate
  or tail distribution. Confidence is low-to-medium for candidate retention
  and low for profitability claims.
- **Retrospective selection:** The latest historical interval informed the stop
  comparison. It is not an untouched holdout.
- **Queue uncertainty:** Public trade-through is stricter than touch but cannot
  reveal private queue position, cancellations, or partial maker allocation.
- **Regime dependence:** The long signal may work only in the observed market
  path; its first six-month aggressive window was negative with the fixed stop.
- **Shared portfolio conflict:** A future long arm and the running short arm
  cannot independently spend the same equity. One BTC position/pending order
  and deterministic conflict arbitration are required before combination.
- **Income mismatch:** The exact 91-day profit is far below the stated monthly
  objective. Scaling this sample would magnify uncertainty and stop losses, not
  prove a larger edge.

The candidate is falsified by a fresh forward PF at or below 1, a liquidation,
repeated expired entries that remove most winners, materially worse realized
fees/slippage, or conflict behavior that degrades the running short arm.

## 5. Validation plan

1. Keep the current short-only shadow run unchanged and continue recording
   venue-matched L2, trades, mark/oracle context, funding, and regime rows.
2. Run this long candidate as annotation-only decisions against the same live
   feed; do not submit or reserve capital.
3. Freeze the signal, 60 bps stop, 35%/30x risk, 8% target, 24-hour hold, and
   60-second maker lifetime before collecting forward outcomes.
4. Require exact decision-time parity between offline reconstruction and live
   annotations.
5. After a meaningful resolved sample, replay the combined long/short streams
   through one shared portfolio with one BTC position and predeclared conflict
   arbitration.

Good enough for a shadow-only long challenger means no causal/parity mismatch,
no liquidation, positive net expectancy after exact costs, and no degradation
of the short candidate under shared-account arbitration. This is not a live
promotion criterion.

## 6. Recommendation and trade-offs

| Option | Evidence | Benefit | Main risk | Decision |
|---|---|---|---|---|
| Do nothing / short only | strongest current forward path | no new interaction risk | misses long opportunities | keep as current runtime control |
| Low-risk long reference | positive in 3/3 bar windows | stable, small drawdown | economically too weak | retain as reference |
| 35%/30x no stop | one recent liquidation | high nominal winner size | tail loss dominates | reject |
| 35%/30x signal-wick stop | negative in 3/3 windows | no liquidation | over-stops winners | reject |
| 35%/30x fixed 60 bps stop | exact +$376, PF 1.32, no liquidation | first executable-looking long path | five fills, retrospective, gap flag | annotation-only challenger |

Recommendation: freeze the fixed-60-bps long as an annotation-only challenger.
Do not add it to the active execution strategy yet. The next evidence should be
fresh live annotations followed by one shared-portfolio arbitration replay, not
another stop-distance grid.

The prospective window is frozen from `2026-07-30T12:00:00Z`. Signal, risk,
shared-portfolio, source-code hash, and falsifier identity are recorded in the
immutable forward-freeze artifact; changes after that boundary constitute a new
candidate rather than a continuation of this test.

## 7. Artifact identity

- Exact trade-through replay:
  `data/logs/research/hypervelocity_liquidity_sweep_long_20260428_20260728_trade_through_hv35x30_stop60_v1.json`
- Exact artifact SHA-256:
  `184fa7691b33be271d1382637aedf1c7609fbfad2e1dd05c86ac8bdb5af19442`
- Later fixed-stop bar artifact SHA-256:
  `a6cc0969f8fd30a7cba6ef6c5035e1b910c1bdb3a1bf2854795fecbcc5df5d68`
- Validation fixed-stop bar artifact SHA-256:
  `bbd9123d1d12847dea035ae3c5b9f222320270c640a753f853feb5d795543ae6`
- Development fixed-stop bar artifact SHA-256:
  `9fb2a1849b0e5815443c069b6ecaf0758cb266224dc20ff1b0fdf818bef21362`
- Forward-freeze artifact:
  `data/logs/research/hypervelocity_liquidity_sweep_long_forward_freeze_20260730T1200_v2.json`
- Forward-freeze SHA-256:
  `6fa740538267175fdfae728c1a5e73473785f4a267bb0fb11098948ff17fe4d4`
- One-hour source-long isolation artifacts: development
  `d8e985d9b500cb08d48e31ac59fc1bea1597428ba38f89e3b0cecfb75d3500c9`,
  validation
  `c388d963aa33cd389dedca131b54270f8013a628653add9a067ae4021aab9687`,
  and latest
  `8f85c1a471ce52f8658c5d2a5ea54cf6948d29d29607cbbce724c54dbd3a3e08`.
- Fifteen-minute source-long isolation artifacts: development
  `158786c5c52a5e18fe85c292726752f00867383f198065318c797daed30e743b`,
  validation
  `fed75c6d19c1a6697b132d8ea5c87bf39b0b8903f8abdcb403c6d7c85b8201de`,
  and latest
  `ed4974912c615525d4c20e4b467e5ddfa0d6990976ae070b3e9700db20002d9c`.
