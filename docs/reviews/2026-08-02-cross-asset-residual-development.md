# Cross-Asset Residual Development Review

## Problem restatement

The experiment asked whether a structurally different, bidirectional
cross-asset residual mean-reversion mechanism could add repeatable low-timeframe
opportunities across BTC, ETH, SOL, and HYPE. The required output was immutable,
report-only evidence using causal Hyperliquid-native inputs, both-leg friction,
funding, isolated liquidation, and complete losing-cell retention.

The experiment did not ask whether one pair or one post-hoc exit could be made
to look profitable. A useful development result needed one globally shared
signal and exit contract that remained net positive across a meaningful breadth
of the six declared pairs.

## Explicit assumptions and known facts

- Development window: `2025-07-28T00:00:00Z` through
  `2026-01-28T00:00:00Z`, half-open.
- Symbols: BTC, ETH, SOL, and HYPE; all six unordered pairs were retained.
- Signal clock: completed five-minute bars with a trailing 14-day log-price OLS
  fit, daily refit, two-day residual z-score, and a causal error-correction
  t-statistic diagnostic.
- Entry contract: fresh crossings of `-2z` or `+2z`, in both spread directions.
- Base exit contract: mean reversion inside `0.5z`, adverse `4z` residual stop,
  or 24-hour maximum hold.
- Portfolio contract: independent $15,000 research account per pair, one atomic
  pair position at a time, 5x isolated leverage, 10% margin allocation, and
  0.5x gross pair notional. Pair results cannot be summed as one portfolio.
- Friction contract: 13 bps round trip per leg, composed of 9 bps fees and
  4 bps adverse slippage. Funding rates are exact cached hourly Hyperliquid
  observations, while cash flow uses candle-open notional rather than exact
  historical mark/oracle notional.
- Liquidation contract: each leg uses its configured isolated margin and the
  venue maximum for BTC, ETH, SOL, or HYPE. Liquidation exits also receive a 1%
  notional penalty. This is conservative research modeling, not a claim of
  exact historical mark-price or asynchronous-leg execution.
- Authority: every artifact and trade is `report_only=true` and
  `execution_authority=none`.

The plan's earlier phrase `no liquidation claim` was superseded during
implementation by explicit isolated-liquidation modeling and regression tests.
That implementation change is disclosed here rather than silently treating the
original wording as current.

## Evidence identity and validation

The original v1 artifacts are preserved but invalidated for economic inference.
An independent review found that liquidation detection used the minute high/low
while the surviving partner leg was closed retroactively at that minute's open;
end-of-data closure had the same open-after-full-minute timing defect. V2 closes
liquidation and final-bar exits at the observed minute close with an execution
timestamp one minute later, includes prospective exit costs in open drawdown,
and carries report-only authority on every trade row.

Corrected base development evidence:

- `data/logs/research/cross_asset_residual_development_v2.json`
- JSON SHA-256:
  `147d05ba913007404b5baa5b125a9e2b5f8fef1639ba76d2a08075d26811c2fd`
- `data/logs/research/cross_asset_residual_development_v2.trades.parquet`
- Parquet SHA-256:
  `1ac159d30e27d5c60004b9d3a0345d645951f327b1e3b116f85b4518f43c99c1`

Corrected bounded exit-surface evidence:

- `data/logs/research/cross_asset_residual_exit_surface_v2.json`
- JSON SHA-256:
  `179101b1d28cafc8a36795a9ea04dad1064641cc5b6a2f9daa12eafa6743ac75`
- `data/logs/research/cross_asset_residual_exit_surface_v2.trades.parquet`
- Parquet SHA-256:
  `7a37c98438173f4a029a3e0b2bac970f884462f6efae72f04c93ee7bbccf1106`

The surface evaluated 15 globally shared combinations: stop z-score in
`{3, 4, 5}` and maximum hold in `{1, 3, 6, 12, 24}` hours. This produced 90
complete pair/config cells and 19,187 recorded trade lifecycles. Validation
recomputed eight source-file hashes, the selected-frame hashes, the trade
sidecar hash and row metadata, all derivable cell aggregates and equity chains,
and report-only authority. Embedded provenance binds nine exact generator
modules/scripts. The focused residual suite passed 46 tests. The validator does
not claim independent derivation of signal counts, conflict rejections, or
maximum drawdown from the trade sidecar alone.

