# Hypervelocity Emergency Stop Option Study

**Status:** Design only. No runtime behavior or faithful configuration change is approved by this document.

## Problem

The verified 90-day TP-only comparison produced 40-47 terminal liquidations
per L2 result and worse than -99.95% maximum drawdown for every shortlisted
entry configuration. The next question is whether a causal emergency exit can
reduce liquidation severity without converting normal BTC wicks into repeated
taker-fee losses.

At the fixed 70% margin and 40x leverage, a 0.2% favorable price move produces
the 8%-of-margin target. With 1.5 bps maker fees on entry and target, the
measured fixed-size target is approximately +4.76% of portfolio equity. Before
slippage, a 0.5% adverse price stop costs approximately 15.7% of portfolio
equity after maker-entry and taker-exit fees; a 1.0% stop costs approximately
29.7%. Stop distance is therefore a primary strategy variable, not a minor
execution detail.

## Causal candidates

| Candidate | Entry-time stop definition | Main benefit | Primary failure mode |
|---|---|---|---|
| TP-only control | No discretionary stop | Preserves observed behavior | Repeated liquidation dominates compounding |
| Consolidation wick | Long: lowest low; short: highest high of the completed pre-entry consolidation | Ties exit to the structure being traded | One anomalous wick makes the stop too wide |
| Confirmed pivot | Last causally confirmed higher-low/lower-high pivot | Uses local invalidation structure | Pivot confirmation lag or no valid pivot |
| Buffered wick/pivot | Structural stop plus adverse tick/volatility buffer | Reduces exact-level sweep-outs | Wider losses may approach liquidation economics |
| Liquidation-proximity failsafe | Fixed distance before current isolated liquidation boundary | Directly reduces terminal liquidations | Still realizes a large loss and depends on mark accuracy |

The consolidation window must be known before entry. It cannot end after the
entry bar. A pivot is valid only after its right-side confirmation bars close.
If a candidate has no causal stop at entry, the trial must report `no_stop`
rather than substitute a future or arbitrary level.

## Execution assumptions

- Freeze the structural stop at entry for the first experiment; trailing is a
  separate hypothesis.
- Submit a reduce-only stop-market intent.
- Charge the maker entry fee and taker exit fee.
- Fill at the first adverse BBO after the trigger; preserve gap-through loss.
- If stop and target occur in one OHLC bar without event ordering, count the
  stop first. L2 event replay may resolve the actual order.
- Continue to allow only one BTC position and require structural reset before
  same-direction re-entry.
- Retain the existing TP-only hold-through-RANGE behavior unless the stop price
  itself is reached.

## Measurements

Report every candidate and walk-forward segment:

- final marked and realized equity;
- maximum drawdown and time under water;
- targets, stops, partial liquidations, and terminal liquidations;
- maker/taker fees and adverse gap slippage;
- stopped trades that later reach the original 8% target before the original
  liquidation boundary (`stop_regret`);
- liquidations avoided by an earlier stop;
- results by long/short and entry regime;
- sensitivity to touch, through, and public-trade-through entry fills.

## Validation sequence

1. Freeze the existing TP-only artifact as the control.
2. Compute causal stop levels on the 129,600 strict Hyperliquid bars and reject
   any prefix-instability/look-ahead violation as a technical failure.
3. Screen stop definitions and a small, declared buffer grid on the serial
   portfolio diagnostic; retain every result.
4. Replay the control and non-duplicate stop finalists on the verified L2 and
   public-trade archive.
5. Do not promote a stop based only on lower drawdown. Require improved
   geometric equity under multiple fill assumptions without unacceptable
   stop-regret or fee churn.

## Recommendation and falsifier

Start with consolidation-wick and confirmed-pivot stops, each unbuffered and
with a small declared buffer challenger, plus the liquidation-proximity
failsafe. Keep TP-only as the control. This is a research priority because the
entry-parameter comparison did not solve the liquidation path.

Confidence is medium. Structural stops are mechanically capable of reducing
loss per failed trade, but BTC wick frequency may reduce the observed 85%-86%
target rate below the new break-even level. The recommendation is falsified if
walk-forward/L2 evidence shows lower drawdown but worse geometric equity across
the conservative fill assumptions, or if stop-regret is concentrated in trades
that subsequently complete the original target.

## First Operational Definition

The first consolidation-wick trial uses the most recent fully completed causal
BBWP<25 episode. Its minimum low is frozen as the long stop and its maximum high
as the short stop when compression ends. This removes an arbitrary fixed
lookback. A level at or beyond the isolated liquidation boundary is reported as
`ineffective_stop`; it is not clamped or replaced.

Before modifying the stateful event engine, apply the frozen level to the exact
filled lifecycles from
`hypervelocity_bbwp_recovery6_20260727.json`. The bar screen uses only full 1m
bars strictly after entry and completed before the recorded outcome, so partial
entry/outcome minutes remain explicitly unobserved. Retain target stop-regret,
liquidations avoided, ineffective levels, fee-adjusted PnL delta, and causal
prefix-stability evidence. Run exact BBO stop ordering only if this first stage
improves the fixed lifecycle set.

The liquidation-proximity follow-up uses a fixed two-point grid before results
are inspected: 75% and 90% of the directional distance from entry to the
modeled isolated-liquidation price. Both levels are frozen at entry, charged a
taker exit fee, and screened on the same exact fills/full-bar window. This is a
failsafe diagnostic, not a faithful-runtime default.

Fixed-lifecycle result: the 75% candidate hit 46 stops, avoided 37 recorded
liquidations, stopped 9 eventual targets, and improved additive fee-adjusted PnL
from -$5,876.53 to +$811.75. The 90% candidate avoided 30 liquidations with 3
target regrets but remained -$3,518.42. Implement the 75% candidate as an
optional stateful maker-replay setting with a `None` default. A gap that crosses
both stop and liquidation is conservatively liquidated first; otherwise the
stop exits the remaining quantity at adverse BBO with taker fees. Runtime and
faithful config remain unchanged.

Stateful public trade-through replay falsified both proximity candidates. The
unstopped recovery-6 path ended at $4,123.47 with 39 full and 24 partial
liquidations. The 75% failsafe ended at $1,243.95 with 63 stops and -99.36%
drawdown. The 90% failsafe ended at $3,669.03 with 47 stops and -98.91%
drawdown. Both eliminated recorded liquidation statuses but worsened geometric
equity through stop/re-entry churn. No emergency stop is promoted; the optional
research parameter defaults to `None`.
