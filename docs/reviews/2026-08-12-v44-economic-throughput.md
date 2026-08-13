# v44 Economic Throughput and v45 Growth-Sizing Review

## Scope

This is a report-only sizing and opportunity diagnostic for the proposed
`multi_asset_bidirectional_btc_specialists_corrected_candidate_v44` profile.
It does not authorize execution, change a strategy, or impose an implicit
performance gate.

The question is narrower than whether v44 is technically safe: does the
current three-asset roster have enough causal opportunity and after-friction
expectancy to make a future $5,000 deployment economically meaningful?

The separately versioned v45 candidate preserves the v44 providers, entries,
stops, targets, and time exits. It changes only HYPE and SP500 base sizing. It
does not modify the active v39 process or grant live execution authority.

## 08:30Z continuation evidence

The latest reconciled live archive contains 61 closes: 27 wins, 34 losses,
net -$0.995574, PF 0.9228, and -$3.049798 after removing the largest winner.
The active v39 run contributes ten of those closes: 2 wins, 8 losses, net
-$3.042340, PF 0.0382. Every provider-symbol mapping represented in that
ten-close set is absent from v45. Three remaining v39 positions are still
open, protected by venue stops, and excluded from closed performance.

Fresh canonical-regime evidence through decision time 1786522980000 remains
unsuitable for increasing size. At a 15-minute horizon, pooled primary
TREND_UP accuracy is 47.00% and TREND_DOWN accuracy is 47.16%. At 60 minutes
they are 55.68% and 46.06%, respectively, using overlapping observations.
The 15-minute episode-onset sample is smaller and worse: TREND_UP 10.0%
(n=10), TREND_DOWN 46.15% (n=13). This supports preserving regime as
telemetry/conflict context, not treating its confidence as a win probability.

Unused-slot research advanced without changing live authority. SKHX now has
64 prospective completed 15-minute bars and ten fresh decision bars with zero
entry/exit/stop signal disagreements across candle sources. It still has three
unresolved venue-path bars in the unsupplemented recorder audit and 16 candle
OHLC mismatches. The later 09:00Z update resolves those three recorder paths
from exact exchange history. The standalone MU shadow collector is running
with no signer or order surface. The later 09:15Z update resolves its bounded
prospective path and strategy-decision parity, while historical development
path uncertainty and untouched out-of-sample economics remain unresolved.

## 09:00Z SKHX evidence update

The three recent SKHX path failures were local recorder gaps rather than
missing venue history. Exact 0xArchive supplementation supplied 28,318 L2
snapshots and 4,309 non-null mark observations over the affected four-hour
window. All three bars now satisfy the original 5-second mark and 15-second L2
contracts. The repaired prospective audit has 64 completed bars, ten fresh
decision bars, and zero entry, exit, or stop disagreements across the two
candle sources. Sixteen candle OHLC rows differ, so raw candle equality is not
claimed; the frozen strategy decisions are nevertheless identical in this
bounded prefix.

The older development archive remains a separate issue. Its frozen selected
track is 15-minute bidirectional breakout pressure with EMA 21/55, lookback 16,
minimum absolute imbalance 0.5, and a 40 bps signal stop under the 80 bps
portfolio ceiling. Development produced 34 trades, nominal +$14.76/PF 2.43 and
stress +$12.91/PF 2.09 on $500. Stress remains +$3.84/PF 1.32 after removing
the largest winner. These are development results, not out-of-sample claims.

The exact threshold diagnostic explains the technical rejection:

| Maximum mark gap | Unresolved bars | Affected lifecycles |
|---:|---:|---:|
| 5.0s frozen contract | 1,586 | 24/34 |
| 6.0s sensitivity | 21 | 4/34 |
| 7.5s sensitivity | 10 | 2/34 |
| 10.0s sensitivity | 8 | 1/34 |
| 15.0s sensitivity | 6 | 1/34 |

Most failures are the archive's approximately five-second sampling cadence
plus delivery jitter: 1,565 of 3,667 bars fall between 5.0 and 6.0 seconds.
One 24-hour long lifecycle crosses a genuine 80.863-second mark gap on June 20,
so widening the threshold cannot make the path exact. Its observed entry-to-
exit market move was positive, but that does not prove what the unseen mark did
inside the gap. SKHX therefore remains report-only; validation and holdout stay
unopened pending a predeclared conservative gap treatment or exact recovered
mark evidence.

