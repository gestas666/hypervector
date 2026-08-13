# v39 Forward Trial and v42 $5K Successor Plan

## Decision

Keep the exact v39 profile running at the current canary scale. Do not mutate its
entry, exit, route, or sizing contract while the correlated open lifecycles
remain unresolved. Prepare v42 as a separate successor identity rather than
editing v39 or treating v41 technical readiness as proof of route expectancy.

Confidence is high for the separation of technical and economic acceptance.
Confidence is low-to-medium for individual route edge because exact v39 has
five closes, one win, four losses, and three open lifecycles. The eight raw
lifecycles form only two overlapping market episodes and only one episode is
complete.

This plan is falsified by a technical incident in v39, a source-identity
mismatch, or new exact route outcomes that materially contradict the route
dispositions below.

## Evidence boundary

- Exact v39 route review:
  `data/logs/research/bidirectional_cohort/v39_route_portfolio_review_20260811T1830Z_v1.json`
  (`66b7c8976f1332539075d978c69da35459fde9553c43c5cf670acc508e9c687c`)
- Five-close exact v39 route review:
  `data/logs/research/bidirectional_cohort/v39_route_portfolio_review_20260811T2258Z_v3.json`
  (`42e00d753be02e40c92a135ecd866cd49e08151d028065b85efdefce34e42444`)
- v41 technical sizing assessment:
  `data/logs/research/bidirectional_cohort/v41_successor_readiness_20260811T1730Z_v1.json`
  (`8f420e742156e442494708cb16c1aeaea3832d0cc1c11166e2418cdad8618880`)
- HYPE direction-alignment replay:
  `data/logs/research/hype_breakout_entry_alignment_hl365d_v2_20260806.json`
  (`c03cd58711d6439f4ffa9b43362a58f6da8fe5ab47eb4bdb1d71167e9da7b472`)
- Latest direction-alignment decision journal:
  `docs/research-journal/hype-breakout-direction-alignment-v5.json`
  (`e6abf5e0fc9a19c7d78f6641de1989ca407a0f0b50bc48b30351463f932e305e`)
- Immutable live exit and profit-lock baseline:
  `data/logs/research/bidirectional_cohort/v39_live_audit_open_exit_baseline_20260811T1804Z.json`
  (`37e7e6ba186d776841142baf8cb507c7027475a63cfc0e1b6a08ef2d8d2eadd5`)
- Exact two-close v39 prefix audit:
  `data/logs/research/bidirectional_cohort/v39_live_prefix_audit_20260811T192046Z.json`
  (`b65b4b640c2670dcaccef3a3ac417bfeb16eaec393cf0b4baf0b2e0cf4011fdc`)
- Exact three-close v39 prefix audit:
  `data/logs/research/bidirectional_cohort/v39_live_prefix_audit_20260811T195200Z.json`
  (`5f99bf8a466eaf5592b91d07e38291ea4ff097798a8e1f634a2531c856f4edc4`)
- Corrected left-censored regime-onset evidence:
  `data/logs/research/bidirectional_cohort/v39_regime_forward_accuracy_20260811T190809Z_v2.json`
  (`7435316ea763cbeec27b8dfb34d2c9a8414745211988f397ac614e4ec7b938b3`)
- Expanded 1,652-observation regime-onset evidence:
  `data/logs/research/bidirectional_cohort/v39_regime_forward_accuracy_20260811T200500Z_v3.json`
  (`c76e8e7b33e4d5f6e6279a1731a34ef48a5d0035fa673b1cbe7bad710a45a14c`)
- Expanded 2,304-observation regime-onset evidence:
  `data/logs/research/bidirectional_cohort/v39_regime_forward_accuracy_20260811T2249Z_v4.json`
  (`af532a9ba1a3fe26ff765b33b43ea772c52ddb7750b498f3e1940d8d73a7f1cc`)