## Results

The base `stop4_hold288` contract lost money in all six pair cells:

| Pair | Trades | Net PnL | PF | Max DD | Liquidations |
|---|---:|---:|---:|---:|---:|
| BTC/ETH | 145 | -$577.31 | 0.7148 | 4.72% | 0 |
| BTC/SOL | 157 | -$671.73 | 0.7543 | 6.42% | 1 |
| BTC/HYPE | 114 | -$2,025.85 | 0.4916 | 14.02% | 0 |
| ETH/SOL | 147 | -$375.01 | 0.8812 | 5.62% | 1 |
| ETH/HYPE | 108 | -$1,203.90 | 0.7330 | 10.21% | 1 |
| SOL/HYPE | 133 | -$802.56 | 0.8558 | 9.38% | 1 |

The exit surface did not recover the branch. Every one of the 90 cells had
negative net PnL and PF below 1.

| Global variant | Positive cells | Median net | Median PF | Worst net | Liquidations | Trades |
|---|---:|---:|---:|---:|---:|---:|
| stop5_hold288 | 0/6 | -$675.09 | 0.7609 | -$2,273.87 | 5 | 752 |
| stop4_hold144 | 0/6 | -$702.31 | 0.8261 | -$1,989.82 | 2 | 902 |
| stop4_hold288 | 0/6 | -$737.15 | 0.7437 | -$2,025.85 | 4 | 804 |
| stop5_hold144 | 0/6 | -$760.57 | 0.8285 | -$2,234.88 | 2 | 872 |
| stop3_hold144 | 0/6 | -$945.91 | 0.7944 | -$2,317.42 | 0 | 1,049 |
| stop4_hold72 | 0/6 | -$1,073.92 | 0.6751 | -$2,196.89 | 1 | 1,108 |
| stop5_hold72 | 0/6 | -$1,076.64 | 0.6867 | -$2,457.17 | 1 | 1,098 |
| stop3_hold288 | 0/6 | -$1,238.95 | 0.7372 | -$2,252.87 | 0 | 988 |
| stop3_hold72 | 0/6 | -$1,321.34 | 0.6436 | -$2,553.30 | 0 | 1,203 |
| stop3_hold36 | 0/6 | -$1,833.52 | 0.5564 | -$2,428.05 | 0 | 1,449 |
| stop5_hold36 | 0/6 | -$1,850.77 | 0.5727 | -$2,365.03 | 1 | 1,405 |
| stop4_hold36 | 0/6 | -$1,973.00 | 0.5559 | -$2,191.85 | 1 | 1,408 |
| stop3_hold12 | 0/6 | -$2,674.95 | 0.3691 | -$3,504.62 | 0 | 2,054 |
| stop5_hold12 | 0/6 | -$2,783.48 | 0.3545 | -$3,639.38 | 0 | 2,047 |
| stop4_hold12 | 0/6 | -$2,854.06 | 0.3542 | -$3,577.83 | 0 | 2,048 |

`stop5_hold288` was least negative by median net PnL. `stop5_hold144` had the
highest median PF, while `stop4_hold144` had a slightly less-negative worst
cell. None changed the economic conclusion.

The causal correction produced no negative-to-positive sign flips. The largest
change was ETH/SOL `stop5_hold288`, which improved from -$178.92 in invalidated
v1 evidence to -$103.65 in v2. That cell's seven continuity-gap-overlapping
trades contributed +$155.35; its remaining 130 lifecycles contributed -$259.00.
The correction therefore did not conceal a survivor.

## Analysis and reasoning

The base attribution initially looked promising because mean-reversion exits
were strongly positive in isolation. That observation did not survive the
complete lifecycle. Residual-stop and maximum-hold tails erased the profitable
convergence exits, and shorter holds increased churn and cost exposure.