The predeclared diagnostic replaces that one unresolved trade with a synthetic
100 bps notional loss. Under stress friction, development remains +$10.16,
PF 1.80, and +$1.08/PF 1.09 after removing the largest winner. This supports
continued research but does not resolve the missing mark path: the replacement
is explicitly not an observed fill, validation remains unopened, and execution
authority remains none.

## 09:15Z MU evidence update

The report-only MU collector now has 69 completed prospective 15-minute bars.
Its original audit found two unresolved bars: one mark-cadence miss and one
approximately 125-second local L2/mark recorder gap. Exact 0xArchive
supplementation supplied 23,568 books, 6,345 public trades, and 3,587 exact
price observations over the affected three-hour interval. Both bars now meet
the frozen risk-path and L2 contracts.

The repaired prefix has 37 fresh breakout-pressure decision bars. Replaying
the frozen provider on live candle snapshots and reconstructed public-trade
OHLC produced zero entry, exit, or stop disagreements. Nine of 69 raw OHLC
rows differ, so this is strategy-decision parity rather than raw-candle
equality. The collector remains report-only and has no signer/order authority.

Historical MU development is still technically unresolved. The frozen
15-minute breakout track produced 56 development trades: nominal +$14.81,
PF 1.71 and stress +$13.14, PF 1.60 on $500; stress remains +$7.21/PF 1.33
after removing its largest winner. However, 43/56 lifecycles violate the
original five-second historical mark-path contract and 25 have unresolved
entry slices. At a 15-second sensitivity, two lifecycles remain affected.
Prospective parity does not reconstruct those historical gaps, and validation
and holdout remain unopened. MU is therefore a qualified data-collection track,
not an unused live portfolio slot.

## 09:52Z live continuation update

The active v39 backend remains healthy and consistent. The archive now has
61 all-time closes and ten current-run closes at 2W/8L, -$3.0423. ETH, SOL,
and SP500 are open. Each exact asset ledger currently reconciles a full-size
reduce-only venue stop; the three marked values are provisional and changed
during the audit.

Two open routes are absent from v45: onset ETH/SOL. SP500 pressure is the only
retained route. Its short moved approximately 34 bps
favorably before returning near breakeven. The existing report-only profit-lock
challenger estimates that the predeclared 25-bps activation, 15-bps floor,
10-bps trailing policy would have triggered around +24.1 bps gross and about
+$0.156 net before funding and additional exit slippage. This is one unresolved
live lifecycle and cannot establish an exit edge. Its actual close and the
frozen counterfactual must be recorded before considering an SP500 exit change.

BRENTOIL subsequently hit its protective stop after 78.6 minutes: -$0.687962
net, -4.6128% on entry margin. It reached only +25.82 bps MFE, then surrendered
114.35 bps from peak; the five-minute post-exit path briefly continued in the
original short direction by 18.40 bps. The entry and exit regime challenger
were unavailable, so this lifecycle cannot validate regime sizing. Historical
stress evidence was already negative, and this exact forward loss strengthens
the decision to exclude BRENTOIL pressure from v45; it does not justify fitting
a one-trade profit lock after the fact.

That single-lifecycle hypothesis has now been challenged against the exact
SP500 breakout-pressure stress lifecycles using causal one-minute L2-midpoint
OHLC. The immutable report is
`data/logs/research/xyz_sp500_breakout_profit_lock_l2_proxy_20260812_v2.json`
(SHA-256 `15bfa0261e0fddcd6573f185a06a48e636d37e3c34cf10e016e669530c811666`).
At the frozen 15-second continuity boundary all 13 validation lifecycles resolve.
The observed live 25/15/10 lock changes the same validation rows from +$0.648375
before funding to -$0.097812 after modeled fees, PF 0.9151, and -$0.318413 after
removing its largest winner. The 40/15/20 policy is also negative. The 60/15/30
policy is positive in validation (+$0.874091, PF 1.5912) but negative in every
development continuity sensitivity, so it is withheld rather than selected
post hoc. Disposition: no SP500 exit-policy change. The proxy uses midpoint
rather than venue mark/trade OHLC and excludes funding and additional exit
slippage; those limitations weaken any positive claim but do not rescue the
two validation-negative policies.