- Completed-bar dual-MTF profit-reversal challenger:
  `data/logs/research/bidirectional_cohort/v39_dual_mtf_profit_reversal_exit_20260811T204800Z_v3.json`
  (`e857d58a0d7e930b08442cf258864512f6dab8ca4197783d45fd8af926d2b417`)
- Exact SKHX prospective venue-path audit:
  `data/logs/research/xyz_skhx_prospective_path_audit_20260811T212321Z_v5.json`
  (`f6f8406b6fb157181d59b3db1feab4feeb89b992e8b8b1eebb4600477523f23c`)
- Exact MU prospective venue-path audit:
  `data/logs/research/xyz_mu_prospective_path_audit_20260811T212321Z_v5.json`
  (`7cc532a8e6ca52ef156ea75e58db5e30530911b8b5a1136b98416b4d6873efed`)
- Exact v39 HT side-authority decision artifact:
  `data/logs/research/bidirectional_cohort/v39_ht_side_authority_challenger_20260811T213345Z_v2.json`
  (`e54775deb4f1d7ade837998dc95e8772914b0823e4d1d5e7bb2d3d06ac7aa4a6`)
- BTC HT agree-only and profit-lock replay:
  `data/logs/research/btc_ht_agree_only_profit_lock_hl365d_v2_20260811.json`
  (`745e90363fca0014f789310ad4dcb35453b8490edec397cdb9cd73daf10738dd`)
- ETH HT agree-only and profit-lock replay:
  `data/logs/research/eth_ht_agree_only_profit_lock_hl365d_v2_20260811.json`
  (`fdfc34497d488cbe2e8f184925593c74956e4734eb1c4f26bde7072d08f13508`)
- SOL HT agree-only and profit-lock replay:
  `data/logs/research/sol_ht_agree_only_profit_lock_hl365d_v2_20260811.json`
  (`d060839187479b4c965149ced2bade188db2c198b22a70a959fff2bf808b50d5`)
- BTC HT reset-aware profit-lock replay:
  `data/logs/research/btc_ht_reset_profit_lock_hl365d_v3_20260811.json`
  (`dfa2091e0633bb50e975249c102711c5f0103f391af0995c72d03ec41f74f41d`)
- ETH HT reset-aware profit-lock replay:
  `data/logs/research/eth_ht_reset_profit_lock_hl365d_v3_20260811.json`
  (`896c64261c126cfbd1f96553c2d9264bd1793450c0699d6d0eb0ae215342cae5`)
- SOL HT reset-aware profit-lock replay:
  `data/logs/research/sol_ht_reset_profit_lock_hl365d_v3_20260811.json`
  (`cc3cc7f71e795802a56654cb5c1cc6299ed51c9037dbd272a97011da8a0e0cf5`)
- BTC HT purged return-ranker replay:
  `data/logs/research/btc_ht_onset_return_ranker_hl365d_v1_20260811.json`
  (`dd594adb2c2570b253f975055d8feaacec59fa0371261bfe53515e40d42b01bf`)
- ETH HT purged return-ranker replay:
  `data/logs/research/eth_ht_onset_return_ranker_hl365d_v1_20260811.json`
  (`ff24224bf75ad8131bb96763a09e5b912a491813b635709efc5483f7d7d0622b`)
- SOL HT purged return-ranker replay:
  `data/logs/research/sol_ht_onset_return_ranker_hl365d_v1_20260811.json`
  (`58e43a226bad5df13df787429907dcf161d0c43b39bfecd9274bdf2278b64a07`)
- Frozen HYPE Compression exit-policy replay:
  `data/logs/research/hype_compression_breakout_challenger_20260811_v4/report.json`
  (`88bb77f5053f0df8741e9e441b328d461761927f42e1037611747667ff8de044`)
- Inactive focused-growth v42 design:
  `data/logs/research/bidirectional_cohort/v42_focused_growth_5000_design_20260811T1828Z_v1.json`
  (`608f8f5e41c5643786d1b2a115c70baa133e85587905d2407e42d9a6a3238cc4`)
