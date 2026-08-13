# v49 Trade-Oracle challenge review

Generated at: 2026-08-12T19:04:19Z  
Notebook: `Trade-Oracle` (`0533df6d-061c-40e8-a74c-14d0b8bb0b63`)  
Authority: advisory and report-only; no execution, sizing, filtering, or promotion effect

## Question scope

The notebook was asked for a falsification-oriented checklist to distinguish an
implementation/configuration defect from an unproven mechanism or a weak edge.
The concrete prompts included the HIP-3 30-second-versus-15-second pressure
freshness mismatch, SOL's 60-versus-80-bps stop mismatch, completed-bar parity,
sparse signals, fallback exits, regime interactions, and largest-winner
dependence before a move from approximately $500 to $5,000.

## Accepted as diagnostic principles

- Freeze entry, exit, and risk rules under exact versioned identities.
- Require completed-bar research/live signal parity and causal timestamps.
- Reconcile actual executable BBO, fee, slippage, and funding evidence rather
  than substituting generic friction.
- Record MAE, MFE, exit reason, and missed eligible or capacity-blocked setups.
- Group overlapping positions when assessing concentration and stop waves.
- Report medians and results after removing the largest winner.
- Treat forward evidence as the principal defense against overfit.

These principles are already represented by the v39 lifecycle audit, v49
observer, prospective HIP-3 parity reports, BBO markout reports, and the v49
strategy-repair disposition.

## Rejected or downgraded claims

- `50` forward trades is not adopted as a hard promotion gate. It was presented
  without source-specific power analysis and conflicts with the project charter's
  ungated-trial requirement. Trade count remains reported evidence.
- A friction-decay ratio threshold of `0.35` is not adopted as universal. The
  relevant comparison is route-specific net expectancy under exact venue costs.
- A universal `1.5%` portfolio stop-wave limit is not adopted. The current v49
  modeled stop wave is reported as a scenario, not a probability or implicit
  rejection gate.
- `100%` equality to a historical candle's opening quote is not a valid fill
  parity definition. Signal parity and executable-quote parity are separate;
  live fills need not equal candle open.
- The notebook's generic `4.5 bps` fee assumption is not used. Current evidence
  binds the effective route fee source explicitly.
- Its recommendation to retire the repaired ETH Range mechanism is not accepted.
  The dual-MTF rule is versioned as a prospective post-loss challenger, not
  represented as untouched out-of-sample proof.
- Missing path evidence is not silently converted into a synthetic loss or fill.
  It remains technically unresolved and is reported separately.

## Current evidence update

At 2026-08-12T19:03:11Z, the v49 observer had 97 evaluation cycles for each
5-minute route, all five provider-symbol mappings present, zero duplicate or
future decisions, zero technical gaps, and zero eligible entries. Near-miss
evidence does not support relaxing filters:

- HYPE's one independent missing-compression case was approximately `-28.49`
  bps at 15 minutes and `-38.69` bps at 60 minutes after estimated friction.
- HYPE's missing-onset cases contain one positive 15-minute independent path
  (`+32.26` bps) that reversed to `-50.12` bps by 60 minutes; this is insufficient
  to remove the onset requirement.
- SOL's three independent hourly-cross near-misses averaged `-13.44` bps at 15
  minutes and `-16.95` bps after removing the largest path.

## Decision

Keep the repaired v49 contracts unchanged while prospective evidence accrues.
Continue measuring exact eligible episodes, missed opportunities, executable
friction, route-specific regime interactions, overlapping risk, and
largest-winner robustness. Do not use this notebook response as an automatic
performance gate or as authority to change the live strategy.

Confidence: high that the accepted items are useful observability and
falsification controls; low that the notebook's numerical thresholds generalize
to this portfolio. This decision would be falsified by source-backed material
showing that one of the rejected thresholds is calibrated to the exact route,
venue, horizon, and loss function, or by repeated prospective near-misses that
remain positive after exact costs and largest-winner removal.

## Exit-policy challenge update

Queried at: 2026-08-13T01:05Z  
Conversation: `2d08c822-c2c0-4ccb-8554-63f92567223c`

The notebook was given the frozen BTC, ETH, SOL, and HYPE exit evidence and
asked to falsify fixed-target, delayed-lock, and native/time/regime-only exit
hypotheses. Its strongest supported criticism was that the current samples are
too sparse to label any exit globally optimal. In particular, one unresolved
SOL giveback path cannot justify changing every Range lifecycle, seven ETH
maximum-hold winners do not establish future invariance, and HYPE's development
return remains dependent on unstable chronological folds.

Accepted additions to the validation contract:

- Compare each challenger against the same frozen entries in an exit-only cell;
  do not change entries and exits simultaneously.
- Separately compare any entry challenger under the unchanged native exit, then
  evaluate the integrated pair only after the two isolated comparisons.
- Report MFE-to-exit giveback distributions, median lifecycle economics,
  direction slices, chronological folds, and results without the largest winner.
- Treat a fixed target as a mean-reversion hypothesis and a delayed lock as a
  right-tail-preservation hypothesis; neither is a generic risk improvement.