The 10:57Z v45 observer prefix has 189 route evaluations and zero eligible
signals: HYPE 165, SP500 13, BTC short 7, and BTC long 4. The raw
decision-time metrics needed for future route-native sizing are present, but no
eligible outcome exists yet. This supports continuing capture; it does not
support loosening entries or increasing leverage to manufacture frequency.

## 10:39Z SKHX prospective observer update

The development-selected SKHX track now has a standalone, durable prospective
observer using the exact frozen 15-minute identity: EMA 21/55, breakout
lookback 16, minimum absolute depth-ten imbalance 0.5, and 40-bps signal stop.
The implementation shares the causal MU pressure/cursor machinery rather than
cloning it, while preserving distinct symbol, provider, profile, asset-ledger,
cursor, journal, and status identities.

Two bounded public-mainnet polls passed. The first created a bootstrap cursor at
decision boundary 1786530600000 without replaying an historical decision; the
second reused that cursor and again published no decision. Each poll captured
an exact 10x10 `xyz:SKHX` book. Status explicitly reports
`execution_authority=none`, `signing_client_constructed=false`, and
`orders_supported=false`. The persistent report-only observer is now running.
It is not registered in v39/v45, cannot create an intent or order, and retains
the public-trade-OHLC versus live-candle parity blocker. Promotion remains
withheld until prospective entries and completed after-cost outcomes exist.

## Exact roster and capacity

The profile contains three assets even though the account capacity is ten:

- BTC: one shared asset slot for the 30-minute short specialist and one-hour
  long liquidity-sweep specialist.
- HYPE: one-minute collection for a completed five-minute compression setup.
- `xyz:SP500`: 15-minute HIP-3 breakout-pressure setup.

One position per asset limits simultaneous positions to three. The ten-position
setting is an upper bound, not a populated portfolio.

## Descriptive cadence

| Route | Evidence window | Events | Descriptive events/week |
|---|---:|---:|---:|
| BTC short | 2026-07-30 12:00Z to 2026-08-10 23:00Z | 1 | 0.61 |
| BTC long | 2026-05-04 11:00Z to 2026-08-06 14:00Z | 7 | 0.52 |
| HYPE compression development | 365 days | 138 | 2.65 |
| HYPE compression confirmation | 14 days | 4 | 2.00 |
| SP500 pressure common window | 22.36 days | 19 | 5.95 |

These frequencies are not additive forecasts. Occupancy, simultaneous signals,
market state, and different evidence contracts can reduce realized portfolio
frequency. The first exact v44 observer prefix produced no eligible signals;
that prefix is too short to estimate forward cadence.

## Dollar-throughput hurdle

At 8, 12, and 20 completed trades per week, the mean net result required per
trade to produce selected monthly outcomes is:

| Trades/week | $500/month | $1,000/month | $2,000/month |
|---:|---:|---:|---:|
| 8 | $14.42 | $28.85 | $57.69 |
| 12 | $9.62 | $19.23 | $38.46 |
| 20 | $5.77 | $11.54 | $23.08 |

This arithmetic is a diagnostic, not a return forecast. It shows why frequency
without net expectancy, or risk without opportunity flow, cannot satisfy the
economic objective.

## Current $5,000 risk shape

| Route | Planned notional | Route p99 stop wave | Equity fraction |
|---|---:|---:|---:|
| BTC short | $3,333.33 | $33.38 | 0.67% |
| BTC long | $4,166.67 | $35.48 | 0.71% |
| HYPE | $774.21 | $8.53 | 0.17% |
| SP500 | $860.02 | $7.37 | 0.15% |

Only one BTC direction can occupy the BTC slot. The simultaneous three-asset
p99 stop-wave model is $51.38, or 1.03% of equity. This is not a maximum-loss
guarantee; gaps, depleted depth, stop latency, and correlated co-triggers can
exceed it.

