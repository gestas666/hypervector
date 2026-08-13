# Source-follow production-queue lead review — 2026-07-29

## Problem and success criteria

The source-follow shadow candidate previously survived an optimistic
trade-through replay. This review asks whether a minimally changed candidate
retains positive expectancy under the production shadow execution path:
displayed queue ahead, public-trade consumption, partial fills, 50 ms submit
and cancel latency, authentic mark/oracle observations, official funding,
maker and taker fees, isolated liquidation, and a 24-hour maximum hold.

A useful lead must improve the frozen control on the same development evidence
without changing execution economics, suppressing reported trials, granting ML
execution authority, or modifying the active backend.

## Fixed contract

- Starting equity: $15,000 per independently reset development block.
- Signal source: pinned Hypertrader revision
  `ad15f2bdc949619be495a5f516babd08f7f52a90`.
- Entry: confirmed completed-5m `TREND_DOWN` onset, short only, confidence at
  least 0.70, range at most 100 bps, 24/7, one 60-second post-only pulse.
- Risk: 50% isolated margin, 30x leverage, one BTC position.
- Exit: 8% gross-margin target, no fixed stop, first fresh-BBO taker exit after
  24 hours.
- Model: observe-only; it cannot filter or resize execution.

The lead changes one signal field: completed-5m onset range must also be at
least 12 bps. The threshold was discovered on the development periods and is
therefore not independent evidence.

## Matched development result

The twelve gap-free development blocks contain 421 raw source decisions. The
12-bps lead retains 285 decisions, or 67.70%. All trials completed and remain
reported; the threshold is a configured strategy feature rather than an
implicit trial-abort gate.

| Metric | No range floor | 12-bps floor | 25x sensitivity |
|---|---:|---:|---:|
| Completed trades | 153 | 116 | 148 |
| Target completions | 131 | 106 | 124 |
| Time exits | 6 | 1 | 11 |
| Liquidations | 16 | 9 | 13 |
| Partial liquidations | 47 | 28 | 34 |
| Profit factor | 1.150 | 1.913 | 1.075 |
| Reset-block net PnL | +$7,586.91 | +$25,095.49 | +$3,737.63 |
| Positive blocks | 8/12 | 10/12 | 8/12 |
| Worst block drawdown | -48.17% | -48.17% | -51.25% |

The lead paid $6,918.83 in maker fees and $802.79 in taker fees and received a
net $524.54 in funding cashflow. The result includes friction; it is not gross
price movement presented as net profit.

Outcome attribution explains the change. In the control, all six 24-hour exits
and seven of sixteen liquidations followed completed signal bars below 12 bps;
the sub-12-bps cohorts lost $14,975.52 in aggregate. This is a historical
association, not proof that 12 bps is a stable causal boundary.

Lowering leverage to 25x is rejected as the next lead. It moved the target
farther away, created eleven maximum-hold exits, lowered PF to 1.075, and
worsened the block-return sensitivity despite reducing some liquidation risk.

## Next-period observation

The already observed 2026-04-18 through 2026-04-28 slice retained nine of
fifteen source decisions and completed four targets with no liquidation. It
ended at $16,451.84 from $15,000 with -18.87% maximum drawdown. This supports
temporal plausibility but is not a strict blind holdout because the slice was
already examined during earlier candidate work.

## Continuous-account validation

A single-account replay across all twelve verified segments carried equity and
proportional order size forward. It crossed 29.08 omitted calendar days only
while execution was flat and idle. The account covered 234.875 verified days
over a 263.958-day calendar span.

| Continuous metric | Result |
|---|---:|
| Initial equity | $15,000.00 |
| Final equity | $36,243.91 |
| Net PnL | +$21,243.91 |
| Return | +141.63% |
| Completed trades | 114 |
| Targets / time exits / liquidations | 100 / 2 / 12 |
| Profit factor | 1.428 |
| Maximum drawdown | -51.03% |
| Maker / taker fees | $9,771.99 / $1,317.11 |
| Funding cashflow | +$730.96 |

All twelve segments ended flat, the final account had zero open positions, and
missing and stale oracle-settlement counters were zero. Eight of twelve
continuous segment returns were positive.

The result is materially weaker than the $58,184.57 product of independently
reset block returns. Compounded order size changed queue/fill paths, reducing
the ending balance by $21,940.66 versus that sensitivity. The continuous path
nevertheless retained a positive PF and more than doubled the account after
all modeled friction.

A geometric annualization over this development calendar span would end near
$50,804 from $15,000, or about +$35,804 net. That is an in-sample sensitivity,
not a forecast, and it remains well below the requested $100,000 annual net
objective.

## Consolidation-wick risk screen

The production replay was repeated after adding signal time, final weighted
entry price, maximum filled entry quantity, and the measured isolated
liquidation boundary to every lifecycle. All 19 prior aggregate fields matched
exactly: final equity, trade outcomes, profit factor, drawdown, fees, funding,
fill quantity, uncertainty annotations, oracle counters, and open positions.
The enriched control therefore retained the exact no-stop execution path.