- Inactive v42 config:
  `configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml`
  (`825cbfc1be69ff4dd38528ef7939f7216be3092999bb93400c26b7acd30e78c9`)
- Point-in-time v42 public-wallet sizing preflight:
  `data/logs/research/bidirectional_cohort/v42_growth_5000_preflight_20260811T2245Z.json`
  (`fc1531f58196e70761d367f2d0be15fb8979162c5c54d54719fd56a293809aa1`)

The v39 prefix is an exact current-profile snapshot, not a completed forward
window. Mixed-profile history is descriptive and cannot establish v42 edge.

## Current v39 experiment

The current process contains 14 provider-symbol routes and 28 directional
scopes. At the five-close prefix it had 17 eligible evaluations, completed
SNDK, SPCX, ETH, and SOL protective-stop losses, and one BTC maximum-hold win.
ETH, SOL, and SP500 remained protected open positions. Realized current-run net
PnL was -$2.212873, with one win, four losses, and profit factor 0.00765. The
eight raw lifecycles form two timestamp-overlap clusters: one completed SNDK
episode and one ongoing seven-lifecycle short episode. Open PnL remains
provisional and is excluded from route dispositions.

Success criteria for this run are deliberately separated:

1. Technical correctness: every intent and non-action is journaled; fills,
   stops, fees, funding, deadlines, recovery, and TUI identity reconcile.
2. Economic evidence: route returns are reported after realized friction,
   separately by side, regime, and exit reason, including largest-winner
   removal and missed/avoided paths.

Technical failure may fail closed immediately. Economic performance remains a
reported trial result and is not an implicit live abort gate.

## Route disposition for successor research

| Provider-symbol route | Current evidence | v42 disposition before new closes |
|---|---|---|
| HYPE Compression / HYPE | Development was weakly positive but fold-unstable; no exact close | Highest-value exact forward research track; no automatic scale-up |
| HIP3 Pressure / SP500 | Approximate nominal and stress results positive; one open exact lifecycle | Retain for exact fill, stop, and co-trigger evidence |
| Hulk / BTC | Development and validation positive, pseudo-holdout negative | Retain as contradictory research, not proven edge |
| Hulk / SOL | Validation failed materially | Retain only to resolve transfer uncertainty at canary scale |
| HT Onset / BTC | Exact 365-day v39-shape control was -6,487.62 bps in development with all five folds negative, but +693.09 bps/PF 1.15 in the later block; its first exact v39 close won only $0.0171 net | Exclude unchanged from the $5K successor; retain the lifecycle as diagnostic evidence |
| ETH Pullback / ETH | Pooled and side/relation arms failed robust costs | Do not scale without a new causal mechanism identity |
| HT Onset / ETH | V39-shape control was -7,246.85 bps development and -2,031.28 bps later; agree-only also lost and every profit lock was development-negative | Exclude unchanged from the $5K successor |
| HT Onset / SOL | V39-shape control was -9,281.43 bps development and -2,973.10 bps later; agree-only and every profit lock failed the later block | Exclude unchanged from the $5K successor |
| Source Follow / BTC | Exact deployed-shape replay negative, PF below one | Exclude from the $5K successor unchanged |
| Hulk / ETH | Both sides and chronological segments negative | Exclude unchanged |
| Hulk / HYPE | Both sides and chronological segments negative | Exclude unchanged |
| HIP3 Pressure / SPCX | Exact short reached +100.14 bps MFE, surrendered the move, and stopped at -80.41 bps gross; all predeclared profit-lock shadows improved this one lifecycle | Do not scale unchanged; retain a separately frozen route-specific exit challenger, not a universal trail |
| HIP3 Pressure / SNDK | Nominal result reversed under stress; first exact v39 close lost | Do not scale unchanged |
| HIP3 Pressure / BRENTOIL | Nominal and stress results negative | Do not scale unchanged |