The old v44 artifact reused a $750 visible-depth curve for BTC route notionals
above $3,300. That approximation understated the evidence contract even though
the updated BTC p99 depth estimate is slightly lower in the latest bounded
window. The v45 report therefore reprices BTC at $4,166.67, HYPE at $1,750,
and SP500 at $1,750 rather than copying the old curve.

## Proposed v45 base risk

| Slot | $500 notional | $5,000 notional | Modeled p99 loss fraction |
|---|---:|---:|---:|
| BTC, worst mutually exclusive side | $416.67 | $4,166.67 | 0.71% |
| HYPE | $175.00 | $1,750.00 | 0.38% |
| SP500 | $175.00 | $1,750.00 | 0.30% |

The resulting route-aware simultaneous p99 stop wave is 1.394% of equity:
$6.97 at $500 and $69.68 at $5,000. Maximum simultaneous margin is 30.67%
and gross notional is 1.53 times account equity. HYPE and SP500 use 7% margin
at fixed 5x leverage. This increases economically useful exposure without
changing their signal or exit logic.

This remains a marginal-quantile stress, not a joint probability or loss
ceiling. Ten consecutive modeled full loss waves would be approximately 14%
before compounding; gaps, correlation, stale stops, or venue failure could be
worse.

## Variable sizing and leverage

Changing leverage alone does not change profit or loss when notional is held
constant; it changes collateral usage and liquidation distance. The growth
control should therefore be a bounded notional/risk multiplier while leverage
remains 5x unless a separate collateral test supports a change.

No current route has a sufficiently validated continuous strength score:

- regime direction accuracy is generally near chance and cannot justify an
  increase tier;
- observer readiness is prerequisite completion, not win probability;
- Hulk score has encouraging but sparse and non-monotonic slices;
- HYPE BBWP, BTC sweep strength, and SP500 imbalance were not frozen alongside
  enough compatible outcomes to calibrate size.

The all-time live entry challengers also reject a pooled sizing score. Provider
readiness is effectively constant: 58 of 60 closed lifecycles recorded 1.0 and
the other two recorded 0.6667. Structure and component scores are materially
non-monotonic by route. For example, the higher-score Hulk/SOL slice lost while
the lower-score slice contained the winner; HYPE's higher-structure subset was
more negative than its excluded subset. These mixed-profile observations are
descriptive rather than v45 evidence, but they directly falsify using the
existing pooled readiness or regime score to increase live risk.

Accordingly v45 records variable tiers as telemetry only. A future executable
policy can start with bounded 0.75x, 1.00x, and 1.25x notional tiers only after
the frozen route-native score demonstrates positive after-friction expectancy
and largest-winner robustness out of sample. Regime may reduce size if a
forward test supports that use; it must not increase size under the current
accuracy evidence.

The first route-native score candidates are deliberately narrow and remain
hypotheses:

- Hulk BTC short: the provider's completed-bar expansion strength, structural
  stop distance, and executable spread/depth at the decision boundary;
- BTC liquidity-sweep long: sweep displacement/reclaim strength, distance to
  the fixed 60-bps stop/target, and executable spread/depth;
- HYPE compression: completed compression duration and percentile, breakout
  displacement, and executable spread/depth;
- SP500 HIP-3 breakout: decision-time depth-10 pressure, book freshness,
  spread, and breakout displacement from the completed 15-minute bar.

These inputs must be frozen at decision time. Later regime labels, realized
excursion, exit reason, and the outcome of concurrent trades are labels for
analysis rather than sizing inputs. Trade Oracle and the ML4T workflow support
route-specific features, purged chronological evaluation, and transaction-cost
measurement; they do not establish that any listed feature predicts this
portfolio's returns.

The v45 technical acceptance now verifies the exact route-native feature
contract before accepting a post-start checkpoint. The current observer passes:
8 Hulk fields, 6 BTC-sweep fields, 7 HYPE fields, and 7 SP500 fields reconcile
against every route evaluation. Removing one required field produces a
technical rejection. This check is report-only and authorizes no resizing; it
prevents a future 0.75x/1.00x/1.25x study from silently operating on incomplete
or unjoinable telemetry.

The first exact sizing snapshot reconciles the isolated observer identity,
source run, routed action, and ledger prefix: 189 evaluations across four
frozen routes, zero eligible entries, and therefore zero size-tier candidates.
It grants no authority and selects no tier. This is expected quiet-prefix
evidence, not evidence that the routes are profitable or that 1.25x should be
activated.

