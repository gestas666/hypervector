# SOL range-onset backward validation and stop-shape audit

## Problem restatement

The later Hyperliquid venue replay is positive, but the range-onset recipe was
identified after later data had already been inspected. The required challenge
is therefore a chronologically earlier venue-matched window. Candle evidence
can screen the hypothesis, but it cannot establish finite-depth execution,
public-trade stop timing, sampled-mark liquidation, or venue gaps.

## Fixed assumptions

- Symbol: SOL perpetual on Hyperliquid.
- Signal: causal 1-hour SMA 10/30 cross admitted by completed 5-minute
  RANGE/BREAKOUT state.
- Portfolio: $15,000 reset equity per disjoint provider block.
- Exposure: 3% isolated margin at 5x, or 0.15x total-account notional.
- Friction: taker fees, 2 bps per-side bar slippage, authentic hourly funding,
  a 48-hour maximum hold, and no forced close across large data outages.
- Runtime/model authority: none. The active forward configuration was not
  changed by either retrospective challenge.

## Earlier candle and funding evidence

The immutable March 1 through July 28, 2025 candle archive contains 203,475
observed rows. There are 4,767 timestamp gaps representing 11,085 missing
minutes. Only gaps of at most 30 minutes were explicitly repaired as
zero-volume rows; four larger outages split the evaluation into five blocks.
Four blocks had sufficient causal warmup.

The frozen 60-bps recipe produced 25 trades, 3 wins and 22 losses. Product
equity was $15,020.77 (+0.1385%), profit factor was 1.0635, only one of four
complete blocks was profitable, and leaving out the strongest block made the
aggregate negative. Long profit factor was 0.9117; short profit factor was
1.3087. No bar-mode liquidation was reported.

The predeclared 16-cell shape surface changed only stop distance and maximum
hold. Its strongest earlier cell was 80 bps with a 48-hour hold: 25 trades,
4 wins and 21 losses, $15,300.67 product equity (+2.0045%), profit factor
1.7655, two of four positive blocks, and -2.6596% worst block drawdown. This is
a challenger result, not a selected runtime setting, because it is sparse and
still based on bar execution.

## Later exact venue stop-shape evidence

A paired audit binds 12 source capacity artifacts to 12 capacity-shape
artifacts. It verifies exact equality of every 60-bps control across
development, validation, pseudo-holdout, and continuous segments, and verifies
an identical 42-entry decision-time/direction population for 60 and 80 bps.

| Stop | Trades | W/L | PF | Product return | Positive blocks | Liquidations |
|---|---:|---:|---:|---:|---:|---:|
| 60 bps | 42 | 12/30 | 3.8597 | +8.8420% | 7/12 | 0 |
| 80 bps | 42 | 12/30 | 3.4152 | +8.4190% | 7/12 | 0 |

The 60-bps arm also has positive leave-one-block-out PnL in every omission.
Longs contributed +$391.64 at PF 2.9593; shorts contributed +$895.06 at PF
4.5795. The 80-bps arm changed 24 exits but reduced aggregate PnL by $59.00
on reset blocks and product equity by $63.45.

The paired audit caught and rejected several challenger artifacts whose signal
warmup did not reproduce their source controls. Replacement artifacts were
generated from the authoritative source warmup boundaries; rejected artifacts
remain immutable evidence and are not silently overwritten.

## Data-infrastructure correction

The initial normalizer incorrectly converted some `crossed=false` maker
participant rows into additional public prints. That hypothesis was falsified
against the independent venue candles: the first 21 days contained 451,984
normalized rows but only 361,309 taker prints. Taker-only normalization exactly
reproduces open, high, low, and close on all 21,425 observed candle minutes and
volume/trade count on 21,422. The three degraded minutes are each missing one
archived taker and do not intersect a Block 1 position lifecycle.

