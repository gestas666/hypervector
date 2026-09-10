# Original full-fee allocation comparison

The first/full-prefix/recorded-clock full HIP-3 fee pair is complete and
independently reconciled. High confidence applies to these historical
calculations, conditional on the retained source and modeled execution rules.
The full 48-case assessment and any deployment recommendation remain pending.

| Metric, July 21–September 7 UTC | Control | Equal allocation |
| --- | ---: | ---: |
| Net equity change | -$33.44 | +$92.00 |
| Return on starting $4,857.59 | -0.69% | +1.89% |
| Maximum marked drawdown | $233.56 / 4.67% | $365.68 / 7.05% |
| Earlier 28 days | +$103.59 | +$250.59 |
| Later 20 days | -$137.03 | -$158.60 |
| Average gross notional | $872.60 | $1,765.76 |
| Net after removing three largest winners | -$258.74 | -$391.45 |

Both cases contain the same 177 closed trade identities, 66 winners and 111
losers, no open trades, and a 37.29% win rate. Equal allocation adds $125.43 net
and $132.11 maximum marked drawdown with 2.0236 times average gross exposure.
Its later-segment advantage under the lower fee assumption does not persist:
it loses $21.57 more than control in this full-fee later segment. These are
previously available historical periods, not new prospective holdouts.

This predeclared stress changes the three non-crypto assets from 0.9 to 9 bps
fees per side, preserving adverse slippage of 5.5 bps per side. Core fees remain
4.5 bps. The scenario does not establish actual historical discount states or
today's fee eligibility. The September 7 fee qualification is a separate
point-in-time observation and is not retrofitted into this history.

The strict hypothesis that only fee cashflows change was falsified by one
SNDK long liquidation on August 7. Higher entry fees reduce modeled isolated
collateral and move its liquidation price from 1248.9692660171054 to
1250.0932259605265. Independent arithmetic from the frozen leverage, maximum
leverage, quantity, margin, entry fee and funding reproduces both prices.
All other non-fee trade fields match. Added fees are $129.58178576 / $277.83259119;
the changed gross liquidation PnL offsets $0.42598082 / $0.91265547. Their
net profit reductions are therefore $129.15580494 / $276.91993571. This is an
explained consequence of the retained model, not evidence of a real venue fill.

Both cases separately authenticate 2,297 references, match the retained and
fresh independent account audit, and conserve seven equity totals. The
comparison additionally checks every trade field, per-trade cash identity,
aggregate fee/gross attribution and the liquidation calculation. A changed
source, unexplained price difference or nonconserved total falsifies this
acceptance. Concentration removals are diagnostics, not implicit rejection
gates or proof that a trend-following strategy is invalid.

Retain the positive full-period modeled allocation difference and its cost
sensitivity. Complete the remaining source/timing cases before a deployment
recommendation. Both prospective seals remain intact. No live strategy,
allocation, fees, execution, configuration or TUI installation changed.

Evidence is under `data/logs/research/bidirectional_cohort/`:
`v89_original_account_case_08_analysis_20260910_v1/`,
`v89_original_account_case_09_analysis_20260910_v1/`, and
`v89_full_fee_historical_account_comparison_20260910_v1/`.
Use `comparison_v2.json` and `compare_cases_v2.py`; the prior pair is retained
unchanged. Their numerical results match; revision 2 only meets the function
size convention while preserving the prior immutable source references.