These dispositions are research recommendations, not execution gates. v39
continues under the user-authorized ungated trial contract.

## Prospective HIP-3 evidence

The isolated public-data recorders for `xyz:SKHX` and `xyz:MU` are running
outside the execution factories. The first exact content-bound audits each
cover 20 completed 15-minute bars. SKHX has 20/20 mark paths and 20/20 L2 paths
within the frozen cadence limits; its maximum observed mark gap is 2,343 ms and
maximum L2 gap is 6,987 ms. MU also has 20/20 on both paths, with maxima of
3,262 ms and 5,601 ms. Public trades exist in all 20 bars for both symbols.

Each recorder disclosed one clean WebSocket reconnect. The surrounding exact
observations kept the discontinuity within the stated channel cadence, so it
is reported but does not create an unresolved bar. The audit preserves the
different timestamp semantics: mark coverage uses local receipt cadence
because `activeAssetCtx` has no exchange timestamp; L2 uses declared exchange
timestamp bounds. Exact event-content and generator hashes are frozen in each
artifact.

This closes only the short prospective mark/L2 coverage question. It does not
repair historical gaps, establish profitability, or resolve the remaining
public-trade OHLC versus live `candleSnapshot` row-parity blocker. SKHX remains
a research challenger to SNDK for one semiconductor-cluster slot; MU remains a
separate challenger. Neither is added to v42 merely to fill unused capacity.

A later fixed-config development sensitivity resolves the materiality question
on the common retained-candle tail without claiming full historical row parity.
Across 2,476 contiguous 15-minute bars, both sources produced the same 24 entry
signals and 22 completed lifecycles. Only the 2026-06-30 13:45Z EMA exit flags
disagreed, changing net PnL by about -$0.0025 in both scenarios. The immutable
evidence is
`data/logs/research/xyz_skhx_signal_source_sensitivity_20260812_v2.json`.
SKHX remains excluded because OOS was not evaluated, historical risk paths are
unresolved, and common-tail stress net becomes negative after removing the
largest winner.

## Exit-policy finding

Do not add a universal trailing stop. Across 50 mixed-contract live lifecycles,
the three predeclared universal trails reduced average performance and produced
estimated normalized profit factors below one. Regime-conditioned trails also
underperformed their actual exits on average.

Provider-specific exits remain report-only challengers. An adjustment requires:

- a frozen causal rule and exact provider identity;
- point-in-time completed-bar inputs;
- actual-versus-challenger economics after fees, funding, and exit slippage;
- chronological development and later-window evaluation;
- largest-winner and side-specific robustness;
- disclosure of every tested policy to control multiple-testing bias.

No fixed trade-count threshold grants authority. Sparse results retain wide
uncertainty rather than being success-shaped or rejected solely by count.

The exact 365-day HT transfer surface rejects applying A25/A40/A60 to the
unchanged BTC, ETH, or SOL onset routes. Every BTC and SOL lock was worse than
control in both development and the later 60-day block. ETH A60 improved the
later block by 518.05 bps but still lost 1,513.23 bps, while its development
result deteriorated from -7,246.85 to -16,413.02 bps. The policies generated
more completed lifecycles by releasing occupancy sooner, so the apparent
four-close prefix improvement does not generalize after turnover and costs.
No HT profit lock is retained for v42 from this surface.

A second frozen replay tested the narrower hypothesis that the fixed locks
failed only because early exits exposed repeated same-episode onsets. Each
reset-aware arm blocks same-side re-entry after a profit-protection exit until
the completed structural direction changes. This removed substantial turnover
and improved drawdown on the losing ETH/SOL controls, but it did not recover an
after-cost edge. In the later block, the best BTC reset arm was -41.27 bps
versus +693.09 bps control; the best ETH reset arm was -573.81 bps versus
-2,031.28 bps; and the best SOL reset arm was -537.57 bps versus -2,973.10
bps. Every reset arm remained negative after removing its largest winner. In
development, every reset arm was also negative and BTC/ETH had five negative
chronological folds for every setting. The reset contract is therefore useful
as a churn-control finding but is not a replacement strategy or a v42 route.