All 538 downloaded trade bundles were rebuilt as `taker_only_v2`; every prior
bundle remains preserved under a recoverable backup directory. The 504 bundles
already in DuckDB were replaced in atomic batches. Archive discovery and
backfill resume now reject stale normalization. A dedicated trade/candle parity
audit records degraded minutes instead of silently treating them as exact and
binds every hourly trade manifest, including an hour with zero trades. The
post-repair checksum audit confirms 361,309 public trades across all 504 first-
block hours.

## First earlier exact venue block

The preregistered first exact block uses March 1 causal warmup and executes from
March 2 06:00 through March 21 23:00 UTC. The final 59 minutes were excluded to
avoid bridging the declared large source outage. The database provides
3,023,046 L2 snapshots and 337,667 corrected public trades over the execution
window. Hourly sampled marks, authentic funding, public-trade crossings, and
finite visible-depth fills all completed.

| Stop | Trades | W/L | Mark PF | Final equity | Mark DD | Liquidations |
|---|---:|---:|---:|---:|---:|---:|
| 60 bps | 5 | 1/4 | 3.1742 | $15,121.24 | -0.9769% | 0 |
| 80 bps | 5 | 1/4 | 2.2942 | $15,099.74 | -0.9769% | 0 |

The public-trade bound also favors 60 bps: $15,130.83 and PF 3.8264 versus
$15,114.75 and PF 2.8442. This is encouraging but fragile. Development and
pseudo-holdout thirds both lost; the single validation winner produces the
aggregate profit. The remaining three complete earlier blocks must determine
whether that concentration persists.

## Second earlier exact venue block

Predeclared Block 3 executes May 26 21:00 through June 8 09:00 UTC after a
May 25 15:00 causal warmup. All 330 hourly L2, public-trade, and mark bundles
passed checksum validation. The normalized tape exactly reproduced all 19,796
observed candle minutes on OHLC, volume, and trade count; four wall-clock
minutes are absent from both sources rather than contradictory.

| Stop | Trades | W/L | Mark PF | Final equity | Mark DD | Liquidations |
|---|---:|---:|---:|---:|---:|---:|
| 60 bps | 1 | 0/1 | 0.0000 | $14,983.73 | -0.2090% | 0 |
| 80 bps | 1 | 0/1 | 0.0000 | $14,979.03 | -0.2403% | 0 |

The exact 60-bps loss of $16.27 closely matches the frozen bar estimate of
$16.13 lost; the exact 80-bps loss of $20.97 similarly matches the $20.63 bar
estimate. Across completed Blocks 1 and 3, 60 bps has $104.97 reset-block net
PnL, PF 2.4573, $15,104.84 product equity, and zero liquidations. This remains
dependent on the single Block 1 winner and is not a promotion result.

## Complete four-block exact audit

The subsequent immutable v2 audit completed all four gap-safe public-trade
blocks without changing the declared signal population, 3% margin, 5x isolated
leverage, or 48-hour maximum hold. It supersedes the interim two-block decision
above.

| Stop | Trades | W/L | PF | Reset-block net | Product return | Positive blocks | Liquidations |
|---|---:|---:|---:|---:|---:|---:|---:|
| 60 bps | 25 | 3/22 | 1.0734 | +$24.74 | +0.1603% | 1/4 | 0 |
| 80 bps | 25 | 4/21 | 1.7852 | +$306.69 | +2.0448% | 2/4 | 0 |

For 80 bps, long PF was 2.3548 and short PF was 1.0201. Removing any one
block retained at least +$31.50, but removing the largest winning trade changed
aggregate PnL to -$29.05. The sampled-mark surface remained censored because
Block 2 contained one 130-second mark-query gap beyond the declared 120-second
limit; no pooled sampled-mark result is claimed. The complete public-trade
surface is therefore supportive but fragile, not proof of a durable edge.

## Decision and confidence

Freeze the SOL forward/canary hypothesis at 80 bps and 0.15x total-account
notional. The complete earlier exact public-trade evidence is materially
stronger than 60 bps, while still depending on one large winner. This selection
authorizes observation and a deliberately small execution canary; it does not
authorize scaling or a profitability claim.

