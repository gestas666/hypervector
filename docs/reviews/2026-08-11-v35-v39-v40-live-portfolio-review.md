# v35 live evidence, v39 revision, and v40/v41 $5,000 readiness review

## Decision summary

The evidence supports using v39 as the next approximately $500 live revision
after the active v35 backend reaches a flat, order-free boundary. Exact-size
liquidity evidence supports v41 as a better-balanced $5,000 sizing candidate
than equal-weight v40. It does not yet prove that either growth profile is a
profitable portfolio.

The staged revision addresses the two clearest inactive or adverse routes:

- retire Range Onset, which produced no v35 entries and only one losing
  historical lifecycle under incompatible contracts;
- retire HIP3 Swing, including the weak GOLD and SNDK histories;
- remove `xyz:GOLD` from the asset roster;
- replace generic HYPE HT-Breakout with the separately identified compression
  breakout route;
- preserve executable long and short authority for every retained route;
- preserve isolated 5x leverage, 3% margin fractions, one position per asset,
  and ten portfolio slots.

This is a route and observability improvement, not proof of positive future
expectancy. The exact v35 contract has zero closed compatible trades. The next
useful evidence is therefore prospective v39 execution, not another aggregate
claim based on earlier mixed configurations.

## Scope and success criteria

This review reconciles:

1. active v35 process, checkpoint, position, order, and fee telemetry;
2. every archived closed lifecycle and fill in the research database;
3. provider eligibility and missed-opportunity annotations in the current run;
4. canonical regime evidence and current-run regime alignment;
5. the staged v39 approximately $500 profile;
6. the v40 equal-weight and v41 risk-normalized $5,000 sizing scenarios; and
7. TUI/backend identity and transition behavior.

The transition is technically acceptable only when the active ledger and
venue agree, no position or owned order remains, the staged profile identity is
exact, all retained routes are executable, and venue sizing/precision checks
pass. Performance, trade count, model score, and drawdown remain reported
results rather than implicit execution gates, consistent with
`SRS_HV1_NO_GATES`.

## Immutable evidence used

| Evidence | SHA-256 |
|---|---|
| `v35_live_audit_after_sndk_stop_20260811T0542Z.json` | `2adc2e09992cdede830fdf304f16a240ceffc57aa3c320f7f27cb4a949bbe9a3` |
| `v39_current_500_preflight_after_sndk_stop_20260811T0544Z.json` | `d4a693a20333e956af27f4771ba3621f07720cee705980bf0ce0c8a68c628072` |
| `v35_live_prefix_review_20260811T0520Z.json` | `b3cdb9085714d374f4ff4cf800c22df4408a7f10be2d5918e48ff0bc817ead36` |
| `v39_current_500_preflight_20260811T0525Z.json` | `2efaa2fa520d018b0487d3e3bf0abcc662840d21ebe87ac8554f031c26c7eff1` |
| v35 one-hour audit delta | `71952e708190b0d0cecabaae7581c13578e353571f76f72c0a61bb5baf44cfe7` |
| v35 02:43 UTC continuation audit | `90fdf64955dafc9e209434382a5b979ef9be2c0435b9ce3111a4c36c3c80097a` |
| v35 02:08–02:43 UTC audit delta | `6bb67c4680cf1b620e0e68c292eff7b327bbae5506c275bb46cb294f420c22fc` |
| `v35_live_audit_goal_continuation_20260811T0333Z.json` | `805d9a0fdb20c4c052ad7ef76f4de50c722401f152fe5122b1060107449a5b63` |
| `v35_live_audit_goal_continuation_20260811T0410Z.json` | `4070b0ce179f1bbf082195097e1211371d85459abff54a86461931e23ef942c7` |
| `v35_live_audit_delta_20260811T0350Z_20260811T0410Z.json` | `cff427e3777a0429f044cef0808c2168f7cea7ea5f4e68be46401c877cc57fa7` |
| `v39_current_500_preflight_20260811T0355Z.json` | `fb0f330afe810a2d0fe24594028364678c482d068b4e23a178867dda7180cbbf` |
| v40 point-in-time preflight | `bb5f09aee3f9ce885151aa7de23eadfbc7fe99369d82f98121ada144dd01eaea` |
| v40 empirical growth stress | `f9bd89ba16c6bd8c0b2c9f713da3a8cf2534ab2662fbbd30a7e898eb47f48d01` |
| v40 inverse-p99 allocation | `948da657eaa1bc84986f7a5969bb6ccb138c4fbcf242ff5db1936d642ab5c04c` |
| v40 exact-notional repricing | `5fa26b93a9ba8a177a34825faa969be148eb6a0a1649e31d81059d73cbcd61bf` |
| v41 point-in-time preflight | `9723bb07ffe052a072d3487e6d6e6ceafbd76adad723558f9d3f231b35aa8992` |
| v35 config | `4b5b35b2045e5c600a6acd4c7365e9acc771ee6074b18b5e7d30268ba17432cc` |
| v39 config file | `bfb1174151c6a17865477c395d9ae793536eebe68384a2ee8c65f05d3669d64a` |
| v40 config file | `ec8ace746188a3e5350c15c247c5adcfb143be5d4701175497ff0383e5c7fee5` |
| v41 config file | `24cc34fb68c7058fa1cb492460a5de806cc3abae23ae92e77502bea8594670da` |

