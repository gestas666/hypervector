# Four-Pine causal stack: 15m versus 30m

Status: frozen research specification; report-only; no execution authority.

## Development freeze — 2026-08-01

The 15m/30m source-control matrix and staged development tuning are complete.
No validation or pseudo-holdout result was inspected before this freeze.

Immutable evidence:

- `pine_stack_15m_30m_development_v1`: 192 Stage-A cells in DuckDB;
- `pine_stack_eth30_entry_tuning_development_v1`: 27 entry cells;
- `pine_stack_eth30_risk_hold_development_v1`: 9 risk/hold cells;
- `pine_stack_eth30_tp_support_development_v1`: 9 TP-support cells;
- `pine_stack_eth30_tp_axis_threshold_development_v1`: 5 semantic cells;
- `pine_stack_eth30_final_interaction_development_v1`: 4 final cells.

Observed development evidence:

- 30m beat 15m in 91 of 96 paired Stage-A comparisons;
- ETH 30m `cs_trend` was positive under all four Stage-A exit variants;
- the source-equivalent ATR10/sensitivity5/trend30 entry control produced
  +3701.72 USD, PF 1.571, 9.62% maximum drawdown, 134 trades, and zero
  liquidations;
- five of the source control's six direct entry-parameter neighbors were
  profitable;
- all nine stop/hold neighbors were profitable;
- TP density pivot5/bins5/minimum-pool50/threshold80 without time-of-day
  produced +3778.26 USD, PF 1.745, 5.83% maximum drawdown, 141 trades, and
  zero liquidations;
- sentiment thresholds 55 and 60 reduced the `cs_trend` development result,
  so Market Sentiment remains backend annotation rather than an entry gate.

Frozen validation identities, all ETH native 30m with ATR10, sensitivity5,
Trend Levels lookback30, 10% margin stop, 5x leverage, and nominal friction:

1. CS flip exit, 8-hour maximum hold;
2. CS flip exit, 4-hour maximum hold;
3. TP80/no-time exit with pivot5, bins5, minimum pool50, 8-hour hold;
4. TP80/no-time exit with pivot5, bins5, minimum pool50, 4-hour hold.

Validation is an evidence report, not an implicit execution gate. A negative
result remains journaled. The primary development hypothesis is falsified if
the simpler TP80/no-time 8-hour candidate loses after nominal friction in the
untouched validation window or if one-minute path replay materially reverses
its native-bar result.

## Validation freeze — 2026-08-01

The untouched half-open validation interval `2026-01-28T00:00:00Z` through
`2026-04-28T00:00:00Z` was opened only after the four identities above were
frozen. Artifact and DuckDB run identity:
`pine_stack_eth30_frozen_validation_v1`.

Validation results:

- CS flip / 8h: +1897.22 USD, PF 1.556, 3.58% drawdown, 76 trades, four of four
  calendar slices positive, zero liquidations;
- CS flip / 4h: +951.15 USD, PF 1.348, 4.19% drawdown, 77 trades;
- TP80/no-time / 8h: +552.52 USD, PF 1.226, 3.19% drawdown, 77 trades;
- TP80/no-time / 4h: +629.00 USD, PF 1.265, 3.46% drawdown, 77 trades.

The CS flip / 8h result decomposed to +774.98 USD across 36 long trades and
+1122.24 USD across 40 short trades. The TP challenger remained positive but
did not preserve its development advantage. Therefore only the plain CS flip /
8h identity advances to pseudo-holdout; the other three remain recorded controls.

The pseudo-holdout hypothesis is frozen before inspection: ETH native 30m,
adaptive CS ATR10/sensitivity5, Trend Levels lookback30 alignment, 10% margin
stop, 8-hour maximum hold, CS opposite-onset exit, 10% isolated margin at 5x,
nominal fees/slippage, and historical funding. No sentiment gate and no TP exit.

## Pseudo-holdout result — exact candidate rejected

The sealed `2026-04-28T00:00:00Z` through `2026-07-28T00:00:00Z` run identity
`pine_stack_eth30_frozen_pseudo_holdout_v1` lost 1242.85 USD with PF 0.650,
8.95% maximum drawdown, 82 trades, zero positive calendar slices, and zero
liquidations. Longs lost 524.18 USD and shorts lost 718.67 USD. This falsifies
promotion of the frozen CS-flip/8h configuration.