Confidence is high that the immutable four-block public-trade result is
internally reproducible and low-to-medium that its payoff distribution will
persist forward. A forward PF at or below one, repeated stop/fill divergence,
unexplained regime-decision mismatch, or a new clean block that makes the
leave-one-block-out result negative would weaken or falsify the candidate.

## Required next validation

1. Complete the execution-incapable funded-account preflight and record venue
   metadata, fee tier, equity, positions, orders, funding, and L2 evidence.
2. Restart the unchanged 80-bps shadow observer through the finalized launcher
   without deleting its append-only evidence.
3. Run the explicitly acknowledged $150 mainnet canary and compare every real
   decision, fill, fee, funding update, stop, and close against its shadow
   counterfactual.
4. Do not scale until real lifecycle parity is demonstrated and fresh resolved
   trades update the sparse payoff estimate.

## Immutable evidence

- Frozen backward challenge:
  `data/logs/research/sol_range_onset_backward_temporal_validation_20250301_20250728_v1.json`
  (`e37e943a59882645ff8954b2356d8c7671554b61a5c173ce0b43e89fe4bcdb7f`).
- Predeclared backward surface:
  `data/logs/research/sol_range_onset_backward_predeclared_shape_surface_20250301_20250728_v1.json`
  (`84673a55dce5d561b758f3976833fa214c7feb786fcd0f433f2b7182c8a82ba5`).
- Later paired stop audit:
  `data/logs/research/sol_range_onset_capacity_shape_paired_audit_20251126_20260730_v1.json`
  (`44f7321d6223728edcf80a3e6c30a4b3ab6171a49c38a3f552bd9d07c494c485`).
- Block 1 exact event replay with complete execution-model identity:
  `data/logs/research/sol_range_onset_event_capacity_shape_SOL_20250302T06_20250321T23_backward_block01_taker_v3.json`
  (`f650127e327143905b54a917eaabd8d38a877e3cc79f001e39f69b47b54314ec`).
  The immutable v2 predecessor has identical PnL and trade outcomes but did not
  bind the 48-hour hold, fee, cooldown, and venue-leverage assumptions.
- Block 1 trade/candle parity:
  `data/logs/research/oxa_trade_candle_parity_SOL_20250301_20250322_taker_v2.json`
  (`b74a976482660666ee063f0446af2c5cc6c0841a4cc7fa7abc515b9fced9ecc0`).
- Block 1 post-repair archive audit:
  `data/logs/research/oxa_archive_audit_SOL_20250301_20250322_taker_v2.json`
  (`ed958c7f50ddaf96b93fe42674d512e7e374dde6dee976e4e607421ed6c70039`).
- Block 3 post-repair archive audit:
  `data/logs/research/oxa_archive_audit_SOL_20250525T15_20250608T09_taker_v2.json`
  (`594c321c4eef5dc88a2be2401a623849c6db6d33a821ad5e277b0c9a7bb5998b`).
- Block 3 trade/candle parity:
  `data/logs/research/oxa_trade_candle_parity_SOL_20250525T15_20250608T09_taker_v2.json`
  (`3bddee46bafde3f2cfce9d809b5cb15ba000cd28122ca9c5113b5b5bdfc264a5`).
- Block 3 exact event replay:
  `data/logs/research/sol_range_onset_event_capacity_shape_SOL_20250526T21_20250608T09_backward_block03_taker_v3.json`
  (`157c8e081fb3f6ab1c33fe3be8545b395275e606ed02b4bba2737444e5fe35eb`).
- Complete four-block exact audit v2:
  `data/logs/research/sol_range_onset_backward_exact_audit_20250302_20250727_v2.json`
  (`2c1ea069c913ffc9a0fc6de8d8685b66a878fdef5cb6ce67ccf7a3deed58afab`).