The runtime parser computes profile fingerprints independently of the raw file
hash. The v39 preflight identifies candidate fingerprint
`8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5`;
the v40 preflight identifies
`9cc30910f7d9b2f6d418213226665d3a4671e292dd2c82cfcad1eb4dbca99679`.
The v41 preflight identifies
`c940b2ef8ec444b880910eacaf600d5927654e280941f8aaf0bec781f1739de7`.

## Active v35 state at review cutoff

The live process is run `bidirectional-live-1786402452315`, profile v35,
fingerprint
`8acc70105f8254dc6a7a3f690cebbaec8b3b81c94547d11b895eb6bbe03a24c4`.
The combined ledger and all nine asset ledgers were advancing, the checkpoint
writer was recovered, and the checkpoint heartbeat was current.

Three positions prevent a profile restart:

| Symbol | Route | Side | Size | Entry | Protection | Target | Liquidation |
|---|---|---:|---:|---:|---|---|---:|
| SOL | Hulk Expansion | short | 0.98 | 75.854 | reduce-only stop 76.423 | reduce-only 74.147 | 88.7727 |
| `xyz:GOLD` | HIP3 Swing CMD | long | 0.0171 | 4362.0 | reduce-only stop, oid 513912102834 | none | 3565.1957 |
| `xyz:SPCX` | HIP3 Swing IDX | long | 0.54 | 137.21 | reduce-only stop, oid 514243552748 | none | 112.5892 |

The latest preflight reconciles all three positions and all four owned orders.
It reports `SOL`, `xyz:GOLD`, and `xyz:SPCX` as transition blockers. SOL has
full stop coverage plus a target. Both HIP3 Swing positions have full stop
coverage and no target; v35 manages their fixed maximum-hold exits.

SNDK protective stop filled at 1254.2 after a 1264.1 long entry, versus its
1254.0 trigger. Gross PnL was -$0.584100, fees $0.012836, funding -$0.001637,
and the reconciled result was -$0.598573 net. The stop removed its owned order,
the ledger became flat, and no fault was emitted. This correctly executed the
frozen v35 contract and is adverse evidence for retired HIP3 Swing.

Both lifecycles have persisted fixed maximum-hold clocks:

- GOLD opened 2026-08-10 16:30 UTC and is due no later than
  2026-08-11 16:30 UTC unless its stop or another authoritative portfolio exit
  closes it first;
