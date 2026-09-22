# V89 bankroll builder: performance analysis and prioritized fixes

Date: 2026-09-20 (checkpoint generated 09:12 UTC). Scope: the live profile
`multi_asset_growth_first_5000_noncrypto_live_v89.toml` (fingerprint
`39e334fc…667a7f`), run `bidirectional-live-1789586105858`, and the compatible
V89 history since the September 7 launch. This is a report-only analysis. It
proposes no automatic gate and changes nothing; every item below is a human
decision that needs its own explicit approval under `SRS_HV1_NO_GATES` and
`SRS_HV1_HONESTY`.

## 1. Summary

The V89 profile is not losing money, but it is not building a bankroll either.
Thirteen days of live trading produced 20 closed trades, 7 wins and 13 losses
(35% win rate), net **+$5.52** after $3.79 fees and +$0.99 funding, profit
factor 1.07. Account equity is **$4,873**, still below the $5,000 sizing basis
the profile is named for. The compatible all-time archive for the whole
`growth_first_5000` lineage is **-$324.46 over 144 closes** (57W/87L).

Everything positive comes from one route. SNDK's hourly Donchian 20/10 made
+$49.84; its three winners ($23.50, $27.25, $25.30) are **88% of all gross
profit**. Without SNDK the portfolio is -$44.32 on 13 trades. The pre-launch
replay predicted exactly this shape: 41.9% wins and a negative result once the
three largest winners are removed. Live has reproduced the fragility, not
refuted it.

The mechanical findings that matter most:

| # | Finding | Evidence |
| --- | --- | --- |
| A | Losing trades surrender large favorable excursions. Five of nine measured current-run lifecycles "cleared cost hurdle then surrendered"; four of those gave back 156 to 297 bps at 10x leverage. Two of the three current-run stop-outs were whipsaws: price resumed the trade's direction by 25 to 35 bps within the hour after the stop. | `completed_hold_capture`, `post_exit_path`, section 4.3 |
| B | The three originally tested tight locks did not improve that nine-trade sample. The checkpoint's own counterfactual shows every tested lock (a25/a40/a60) losing $19.61 to $27.32 versus actual, because they cut the SNDK winners. | `profit_lock_challenger`, section 4.4 |
| C | Both SNDK winners in the current run exited on the 24-hour timer, not the exit channel, at 546 and 506 bps net with 500 to 600 bps MFE. The timer was well timed on these two (price reversed 126 and 7 bps within the hour), but it is an arbitrary clock, not a strategy exit. | section 4.3 |
| D | Backend availability is the largest realized risk-control breach: six runs in 13 days, `automatic_restart=false`, and a September 12 to 15 outage that held a 24-hour-contract SNDK short for 96.7 hours with only its venue stop. | section 4.5 |
| E | BTC is sized 5x the non-crypto routes with 5x the fee rate (4.32 vs 0.86 bps). One BTC loss (-$17.72) equals 3.2x the median XYZ loss, and the current 20-bps entry contract has zero compatible closes. | section 4.2 |
| F | Telemetry gaps block exit research: completed-path MFE/MAE and post-exit paths are missing for the 11 and 10 lifecycles that predate the September 16 run, post-exit horizons stop at 60 minutes, and exit regime context is missing for 10/20. The ignored-exit scorecard reports `insufficient_resolved_exit_evidence`. | section 4.6 |
| G | Two of seven routes (ETH, HYPE) have zero eligible signals in about 5,150 evaluations each; Brent is 1W/5L with PF 0.18. | section 3.1 |

## 2. Evidence base

