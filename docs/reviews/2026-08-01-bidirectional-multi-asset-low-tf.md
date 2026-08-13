# Bidirectional Multi-Asset Low-TF Research Checkpoint

## Status

This is a report-only research checkpoint. It provides no execution authority,
does not arm a canary, and does not establish a promotable strategy.

Confidence in the implementation mechanics is **medium-high** after focused
causal, lifecycle, and accounting tests. Confidence in any surviving economic
edge is **low** because no candidate remained positive in every untouched
chronological segment.

## Frozen inputs

- Hyperliquid 1m OHLCV caches for BTC, ETH, SOL, and HYPE.
- 5m decision/execution bars and completed 15m context.
- Development: `2025-07-28` through `2026-01-28` UTC.
- Validation: `2026-01-28` through `2026-04-28` UTC.
- Pseudo-holdout: `2026-04-28` through `2026-07-28` UTC.
- Starting research equity: `$15,000`.
- Isolated `5x` leverage and `0.50%` desired risk per trade.
- Position quantity is reduced when the desired risk would exceed 70% isolated
  margin; the signal is retained and realized risk is reported.
- Nominal all-in round-trip friction: `13 bps` (`9 bps` taker fees plus `4 bps`
  modeled slippage).
- Stress all-in round-trip friction: `20 bps`.
- Hourly venue funding, isolated liquidation, one-minute barrier ordering, and
  adverse same-minute stop/target resolution are included.

## Trade Oracle provenance and audit

Notebook: `Trade-Oracle`, ID
`0533df6d-061c-40e8-a74c-14d0b8bb0b63`; conversation
`2d08c822-c2c0-4ccb-8554-63f92567223c`.

The Oracle was used as a hypothesis challenger only. Its first response mixed
canonical rules with invented thresholds and double-counted the specified
round-trip friction. A follow-up forced it to retract the cost error and separate
source-backed rules from extrapolations.

Usable source-backed mechanisms were:

- range reclaim to the established range midpoint;
- 21/55 EMA direction plus BBWP expansion;
- PMARP mean reversion;
- canonical Krown 5m long: EMA 21 above EMA 55, BBWP below 35, PMARP below 25,
  exit at PMARP 80.

The notebook explicitly lacked ETH, SOL, and HYPE outcome evidence. Every
altcoin application therefore remained an asset-specific hypothesis.

## Critical replay correction

The initial replay rejected entries when risk-sized quantity required more than
the configured isolated-margin cap. This created an invalid interaction: greater
adverse entry slippage widened the entry-to-stop distance and could allow more
signals to pass the margin check.

Corrected behavior caps quantity at available isolated margin and records the
smaller realized dollar risk. A regression test now requires the tight-stop trade
to fill at capped quantity rather than receive a performance-shaped rejection.

Consequences:

- Earlier BTC close-invalidation development results were invalidated and
  replaced below.
- SOL trend-long and HYPE wick-stop results were materially stable after the
  correction.
- All pre-correction rows not explicitly rerun must be treated as invalid.

## Corrected chronological results

All dollar values below use one standalone `$15,000` research account per cell;
they are not summed as if multiple independent accounts existed.

### Nominal 13 bps friction