- SOL opened 2026-08-11 01:00 UTC and is due no later than
  2026-08-12 01:00 UTC;
- SPCX opened 2026-08-11 04:45 UTC and is due by 2026-08-12 04:45 UTC.

The v35 GOLD execution plan intentionally ignores provider-recipe HA-flip exits.
Fourteen such signals had been observed by 05:19 UTC. Continuing after the first
was +118.16 bps gross at cutoff, after reaching +201.60 bps and giving back
83.44 bps. This provisional path cannot establish an exit policy edge.

No restart, forced close, or order mutation is implied by this review. v39
activation waits for all three positions and every owned order to clear.

### 05:19 UTC immutable prefix

The immutable prefix contains 765 poll cycles, 3,835 post-activation strategy
evaluations, eight eligible decisions, eight intents, three routed actions, and
five withheld intents. Every withheld intent was a duplicate same-direction
entry while that asset was already open. The run has four venue entries and no
closed lifecycle: GOLD was adopted from the prior run; SOL, SNDK, and SPCX were
opened by this run. Faults and regime-routing conflicts remain zero.

At cutoff the four provisional marked lifecycle nets were SOL -$0.172446,
GOLD +$0.595890, SNDK -$0.326680, and SPCX -$0.084495. Their sum is near flat,
but it is neither realized PnL nor exact-v35 edge evidence. The current run's
portfolio equity was down $0.629892 from its first snapshot and had reached four
simultaneous positions, $45.33 maximum margin, and $224.03 maximum notional.

SNDK emitted two HA-flip exits after entry; SPCX emitted one alignment-loss
exit. v35 correctly followed its frozen `provider_recipe_exit_policy=ignore`
contract and retained both positions. Together with GOLD's 14 ignored exits,
the provisional continuation median is -3.18 bps and only GOLD is positive.
This supports retiring HIP3 Swing, but resolved closes are still required to
compare fixed-hold and recipe-exit economics.

Technical coverage is incomplete: HIP3 Breakout has four missing metric values
for SP500 and two for SPCX, involving `imbalance_10` and
`pressure_age_seconds`. The missing-field root cause remains unproven. v39
serializes explicit causal `pressure_status`; prospective rows must establish
whether the new contract removed the defect.

## Data-quality and accounting reconciliation

Research DuckDB contains 47 lifecycle close orders and 51 close fills because
four exits filled in multiple pieces. Across all attributed fills there are 51
entries and 51 exits, with unique fill identities.

Independent accounting reconciles with zero observed arithmetic error:

- gross PnL: +$2.658950;
- fees: -$1.719343;
- funding: +$0.057785;
- net PnL: +$0.997392;
- 23 wins / 24 losses;
- profit factor: 1.10349;
- largest-winner-removed net: -$1.056832;
- maximum closed-equity drawdown: -$4.684876.

The compatibility audit classifies 42 lifecycles as incompatible with exact
v35 and five as unverifiable. It finds zero compatible v35 lifecycles. These
figures are therefore descriptive historical diagnostics, not a v35, v39, or
v40 performance forecast.

## Strategy findings

| Strategy family | Trades | W/L | Net USD | PF | Interpretation |
|---|---:|---:|---:|---:|---|
| Hulk Expansion | 5 | 4/1 | +1.467771 | positive | Retain bidirectionally; sample is small and mixed-contract |
| HIP3 Swing IDX | 3 | 1/2 | +0.305183 | 1.242 | Retire with HIP3 Swing; largest winner dominates |
| ETH Breakout Pullback | 2 | 2/0 | +0.004716 | no losses | Retain; economics are nearly flat and sparse |
| HIP3 Swing CMD | 4 | 1/3 | -0.049990 | below 1 | Retire; Brent winner masks GOLD/SNDK losses |
| Hypervelocity Source Follow | 5 | 3/2 | -0.104597 | 0.695 | Retain as forward evidence route, not proven edge |
| Range Onset | 1 | 0/1 | -0.174380 | 0 | Retire; current v35 also produced no entries |
| generic HT-Breakout | 27 | 13/14 | -0.451311 | below 1 | Retain selected assets; HYPE route is replaced |