| Source | What it provides |
| --- | --- |
| `data/runtime/bidirectional_cohort/latest_checkpoint.json` (2026-09-20 09:12 UTC) | Live portfolio, strategy scorecard, execution quality, risk utilization, trade reflections, profit-lock counterfactuals, readiness blockers |
| `configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml` | Seven assets, seven providers, sizing, stops, hold contracts |
| `docs/reviews/2026-09-07-v89-operator-live-launch.md`, `2026-09-07-frequency-and-noncrypto-expansion.md` | Pre-launch research: 160-trade pooled replay, known limitations |
| `docs/proposals/v89-technical-release-20260910-v3/recommendation.md` | 48-case historical matrix, equal-cap comparison, cost stress |
| `docs/reviews/2026-09-16-v89-*` (SPCX/SNDK exit reconciliation, Brent entry, entry-read-failure protection) | Reconciled single-lifecycle audits and the installed protection fix |
| `HANDOFF.md` September 14 to 18 entries | Restart history, outage, pending prospective seals |

All figures below are taken from those artifacts. Where I derived a number
(for example, "excluding SNDK"), it is arithmetic on the 20 closed lifecycles
in `audit.trade_reflections.trades`.

## 3. Performance results

### 3.1 Live V89 by route (compatible history, September 7 to 20)

| Route | Closed | W/L | Net USD | PF | Fees | Mean ROM | Research state |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SNDK hourly Donchian 20/10 | 7 | 3/4 | **+49.84** | 2.90 | 0.61 | +14.3% | exploratory, later partition negative |
| SPCX hourly band-20 reentry | 6 | 3/3 | -9.38 | 0.41 | 0.52 | -3.2% | exploratory, concentrated |
| Brent hourly Donchian 8/4 | 6 | 1/5 | -17.22 | 0.18 | 0.52 | -5.8% | exploratory, concentrated |
| BTC liquidity sweep long 1h | 1 | 0/1 | -17.72 | 0.00 | 2.15 | -14.3% | current 20-bps contract unmeasured |
| SOL range-onset short | 0 (1 open) | – | – | – | – | – | post-hoc direction, live probation |
| ETH range-onset long | 0 | – | – | – | – | – | 0 eligible / 5,149 evaluations |
| HYPE compression alignment long | 0 | – | – | – | – | – | 0 eligible / 5,146 evaluations |
| **Total** | **20** | **7/13** | **+5.52** | **1.07** | **3.79** | | |

Route-level observations:

- SNDK: median trade is -$4.28; the mean is +$7.12. All three winners were
  `maximum_hold_seconds` exits. Four losses were two stops, one recipe exit,
  and one 32-minute stop-out on September 11 13:00 UTC.
- SPCX long/short split: long 2W/2L -$3.72, short 1W/1L -$5.66. The one
  short stop-out (-$8.45) had a 297 bps peak giveback.
- Brent: all four losses with completed-path data were in profit first (MFE 10
  to 84 bps net, giveback 75 to 189 bps). Historical basis was already weak:
  32.8% wins and -$42.41 excluding its top three winners.
- BTC: fees were 12% of the $17.72 loss. Historical basis is n=7 signals.

### 3.2 Current run (since 2026-09-16 19:27 UTC)

| Metric | Value |
| --- | ---: |
| Marked equity change | +$33.53 (from $4,839.34 to $4,872.86) |
| Maximum drawdown | 0.40% ($4,821.77 trough) |
| Closed lifecycles since restart | 10, 5W/5L, about +$35 realized |
| Maximum concurrent positions | 5 of 7 |
| Maximum margin used | $325.18 (6.7% of equity) |
| Maximum notional | $4,499 (0.92x equity) |
| Faults | 0 |
| Open now | BTC long, SOL short, Brent long, SNDK short, SPCX long (all with resting stops) |

The current run is the best block so far, and it is still entirely SNDK
(+$52.55 of the realized gain from two timer exits).

### 3.3 Pre-launch and historical replay

| Study | Net | Excl. top-3 winners | Later period | Win rate |
| --- | ---: | ---: | ---: | ---: |
| Pooled 3-asset replay, 48 days, adverse cost | +$197.50 | **-$30.73** | – | 41.9% |
| Full 7-asset account, nominal | +$196.85 (+4.05%) | -$31.83 | -$17.73 | 41.8% |
| Full 7-asset account, adverse slippage | +$95.72 | – | -$87.24 | 40.7% |
| Full 7-asset account, full HIP-3 fee stress (9 bps) | **-$33.44** | – | -$137.03 | 37.3% |
| Equal caps ($1,071 per asset, same $7,500 total), nominal | +$491.17 | – | +$8.87 | – |