Exit attribution across the pseudo-holdout was +1562.00 USD for maximum-hold
exits, -1545.59 USD for CS exit signals, -352.20 USD for opposite-entry closes,
and -907.06 USD for stops. Maximum-hold cohorts were also positive in development
and validation. This observation creates a new, explicitly post-hoc hypothesis:
retain the same entry and risk identity, ignore subsequent CS entry/exit events
while a position is open, and close only at the stop or eight-hour maximum hold.
The pseudo-holdout is contaminated for this new hypothesis. Even a favorable
full-history diagnostic may advance only to fresh forward shadow observation.

## 1. Problem restatement

Determine whether four Pine indicators form an economically useful directional
stack on Hyperliquid native perpetual data, and whether decisions should be made
on completed 15-minute or 30-minute bars. The output is a reproducible comparison,
not a visual judgment. Any later TUI view must render backend-computed state.

Success requires:

- causal signals that are unchanged when future bars are appended;
- the same assets, dates, friction, capital rules, and exit comparisons at both
  timeframes;
- every declared cell retained, including zero-trade and losing cells;
- development selection followed by untouched validation and pseudo-holdout;
- explicit trade count, profit factor, net PnL, drawdown, liquidation, fee,
  funding, ambiguity, and month/asset/direction attribution;
- no live execution authority.

## 2. Source audit

### CS Scalper: entry onset candidate

Source: `reference/pine-scripts/cs-scalper.pine`.

The primary entry event is an adaptive-SuperTrend state flip at lines 895-932.
The source defaults are ATR length 10 and sensitivity 5, producing factors 1.0
through 5.0 in 0.5 steps. Per-factor trailing states accumulate a causal return
performance statistic and are clustered; the mean factor in the highest-performing
cluster drives the final trailing state.

Observed defects and limitations:

- `signalMode` is declared at line 13 but does not affect signal generation.
- The `Short-Term` input does not match the `Short Term` condition at line 626;
  that autopilot branch cannot activate as written.
- The `Mid-Term` input similarly does not match `Mid Term` at line 629.
- `last_bar_index - bar_index <= maxData` at lines 688 and 701 makes historical
  availability depend on the chart's terminal bar. Earlier results can disappear
  as the chart advances. This must not be reproduced.
- The trend-strength filter at lines 899 and 918 checks absolute strength only.
  It can approve a long during strong bearish strength or a short during strong
  bullish strength.
- The “AI Signal Classifier” at lines 774-892 is a manually weighted nonlinear
  score. No learned parameters, training data, loss, or calibration are present.
  It is not an ML model and must be labeled `heuristic_score`.
- That score changes label color/text only; it does not qualify the base signal.
- The volume score assigns the current candle's entire volume to one side using
  candle geometry. It is not venue order-flow pressure.

Backend translation:

- compute factor states sequentially from the beginning of the available warmup;
- use only state available at the completed native bar;
- cluster only the current cross-factor performance vector, without any
  terminal-bar window condition;
- emit a decision at bar close and enter no earlier than the next native bar open;
- test the base flip before testing any additional filter;
- retain the heuristic grade as annotation-only until separately calibrated.

### Trend Levels: structure and directional state

Source: `reference/pine-scripts/trend_levels.pine`.

The source flips up when the current high equals the rolling high and flips down
when the current low equals the rolling low (lines 43-53). It then tracks the
high, low, midpoint, duration, and close-location counts of the active episode
(lines 99-133).

Observed defects and limitations:

- A bar that is simultaneously the rolling high and rolling low finishes bearish
  because two independent `if` statements execute in order.
- The source starts with `trend = na` and `bars = 0`; dynamic-window levels are
  undefined until the first state event.
- Episode levels include the current bar. They are causal at close but cannot be
  treated as pre-bar breakout levels.
- `delta_percent` compares historical closes with a midpoint that evolves each
  bar. It is descriptive state, not a probability or calibrated confidence.

Backend translation:

- preserve the source-order behavior as `source_exact` control;
- add a declared `ambiguous_hold` challenger that retains the prior state when a
  bar makes both rolling extremes;
- expose episode high, low, midpoint, duration, delta, and ambiguity count;
- use state alignment and structural stop/target anchors as separate ablations.

### Market Sentiment: confirmation and attribution

Source: `reference/pine-scripts/market-sentiment.pine`.