A purged walk-forward return-ranking screen then tested the smallest ML role:
ranking unchanged HT entries without choosing direction, changing size, or
installing a model. Ridge and shallow deterministic LightGBM used only
signal-time features, five chronological folds, a 24-hour outcome embargo, and
the same realized HT lifecycle labels. No model passed the predeclared
development acceptance on BTC, ETH, or SOL. The already-opened later block did
contain descriptive pockets: BTC LightGBM's top quintile produced +623.67 bps
and +224.34 bps excluding its largest winner; ETH Ridge produced +918.83 bps
and +295.42 bps excluding its largest winner. Their later rank correlations
were only 0.010 and 0.075, respectively, and neither had development support.
SOL's best later arm remained negative. Selecting BTC or ETH from these later
results would be post-holdout model selection, so all three remain annotation
only and no model is installed in v42.

The HYPE Compression exit study holds the frozen
`compression_5m50_1m40_pullback` entry stream fixed and tests only the unchanged
8h-to-24h controller against the three previously declared reset-aware profit
locks. Every lock failed development acceptance. The selected A40 diagnostic
lost 1,542.74 bps, had only two of five positive folds, produced PF 0.554, and
remained negative without its largest winner. In the already-opened later
window it made 31.64 bps across two closes and stayed positive without its
largest winner, but it underperformed the unchanged control by 224.27 bps.
The immutable disposition is therefore `retain_control_exit`; v42 must not
success-shape the sparse later slice into a profit-lock promotion.

The exact SPCX, ETH, SOL, and BTC lifecycles raise specific, prospective
hypotheses rather than proving an exit edge. SPCX reached +100.14 bps MFE, ETH
reached +36.03 bps, and SOL reached +122.33 bps before their protective stops.
BTC reached +83.17 bps MFE but captured only 17.9% of gross MFE and gave back
68.26 bps before its eight-hour exit; it realized only +$0.0171 net. All three
predeclared BTC profit locks would have improved this single lifecycle by
$0.0352 to $0.0696, but the frozen 365-day and reset-aware HT replays rejected
those same mechanisms. The route is excluded from v42 rather than retuned from
one live win. SOL cleared its measured 8.33 bps cost hurdle, then surrendered
204.94 bps from peak to exit and realized -$0.6800 net. The BTC, SPCX, ETH, and
SOL lifecycles belong to the same ongoing market episode, so they are not
independent confirmations. On the four-close
prefix, the predeclared profit-lock shadows improve estimated net PnL from
-$2.2299 to -$0.5247, -$0.0973, and -$0.2445, respectively, but every policy
remains net negative and the estimates exclude a submitted private exit order.
The falsifier for a route-specific profit lock is later point-in-time evidence
showing lower after-cost net return, profit factor, or largest-winner-excluded
performance than the unchanged provider exit.

The dual-MTF profit-reversal challenger adds three predeclared completed-bar
persistence cells: one, three, and five consecutive 1m/5m states opposing the
position after its estimated cost hurdle had already been cleared. Its first
artifact was rejected because it assigned `BREAKOUT` direction from the shared
structural side rather than the exact timeframe EMA-gap sign. The corrected v3
artifact uses the 1m and 5m EMA-gap signs and retains the failed specification
as negative provenance.

Only ETH and SOL had causal canonical inputs in the four-close v39 prefix;
SNDK and SPCX were withheld rather than backfilled. The one- and three-bar
cells triggered on SOL and improved its estimated exit by $0.2930 and $0.2068,
respectively, but the two eligible lifecycles still lost $0.6033 and $0.6896.
The five-bar cell was $0.0004 worse than the actual exits. Across 42 eligible
mixed-profile lifecycles, the three-bar cell was nominally +$0.1087 with profit
factor 1.0203, but fell to -$1.4741 after removing its largest winner; every
cell was negative under that sensitivity. Longs remained profitable while
every cell slightly reduced or barely changed long-side net, and shorts
improved but remained deeply negative. None is selected or promoted. The
unchanged v39 exit contract remains the forward control while later closes are
scored against all three frozen cells.