The historical edge is thin, concentrated, and decays in the later partition.
Live HIP-3 fees are being charged at 0.86 bps, so the full-fee stress is not
currently realized, but it shows how little cost headroom exists.

### 3.4 Execution quality (60 fills)

| Metric | Mean | Median | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| Acknowledgement latency (ms) | 1,598 | 1,433 | 992 | 2,889 |
| Fill slippage vs reference (bps) | +1.01 | +0.64 | -23.2 | +16.5 |
| 15-second markout (bps) | -1.02 | -0.32 | -13.3 | +26.9 |
| Fee rate (bps): XYZ / BTC | 0.86 / 4.32 | | | |

Current-run submission outcomes: 34 accepted, 0 rejected (13 entries, 13
protective stops, 7 reduce-only closes, 1 target). Entry submission age reached 19.9 s on
SPCX against the 30 s contract, leaving 10 s headroom. Execution is clean; the
problem is not fills.

## 4. Diagnosis

### 4.1 The edge is concentrated, and the bankroll cannot compound at this risk budget

Expected value per trade is +$0.28 across 20 trades. Even at the historical
cadence of 3.7 entries per day, that is roughly $30 per month on a $4,873
account before variance. Planned risk at stop if all seven assets are open is
about $78 (1.6% of equity), so ruin risk is low, but so is growth. The profile
is a research canary with live money, not yet a bankroll builder. Any sizing
increase (the equal-cap study) must wait for the sealed prospective results,
because the historical dollars scale with roughly twice the exposure.

### 4.2 Sizing and fee asymmetry punishes the least-proven routes

| Asset | Leverage | Notional cap | Stop | Risk at stop | Round-trip fee | Fee / risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC | 20x | $2,500 | 60 bps | $15.00 | $2.16 | 14% |
| HYPE | 10x | $2,500 | 80 bps | $20.00 | $2.16 | 11% |
| ETH / SOL | 15x | $500 | 60 bps | $3.00 | $0.45 | 15% |
| SPCX / SNDK / Brent | 10x | $500 | 20–250 bps | $1–12.50 | $0.09 | <1% to 9% |

BTC and HYPE carry 5x the dollar risk of the routes that actually have live
evidence, on historical samples of 7 and 41 signals, with the current BTC
20-bps entry contract having zero compatible closes. The all-time archive shows
the three $2,500-notional BTC routes (two retired Hulk shorts plus the sweep)
at -$202 across 8 closes with $37.81 in fees.

### 4.3 Winners are decided by the timer; losers are decided by giveback

Current-run lifecycles with completed-path capture:

| Trade | Exit | Net | MFE (net bps) | Realized (bps) | Giveback (bps) | Outcome class |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| SNDK long | max hold 24.0h | +27.25 | 628 | 546 | 82 | profitable |
| SNDK long | max hold 24.0h | +25.30 | 609 | 506 | 103 | profitable |
| SPCX long | recipe | +3.05 | 189 | 61 | 128 | profitable |
| SPCX short | recipe | +2.79 | 59 | 56 | 3 | profitable |
| Brent short | recipe | -0.07 | 73 | -1 | 75 | cleared hurdle, surrendered |
| Brent short | recipe | -5.24 | 84 | -105 | 189 | cleared hurdle, surrendered |
| Brent short | stop | -6.24 | 44 | -125 | 169 | cleared hurdle, surrendered |
| Brent long | stop | -7.27 | 10 | -146 | 156 | cleared hurdle, surrendered |
| SPCX short | stop | -8.45 | 128 | -169 | 297 | cleared hurdle, surrendered |