For each eligible decision, the research journal should record the actual
fixed-size result beside counterfactual 0.75x, 1.00x, and 1.25x economics using
the same entry, exit, fees, funding, and measured depth. Enabling 1.25x requires
all of the following on a frozen route identity:

1. ordered score bins produce ordered median and total net returns after fees,
   funding, and slippage in purged walk-forward and prospective live data;
2. the 1.25x bin remains positive after removing its largest winner and does
   not merely concentrate correlated portfolio losses;
3. realized size-dependent slippage does not erase the incremental expectancy;
4. a ten-wave stress at the proposed tier remains within the separately stated
   portfolio drawdown budget; and
5. the same rule survives a later untouched window without threshold retuning.

These are authorization criteria for the optional size increase, not hidden
gates on strategy trials. Trials continue and record their outcomes when the
strategy is technically executable. Failure of any criterion leaves the route
at its frozen base size; it does not rewrite or discard the observed trade.

If the portfolio adopts the proposed ten-wave/15% stress budget, the modeled
single-wave budget is 1.5% of equity. The current v45 p99 components imply:

| Counterfactual | Modeled stop wave |
|---|---:|
| Base v45 | 1.3936% |
| HYPE alone at 1.25x | 1.4898% |
| SP500 alone at 1.25x | 1.4687% |
| BTC long alone at 1.25x | 1.5708% |
| BTC short alone at 1.25x | 1.5186% |
| Every slot at 1.25x | 1.7420% |

Under that proposed budget, a blanket 1.25x state is rejected by arithmetic.
Only one of HYPE or SP500 could occupy 1.25x at a time under the current stress
model; BTC would require a lower maximum multiplier, approximately 1.15x under
the conservative long-route component. Existing BTC notional caps are tighter
at $5,000 equity: the long route reaches its $4,500 cap at 1.08x and the short
route reaches its $4,000 cap at 1.20x. This remains a modeled p99 scenario, not
a loss ceiling or probability. The 1.5% budget is a recommendation for explicit
approval, not an implicit runtime gate.

The proposed implementation order is therefore:

1. keep venue leverage fixed at 5x;
2. calculate route base notional from the explicit stop distance and per-trade
   loss budget, capped by current executable depth and portfolio exposure;
3. apply a frozen route-specific 0.75x/1.00x/1.25x notional multiplier only
   after prospective outcomes show monotonic net expectancy in those bins;
4. reduce or suppress the increase tier when path quality, depth, or portfolio
   concentration is incomplete.

This is variable risk sizing, not a claim that leverage itself creates edge.
Changing isolated leverage without changing notional would only alter the
collateral and liquidation buffer; changing it while margin is fixed would
also change notional and liquidation distance at the same time, confounding
the intended experiment.

## Evidence interpretation

- The available frozen cadence references imply roughly 1.28 raw opportunities
  per day before collisions and session effects: about 0.08/day each for the
  two BTC specialists, 0.27/day for HYPE confirmation, and 0.85/day for SP500
  in its 22.36-day common window. These are cross-window descriptive rates,
  not a forward arrival forecast; the v45 observer has emitted no eligible
  signal yet.
- At $5,000, the BTC short's maximum 75-bps structural stop is about $25 gross
  risk and its 3R target about $75 gross reward. The BTC long's fixed 60/60-bps
  stop/target is about $25 each. HYPE and SP500 each carry about $14 gross risk
  at an 80-bps stop, with path-dependent rather than fixed targets. Fees,
  funding, slippage, and gap-through execution reduce or can exceed these
  values.
- BTC short and long each have only one exact forward event. Their per-trade
  payoff can be meaningful, but repeatability and cadence are not established.
- HYPE confirmation produced four trades in fourteen days, but the result turns
  negative after removing its largest winner.
- SP500 supplied most of the historical frequency, but its frozen common-window
  validation route result was positive after modeled stress friction, while its
  development direction results reversed. The new profit-lock audit also rejects
  the exact 25/15/10 giveback rule despite its favorable appearance on the
  current open short.