## HT side-selection challenger

Freeze three report-only v42 variants at every completed five-minute breakout
onset. Variant A is the current structural-SMA side, variant B uses the detected
breakout side, and variant C takes the setup only when those two sides agree.
The variants must share the same decision timestamp, executable quote, sizing,
stop/hold contract, fees, funding, and exit-friction model. A skipped C setup is
recorded as a no-trade outcome rather than silently removed.

Current exact-v39 evidence is descriptive. The first ETH and SOL shorts aligned
with their breakout and structural sides, then stopped after reaching +36.03
bps and +122.33 bps MFE. The aligned BTC short closed profitably at its
eight-hour fallback after substantial giveback. The post-prefix ETH short is an
opposed structural fade, while SOL and SP500 remain protected opens. These
lifecycles remain in one overlapping episode and cannot establish
side-selection superiority.

The frozen decision artifact now enumerates all eight exact current-run HT
eligible onsets before any later counterfactual scoring: six are aligned and
two are opposed. Structural-side and breakout-side variants each retain eight
decision events; agree-only retains six and records the two opposed events as
explicit no-trades. The artifact makes no fill or performance claim. Later
replay must preserve the same quote, stop, hold, fees, funding, and exit model
for all three arms, including occupied-position outcomes.

The larger historical replay now falsifies agreement as a general repair.
Agree-only censored 637/1,433 BTC, 691/1,546 ETH, and 720/1,637 SOL onsets. It
reduced development losses largely by trading less, but it underperformed the
unchanged structural control in every later 60-day block: -1,680.11 bps on
BTC, -296.51 bps on ETH, and -59.51 bps on SOL. BTC agree-only also converted
a +693.09 bps/PF 1.15 control block into -987.03 bps/PF 0.73. Agreement is
therefore rejected rather than promoted from the eight-event live prefix.

Mixed-profile history is a mechanism prior, not exact-v39 expectancy. BTC has
four opposed closes with approximately 0.295 USD profit factor; ETH has two
aligned losses and three opposed closes near 0.924; SOL has four aligned closes
near 3.10 and one opposed loss. The cross-asset contradiction is itself the
reason to keep asset, side, and episode attribution separate.

Evaluate variants chronologically using transitive timestamp-overlap episodes,
not raw trade count. Report net PnL, median return, profit factor, drawdown,
fees, funding, slippage, side composition, cadence, and net PnL excluding the
largest winner. No fixed episode count or performance threshold grants live
authority. A successor recommendation changes only when frozen later evidence
shows a route-specific after-cost difference that is not explained by one
winner, one side, one asset, or overlapping copies of the same market move.

## Regime role

Canonical regime telemetry remains descriptive in v39. It is evaluated for:

- entry alignment and opposition persistence;
- range/compression avoidance;
- exit-context drift and timer-extension diagnostics;
- regime-sliced route performance and missed opportunities.

The refreshed live prefix contains 2,304 unique point-in-time observations and
16 explicitly left-censored initial state series. At 60 minutes, primary
`TREND_DOWN` onsets remain directionally correct on 10 of 12 observations. At
15 minutes the same onset set is only 6 of 12. Four newly observed primary
`TREND_UP` onsets were 0/4 correct at both 15 and 30 minutes; only three had a
resolved 60-minute path and two were correct. Primary `RANGE` has seven
15-minute onsets and only four stayed within 25 bps. These results remain
small, overlapping, and horizon-sensitive. They support conflict/context
telemetry but do not justify a standalone directional gate, sizing input, or
detector retune.