The distribution is classic trend-following: a few large runs and many
round-trips. The SNDK exit channel (10-hour low/high) never fired inside 24
hours on the two big winners; the timer did. The ATR20 x2 stop never ratchets,
so a 128 bps favorable excursion can still end at a full stop-loss.

Post-exit paths (resolved for the ten current-run closes, 5 to 60 minutes)
add two facts:

| Exit | Net | Direction return after exit, 60 min | Reading |
| --- | ---: | ---: | --- |
| SNDK long, max hold | +27.25 | -126.3 bps | Timer exit well timed; price fell hard |
| SNDK long, max hold | +25.30 | -6.7 bps | Timer exit roughly neutral |
| SPCX short, stop | -8.45 | +34.5 bps in the short's favor | Whipsaw stop |
| Brent long, stop | -7.27 | +24.7 bps in the long's favor | Whipsaw stop |
| Brent short, stop | -6.24 | -42.5 bps | Stop was right |

The two timer exits did not leave money on the table within the hour. Two of
the three stop-outs did: the market came back through the entry direction
right after the stop filled. Horizons beyond 60 minutes are not captured, so
nothing can be said about the following session.

### 4.4 Three tight profit locks underperformed in the original nine-trade sample

| Policy (activation / floor / trail, bps) | Eligible | Triggered | Est. net | Actual net | Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| a25 / floor15 / trail10 | 9 | 8 | $3.80 | $31.12 | **-$27.32** |
| a40 / floor15 / trail20 | 9 | 7 | $11.51 | $31.12 | **-$19.61** |
| a60 / floor15 / trail30 | 9 | 6 | $3.85 | $31.12 | **-$27.26** |

Tight locks would have cut the two SNDK runs long before 500 bps. This does not establish that profit protection should be rejected, nor can an
exit rule promise both bounded giveback and every later 500+ bps winner. The
operator requires explicit profit protection. The September 21 corrected review
compares three declared policies on 27 recovered paths with completed-minute
execution delay and makes the cut-winner trade-off explicit. See
`2026-09-21-v90-profit-protection-readiness.md`; the original table above is
historical, with a different sample and stop-price proxy.

### 4.5 Availability, not strategy, produced the largest contract breach

| Run | Start (UTC) | Note |
| --- | --- | --- |
| `…1788809099824` | Sep 7 19:24 | Launch; five losses on day one (-$21.12) |
| `…1789122347122` | Sep 11 10:25 | BTC and SNDK both long at 13:00, both stopped within 32 min (-$27.99) |
| (outage) | Sep 12 to 15 | Host interruption; SNDK short's 24h deadline passed Sep 12 14:00 |
| `…1789482753345` | Sep 15 14:32 | Overdue close fired on restart at 96.7 h; +$23.50 by luck |
| `…1789497016143` | Sep 15 18:30 | Monitor/leverage display install |
| `…1789569979897` | Sep 16 14:46 | Ran about 4.5 hours before the protection-fix restart |
| `…1789586105858` | Sep 16 19:15 | Protection-fix restart; current |

`configuration_generation.automatic_restart` is `false`. During the outage
the open position had a venue-native stop but no time exit, no recipe exit,
and no regime evidence. The same interruption damaged the September 9 to 23
prospective allocation study, forcing a separate October 7 follow-up. The
TUI already labels these trade-bearing process windows `NOT INDEPENDENT`.

### 4.6 Telemetry gaps prevent the exit research from progressing

- `completed_hold_capture` is `missing_data` (0 of 247+ expected candles) for
  the 11 lifecycles that predate the September 16 run. Cross-restart lifecycles
  lose their candle path.
- `post_exit_path` is `missing_data` for the 10 pre-restart closes and, where
  resolved, stops at 60 minutes. Hourly strategies need 4-hour and next-session
  horizons to judge a 24-hour timer exit.
- Exit canonical regime and exit signal provider are missing for 10 of 20
  trades. In the reconciled September 16 SNDK lifecycle, 691 of 741
  regime-opposition observations were unavailable.
- The ignored-provider-exit scorecard needs 5 resolved lifecycles per route and
  currently reports `insufficient_resolved_exit_evidence`.