Provider-symbol evidence explains the pruning:

- GOLD HIP3 Swing: two losses, -$1.011036;
- SNDK HIP3 Swing: one loss, -$1.093178;
- Brent HIP3 Swing: one win, +$2.054224;
- HYPE generic HT-Breakout: 14 trades, -$0.973612, PF 0.719;
- BTC Hulk: three trades, +$0.233870, PF 3.125;
- SOL Hulk: one trade, +$0.681124;
- HYPE Hulk: one trade, +$0.552777.

The user-required bidirectional contract remains intact. Mixed historical side
results favor long entries, but contract incompatibility and regime imbalance
make a one-sided retirement unjustified:

- long: 33 trades, +$4.116110, PF 1.7105;
- short: 14 trades, -$3.118718, PF 0.1887.

Fresh v39 evidence can update that conclusion if one side repeatedly fails
under the exact same provider and execution contract.

## Exit findings

| Exit family | Trades | W/L | Net USD | Interpretation |
|---|---:|---:|---:|---|
| maximum hold | 20 | 15/5 | +6.232585 | Historically strongest, but mixed-contract |
| manual | 3 | 3/0 | +2.302955 | Operator intervention; not autonomous edge |
| target | 5 | 5/0 | +1.470956 | Positive but sparse |
| opposite intent | 2 | 0/2 | -0.333662 | Continue measuring before changing globally |
| restart stop | 2 | 0/2 | -0.942983 | Operational loss family, not strategy intent |
| protective stop | 15 | 0/15 | -7.732459 | Expected loss realization; entry quality is critical |

The data does not justify removing stops. It instead prioritizes entry-quality
telemetry, prospective route attribution, and preserving exact provider/exit
contracts in every forward lifecycle.

## Regime evidence

The independently verified one-year regime audit remains the strongest detector
evidence:

- RANGE had lower future absolute movement in 48/48 tested slices;
- structural magnitude was positively associated with future movement in
  48/48 slices;
- directional classification was positive in 0/32 pseudo-holdout slices;
- decision-time gap quarantine remained intact.

This supports using the detector as structural/range context, but not treating
its direction as a proven predictive signal. Current v35 regime conflict
telemetry recorded zero conflicts, so it cannot yet distinguish which side of
a conflict should win.

The SOL entry was directionally supported at entry and later degraded to mixed
or transition context. GOLD, SNDK, and SPCX lack canonical regime fields,
which is an explicit observability limitation for the retired HIP3 Swing
routes. No regime conflict was observed, so this run cannot measure whether
regime-aware provider arbitration improves outcomes.

Mixed historical entry-state outcomes are descriptive only:

| Entry state | Trades | Net USD | PF |
|---|---:|---:|---:|
| TREND_UP | 14 | +4.270933 | 11.723 |
| TREND_DOWN | 7 | -2.536597 | 0.0411 |
| RANGE | 14 | +0.599685 | 1.400 |
| BREAKOUT | 4 | -1.467688 | 0.0843 |
| TRANSITION | 1 | -0.124000 | 0 |
| missing | 7 | +0.255000 | 1.076 |

These mixed profiles do not establish a new regime gate. The v39 forward
journal must compare eligible entries, routed actions, withheld reasons,
directional conflicts, and closed outcomes under the same contract.

## Missed-opportunity findings

The current run produced 2,794 provider observations. Deduplication removed
1,218 overlapping provider paths, leaving 1,576 unique directional paths. Using a fixed
13 bps round-trip hurdle, descriptive directional close outcomes were:

| Horizon | Cost-clearing close | Robust MFE |
|---|---:|---:|
| 5m | 13/347 (3.75%) | 5/347 (1.44%) |
| 15m | 14/143 (9.79%) | 10/143 (6.99%) |
| 30m | 16/77 (20.78%) | 13/77 (16.88%) |
| 60m | 11/40 (27.50%) | 12/40 (30.00%) |

These are annotations of every directional provider observation, not simulated
fills. Mean after-hurdle close return remained negative at every horizon. They
suggest that selectivity and holding horizon matter, but do not prove a route
can enter at those prices or retain those outcomes after execution friction.

Retained v39-compatible provider coverage in the v35 prefix was:

| Retained route family | Evaluations | Eligible |
|---|---:|---:|
| Hulk Expansion, four core assets | 56 | 1 SOL short |
| Hypervelocity Source Follow, BTC | 77 | 0 |
| generic Breakout Onset, BTC/ETH/SOL | 1,152 | 0 |
| ETH Breakout Pullback | 384 | 0 |
| HIP3 Breakout, four retained HIP-3 assets | 108 | 0 |

The replacement HYPE Compression route is not part of the v35 prefix. Its
separate later-confirmation replay had four exact-policy trades over roughly
14 days, +255.91 bps and PF 2.41, but fell to -96.19 bps without its largest
winner. That justifies a prospective v39 trial, not an edge claim or an
expectation that HYPE alone will provide high frequency.

Range Onset evaluated all four configured assets 384 times each and produced no
eligible entries. Every evaluation reported `awaiting_hourly_sma_cross`, often
with additional regime blockers. That route is removed in v39 rather than
relaxed into a different, unvalidated strategy.

## Venue friction and HIP-3 fee correction

Historical effective HIP-3 taker fees differ materially by market:

- retained growth-mode SP500/SPCX/SNDK/BRENTOIL: approximately 0.864 bps per
  side;
- GOLD history: approximately 8.64 bps per side.

The live fee telemetry previously projected the generic core account rate for
all HIP-3 assets. The corrected preflight/telemetry contract now carries exact
HIP-3 metadata and reports 0.864 bps when growth mode is explicitly resolved.
An unresolved HIP-3 fee state remains unresolved instead of receiving a fake
generic value. The correction applies on the next backend start; it does not
mutate the running v35 process.

The current core preflight uses 4.5 bps taker fees. The observed SOL entry paid
approximately 4.3199 bps after referral, with +4.4803 bps entry slippage and a
1.137 second acknowledgement. This single fill is useful friction evidence but
not a stable distribution.

## v39 approximately $500 sizing

The refreshed point-in-time v39 preflight used actual equity near $504.70 and
resolved all eight retained assets above minimum lot:

- seven providers expand to 14 provider-symbol routes and 28 executable
  long/short scopes;
- BTC and ETH: $5 margin, $25 notional each;
- SOL, HYPE, SP500, SPCX, SNDK, and BRENTOIL: $15 margin, $75 notional each;
- isolated 5x leverage, $100 all-eight planned margin, and $500 all-eight
  planned notional at the captured account;
- 19.81% realized all-eight margin under the two $25 caps versus the uncapped
  24% eight-by-3% configured ceiling;
- ten total slots, leaving two unused for future separately qualified assets.

Sizing is technically ready. Profile transition is not ready because SOL,
GOLD, and SPCX remain open with four owned orders.

## v40 $5,000 sizing

The report-only v40 scenario uses the same eight assets and provider roster as
v39. Each occupied asset uses:

- $5,000 reference equity × 3% = $150 isolated margin;
- $150 × 5 leverage = $750 notional;
- 24% simultaneous margin if all eight current assets are occupied;
- 30% if ten future slots are occupied.

All eight point-in-time books fully covered a $750 order. Estimated visible
one-way price impact in bps was:

| Asset | Buy | Sell |
|---|---:|---:|
| BTC | 0.0781 | 0.0781 |
| ETH | 0.2665 | 0.2665 |
| SOL | 0.0659 | 0.0659 |
| HYPE | 0.0906 | 0.0906 |
| SP500 | 0.0898 | 0.0644 |
| SPCX | 0.3648 | 0.3648 |
| SNDK | 0.3981 | 0.3981 |
| BRENTOIL | 0.0576 | 0.0576 |

The outer asset envelope places an 80 bps stop on every slot; individual
provider contracts may tighten that distance. At exactly $750 notional, an
80 bps move is $6 per position, or $48 across the eight configured assets
(0.96% of $5,000) before fees, funding, and execution error. Point-in-time
round-trip taker fees add approximately $3.22 if all four core and all four
growth-mode HIP-3 assets enter and exit once. The captured visible-depth costs
add roughly $0.21 under the simplifying assumption that exit depth matches
entry depth.

That approximately $51.43 or 1.03% portfolio scenario is not a hard maximum.
A stop-market order can fill beyond its trigger during a gap, book withdrawal,
latency spike, or liquidation cascade; funding and repeated entries can also
increase loss. It is a reference sensitivity for the frozen point-in-time
books, not a loss guarantee.

The immutable growth stress report adds current official funding, exact fee
schedules, 240 recent core-asset book samples, and historical HIP-3 liquidity
quantiles:

- configured eight-asset p50 stop wave: $54.88 (1.10% of equity);
- configured eight-asset p90 stop wave: $55.85 (1.12%);
- configured eight-asset p99 stop wave: $58.82 (1.18%);
- hypothetical ten-slot p90 wave: $71.83 (1.44%);
- three repeated ten-slot p90 waves: $215.49 (4.31%);
- five repeated ten-slot p90 waves: $359.15 (7.18%).

The two unused slots are synthetic in the ten-slot sensitivity and repeat the
worst observed asset at each quantile; they do not represent qualified future
markets. The report uses v35 market, fee, and funding evidence because v39 is
not active yet. It does not use v35 trade PnL as v40 expectancy evidence.

This proves point-in-time lot/depth feasibility only. It does not measure queue
loss, cancellation before IOC arrival, latency tails, or future liquidity. A
fresh preflight against the funded $5,000 account and current books is required
at the actual transition boundary.

## v41 exact-repriced risk normalization

Equal 3% margin does not imply equal modeled loss. Under the frozen v40 p99
stress, SNDK loses approximately $9.01 per stopped slot while SP500 loses
approximately $6.34, a 1.42x largest-to-smallest ratio. The report-only
inverse-p99 challenger preserves the same 24% eight-asset margin, $1,200 total
margin, $6,000 notional, 5x leverage, provider roster, and long/short authority.

Its exact-repriced candidate sizing is:

| Asset | Margin % | Notional USD | Repriced p99 loss USD |
|---|---:|---:|---:|
| BTC | 3.1332% | 783.31 | 7.2651 |
| ETH | 3.2129% | 803.21 | 7.2650 |
| SOL | 3.1042% | 776.05 | 7.2652 |
| HYPE | 3.0969% | 774.21 | 7.2660 |
| SP500 | 3.4401% | 860.02 | 7.2665 |
| SPCX | 3.0068% | 751.70 | 7.2650 |
| SNDK | 2.4190% | 604.76 | 7.1745 |
| BRENTOIL | 2.5869% | 646.73 | 7.2565 |

The four core assets reproduce the original 240-snapshot source windows before
repricing. The four HIP-3 assets use immutable exact-notional profiles rebuilt
from `data/research/hip3_market.duckdb`. Minimum visible-depth completion is
99.9977%. After exact repricing:

- p50 eight-asset stop wave: $54.70 versus $54.88 for v40;
- p90: $55.53 versus $55.85;
- p99: $58.02 versus $58.82;
- p99 per-asset largest/minimum loss ratio: 1.013x versus 1.422x.