- A fresh v39 one-blocker scan found no cell with at least three independent
  observations that remained positive after friction and largest-winner
  removal. Relaxing a current gate is therefore unsupported by this prefix.
- The latest v39 BTC onset short closed by an opposite Source long intent after
  about 35 minutes for -$0.065627 net. It never cleared its measured 8.65-bps
  cost hurdle (7.51-bps MFE), while the entry provider reported the completed
  5m breakout side was long and opposed to its structural short. This is direct
  live evidence supporting v45's removal of generic BTC onset authority; it is
  not evidence against the separate v45 BTC short and long specialists.

## Recommendation

Use v45, rather than silently resizing v44, as the next growth-oriented $500
canary candidate after the active run is flat and order-free and a fresh
preflight passes. Do not promote the bankroll to $5,000 solely from sizing
arithmetic; first verify the same v45 fingerprint, route behavior, stops,
fees, funding, and realized slippage in live execution.

Improve economic opportunity in this order:

1. Establish exact after-friction expectancy and cadence for the frozen v45
   routes.
2. Improve entry/exit edge where missed-opportunity evidence is causal and
   repeatable.
3. Add independent assets or mechanisms only when they improve portfolio
   throughput after friction; do not fill ten slots mechanically.
4. Keep the proposed variable tiers report-only until route-native score bins
   have causal, after-friction forward outcomes.

The portfolio already has 61 verified live closed lifecycles. Requiring another
arbitrary 50 trades before changing sizing would ignore that operational
evidence and is not part of this plan. Those 61 closes span older and mixed
strategy/profile revisions, so they validate execution behavior, friction, and
failure modes more strongly than they validate the exact v44 route economics.
The remaining evidence question is route comparability, not a fresh count gate:
each v44 route must be checked against its exact live parameters and its own
eligible, filled, and closed lifecycles. No trade count can prove edge by itself.

## Confidence and falsifiers

Confidence is high on the exact v44/v45 topology, configured sizing, depth
provenance, and deterministic arithmetic. Confidence is low-to-medium on trade
frequency and profitability because exact successor forward evidence is still
sparse. Confidence is low that any current continuous score should increase
live notional.

Update or falsify this assessment when any of the following occurs:

- exact forward cadence materially differs from the descriptive windows;
- median net PnL and net PnL excluding the largest winner become stable and
  positive after complete fees, funding, and slippage;
- realized stop loss exceeds the modeled p99 path;
- independent routes increase completed opportunity without increasing joint
  stop-wave concentration disproportionately; or
- exact forward evidence shows that a currently retained route is persistently
  negative or economically immaterial.

## Evidence

- `configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml`
- `configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml`
- `data/logs/research/bidirectional_cohort/v44_btc_specialist_successor_risk_20260811_v1.json`
- `data/logs/research/bidirectional_cohort/v44_portfolio_friction_stress_20260811_v1.json`
- `data/logs/research/20260811_hulk_short_robust_v3_btc_forward_nominal.json`
- `data/logs/research/bidirectional_cohort/btc_liquidity_sweep_taker_parity_20260811_v2.json`
- `data/logs/research/hype_compression_breakout_challenger_20260811_v4/report.json`
- `data/logs/research/evidence_selected_portfolio_v29_common_window_20260808T080301Z.json`
- `data/runtime/research/v44_candidate_shadow_latest.json`
- `data/runtime/research/v45_candidate_shadow_latest.json`
- `data/runtime/research/v45_variable_sizing_latest.json`
- `data/runtime/bidirectional_cohort/latest_checkpoint.json`
- `data/logs/research/bidirectional_cohort/v45_growth_sizing_stress_20260812_v2.json`
- `data/logs/research/xyz_skhx_development_only_diagnostic_20260812_v5.json`
- `data/logs/research/xyz_skhx_prospective_path_repaired_20260812T0900Z_v2.json`
- `data/logs/research/xyz_skhx_prospective_candle_parity_20260812T0900Z_v9.json`
- `data/logs/research/xyz_skhx_prospective_signal_parity_20260812T0900Z_v9.json`
- `data/runtime/research/skhx_hip3_breakout_shadow_latest.json`
- `docs/research-journal/sp500-breakout-profit-lock-l2-proxy-v1.json`
