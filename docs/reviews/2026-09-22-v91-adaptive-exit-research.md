# V91 exit research and pre-registered comparison

Status: research comparison complete; deployment acceptance recorded separately.
No profitability claim. Behavioral specification frozen before
running V91 outcome comparisons on 2026-09-22. User requests all eight executable
assets and aggressive allocation. Existing entry signal definitions and native
brackets remain the baseline; the new contract explicitly binds an additional
`adaptive_exit_policy = "regime_book_profit_retention_v1"` at entry.

## Evidence and limits

Exa supplied the primary sources below after Parallel refused to start for
insufficient account credit. Full extracts and searches are saved in
`data/logs/research/bidirectional_cohort/v91_adaptive_exits_20260922/`.

- [Leung and Zhang, Optimal trading with a trailing stop](https://arxiv.org/html/1701.03960v2):
  a running profit floor and discretionary early liquidation are distinct controls.
  Their optimality results depend on specified diffusion dynamics. They do not
  establish profitable universal stop distances for these markets.
- [Garg et al., Learning to Liquidate Forex](https://arxiv.org/pdf/2202.12578v1.pdf):
  compares learned stopping/continuation estimates with simple liquidation rules;
  highlights forecast overestimation and nonstationarity. Corporate FX liquidation
  differs from leveraged perpetual entries and financing costs.
- [Becker et al., Deep Optimal Stopping](https://jmlr.org/papers/v20/18-232.html):
  learns stopping rules from Monte Carlo samples. A realistic simulator or enough
  representative recorded paths is a prerequisite, not a solved problem here.
- [Gould and Bonart, Queue Imbalance](https://arxiv.org/abs/1512.03492):
  predicts one subsequent mid-price movement on ten Nasdaq stocks. This supports
  investigating book corroboration; it does not validate multi-hour crypto exits.
- [Cont et al., Price impact of order book events](https://arxiv.org/abs/1011.6402):
  event-based order-flow imbalance is different from this system's periodic depth
  snapshot pressure. V91 will name the observed variable accurately.
- [Hyperliquid order types](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types.md):
  reduce-only orders prevent reversing an exposure. Market-triggered protection
  remains exposed to execution slippage and price gaps.

High confidence in these distinctions; an implementation or venue change requires
revalidation. Low confidence in economic improvement until time-held-out and live
outcomes accumulate. No source justifies an invented guaranteed profit floor.

## Frozen behavioral contract

1. Retain existing entry authority, sizing, initial native stops/targets, recipe
   exits, and hard deadlines. No new entry score gate or capital reduction.
2. Evaluate the open lifecycle each successful 15-second cycle. Use fresh executable
   bid for a long, ask for a short; otherwise a fresh completed minute close.
   Never use a current candle high/low as if its event order were known.
3. Arm after gross favorable excursion reaches max(60 bps, twice the trailing
   20-minute ATR in bps, estimated round-trip friction + 20 bps). This is a
   behavioral starting hypothesis, not an optimized result. Preserve the activation
   once reached. Existing smaller native targets may execute first.
4. Once armed, floor is at least estimated round-trip friction + 20 bps and
   peak minus a volatility-aware allowance. Trend-supported allowance is
   max(50 bps, 3 ATR), mixed/unknown max(35 bps, 2 ATR), opposed max(25 bps, ATR).
   Cap giveback at 50% of peak after activation. Persist max(previous floor,
   proposed floor); no regime change, volatility jump, model prediction or restart
   may relax protection. Close if observed liquidation return breaches that floor.
5. Canonical completed 1m/5m/15m weighted alignment is shared with entry routing.
   It is fresh for at most 90 seconds and is unknown if absent/future/stale.
   Opposing depth pressure <= -0.35 relative to the position must persist across
   three distinct venue book timestamps, separated by at least 10 seconds and
   no more than 45 seconds. Require fresh <=30-second uncrossed positive depth.
   Persistent opposing pressure plus non-supportive regime tightens the allowance
   to max(20 bps, ATR). One book observation does not trigger an exit by itself.
6. Persist peak, activation, floor, book confirmation and decision evidence before
   an order; durable exits are immutable and replayed by exact lifecycle identity.
   Missing inputs are explicitly reported and cannot fabricate support. Maintain
   native initial protection throughout software/network outages. The adaptive
   floor is software-triggered and is not a guaranteed venue resting stop.

## ML experiment definition

Estimate the incremental gross signed return of holding another 30 minutes versus
closing at the next available bar open. Features use only completed prices:
1/3/6/12-bar returns, trailing true range, realized volatility, and trend distances.
Available candle granularity and per-asset coverage must be reported. Never
synthesize historical L2 or oracle premiums from candles.

Compare zero/rolling-mean continuation, standardized Ridge(alpha=10), and one
bounded gradient boosting model (100 trees, depth 2, learning rate .05). Three
expanding chronological folds with a full 30-minute label purge. Fit every
transform on training only. One frozen feature/label family; no hyperparameter
grid or random time shuffle. Report MAE, directional association, fold instability,
cost sensitivity and effective non-overlapping label counts. Train-only final
artifacts must record symbols, timestamps, input hashes and model identity.

Initial model authority is prospective research telemetry unless exit-specific
evidence supports a bounded change; any subsequent behavioral variant is a new
reported trial. Model output cannot loosen an armed floor or suppress native exits.

Compare original exits, prior fixed protection, and adaptive retention using the
same recorded data and actual fill conventions. Report missing microstructure
coverage and observational limitations; report net PnL, giveback, cut winners,
drawdown, turnover and nominal/stressed costs. Statistical or PnL results are
reported outcomes, not hidden project trial-abort conditions.

## Verification and alternatives

| Choice | Benefit | Principal failure mode | Evidence needed |
|---|---|---|---|
| Existing exits unchanged | Preserves measured baseline | Large winner giveback | Same-path baseline |
| Fixed protection | Simple, predictable floor | Cuts normal trend pullbacks | Long/short causal replay |
| Adaptive retention | Uses existing market context with monotone floor | Noisy regime/book, software latency | Fault/restart tests and prospective attribution |
| ML continuation | Tests conditional hold value | Leakage, overfit, drift, inadequate sample | Purged folds and prospective labels |

No clarification is needed for offline implementation and the explicitly requested
eight-asset deployment. Technical validity, exact authority and fresh venue state
remain required before placing the new profile into service.

## Measured results

`ml_comparison.json` records three purged chronological folds per asset: 5,991
usable samples each for BTC, ETH, SOL, HYPE, SPCX, SNDK and Brent; 4,933 for TSLA.
Feature bars are 15 minutes and labels hold from the next open for 30 minutes.
Samples overlap; the reported nonoverlapping count is an upper bound, not a claim
of independent observations. Ridge improved mean absolute error versus zero only
for SOL (-0.029 bps) and HYPE (-0.074 bps). Other Ridge differences ranged from
+0.049 to +0.393 bps; boosted differences were positive for all eight assets.
Ridge rank association changed sign across folds for most assets. These results
do not establish profitable exit authority. The serialized Ridge models are
prospective telemetry only, with artifact hash and training cutoff recorded.

`minute_path_comparison.json` applies the exact production state transition to
the previously frozen 28 real-entry paths. Required complete lifecycle plus ATR
history is available for 26; two are withheld consistently from the matched table.
The input lacks recorded regime/L2, so this evaluates the explicit unknown-context
fallback, not the full regime/book hypothesis. Original position sizes are used.

| Matched 26-path outcome | 5 bps adverse fill proxy | 15 bps adverse fill proxy |
|---|---:|---:|
| Original actual exits | -$6.53 | -$6.53 |
| Prior fixed 100/25/50 rule | +$0.48 | -$5.01 |
| Adaptive rule, context unavailable | +$6.43 | -$0.56 |

The adaptive rule triggered 14 exits, improved 11 outcomes and reduced three.
This supports continued empirical evaluation of retention, not a claim of an
eight-asset return improvement. Counterfactual fills, reused historical data,
fixed original entries, unmodeled replacement trades and absent historical
book/regime evidence limit inference. The complete per-trade results include the
cut winners; no parameter was retuned after these results.

## Corrected eight-asset sizing

Unsigned venue observations beginning 10:23:47 UTC on September 22 found all eight
assets flat and order-free, reconciled to the ledger. Equity was $4,870.28. Each
side's displayed depth covered the sampled intended quantity; this is a snapshot,
not a fill guarantee. Existing V90 envelopes are retained and execution is restored
for ETH long, HYPE long and SPCX both directions.

| Asset | Execution sides | Leverage | Formula/cap notional | Posted margin |
|---|---|---:|---:|---:|
| BTC | Long | 10x | $535.73 | $53.57 |
| ETH | Long | 15x | $500.00 | $33.33 |
| SOL | Both | 8x | $506.51 | $63.31 |
| HYPE | Long | 10x | $2,500.00 | $250.00 |
| SPCX | Both | 10x | $500.00 | $50.00 |
| SNDK | Both | 8x | $1,948.11 | $243.51 |
| Brent | Both | 8x | $584.43 | $73.05 |
| TSLA | Both | 8x | $506.51 | $63.31 |

All-eight simultaneous notional is approximately $7,581.30 and margin $830.10,
about 17.04% of the observed equity. Formula margin fractions sum to 22.2%, but
notional caps currently bind ETH, HYPE and SPCX. Gross initial-stop exposure using
the maximum permitted structural distances is approximately $127.35 before fees,
gaps, funding and liquidation effects. Restoring three executable routes increases
possible aggregate exposure; it is not "no added risk." Recompute at startup.

The profit floor estimates friction as 20 bps round trip plus current spread,
explicitly excluding funding. It is an assumption, not measured guaranteed net
profit. V91 does not widen initial stops, relax existing targets, or let ML override
protection. BTC's existing 60-bps native target commonly precedes activation.