This is a modest $0.79 p99-wave reduction, not a profit forecast. Its stronger
result is risk balance without lowering total exposure. The candidate remains
subject to changing books, empirical-quantile tails, correlated signals, and
strategy expectancy. A fresh funded-account preflight is still required.

## v41 connected-provider concentration

The immutable report
`v41_provider_family_concentration_20260811T0535Z_v1.json` (SHA-256
`9f62d9555e66cf4ea0f87a8615947e9e6a9356322613e7b8ad372fa116dbb765`)
binds the exact v41 profile and exact-repriced allocation. It finds three
connected provider clusters:

| Connected scope | Repriced p99 loss | Stop-wave share |
|---|---:|---:|
| BTC, ETH, HYPE, SOL | $29.0614 | 50.0853% |
| BRENTOIL, SNDK | $14.4309 | 24.8707% |
| SP500, SPCX | $14.5315 | 25.0440% |

Therefore v41 equalizes modeled per-asset p99 losses but does not control joint-loss probability.
Initial weights remain venue-risk-only: zero exact
v41 closes make expectancy-weighted sizing an overfit rather than measured
portfolio improvement. Trade Oracle independently supported that distinction;
its proposed 33% co-trigger reduction and 10% family cap were unsourced custom
thresholds and were not adopted. Compatible v39/v41 co-trigger evidence must
update the cluster model before any separate family-weighted profile is built.

## Recommended sequence

1. Keep v35 and its checkpoint writer running while any position is open.
2. Allow the existing provider/venue exit contracts to close all three positions;
   do not restart between open positions.
3. Confirm the venue and every v35 ledger are flat with zero owned orders.
4. Regenerate the v39 preflight and activate v39 with explicit live-risk flags.
5. Verify all eight ledgers, 14 provider-symbol routes, 28 directional scopes,
   fee metadata, regime telemetry,
   stops, funding, position limits, checkpoint identity, and TUI rendering.
6. Review every compatible v39 close plus missed eligible and withheld entries.
7. Use v41, not equal-weight v40, as the current $5,000 sizing candidate;
   regenerate its preflight from the real funded account and run the same
   reconciliation at a flat boundary before any separate live authorization.

## Confidence, risks, and falsifiers

| Claim | Confidence | What would update or falsify it |
|---|---|---|
| v39 parses to the intended roster and risk contract | High | Parser/test output differs from the documented 8 assets, 7 providers, 14 routes, 28 directional scopes, 5x/3%, or executable authority |
| v39 is a cleaner forward experiment than v35 | Medium-high | Retired routes show reproducible compatible edge, or replacement routes malfunction prospectively |
| HIP-3 decision pressure is poll-phase invariant in v39 | Medium-high pending live rows | A later poll changes the selected pre-close receipt, pressure age, `pressure_status`, or decision metrics for the same completed bar |
| v41 is technically sizeable at $5,000 | High for the captured books | Fresh books, venue precision, actual equity, or margin reconciliation fail at transition |
| v41 balances modeled p99 slot loss better than v40 | High for frozen evidence | Exact-notional rebuild or allocation arithmetic no longer reproduces the 1.013x concentration ratio |
| v41 is economically profitable | Low/unproven | Requires compatible prospective closes with repeatable net edge after fees, funding, slippage, and largest-winner sensitivity |
| regime range/structure telemetry is useful | High for structural diagnostics | New point-in-time audits break gap quarantine or reverse the 48/48 structural relationships |
| regime direction should control entries | Low | Requires prospective directional lift; current one-year pseudo-holdout was 0/32 positive |

Operational failure modes remain checkpoint writer loss, ledger/runtime identity
drift, unprotected positions, HIP-3 fee metadata loss, stale books, route
collisions, and TUI projection lag. Each should remain directly observable and
fail closed where it can affect execution.

The open-position transition contract is falsified if any fixed deadline
passes without a close event, if the backend stops managing the timer, or if a
position loses reduce-only stop coverage. Any such event requires immediate
ledger/venue reconciliation before a profile transition.