| Candidate | Segment | Trades | Net PnL | PF | Max DD | Liquidations |
|---|---:|---:|---:|---:|---:|---:|
| BTC range short, close invalidation | Development | 53 | -$1,523.92 | 0.724 | 15.56% | 0 |
| BTC range short, close invalidation | Validation | 49 | -$5,013.24 | 0.217 | 35.10% | 0 |
| BTC range short, close invalidation | Pseudo-holdout | 31 | -$1,944.17 | 0.359 | 13.12% | 0 |
| BTC range short, wick/ATR stop | Development | 51 | +$110.37 | 1.053 | 3.77% | 0 |
| BTC range short, wick/ATR stop | Validation | 49 | -$2,074.12 | 0.296 | 14.89% | 0 |
| BTC range short, wick/ATR stop | Pseudo-holdout | 31 | -$917.98 | 0.399 | 7.49% | 0 |
| SOL trend long, base thresholds | Development | 34 | +$631.44 | 1.218 | 12.15% | 0 |
| SOL trend long, base thresholds | Validation | 18 | +$585.43 | 1.456 | 6.23% | 0 |
| SOL trend long, base thresholds | Pseudo-holdout | 19 | -$142.45 | 0.907 | 5.21% | 0 |
| SOL trend long, tuned 16/9.6 | Development | 26 | +$1,629.86 | 1.799 | 12.15% | 0 |
| SOL trend long, tuned 16/9.6 | Validation | 12 | +$420.27 | 1.467 | 5.79% | 0 |
| SOL trend long, tuned 16/9.6 | Pseudo-holdout | 12 | -$342.41 | 0.648 | 4.33% | 0 |
| HYPE range long, wick/ATR stop | Development | 238 | -$159.87 | 0.988 | 9.22% | 0 |
| HYPE range long, wick/ATR stop | Validation | 105 | -$902.86 | 0.847 | 13.21% | 0 |
| HYPE range long, wick/ATR stop | Pseudo-holdout | 104 | -$1,294.11 | 0.751 | 15.51% | 0 |

### Stress observations

- BTC range short failed at `20 bps` in all three segments.
- Tuned SOL trend long remained positive in development (`+$988.54`, PF `1.470`)
  and validation (`+$163.95`, PF `1.172`) but failed the pseudo-holdout
  (`-$507.29`, PF `0.500`).
- HYPE range long failed every `20 bps` segment.

## Canonical Krown 5m long falsification

The notebook cited 50 BTC trades from late December 2021 to mid-January 2022,
80% wins, average winner `+0.36%`, and average loser `-0.46%`. Fees, slippage,
and funding were not documented.

Two source-plausible BBWP lookbacks and two explicit stop translations were
tested on the current development period:

| BBWP length/lookback | Stop translation | Trades | Net PnL @13bps | PF | Max DD |
|---|---|---:|---:|---:|---:|
| 7/100 | Compression-low close | 326 | -$12,175.29 | 0.208 | 81.29% |
| 7/100 | Compression-low hard stop | 372 | -$11,901.33 | 0.154 | 79.34% |
| 7/252 | Compression-low close | 308 | -$11,734.02 | 0.205 | 78.23% |
| 7/252 | Compression-low hard stop | 341 | -$11,573.12 | 0.135 | 77.15% |

The old sample does not transfer to this window and execution model. No later
segment was consumed because all four declared development controls were deeply
negative. Under the project charter this is a reported result, not an implicit
abort of unrelated research.

## Current conclusions and falsifiers

1. **No candidate in this checkpoint is promotable.** High confidence from the
   observed chronological failures. This conclusion would update only if an
   independently defined candidate remains positive after the same costs in all
   untouched segments.
2. **The SOL long mechanism contains regime-local signal but is not stable.**
   Medium confidence: two positive segments followed by a negative final segment.
   A future forward shadow window with positive net performance at 20 bps would
   increase confidence; continued negative recent outcomes would falsify reuse.
3. **Frequency was not the first-cohort blocker.** Medium-high confidence: raw
   development setup counts were BTC `348`, ETH `689`, SOL `931`, and HYPE
   `1,389` before duplicate variants and portfolio conflicts. Execution quality
   and conditional expectancy were the blockers.
4. **Liquidation was not the observed failure cause.** High confidence for the
   corrected rows above: all recorded zero liquidations. Costs and adverse trade
   outcomes produced the losses.

## Next bounded action

The next source-backed candidate is Krown Strategy #1 rather than another
threshold pass on failed Strategy #2: 5m 21/55 trend state, BBWP below 25, a
causal 55 EMA touch/reclaim, and an explicitly coded opposing RSI-divergence
exit. The existing OG Market Cipher repository contains a fractal divergence
implementation, but it must be audited for historical append invariance before
reuse. Strategy #1 remains report-only and receives one development pass before
any validation segment is read.

The full unselected base matrix must also be rerun through the corrected
margin-cap semantics before it is archived as final evidence. Until that occurs,
pre-correction ETH and non-lead rows are intentionally not quoted here.