Without these, items 5 and 6 below cannot be evaluated honestly.

## 5. Prioritized fixes and enhancements

Priority reflects realized risk and evidence weight, not implementation
difficulty. P0 items are correctness and risk-control; P1 items are the edge
work with the best evidence behind them; P2 items are hygiene. Nothing here is
an automatic trial-abort condition.

### P0: critical fixes

**1. Supervised backend availability and hold-contract continuity.**
Problem: six restarts in 13 days and a three-day outage that turned a 24-hour
hold into 96.7 hours (section 4.5). Fix: a fail-closed supervisor that restarts
the backend after a verified flat-or-adopted reconciliation, with alerting on
heartbeat loss over a configured threshold. Keep the existing overdue-close
request on restart. Acceptance: an induced process kill in the observe-mode
harness restarts within N minutes, adopts the venue position and stop without
duplicate mutation, and the overdue max-hold close fires within one poll.
Also record uptime per run so `NOT INDEPENDENT` windows are visible in the
scorecard.

**2. Explicit, user-configured portfolio concurrent-risk cap.**
Problem: correlated same-hour entries (Sep 8: five losses in 13 hours; Sep 11
13:00: BTC and SNDK longs stopped together). Today the only cap is one
position per asset. Fix: add an explicit optional `[portfolio]` setting for
aggregate risk-at-stop as a percentage of equity and for same-direction
concurrency, defaulting to off so it is not an implicit gate. Withheld entries
must be recorded with a reason, exactly like `observe_mode_no_execution`.
Acceptance: unit tests on the router and a checkpoint field reporting
withheld-by-portfolio-cap counts.

**3. Bring BTC and HYPE sizing to evidence parity.**
Problem: 5x the dollar risk and 5x the fee rate on the routes with the
weakest live evidence (section 4.2). Options for the operator to choose,
in order of preference: (a) reduce BTC and HYPE `max_notional_usd` to $500
until each has at least 10 closes under its current contract; (b) move the
BTC 1h sweep to a maker entry with a post-only fallback, since 8.6 bps
round-trip is 14% of its 60-bps target; (c) leave unchanged and accept the
asymmetry knowingly. Any choice needs a new approval record and a flat
transition boundary. Acceptance: fee/risk ratio per route under 10% and no
route sized above another without at least equal live evidence.

**4. Close the telemetry gaps.**
Problem: section 4.6. Fix: (a) backfill completed-path and post-exit candles
for lifecycles that span restarts from the research DuckDB rather than the
in-process buffer; (b) extend post-exit horizons to 240 minutes and 24 hours
so hourly-clock exits can be judged on their own timescale; (c) persist
exit-time canonical regime and provider decision in the close event.
Acceptance: `completed_hold_capture.status != missing_data` and
`post_exit_path` resolved at all horizons for every new closed lifecycle; the
ignored-exit scorecard reaches its 5-lifecycle threshold on SNDK, SPCX and
Brent within the next block.

### P1: enhancements with the strongest evidence

**5. Structure-based stop and exit research for the hourly non-crypto routes.**
Problem: 150 to 300 bps givebacks on losers, two of three current-run stops
whipsawed within the hour, and fixed-bps locks lose money (sections 4.3 and
4.4). Candidates to preregister and replay on the frozen 48-day window plus
the sealed prospective blocks: ratchet the ATR20 x2 stop to entry once MFE
exceeds 2x ATR; tighten the exit channel from 10 to 5 hours once MFE exceeds
3x ATR; a wider initial stop multiple (2.5x or 3x ATR) at reduced size to hold
risk-at-stop constant; partial exit for SPCX at half the distance to the band
mean. Each must be evaluated with the existing counterfactual harness,
reporting delta versus actual on the same lifecycles as the rejected locks.
Do not promote from the 20-trade live sample. Acceptance: positive delta
versus actual across both the historical matrix and at least one sealed
prospective block, with the two SNDK runs retained.