A predeclared, report-only screen then placed a short stop at the high of the
most recent completed BBWP(20, 240)<25 compression episode. The screen used
394,468 native Hyperliquid 1-minute candles plus 92 explicit zero-volume
`hl_gap_fill` minutes. The native candle timestamp set exactly matched the
minutes containing archived Hyperliquid public trades; the bounded fills
represent no-trade minutes rather than fabricated price excursions. The first
signal occurred more than three days after the candle boundary, exceeding the
260-minute BBWP warmup requirement.

| Fixed-lifecycle screen metric | Result |
|---|---:|
| Filled lifecycles | 114 |
| Effective stops | 93 |
| Stop hits | 37 |
| Liquidations avoided | 11/12 |
| Completed targets stopped early | 26/100 |
| Benefit on liquidated lifecycles | +$19,955.73 |
| Cost on target-completed lifecycles | -$65,396.62 |
| Original net PnL | +$21,243.91 |
| Counterfactual net PnL | -$24,196.99 |
| Net PnL delta | -$45,440.89 |

The consolidation-wick stop is rejected. It removed most liquidation events
but destroyed more target expectancy than it preserved. No stateful stop,
runtime gate, or parameter search was added. This is a fixed-lifecycle screen:
it cannot resolve intraminute mark/BBO ordering, stateful re-entry, or actual
stop slippage. Those limitations could change individual fills, but total
recorded funding was only +$730.96 and cannot plausibly bridge the measured
$45,440.89 deficit without a separate contradictory replay.

## Runtime boundary

The control remains
`configs/hypervelocity_source_follow_shadow.toml`, with an explicit 0-bps
minimum. The lead is a distinct shadow-only profile at
`configs/hypervelocity_source_follow_minrange12_shadow.toml`. Backend identity
and read-only TUI telemetry expose the minimum and maximum completed-5m ranges.
The lead profile has no live authority. The existing faithful backend was not
restarted, reset, or cut over.

## Immutable evidence

- Continuous production replay:
  `data/logs/research/hypervelocity_source_production_minrange12_continuous_dev_20250728_20260418_20260729.json`
  (SHA-256
  `0a47047393b349c15f2ffd8153b24508122610915b367668710a5b4554129209`).
- Enriched continuous production replay with exact aggregate parity:
  `data/logs/research/hypervelocity_source_production_minrange12_continuous_dev_details_20250728_20260418_20260729.json`
  (SHA-256
  `87bbf0a794b235b197a88134135d95d18b863e250350365a91a82bd8aa7ccdd1`).
- Frozen consolidation-wick screen:
  `data/logs/research/hypervelocity_source_production_minrange12_wick_screen_20250728_20260418_20260729.json`
  (SHA-256
  `2ee5c8fac7da4113d13ea5481da6534d832b63059edd0ad2d121c1a6897a8d37`).
- Next-period observation:
  `data/logs/research/hypervelocity_source_production_minrange12_holdout_20260418_20260428_20260729.json`
  (SHA-256
  `80eab12b933696b95aba6f7fcd3ffb18d88d5b00a95f3f3b8a16c71bbedc7e36`).
- Lead shadow profile:
  `configs/hypervelocity_source_follow_minrange12_shadow.toml` (SHA-256
  `4add84eab5052dc9b7318a860e80a500468c9fe0243ba1d319ca3298a55c0ad4`).

## Verification

- Immutable artifact contract and integrity invariants: passed.
- Continuous replay orchestration tests: 5 passed.
- Repository non-network Python suite: 1,448 passed, 4 deselected.
- Focused Ruff checks and changed-file whitespace checks: passed.
- Rust/TUI suite: 34 passed; no Rust files changed during this
  continuous-replay checkpoint.

## Confidence, risks, and falsifiers

- Execution implementation confidence: high for the tested local path. The
  relevant tests and repository regression suites pass, and label/runtime
  parity is exact. Private queue cancellations and true receipt latency remain
  unknowable from the archive.
- Historical edge confidence: medium. The continuous account retained PF
  1.428 and +141.63%, while the matched block comparison, attribution, and
  next-period slice also improved. The threshold was selected on development
  evidence, and compounding added three liquidations versus reset blocks.
- Live or income confidence: low. The -48.17% reset-block drawdown was already
  operationally severe; continuous drawdown was worse at -51.03%, and no fresh
  forward sample establishes stationarity.

The lead is weakened or rejected if fresh shadow PF falls to 1 or below after
friction, drawdown repeatedly exceeds the historical envelope, real fill
timing is materially worse than replay, source labels drift, or ledger/TUI
identity and accounting diverge. The consolidation-wick emergency exit failed
its predeclared screen and must not silently replace the lead. The next useful
evidence boundary is a fresh forward shadow window on the unchanged no-stop
lead, with the new lifecycle telemetry retained for liquidation attribution.