The score is the unweighted mean of eleven normalized components at lines
518-521: RSI, stochastic, stochastic RSI, CCI, bull-bear power, moving average,
anchored VWAP, Bollinger Bands, SuperTrend, linear-regression correlation, and
confirmed market structure. Market-structure pivots use five left and five right
bars (lines 247-274). Optional sentiment divergence also uses five-left/five-right
pivots and is known only on the confirmation bar (lines 547-565).

Observed defects and limitations:

- The eleven components are highly correlated price-derived measures. An
  unweighted average is not eleven independent confirmations.
- Normalization at lines 155-164 carries state since the most recent component
  transition; zero-width ranges can produce undefined values.
- `request.security` at lines 277-292 must be translated using completed native
  bars only. A live partial higher-timeframe value is prohibited.
- Auto VWAP anchoring changes from daily at 15m to weekly above 15m (lines
  128-147). A fair 15m/30m comparison must use the same explicit anchor.
- Divergence is plotted five bars back but is not knowable there. The backend may
  emit it only at confirmation.

Backend translation:

- implement and expose all eleven component values plus the aggregate;
- use a fixed daily anchor in the matched-timeframe comparison, with weekly anchor
  as a separately named sensitivity test;
- begin as annotation-only, then test directional thresholds without changing the
  base CS event stream;
- report component correlations and ablations before assigning weights.

### SuperTrend TP Dimensions: exit-context challenger

Source: `reference/pine-scripts/supretrend_tp_dimensions.pine`.

The source uses SuperTrend ATR 10/factor 3, confirmed three-left/three-right
zigzag pivots, five histogram bins, and three default context axes: 50-bar
relative-volume percentile, time of day, and recent-range position (lines 7-20).
It stores context from the pivot bar only after confirmation (lines 206-248).
Each axis score is the current-bin count divided by the peak-bin count in a
conditional histogram (lines 145-158), and the aggregate is their mean. The
source explicitly states that this is a density match, not a forward probability
(lines 211-217 and 420-422).

Observed defects and limitations:

- A score of 100 can be produced by one sparse observation; no minimum support is
  enforced.
- Exact-bin conditioning across multiple axes can make samples extremely sparse.
- Time of day is a possible overfit axis and has different sample counts at 15m
  and 30m.
- A newly confirmed pivot enters the pool before the current score is calculated.
  This is causal at confirmation but can inflate the score on that bar.
- Intermediate pivots are treated as exit contexts even when they did not end the
  SuperTrend run.

Backend translation:

- preserve score meaning as `density_match`, never `probability`;
- expose pool size, conditional support per axis, and insufficient-support state;
- compare all three axes with a no-time-of-day ablation;
- test thresholds 80 and 100 only after minimum-support checks;
- compare this exit against fixed structural/ATR and maximum-hold exits.

## 3. Combined architecture

| Layer | Primary role | First use | Must not do |
|---|---|---|---|
| CS Scalper | Directional entry onset | Base entry event | Use terminal-bar-dependent history |
| Trend Levels | Regime/structure | Annotation, then alignment ablation | Treat current episode level as prior breakout evidence |
| Market Sentiment | Confirmation/ranking | Annotation, then threshold ablation | Present correlated mean as ML probability |
| TP Dimensions | Exit context | Annotation, then exit challenger | Exit on unsupported score 100 |

The combined candidate is not permitted to hide the base event stream. Every
withheld event records the exact contributing condition so that trade suppression
and economic effect can be attributed.

## 4. Frozen development surface

Assets: BTC, ETH, SOL, HYPE native Hyperliquid perpetuals.

Segments: reuse the existing half-open development, validation, and pseudo-holdout
windows. Build features with leading warmup outside each scored segment whenever
source history permits. Report any warmup shortfall.

Timeframes:

- native 15m decisions and next-15m-open entry;
- native 30m decisions and next-30m-open entry;
- no 5m signal mixed into either comparison;
- identical UTC dates and fixed daily VWAP anchor.

Stage A, source controls:

- CS causal correction, ATR 10, sensitivity 5;
- Trend Levels source-exact length 30;
- Market Sentiment defaults, annotation-only;
- TP Dimensions defaults, annotation-only;
- fixed ATR/structure stop plus maximum hold for base entry attribution.

Stage B, component ablations:

- CS only;
- CS plus Trend Levels alignment;
- CS plus sentiment 55/45;
- CS plus Trend Levels plus sentiment 55/45;
- each entry variant with TP-density exit at 80 and 100, subject to support;
- TP-density with and without time-of-day conditioning.

Stage C, bounded tuning on development only:

- CS sensitivity: 3, 5, 8;
- CS ATR length: 7, 10, 14;
- Trend Levels source length: 20, 30, 48;
- sentiment directional bands: 55/45 and 60/40;
- TP pivot width: 3 and 5;
- TP bins: 5 and 10;
- TP minimum directional pool: 25 and 50;
- maximum hold: 8, 16, and 32 native bars;
- stop distance: 1.0, 1.5, and 2.0 ATR.

This is staged, not a full Cartesian product. Each stage retains the source control
and changes one logical layer at a time. Only a bounded shortlist advances to the
untouched validation window.

## 5. Friction and risk evidence

Use actual historical funding where available, explicit Hyperliquid fee tier,
adverse slippage, next-bar execution, one-minute intrabar stop/target ordering,
gap handling, isolated-margin liquidation, and one position per coin. Development
cell results are independent-strategy evidence; portfolio claims require a later
shared-capital replay with maximum concurrent exposure and conflict policy.

Nominal and stressed friction must both be reported. A candidate that depends on
maker fills requires order-book/event replay or a forward canary before promotion.

## 6. Validation and falsification

Required tests:

- unit parity fixtures for each Pine component;
- append invariance for every emitted state, score, pivot, and entry;
- 15m/30m aggregation completeness and timestamp-availability tests;
- source-exact versus corrected-CS event-difference ledger;
- component correlation and withheld-trade attribution;
- development, validation, pseudo-holdout, cost stress, parameter-neighbor, and
  month/asset/direction slices;
- shared-capital replay only after individual-cell evidence is complete.

The stack is falsified for promotion if positive development performance does not
survive validation after realistic friction, if results depend on a narrow isolated
parameter, if append invariance fails, or if most apparent edge comes from sparse
TP-density bins. That does not abort research; it records a failed trial under
`SRS_HV1_NO_GATES`.

## 7. Backend and TUI contract

No TUI strategy calculation is permitted. Backend telemetry must include:

- symbol, native timeframe, source-bar open, source-bar close/available time;
- forming versus completed status;
- CS factor range, chosen factor, state, state age, and onset;
- Trend Levels state, episode high/low/midpoint, duration, delta, ambiguity;
- all eleven sentiment components, aggregate, threshold, and divergence
  confirmation time;
- TP density score, three axis scores, directional pool size, conditional support,
  threshold, and insufficient-support state;
- exact decision reason, withheld reasons, position, stop/target, fees, funding,
  liquidation estimate, and parameter/source hash.

Proposed read-only visuals after backend validation:

1. Candle chart with CS trailing line, Trend Levels episode bands/midpoint, entry,
   exit, stop, and confirmed-pivot markers. Forming candles are visibly distinct.
2. Confluence panel with sentiment aggregate and eleven compact component bars.
3. Exit-context panel with density gauge, per-axis histograms, sample support, and
   a clear `DENSITY MATCH — NOT PROBABILITY` label.
4. 15m/30m comparison panel showing event count, agreement/disagreement, current
   completed states, and last update times.

## 8. Current recommendation

The staged comparison, tuning, validation, and pseudo-holdout are complete. Do
not promote the frozen ETH 30m candidate: its later pseudo-holdout loss directly
contradicts the positive development and first validation evidence.

Run only the zero-capital `pine_stack_eth30_forward_observer_v1`. It computes the
four source components on completed native 30m ETH bars, persists append-only
backend decisions, and has no wallet, order construction, portfolio, shadow-fill,
or live authority. The TUI is a read-only projection of that ledger and shows:

- CS Adaptive Supertrend state, onset, selected factor, and trailing stop;
- Trend Levels episode state, duration, high, low, midpoint, and ambiguity;
- all eleven Market Sentiment components as annotation only;
- TP Dimensions density, support, and the explicit `NOT PROBABILITY` semantic;
- zero capital, no orders, and `PSEUDO-HOLDOUT FAILED` lifecycle status.

The separate `xyz:SP500` HIP-3 qualification track is deferred by user decision
and is not represented as active work or execution authority.

Confidence is high that the frozen candidate failed its tested promotion path,
and medium that the forward observer and TUI preserve the intended component
semantics. A ledger/TUI mismatch, an order/place attempt, a forming-bar decision,
or restart duplication would falsify the implementation. Genuinely fresh,
venue-matched forward observations with stable after-cost outcomes could justify
a new preregistered candidate, but cannot retroactively repair this failed one.