**6. Maximum-hold policy for SNDK: measure before changing.**
Problem: the timer, not the exit channel, closed both 500-plus bps winners at
exactly 24.0 hours. The 60-minute post-exit paths show both reversed (-126
and -7 bps), so there is no evidence yet that the timer is cutting winners
short; there is also no evidence beyond one hour. HYPE already has
`extend_while_regime_supported` with a hard cap; SNDK does not. Depends on
item 4 (longer post-exit horizons and exit regime context). Only after those
exist should a 48-hour hold with a 72-hour hard cap and regime-supported
extension be evaluated. Acceptance: 240-minute and 24-hour post-exit
continuation measured on at least five timer exits before any proposal.

**7. Brent 8/4 route disposition.**
Problem: 1W/5L, PF 0.18, -$17.22 live; historical excluding its top three
winners was -$42.41 at 32.8% wins; every loss surrendered a favorable
excursion. The September 22 04:00 UTC SNDK/Brent seal opens in two days.
Recommendation: make no change before the seal; if the sealed block is also
negative after costs, the operator should decide between observe-only
(`execution_symbols` empty, keeping the provider visible) and continued
execution at reduced notional. Not an automatic gate; a scheduled human review
with the criteria written down now.

**8. Entry dispatch headroom on hourly routes.**
Problem: SPCX submission age reached 19.9 s of the 30 s contract on a 15-minute
source clock. Acknowledgement alone averages 1.6 s. Fix: measure the
hour-boundary path (candle publish to dispatch) per provider and either reduce
serial venue reads before submission or raise the contract with a documented
reason. Acceptance: p95 submission age under 15 s, no stale-entry withholdings.

**9. Dormant ETH and HYPE routes.**
Problem: zero eligible signals in about 5,150 evaluations each. ETH is blocked
100% by `awaiting_hourly_sma_cross` and 73% by `5m_regime_not_admitted`. Both
directions were chosen after historical inspection. These routes cost nothing
in capital today (capacity is per asset) but consume review attention and
carry probationary sizing. Recommendation: keep them, but publish a per-route
"time since last eligible signal" and a blocker-episode summary on the
scorecard so the operator can decide after a full block whether the entry
conditions are too restrictive for the current regime. No loosening without a
preregistered study.

### P2: operational and research hygiene

**10. Minimum uninterrupted observation block.**
Define one block (14 days, matching the prospective studies) during which
non-emergency restarts are deferred and TUI/monitor changes use the
independent monitor rather than the combined launcher. The September 15 and
16 restarts were for display and protection installs; only the protection fix
was urgent.

**11. Synchronized account and position reads.**
The Brent audit found 12 of 28 same-poll account/position pairs differing by
up to $0.147 because valuation reads are serial. Capture one venue timestamp
per reconciliation snapshot so margin and PnL identities are exact.

**12. Equal-cap allocation stays research until October 7.**
Historical +$491 versus +$197 comes with roughly twice the average exposure and
larger dollar drawdowns; the later period still stresses negative under fees.
Wait for the sealed September 23 and October 7 blocks and compare paired
cells, as the protocol already requires.

**13. HIP-3 fee monitoring.**
Live fees match the 0.86 bps nominal, but a 9 bps stress flips the whole
window negative. Keep the `growthMode` and aligned-quote status in the
checkpoint and alert on any observed fee-rate change above 2 bps.

**14. Route retirement bookkeeping in the archive.**
The all-time archive still carries the retired BTC Hulk shorts (-$176) and
early HIP-3 routes. Label retired versus active routes in the archive view so
lineage performance can be read as "what would the current profile have done"
rather than a mixed history.

## 6. What the evidence says not to do

- Do not add fixed-bps trailing locks; all three tested variants lose versus
  actual on the same lifecycles.
- Do not retune stops or exits from any single reconciled trade (the SPCX and
  SNDK September 16 audits already made this point).
- Do not promote the equal-cap allocation on historical dollars.
- Do not open the September 22, September 23 or October 7 seals early, and do
  not select a favorable sub-window from the interrupted allocation study.