Do not convert regime state into a binary gate or sizing multiplier until a
frozen causal challenger demonstrates stable after-cost improvement on later
data. This preserves the project charter while still allowing regime evidence
to influence the separately versioned successor.

## $5K sizing contract

The v41 risk-normalized shape is technically coherent under its stated model:

- $5,000 target equity;
- isolated margin and 5x position leverage;
- 24% total initial margin and 1.2x maximum gross account exposure;
- eight configured assets, one position per asset, and two unused account slots;
- approximately $58 modeled simultaneous p99 stop-wave loss.

The $58 figure is a deterministic visible-depth sensitivity, not a worst-case
loss guarantee. Gap-through stops, latency, correlation spikes, and unavailable
depth can produce larger losses.

If v42 removes routes or assets, unused risk stays unused. It must not be
redistributed automatically merely to reach 24% margin or fill ten slots. Any
new allocation requires a fresh exact-notional venue reprice and a new profile
identity.

The inactive v42 candidate now applies that rule exactly. It contains only BTC
Hulk Expansion, HYPE Compression Pullback, and `xyz:SP500` HIP-3 Breakout
Pressure, with both directions retained for each route. The account cap stays
at ten, but one-position-per-asset limits the candidate to three simultaneous
positions and leaves seven slots unused. It preserves only the corresponding
v41 weights: 9.670175% total initial margin, `$483.51` margin, `$2,417.54`
gross notional, and approximately `0.484x` gross account exposure on `$5,000`.
Its three-asset p99 visible-depth stop-wave sensitivity is `$21.80` or 0.436%
of equity. That sensitivity is not a gap-through or worst-case loss bound.

The candidate is not transition-ready: route edge and profit optimality remain
unproven, v39 has three open lifecycles, and the existing public-wallet v42
preflight correctly rejected transition while positions and orders were open.
No flat/order-free v42 preflight exists. The exact rollout and rollback
boundary is frozen in `docs/runbooks/2026-08-11-v39-v42-transition-contract.md`.

## Required v42 evidence

Before a separately authorized $5K start:

1. Freeze the route set and full search ledger before opening later evidence.
2. Preserve chronological development, validation, and untouched final windows
   for any tuned mechanism; purge overlapping lifecycle labels at boundaries.
3. Reconcile exact venue fees, funding, entry/exit slippage, latency, and stop
   behavior by provider and asset.
4. Report mean, median, profit factor, drawdown, side composition, and net result
   excluding the largest winner.
5. Record effective independent episodes and overlapping/co-triggered positions;
   raw trade count alone is not breadth.
6. Keep technical canary acceptance separate from economic-edge assessment.
7. Run a fresh flat/order-free preflight, prestart backup, poststart checkpoint,
   route matrix, protection audit, and all-screen TUI acceptance.

## Next evidence event

The next decision point is the resolution of the remaining ETH, SOL, and SP500
positions in the ongoing correlated v39 episode.
For each lifecycle, compare the actual exit with the frozen profit-lock,
post-soft-deadline trail, ignored-provider-exit, and regime-opposition
challengers. The SOL close strengthens the profit-surrender mechanism
hypothesis but remains part of that same episode. The ETH short re-entry is a
new protected lifecycle in the episode, not an independent confirmation.
Update the route disposition only from exact reconciled evidence; do not retune
from provisional open PnL.

The authority-none `scripts/v39_dual_mtf_reversal_monitor.py` watcher is bound
to the exact v39 run and profile. Its durable cursor has advanced through the
verified five-close artifact
`v39_dual_mtf_profit_reversal_exit_20260811T225711.310760Z_forward.json` and
checks the checkpoint every 120 seconds. It runs the
three-cell challenger only when the exact current-run close count increases,
validates that the new immutable artifact remains report-only with no selected
policy, and advances its cursor only after publication succeeds. A technical
failure leaves the prior cursor unchanged and cannot alter routes, positions,
orders, stops, sizing, or backend lifecycle state.
