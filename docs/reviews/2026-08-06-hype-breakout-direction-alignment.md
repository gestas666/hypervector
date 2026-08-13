# HYPE breakout direction-alignment review

## Problem and decision

The live HYPE provider chooses entry side from the last completed hourly
SMA10/SMA30 structure and uses a fresh completed-five-minute `BREAKOUT` only
as the onset event. The question was whether entry should require the actual
five-minute breakout direction to agree with that hourly side.

Decision: retain the current structural-side contract. Do not add an alignment
gate or replace structural side with breakout side from this evidence.

Confidence is medium that an alignment gate is not justified. Confidence is
low that opposed entries are themselves an edge. The distinction matters:
rejecting one gate does not promote its opposite.

## Evidence

The immutable venue-history artifact is
`data/logs/research/hype_breakout_entry_alignment_hl365d_v2_20260806.json`
(SHA-256 `c03cd58711d6439f4ffa9b43362a58f6da8fe5ab47eb4bdb1d71167e9da7b472`).
It uses 525,600 authenticated HYPE one-minute bars, 8,760 matched funding
events, an 80-basis-point stop, 4.5-basis-point fee per side, 2-basis-point
slippage per side, an eight-hour soft hold, and regime-supported extension to
a twenty-four-hour hard limit.

| Window and cohort | Trades | Win rate | Mean net bps/trade | PF | Max DD bps |
|---|---:|---:|---:|---:|---:|
| Development control | 956 | 22.91% | -10.21 | 0.852 | 12,072.88 |
| Development aligned | 509 | 21.02% | -13.92 | 0.803 | 9,081.37 |
| Development opposed | 565 | 23.89% | -7.45 | 0.891 | 8,285.84 |
| Opened final control | 200 | 23.50% | -2.48 | 0.963 | 2,942.47 |
| Opened final aligned | 115 | 18.26% | -20.20 | 0.722 | 2,503.03 |
| Opened final opposed | 117 | 26.50% | +17.71 | 1.275 | 2,514.29 |

Aligned-only underperformed opposed-only by 6.47 mean basis points per trade
in development and 37.91 in the already-opened final block. All development
arms remained below a 1.0 profit factor, so none establishes a promotable
standalone edge.

The immutable live-prefix artifact is
`data/logs/research/hype_breakout_entry_alignment_all_live_20260806T0715Z.json`
(SHA-256 `c79fcb85a10bcfa143b3182397d468947e578f77e72959e38b5a3817e3212993`).
The first exact opposed lifecycle closed at its protective stop for
`-$0.73208`, or `-4.9275%` of entry margin after costs. The next lifecycle is
an open HYPE short whose structural and breakout directions are both short;
its resolved outcome is not yet evidence.

## Risks and failure modes

- The comparison was initiated after observing a live conflict and is post-hoc.
- The final sixty-day block was already opened and is not an untouched holdout.
- Filtering entries changes later position occupancy, so cumulative return
  sums are not comparable across unequal trade counts; mean return and profit
  factor are the primary comparison fields.
- One-minute bars and fixed slippage cannot prove the exact live IOC path.
- One exact closed live relation is far too sparse to distinguish regimes.

## Falsifier and next measurement

Update the decision if both conditions occur:

1. A predeclared prospective live sample with exact relation attribution shows
   aligned entries outperforming opposed entries after fees, funding, and
   slippage.
2. A causal unopened venue block using the same active exit contract improves
   mean return per trade and profit factor without materially worse drawdown.

Until then, preserve automatic execution, record every exact relation and
resolved lifecycle, and avoid turning this descriptive component into a gate.
Research revision `hype-breakout-direction-alignment` v3 records this decision
with `execution_authority=none` and `runtime_strategy_changed=false`.