- Do not read the current run's +$33.53 as an edge; it is two SNDK timer exits.
- Do not extend the SNDK hold on the strength of the two big winners; the
  post-exit paths show the timer was well timed on both.

## 7. Suggested sequencing

| When | Action |
| --- | --- |
| Now | Items 4 (telemetry), 1 (supervisor) and 15 (ledger/bundle growth) in isolated worktrees; no live change |
| Sep 22 04:00 UTC | SNDK/Brent seal opens: run item 7 review with the criteria above |
| Sep 23 00:00 UTC | Seven-asset seal opens: read the allocation comparison; record, do not act |
| Next flat boundary after approval | Items 2 and 3 as one explicit profile change (V90) with a new approval record |
| After item 4 has 5 resolved lifecycles per route | Items 5 and 6 preregistered and replayed |
| Oct 7 00:00 UTC | Follow-up seal: decide on equal-cap and on Brent with two sealed blocks |

## 8. Reconciliation with an independent list (2026-09-20)

A second analysis from an earlier checkpoint was compared against this
document. Two items were accepted, several were stale, and two were rejected
on current evidence.

**Accepted and added:**

**15. Ledger and prestart-bundle growth (P0, operational).**
`decisions.jsonl` is 5.4 GB, the live cohort ledgers total 10 GB, and there
are 145 prestart bundles totalling 59 GB at about 900 MB each, one per
restart. The September 18 disk shortage deferred research sync until cleanup;
it is resolved (46 GiB free, sync `running`) but will recur. Every restart
also copies all ledgers into a new bundle, which lengthens startup (the
launcher allows 1,800 s) and therefore lengthens recovery after an outage
(item 1). Fix: content-addressed dedup or compression of bundle ledgers,
rotation of `decisions.jsonl` with verified sealed segments, and a disk
headroom alert. Retired ledgers (`xyz:gold.jsonl`, `zec.jsonl`,
`xyz:sp500.jsonl`, about 0.4 GB) feed the ten-symbol all-time archive and are
part of every bundle identity; archive and compress them, do not delete.

**Stale in the other list:** `maximum_positions` is 7, not 10; current-run
peak is 5 concurrent positions, 6.7% margin and 92% notional of equity, not
3 / 3.7% / 31%; SOL is not dormant (one eligible signal, short open since
September 19 18:00 UTC); Brent funding is +$1.08 received, not paid.

**Rejected on current evidence:**

- *Make caps equity-relative now.* Cap binding is real (BTC effective margin
  2.56% vs configured 5%), but deployment is not the constraint on a PF 1.07
  book. Allocation changes go through the sealed equal-cap study (September
  23 and October 7), whose historical result already shows the exposure cost.
- *Enable `extend_while_regime_supported` on the hourly routes.* Post-exit
  paths show both SNDK timer exits were followed by reversal (-126 and -7 bps
  at 60 minutes). The policy also fails closed to exit when provider or
  canonical evidence is older than `maximum_hold_evidence_maximum_age_seconds`;
  the hourly routes evaluate every 15 minutes, so the HYPE-style 60 s contract
  would exit at the soft deadline regardless. See item 6.
- *Entry headroom "already negative".* The negative values are on ineligible
  evaluations during startup warmup (`measured_no_action_breach`). Submitted
  entries had 7.7 to 20.9 s of headroom. The valid part is the 36.4 s worst
  cycle against a 30 s contract, already covered by item 8.

## 9. Confidence and falsifiers

High confidence in the recorded live arithmetic, route attribution, execution
statistics and the counterfactual lock results, all of which come from the
authenticated checkpoint and reconciled audits. Medium confidence in the
diagnosis that exit structure rather than entry selection is the main lever;
the sample is 20 trades from six non-independent process windows. Low
confidence in any forward return. A changed checkpoint identity, a
reconciliation disagreement, or sealed prospective results contradicting the
historical pattern would revise the priorities above. This document proposes
no live change and is not an approval record.