The notebook suggested universal thresholds of 50 episodes, 15-bps average
giveback improvement, profit factor 1.15, and return skewness above 1.5. These
numbers are not adopted as implicit gates because the cited material does not
calibrate them to the exact route frequency, overlapping episodes, Hyperliquid
friction, or portfolio loss function. They remain reportable reference values.

Current disposition remains strategy-specific: preserve both BTC targets;
retain native ETH and HYPE exits; keep SOL's 25/40-bps delayed-lock and
long-60/short-native variants report-only until multiple resolved, exact-cost
episodes establish directionally stable improvement. Confidence is high on the
experimental isolation requirement and low-medium on the exit ranking. A
predeclared challenger that improves chronological and largest-winner-removed
net economics without truncating the control's right tail would update it.

## Fresh v39 lifecycle cross-check

Source: `v39_route_portfolio_review_20260813T0135Z_v2.json` and its exact
checkpoint (`66` archived closes; `15` current-run compatible closes).

The current-run native exits produced `-$4.25814`. Applying the three existing
delayed-lock challengers to the same frozen entries would have estimated:

- activation 25 / floor 15 / trail 10: `-$0.05473`, PF `0.9437`;
- activation 40 / floor 15 / trail 20: `-$0.72085`, PF `0.6307`;
- activation 60 / floor 15 / trail 30: `-$0.87711`, PF `0.6680`.

This confirms material profit giveback but does not establish one profitable
universal exit. Route slices diverge sharply: SOL's three retired onset trades
would have changed from `-$1.19586` to `+$1.01044` under the 60/15/30 policy,
while the current open SPCX long is marked near `+$4.43`; those same locks would
have exited it near only `+$0.22` to `+$0.78`. The ETH slice also remains
negative under its best tested lock and its one winner would have been reduced.

The v49 decision therefore remains mixed by design: BTC Hulk and Sweep retain
their explicit targets; ETH and HYPE retain their native/time-based controls;
SOL keeps native execution while the delayed-lock and long-60/short-native
variants remain paired challengers. Confidence is high that a universal lock
would be inappropriate for this observed set, but low-medium on the eventual
route-specific parameters because the decisive slices contain only one to
three lifecycles. This assessment would be updated by multiple resolved v49
episodes showing that a predeclared lock improves median and total after-cost
PnL across chronological blocks without materially truncating large winners.

## Continued forward exit snapshot

Frozen at 2026-08-13T02:10:34Z in
`v49_sol_profit_lock_forward_20260813_v3.json` (SHA-256
`ff67e0725246b8b7662cc314f5d93761272531e92239f6f49f35f589225c2bb5`).
The same unresolved SOL short had recovered to `+33.2716` bps exact-depth net
after fees and funding on the simulated `$7,500` notional. Relative to the
current exact boundary, the predeclared 25/15/10 and 40/15/20 locks remained
ahead by only `$5.6347` and `$2.2911`, while the 60/15/30 lock was behind by
`$5.1638`. This materially weakens the earlier snapshot's apparent lock
advantage and demonstrates why an unresolved path cannot select its own exit.

The active v39 ETH long independently reached `+49.48` bps MFE before becoming
slightly negative. Its 25/15/10 and 40/15/20 estimates would have retained
approximately `$0.0544` and `$0.0515` before funding and added exit slippage.
Conversely, the active SPCX long reached `+837.32` bps MFE and remained marked
near `+$4.76`; the same three locks would have exited near only `+$0.22` to
`+$0.78`. Both are provisional open lifecycles, but together they reinforce
route-specific evaluation rather than a portfolio-wide TP or trailing rule.

Revised confidence: medium that SOL and ETH warrant continued delayed-lock
measurement, high that a universal lock is contradicted by the available live
paths, and low that any exact lock parameters are optimal. Resolution of the
SOL lifecycle, later native closes, or a same-entry chronological comparison
that reverses these economics would update this assessment.

## Cross-restart entry-filter challenge

Frozen in `v49-cross-restart-filter-disposition.json` from three compatible
v49 observer restarts. Exact visible-depth, taker-fee, and funding replays
isolated conditions that were the sole missing blocker while all other route
requirements were satisfied.

The observed relaxations did not support loosening any configured entry rule:

- SOL without the hourly cross lost `-150.93` bps across 20 resolved 15-minute
  paths, with both long and short slices negative.
- HYPE without breakout onset lost `-85.25` bps across 19 resolved 15-minute
  paths and `-85.97` bps across seven resolved 60-minute paths. Its only
  isolated missing-compression path lost `-99.18` bps and crossed the stop
  proxy.
- BTC Hulk without the expansion trigger lost `-17.19` bps in its sole
  resolved 60-minute path.
- ETH without the hourly cross lost all eight resolved 15-minute paths. Its
  two-path 60-minute slice gained `+10.61` bps only because of one winner and
  became `-5.33` bps after removing it. Both isolated missing-regime paths
  lost.

BTC Sweep supplied no exact one-blocker rows, so no marginal Sweep-filter claim
is made. These are fixed-horizon counterfactuals rather than native lifecycles
or fills; they support retaining the present conditions, not a profitability
claim for the strategies themselves. Confidence is high on source identity and
arithmetic, medium on the direction within this window, and low on future
profitability. A later independent window that remains positive after exact
friction, chronological slicing, and largest-winner removal would falsify this
disposition.