The surface is informative because the failure is broad rather than dependent
on one exit boundary:

1. Tightening maximum hold from 24 hours to one hour increased completed-trade
   counts and made median losses substantially worse.
2. Relaxing the stop from 3z to 5z did not create a positive pair cell.
3. HYPE pairs were generally weakest, but removing HYPE would still leave no
   positive BTC/ETH/SOL cell under the tested global contracts.
4. Liquidations were not the sole cause. Several variants had zero liquidation
   and still lost in all six cells.
5. Modeled transaction costs were material, but some base cells were already
   gross negative. This is not merely a fee-optimization problem.

## Uncertainties, risks, and failure modes

- The fixed-slippage model does not reconstruct queue position, legging delay,
  order rejection, or price-dependent market impact. Real two-leg execution is
  likely less favorable, but that remains unverified.
- Liquidation uses OHLC path bounds and a venue-aware isolated approximation,
  not the exact historical mark-price stream or maintenance-tier transition.
- Daily OLS can be unstable around structural breaks; the diagnostic t-statistic
  is not a formal ADF p-value.
- The selected window contains 67 BTC, 69 ETH, 108 SOL, and 78 HYPE explicit
  `hl_gap_fill` minutes. Because the fit spans 14 calendar days and gaps recur
  approximately weekly, every emitted signal formation window intersects at
  least one fill. Only 36 of 804 base trade lifecycles overlap a fill. V2
  reports both counts and affected/unaffected PnL but cannot reconstruct the
  missing venue path; exact magnitudes remain conditional on that limitation.
- The full one-year Parquet sources were physically read before causal window
  filtering. No later row enters calculations, but strict sealed non-access was
  not established, and earlier project work had already inspected later
  segments. Fresh forward evidence is the strongest independent confirmation.
- This is one six-month development interval. It supports rejection of this
  exact contract, not a universal claim that cross-asset relative value cannot
  work.
- A different signal family—dynamic factor residuals, lead-lag prediction,
  volatility-normalized spreads, or a genuine cointegration test—would be a new
  hypothesis and must not inherit this branch's signal identity.

## Validation and falsification

Confidence is high that the exact tested residual contract lacks development
edge on the frozen interval: corrected v2 retains 90/90 negative cells and no
PF above one, while code/source/sidecar hashes and derivable row identities
validate. Confidence is medium in exact loss magnitudes because continuity
fills, asynchronous two-leg execution, funding notional, and mark-based
liquidation remain approximated.

This assessment would be updated by either:

- an independently specified residual signal that is net positive across a
  broad set of pairs before opening validation; or
- evidence that a material accounting, causality, funding, cost, or liquidation
  defect changes multiple cells from negative to positive after correction.

A single post-hoc profitable pair or exit value would not falsify the breadth
result.

## Recommendation and trade-offs

| Option | Evidence | Benefit | Risk | Decision |
|---|---|---|---|---|
| Promote `stop5_hold288` | 0/6 positive, median PF 0.76 | Least-negative median | Still negative everywhere; five liquidations | Reject |
| Promote `stop4_hold144` | 0/6 positive, median PF 0.83 | Better median PF and tail than base | Still negative everywhere | Reject |
| Tune more stop/hold values | Broad failure across 15 global variants | Could find a narrow in-sample pocket | High overfit risk; same failed mechanism | Stop |
| Open later historical windows anyway | No development survivor | More data | Spends already-exposed evidence on a failed branch | Do not open |
| Preserve artifacts and test a new mechanism | Complete immutable failure evidence | Advances research without hiding losses | New implementation work | Proceed |

No residual candidate is eligible for the runtime router, TUI strategy list, or
forward observer. Preserve the artifacts as negative evidence and move to a
different causal mechanism rather than continuing exit-only tuning.

## Next action

Select one bounded mechanism that is not residual convergence and does not
duplicate the already rejected low-timeframe classifiers, EMA-touch/reclaim,
or flow-exhaustion screens. Freeze its signal, friction, portfolio, and evidence
contract before inspecting outcome cells. Live execution remains unchanged and
disarmed.
