# Creator Screenshot Forward Validation

## Problem and evidence boundary

The new creator screenshots are independent forward evidence for Hypervelocity
entry direction and fixed-target behavior. They are not a complete execution
ledger: entry price, exit price, side, displayed entry minute, gross result,
and aggregate cards are visible, but exit timestamps, losing rows, order IDs,
and exit reasons are not.

The review uses the trade rows as authoritative observations. It does not use
the adjacent aggregate cards as a sequential equity ledger because they change
from 59 positions, 43W/16L, and $130.56 PnL to 60 positions, 42W/18L, and
$87.38 PnL. One additional position cannot reduce wins by one and add two
losses, so the cards are either different views/runs or contain unreconciled
application state.

Evidence checksums:

- `Screenshot 2026-07-27 at 4.26.05 PM.png`:
  `a8932289749cb790104cc2b4369111417a4466b73bdcc3a8d090449901870a2f`.
- `Screenshot 2026-07-27 at 4.27.15 PM.png`:
  `24c7982aa3d4c186602fa7bbd1214124a2ef4372078c0d326e2fe8a92ced1ad7`.
- `unnamed.png`:
  `d6cbbce5eecb70eeeefa3e8481c1e7b286a8bfa88a2eb198578fff89cdc66af0`.
- `unnamed (1).png`:
  `0c0411651bf9c5ebe303216e8bc36e9f13d2442137b25ee3cf275d2853371656`.
- Original reconciled CSV:
  `68b40a3b9afc9ec584fc30b4887e2f9092d025b312e599bbaf5f175bd4a7c430`.
- Derived screenshot rows:
  `docs/external/creator_screenshot_positions_20260727.csv`,
  `ca315315af09406d8c7c987d422285e59970c991739d2105ff7eedec8c99412e`.

## New unique trade evidence

The first screenshot closes the previously known tracker-only BTC short at
$63,893 with an exit at $63,766 and +8.0% margin return. It therefore upgrades
one existing logical position from tracker-only to outcome-backed evidence; it
is not a new entry.

The same screenshot adds one new BTC long at $64,395 with an exit at $64,523,
+8.0%, and $36.11 displayed PnL. Its displayed entry time is Jul 25 at 1:50 PM.
The screenshot clock is inferred as UTC-5 because the prior $63,893 short shown
at Jul 24 10:06 AM matches the source tracker's exact 15:06:32 UTC open and
price. The new long is consequently aligned to 18:50 UTC at minute precision.
An authoritative timestamp export would falsify or strengthen this inference.
The screenshot clock is not labeled with a timezone. A sensitivity check at
17:50 UTC, corresponding to US Eastern daylight time rather than the observed
UTC-5 mapping, also classifies 1m and 5m as TREND_UP with a long entry. The
directional match for this row is therefore unchanged by that one-hour clock
uncertainty.

After deduplication, the source set contains 23 outcome-backed entries: the
original 21 trade-backed positions, the upgraded $63,893 short, and the new
$64,395 long.

The second position-history screenshot also shows a Jul 24 07:46 short at
$64,865.67 with a $64,757.37 exit and +6.7%. It corroborates, rather than adds
to, the existing two-row split exit opened around 12:47 UTC. The two recorded
exit prices, weighted by their recorded quantities, equal $64,757.3669. The
displayed entry differs from the stored $64,880 intent, so the evidence cannot
yet distinguish effective average fill, later position adjustment, or a
different application representation. Authoritative fill IDs would resolve
that discrepancy. The active $64,679 short screenshot lacks an entry timestamp
and resolved exit, so it is retained as qualitative evidence only.

## Decision-time regime comparison

Correction: the earlier wording in this section conflated structural direction
with executable entry eligibility. Using completed-bar availability, the
canonical 5-minute structural direction matches 20/23 outcome-backed entries
(87.0%), but canonical `entry_direction` matches 17/23 (73.9%). Three
structurally aligned 5m `BREAKOUT` rows are still in
`5m_breakout_awaiting_1m_confirmation` at the creator entry minute. Both new
screenshot rows are executable-direction matches:

- Jul 24 15:06:32 UTC short: 1m RANGE, 5m TREND_DOWN, 15m TREND_DOWN,
  structural short, BBWP 78.33, confidence 73.06%.
- Jul 25 18:50 UTC long: 1m TREND_UP, 5m TREND_UP, 15m TREND_UP, structural
  long, BBWP 51.25, confidence 70.69%. Exact L2 at that minute had opposed
  OBI5 of approximately -0.359, consistent with pullback entry timing.

The three misses are early reversal entries rather than RANGE errors:

| Source entry | Side | 1m | 5m | 15m | Next matching 5m direction |
|---|---|---|---|---|---|
| Jul 20 00:52 UTC | short | TREND_DOWN | TREND_UP | TREND_UP | about 243 min later |
| Jul 22 01:17 UTC | short | TREND_DOWN | TREND_UP | TREND_UP | about 93 min later |
| Jul 23 13:33 UTC | long | TREND_DOWN | TREND_DOWN | TREND_DOWN | about 416 min later |

The three additional executable-signal misses are a Jul 20 18:19 UTC long and
Jul 23 12:35 and 12:43 UTC shorts. Their 5m structural direction agrees with
the creator, but the current narrow 1m confirmation has not yet armed the
entry. A report-only 1m-trend breakout-confirmation challenger previously
recovered these trade-backed directions, but worsened the exact source-window
portfolio from $114.37 to $99.48 and drawdown from -77.78% to -80.79%. It
therefore remains unpromoted rather than being treated as an automatic fix.

This supports the current 5m primary detector for ordinary continuation
structure but falsifies the claim that the complete executable detector
reproduces every creator entry. Confidence is medium: 23 entries are useful
forward evidence but still a small, clustered sample.

## Tested challengers and decisions

The authentic 90-day canonical, first-opposed-OBI5 replay without a stop filled
302 trades: 261 targets and 41 liquidations. Despite an 86.4% target rate, it
reduced $120 to $0.07 with -99.97% maximum drawdown. This falsifies TP-only as a
complete executable model under 70% allocation and 40x isolated leverage.

The exact 2% margin-stop replay is stored at
`data/logs/research/hypervelocity_canonical_pressure_stop2_authentic_20260727.json`
with SHA-256
`0e34d4fc4be50a68d5181d9417004783fd3a86433d9ebad381911f91e66201a8`.
It produced 458 fills, 81 targets, 375 stops, two gap liquidations, $96.66 in
fees, $0.01 final equity, and -99.99% maximum drawdown. Its 81.9% stop rate is
incompatible with the creator card's approximate 30% loss share. The 3% run
was not authorized because the declared 2% prerequisite failed every survival
and behavioral-alignment criterion.

A first-opposite-5m-regime fixed-lifecycle screen intercepted 36/41 modeled
liquidations but cut 47 eventual targets. All 83 early exits were net losses;
additive PnL improved from -$119.93 to -$87.03 but remained decisively
negative. It does not justify an exact event replay.

The local price-only Pine Trend State annotation fixes all three source
direction misses but matches only 12/23 entries standalone. Two integrations
were screened:

- continuous DAFE+RSI 60/40 override: 935 bar trades and 141 liquidations;
- one transition opportunity lasting two 5m periods: 955 trades and 139
  liquidations.

Both nearly erased the bar portfolio and altered more than 20,000 bars. This is
in-sample source fitting with unacceptable full-window churn, so Trend State
remains annotation-only.

Finally, entry OBI5 magnitude does not separate targets from liquidations in
the existing 281-fill attribution set. Thresholds from 0.0 through 0.8 retain
target rates of only about 85-88% while discarding winners. No pressure-strength
threshold is promoted.

## Source-timing replay and transition-confirmation falsification

The 23 outcome-backed creator timestamps were replayed as a prescribed source
schedule against verified Hyperliquid books, trades, marks, oracle prices, and
funding. Nineteen maker orders filled; all 19 reached the fixed target and none
liquidated. The replay moved $120 to $290.05 with -34.30% maximum drawdown. This
confirms that creator timing is profitable on its own July 18-25 observation
window under the modeled venue contract. It does not identify the creator's
entry trigger and is not out-of-sample evidence. The immutable artifact is
`data/logs/research/hypervelocity_source_schedule_outcome_backed_authentic_20260727.json`.

A causal feature comparison used those 19 resolved source fills and the 23
canonical fills in the same interval (20 targets, three liquidations). Creator
fills had median 5m directional EMA gap of 14.89 bps and median regime-strength
percentile of 73.06, compared with 2.63 bps and 34.31 for the three canonical
liquidations. All three canonical liquidations were shorts on the first minute
of a new 5m down state while 15m context remained bullish. These are useful
attribution signals, not safe thresholds: creator fills ranged from -29.81 to
59.17 bps in directional 5m gap and 39.86 to 94.86 in strength, and the source
contains valid early counter-context reversals.

A report-only challenger therefore tested the narrower causal hypothesis: wait
one completed 1m decision before entering a newly changed 5m state when the
directional 15m context is opposed. The full event replay rejected it:

| Candidate | Fills | Targets | Liquidations | Final $120 | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Canonical first-opposed OBI5 | 302 | 261 | 41 | $0.0668 | -99.97% |
| Fresh/opposed confirmation-1 | 295 | 254 | 41 | $0.0395 | -99.98% |

The first 60 days worsened from 177 targets/31 liquidations to 171/32. The
final 30 days changed from 84/10 to 83/9, which is insufficient to offset the
older degradation. Outcome-backed creator structural-direction alignment
remained 20/23, but the execution rule removed seven targets without reducing
full-window liquidations. The challenger artifact is
`data/logs/research/hypervelocity_canonical_pressure_fresh_opposed_confirm1_authentic_20260727.json`
with SHA-256
`b50b98958a9269d1ca601c29b521e1c4e989f46a1e25cdb7346634ce2cebdac1`.
It remains research-only and is rejected for runtime promotion.

## Original reverse-engineering plan evidence audit

The July 24 reverse-engineering plan is useful as a hypothesis inventory, but
it does not maintain a strict boundary between observed fields and inferred
mechanics. The following statements are supported by the creator rows or by
the later explicit strategy contract:

- BTC direction alternates in same-side runs rather than on every trade.
- The visible successful exits repeatedly report about +8% margin return.
- Recorded execution is consistent with 40x leverage and maker intent.
- Entries should be directional and should not open in a RANGE state.

The following plan statements are not established by the source records and
must not be treated as runtime requirements:

- A 2-3% margin stop, ATR stop, trailing stop, or trend-invalidation exit. The
  screenshots show aggregate losses but no losing exit rows or exit reasons.
- A 15m hard veto. The current contract uses 5m primary structure with 15m as
  visible non-veto context, and three successful creator reversals lead the
  current 5m direction.
- Funding-triggered reversal, dynamic leverage, or order-book pressure as an
  entry gate. These are plausible annotations but are not observable in the
  supplied position rows.
- A 32% equity allocation. The plan derives that value from target return and
  leverage rather than from an observed account balance. The later explicit
  70% margin allocation is the authoritative contract.
- A two-position/two-target implementation. Simultaneous source rows can also
  be partial-exit bookkeeping, and the explicit one-position-per-coin rule
  supersedes this inference.

The plan's claim that zero booked losing rows implies a tight stop is also
falsified as an inference by the new aggregate cards: they display 43W/16L and
42W/18L, although the cards cannot be reconciled into one sequential ledger.
The loss mechanism remains unknown.

Confidence is high in this observation-versus-inference separation because it
follows directly from which fields are present in the evidence. Authoritative
creator order/fill exports containing losing exits would update the stop and
exit assessment.

## Additional rejected loss-control and entry challengers

A weak counter-context delay retained a new 5m direction only when its causal
strength percentile was at least 50. The authentic replay produced 282 fills,
238 targets, 44 liquidations, $0.0063 final equity from $120, and -99.997%
maximum drawdown. It worsened both the first 60-day development segment and
the final 30-day segment, so adjacent strength thresholds were not swept. The
immutable artifact is
`data/logs/research/hypervelocity_canonical_pressure_opposed_strength50_authentic_20260727.json`
with SHA-256
`cd3f7fba1e9c151e9db96842df138d76ec46ea94f3d6fa9a671bd54ce7e1e858`.

A tracker-disappearance exit proxy was reconstructed for 12 early positions.
Using the latest Hyperliquid mark at or before disappearance, eight proxies
were positive and four negative, with median +1.57%, minimum -28.64%, and
maximum +7.14% gross margin return. Nearest-mark sensitivity remained eight
positive and four negative. This is evidence that losses cannot be ignored,
not an authoritative exit rule: tracker disappearance is not a fill, the
creator venue can differ from Hyperliquid, and costs are excluded. Artifact:
`data/logs/research/hypervelocity_tracker_exit_proxy_20260727.json`, SHA-256
`a6ae1014f19a40321a278cf862a7b2f098e16016b87196ad507cf87749c2c1f6`.

A causal strict 2-left/2-right confirmed-pivot stop was screened on all 302
canonical filled lifecycles. It generated 154 stop hits, avoided 37 recorded
liquidations, and stopped 117 trades that later reached the original target.
Fee-adjusted additive PnL improved by only $0.42, while fixed-lifecycle
geometric equity still lost about 99.33%. It therefore did not qualify for a
stateful re-entry replay. Artifact:
`data/logs/research/hypervelocity_canonical_confirmed_pivot_stop_20260727.json`,
SHA-256
`c2068f96a02590a8fcf8e6b8a620e6a4f2b01eb19db6a70305d2a38a170087bb`.

An exploratory first-opposing-1m-state loss exit intercepted most recorded
liquidations but also exited many eventual targets and still lost more than
99% of fixed-lifecycle geometric equity. Loss thresholds and short persistence
delays did not produce a profitable development result. These scratch screens
were not retained as immutable artifacts, so they are not promotion evidence
and the inspected final 30-day rows are no longer an untouched holdout for
future tuning.

The observe-only metalabel comparison used 302 canonical fills and 151
walk-forward predictions containing 22 liquidations. Logistic regression
without book features had the strongest mean ranking (ROC AUC 0.6002), but its
mean log loss of 0.41995 was effectively tied with the past-only base rate at
0.42059 and was unstable across folds. LightGBM and the book-feature variants
did not improve the result. Post-hoc utility thresholds still lost money or
achieved apparent survival by selecting no trades. The metalabel therefore
remains `observe` with `may_filter=false` and `may_scale=false`.

## Creator-calibrated fixed-stop grid

The final fixed-stop hypothesis used the faithful regime decisions directly,
without OBI, confidence, strength, age, 15m, or model gates. The no-stop
control and predeclared 6%, 10%, 14%, and 18% gross margin stops shared one
90-day Hyperliquid event tape with public trade-through fills, authentic
mark/oracle prices, official funding event timestamps, 70% allocation, 40x
isolated leverage, and the fixed 8% target.

| Candidate | Fills | Targets | Stops | Liquidations | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| No stop | 281 | 241 | 0 | 40 | $3.80 | -99.979% |
| Stop 6% | 394 | 159 | 234 | 1 | $6.06 | -99.943% |
| Stop 10% | 389 | 204 | 184 | 1 | $4.34 | -99.965% |
| Stop 14% | 371 | 227 | 143 | 1 | $6.31 | -99.956% |
| Stop 18% | 362 | 230 | 131 | 1 | $0.47 | -99.997% |

All candidates lost money in all three chronological 30-day slices. The stops
successfully changed the proximate failure mode from 40 liquidations to one,
but early exits rearmed the strategy and created more entries, stop-outs, and
fees. Even the numerically least-bad 14% stop lost more than 99.9%. No fixed
stop is promoted. Artifact:
`data/logs/research/hypervelocity_creator_margin_stop_grid_20260727.json`,
SHA-256
`b0e6c9d584db7ffd631da810cdca7ca656025c07af681a36345843e800884b37`.

## Source-bounded maximum-hold grid

The predeclared no-timeout/6h/12h/24h grid tested whether stale positions,
rather than entry direction, explain the catastrophic faithful replay. It used
the same verified 90-day tape, authentic mark/oracle/funding context, faithful
decisions, fees, and re-entry contract as the fixed-stop comparison.

| Candidate | Fills | Targets | Time exits | Liquidations | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| No timeout | 281 | 241 | 0 | 40 | $3.80 | -99.979% |
| 6 hours | 312 | 238 | 45 | 29 | $0.80 | -99.997% |
| 12 hours | 286 | 241 | 11 | 34 | $18.17 | -99.929% |
| 24 hours | 281 | 241 | 1 | 39 | $4.47 | -99.976% |

All four paths lost money in every 30-day slice. Twelve hours retained more
terminal equity than control but still lost 99.82%, changed six shared eventual
targets into losing time exits, and generated a different later lifecycle
path. Six hours reduced liquidations most but replaced 21 shared eventual
targets with time exits and increased fills to 312. The creator-duration check
preserves 28/33 closed positions at 6h, 30/33 at 12h, and 33/33 at 24h.

No deadline is promoted. The result rejects maximum hold as a standalone
repair; it does not establish the creator's unknown losing-trade exit rule.
Artifact:
`data/logs/research/hypervelocity_source_bounded_max_hold_20260727.json`,
SHA-256
`6cab0f15e041f8e03485051041d073f8ea2c0551703379a78c37207f7c9969af`.

## Source-bounded target ladder

The merged creator inventory contains 35 logical entries. Twenty-seven align
with the causal 5m structural direction, and 21 of those occur in repeated
same-direction entries inside one uninterrupted structural episode. The
matched episode distribution is six episodes with one entry, three with two,
three with three, and one with six. This directly falsifies the faithful
runtime assumption that the creator takes at most one successful trade per 5m
episode, but it does not establish the creator's re-entry trigger.

A frozen control/cap-2/cap-3/cap-6 target-continuation grid tested the smallest
bounded repair. Challengers retained the 60-second cooldown, required a prior
successful target, used no extra clearance, and still required regime reset
after liquidation or maker expiry.

| Candidate | Fills | Targets | Liquidations | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Regime-reset control | 281 | 241 | 40 | $3.8034 | -99.9794% |
| Target ladder cap 2 | 409 | 355 | 54 | $0.9088 | -99.9975% |
| Target ladder cap 3 | 504 | 427 | 77 | $0.000432 | -99.999999% |
| Target ladder cap 6 | 637 | 540 | 97 | $0.000009 | -99.99999998% |

Every path lost money in every 30-day slice. Cap 2 preserved 20/27 matched
source entries but created 198 candidate-only resolved lifecycles and 14 more
liquidations than control. Cap 3 preserves 24/27 source entries and cap 6 all
27, but both increase trade-path churn and liquidations further. Repeated
same-side trading is real creator behavior; applying it to every eligible
episode is not the missing edge.

No cap is promoted. Artifact:
`data/logs/research/hypervelocity_bounded_target_ladder_20260727.json`, SHA-256
`32f66644265552083d0f990910fdcbfacc960d7125942bfd2f4d18c2a0cd9a61`.

Confidence is high that this fixed-stop family does not repair the faithful
strategy on the inspected development archive. This does not establish the
creator's actual loss rule: the screenshots still expose aggregate loss counts
without any losing exit row or exit reason. A loss rule coupled to a longer
refractory period could behave differently and would require an independently
declared test rather than post-hoc modification of this grid.

## Mature-episode continuation follow-up

The creator screenshots show both facts that a faithful re-entry model must
preserve: repeated same-direction entries can occur only two minutes apart,
and all 14 direction-matched continuations in the reconciled sample occur at
least 38 completed 1m bars into the current uninterrupted 5m structural
episode. This supports rapid continuation inside a mature structural trend,
not a long post-exit cooldown.

The two aggregate scorecards remain separate evidence snapshots. One shows
59 positions at 43W/16L and the other 60 positions at 42W/18L; they cannot form
one monotonic ledger without additional provenance. They were not summed or
treated as a sequential equity curve.

A frozen 30-minute mature cap-2 challenger preserved all 14 observed creator
continuations. In the serial screen it reduced cap-2 liquidations from 70 to
58, but remained worse than regime reset. The authentic event replay produced
415 fills, 361 targets, 54 liquidations, $1.0327 final equity, and -99.9969%
maximum drawdown. Unrestricted cap 2 produced 409/355/54 and $0.9088; control
produced 281/241/40 and $3.8034. All three mature-candidate chronological
slices lost money.

Maturity therefore improves source fidelity and reduces fee churn, but does
not supply the missing tactical entry trigger. It is not promoted. Artifact:
`data/logs/research/hypervelocity_mature_target_continuation_20260727.json`,
SHA-256
`6b146c73d0832becb553c946f75c85fbfca17756083df89bce70a5cd991ea7f7`.

## Target-before-stop observe-only metalabel

The predeclared follow-up labeled the 371 faithful 14% stop lifecycles as
target versus loss: 227 targets, 143 stops, and one liquidation. Three
expanding, outcome-aware, 60-minute-embargo folds produced 186 out-of-fold
predictions containing 75 losses. The candidate set was frozen before the run:
past-only base rate, regularized logistic with and without L2, temporal
logistic with L2, and LightGBM with and without L2.

| Candidate | Mean log loss | Mean ROC AUC | Lowest-risk-half target rate | Folds above 70.69% break-even |
|---|---:|---:|---:|---:|
| Past-only base rate | 0.67861 | 0.5000 | 60.22% | 1/3 |
| Logistic, bar/regime | 0.69819 | 0.5047 | 65.59% | 2/3 |
| Logistic + L2 | 0.71226 | 0.4861 | 55.91% | 0/3 |
| Temporal logistic + L2 | 0.78484 | 0.5024 | 59.14% | 1/3 |
| LightGBM, bar/regime | 0.72168 | 0.4273 | 54.84% | 0/3 |
| LightGBM + L2 | 0.73187 | 0.4562 | 58.06% | 1/3 |

The base rate won mean log loss. Logistic without L2 beat it by only 0.00064
in one fold and lost in the other two; its first-fold lowest-risk half reached
only 51.61% targets. Adding L2 worsened mean log loss by 0.01407 for logistic
and 0.01019 for LightGBM, with the book variant improving only one of three
folds in each family. No learned candidate put its lowest-risk half above the
fee-adjusted break-even rate in all folds. This rejects the current
target-before-stop model as an execution filter or scaler and leaves ML
strictly observe-only.

Artifact:
`data/logs/research/hypervelocity_stop14_outcome_metalabel_20260727.json`,
SHA-256
`bd4e36c0ac7e9f4aa5c51113a8bbc816d54512f53454fefe1399b5aa7a239f64`.
The source configuration remains
`801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
Confidence is high that none of these six frozen candidates learned a stable
edge on this inspected replay, but low-to-medium that the hypothetical 14%
stop label represents the creator's actual loss decision. A creator losing
trade with entry, exit, timestamps, size, and exit reason would directly
falsify or refine the label. A fresh sealed venue-matched window would need to
beat the past-only baseline and the 70.69% economic threshold consistently,
not just in one favorable fold, before runtime promotion could be reconsidered.

## Current decision and falsifier

### Extended Jul 9-27 creator-window update

The new Jul 24 short and Jul 25 long outcomes were normalized without
fabricating missing close timestamps. Both align with the authoritative 5m
regime at decision time. The short occurred with 5m/15m down while 1m was
RANGE; the long occurred with all three timeframes up. This supports 5m
authority and treating 1m opposition/range as tactical context rather than a
veto.

The previously frozen 1m-trend breakout challenger was replayed through Jul 27
without retuning. Control produced 70 fills, 64 targets, six liquidations,
$126.85 from $120, and -77.96% maximum drawdown. The challenger produced 67
fills, 61 targets, the same six liquidations, $110.42, and -81.56% drawdown.
Its exact source-direction alignment improved from 17/35 to 20/35, but all 56
shared resolved lifecycles retained the same status and the changed path was
economically worse.

The challenger remains rejected. The positive control slice is encouraging
but still development evidence with extreme drawdown; it does not supersede
the slightly losing 90-day result or authorize runtime changes. Artifacts and
SHA-256 hashes are recorded in
`docs/plans/2026-07-27-hypervelocity-extended-source-window.md`.

Keep runtime configuration
`801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`
unchanged. Keep the metalabel and Pine Trend State annotation-only. The current
detector is directionally close on visible creator entries, while the executable
edge remains unproven because loss exits are not observable.

The highest-information update is a creator losing-trade row containing entry,
exit, side, leverage/size, entry time, exit time, and exit reason. Such evidence
would directly test whether losses are tight stops, manual trend invalidations,
partial closes, or a different sizing path. Fresh creator entries that the
canonical detector repeatedly labels opposite at decision time would lower
confidence in the 5m primary regime; continued 5m agreement would raise it.

## Minimum structural-age falsification

A later report-only test challenged immediate entry into a newly observed
post-BBWP 5m state. It required zero-based hard-state age five before a new
entry while retaining the hard BBWP25 range rule, recovery age six, maker
execution, 70% isolated allocation, 40x leverage, and 8% target.

| Candidate | Fills | Targets | Liquidations | Final $120 | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Hard-BBWP25/recovery-6 control | 445 | 402 | 43 | $20.2578 | -99.4317% |
| Minimum hard-state age 5 | 406 | 361 | 45 | $0.9405 | -99.9381% |

Only 40 resolved signal identities were shared; 405 control outcomes were
removed and 366 different outcomes were introduced. This was broad path
substitution, not a narrow cooldown improvement.

The completed-bar creator audit also invalidated the pre-screen source claim.
Among 22 deduplicated entries with visible exits, exact recovery-6 alignment
fell from 12 to ten. The challenger newly suppressed two matched Jul 24 shorts:

- 12:47:05 UTC: post-BBWP hard-state age two, despite canonical 5m age 212;
- 14:00:45 UTC: hard-state and canonical age zero.

The discrepancy occurred because the pre-screen maturity statement used a
different episode surface than the executable candidate. BBWP range precedence
can reset hard-state age independently of canonical trend age. The claim that
all aligned creator entries were age five or later is withdrawn for this
candidate.

The candidate is rejected with high confidence on the inspected replay. The
artifact is
`data/logs/research/hypervelocity_minimum_structural_age5_20260728.json`,
SHA-256
`b9394e7e4ce16de2d4e3a5aff9cef3f40ff56959e5938e02b35796921109c90b`.
Runtime, faithful configuration, and ML observe-only authority remain
unchanged. New screenshots containing losing exits and reasons, or a sealed
venue-matched shadow window that consistently reverses the liquidation result,
would update this conclusion.

## Creator entry-time positive-unlabeled ranking

The next frozen task asked whether causal bar/regime features rank the exact
creator-selected minute above other hard-BBWP25/recovery-6 eligible minutes.
It did not label the other 10,000-minus candidate minutes as losing trades.
Logistic regression and shallow LightGBM were fixed before inspection, fitted
only on prior UTC days, and evaluated alongside tied and regime-strength-only
baselines. No hyperparameter search or L2 feature was run.

All 35 source decisions were explicitly accounted for: 17 matched the hard
recovery direction, four had the opposite candidate direction, and 14 had no
eligible candidate at that exact completed minute. Fifteen matched decisions
across seven held-out source days were ranked out of sample.

| Ranker | Median positive percentile | Top-10% recall | Mean biased AUC | Worst source day |
|---|---:|---:|---:|---:|
| Uniform tied rank | 0.500 | 10.1% | 0.500 | 0.500 |
| Regime strength only | 0.699 | 52.4% | 0.780 | 0.397 |
| Logistic | 0.534 | 19.0% | 0.433 | 0.081 |
| LightGBM | 0.567 | 0.0% | 0.441 | 0.105 |

Both learned models failed the predeclared association and stability screens.
LightGBM never beat strength on a held-out source day; logistic did so on three
of seven, short of a majority. No learned candidate advances to L2, tuning,
model installation, filtering, or scaling.

The simpler regime-strength rank is a potentially useful timing annotation.
Its better ranks were distributed across Jul 11, Jul 20, Jul 22, Jul 24, and
Jul 25, while Jul 12 and Jul 18 were counterexamples. This does not prove that
a hard strength threshold improves PnL and does not justify an additional
entry gate. Confidence is medium because only 15 matches were out of sample
and screenshot selection may omit losses. Complete new creator logs with
ordinary or weak strength ranks would falsify the association.

Artifact:
`data/logs/research/hypervelocity_source_entry_ranking_20260728.json`, SHA-256
`314d890ef7fa6101dd8a167bf83be7d945024637d06c9c83820f9985ed85db6a`.
Runtime, TUI, faithful configuration, and ML observe-only authority remain
unchanged. A post-run inventory found no new file in `docs/external` after
2026-07-27 19:07:50 EDT.

## Stateful opposite-5m exit falsification

The reverse-engineering document lists trend invalidation as an inferred exit,
not an observed rule. A disabled-by-default stateful trial tested that exact
hypothesis conservatively: after authentic mark liquidation priority, an open
position closed only on a causal opposite 5m structural direction, at adverse
BBO with the taker fee. RANGE, 1m, 15m, confidence, ML, and orderbook pressure
could not trigger it.

The two candidates shared all 2,160 verified archive bundles, authentic
mark/oracle paths, official funding, hard-BBWP25/recovery-6 entries, 70%
isolated allocation, 40x leverage, and the fixed 8% target.

| Candidate | Fills | Targets | Regime exits | Full liq. | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| TP-only control | 408 | 369 | 0 | 39 | $2,466.13 | -97.83% |
| Opposite 5m exit | 577 | 409 | 162 | 6 | $8.10 | -99.96% |

The exit avoided 26 shared control liquidations but converted 65 shared
eventual targets into regime exits. It also rearmed the strategy into 227
candidate-only resolved lifecycles. The 162 regime exits averaged -$350.08;
all three chronological 30-day candidate slices lost money. Lower liquidation
count therefore did not mean lower portfolio risk.

Creator holds contradict the exit hypothesis. The current 5m detector became
opposite during 12 of 33 closed creator positions, and each creator position
remained open until its later recorded disappearance/close. Some first
oppositions preceded the creator close by many hours. Two close-unknown rows
also encountered opposition. The current evidence therefore supports using 5m
as entry direction context more than as a forced exit.

The entry-layer audit further separates detector quality from overfiltering.
The underlying canonical 5m structural side matches 27/35 normalized creator
entries, while the report-only hard-BBWP25/recovery-6 replay direction matches
17/35. The 14 exact-minute no-candidate rows break down into two canonical RANGE rows,
five additional hard-BBWP compression RANGE rows, four recovery-delay rows,
and three strict-breakout-confirmation rows. Four remaining rows have an
opposite replay direction. These counts do not prove that a filter should
be removed, but they identify the next controlled attribution problem.

The opposite-regime exit is rejected with high confidence for this replay and
is not promoted. The active faithful runtime continues to use its canonical
5m-primary classifier, not the report-only hard/recovery transformation.
Artifact:
`data/logs/research/hypervelocity_opposite_regime_exit_20260728.json`, SHA-256
`da8dc0fb9bfce3991d955c0423d9d3637e2fa9e73568b6e6ed1fdeebde4a3518`.
Runtime, TUI, faithful configuration, and ML observe-only authority remain
unchanged.

## Entry-filter factorial closure

A shared-tape 2x2 factorial isolated hard 5m BBWP range precedence and the
six-bar 1m BBWP recovery delay. All four paths consumed the same 2,160 verified
Hyperliquid hourly bundles, 127,814 authentic mark/oracle observations, 2,160
official funding rows, and identical $10,000/70%/40x/8% execution settings.

| Candidate | Fills | Targets | Full liq. | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Canonical control | 277 | 241 | 36 | $27.04 | -99.85% |
| Hard BBWP only | 419 | 370 | 49 | $21.66 | -99.94% |
| Recovery-6 only | 290 | 249 | 41 | $3.26 | -99.98% |
| Hard BBWP + recovery-6 | 408 | 369 | 39 | $2,466.13 | -97.83% |

Neither factor improves the canonical portfolio alone. Their interaction is
materially less bad, but still loses 75.3% with a 97.8% drawdown; its first two
30-day slices lose money and only the final slice grows. The interaction also
causes broad path substitution: only 107 resolved signal identities are shared
with canonical, while 301 are candidate-only and 170 canonical-only.

Source fidelity moves in the opposite direction. Across all 35 normalized
entries, canonical structural direction matches 27 and executable direction
matches 24. Hard-only and recovery-only executable matches fall to 20; the
combined candidate falls to 17. On the 23 outcome-backed rows, canonical
structure/execution match 20/17, versus 18/13 for the combined candidate.
This rejects both filters as source-faithful runtime changes and rejects their
interaction as a stable economic repair. The interaction remains useful only
as a documented research counterexample to simplistic bar-count reasoning.

Confidence is high that neither factor alone helps this replay and medium that
the interaction is non-viable outside it. A later venue-matched window that is
profitable, improves drawdown in every chronological slice, and retains or
improves creator entry eligibility would falsify the rejection. Artifact:
`data/logs/research/hypervelocity_entry_filter_factorial_20260728.json`,
SHA-256
`1c56f8cf8b53aef2b253b6ebe8f675a883c6fb87e55471623cc2fad0071b01c3`.
Runtime, TUI, faithful configuration, fixed target, and ML observe-only
authority remain unchanged.

## Executable-miss and strength closure

The six outcome-backed canonical execution misses were audited separately from
structural direction. Three are early reversals and three have the correct 5m
breakout side while awaiting the narrow 1m confirmation. The existing
1m-trend confirmation challenger recovers the latter rows but remains rejected
because it worsened the exact source-window portfolio and drawdown.

All three early reversals agree with the price-only Pine direction and have
source-aligned RSI/Pine pressure, but even a strict combination of recent Pine
shift, dominance, RSI, and mature opposing canonical state marks 18,179 bars
and 6,357 rising edges. L2 does not isolate them: creator-side OBI5 spans both
signs and creator-side OBI20 is opposed on all three. No reversal override or
orderbook gate advances.

Causal regime strength also fails as a stable hard gate or selective repeated-
entry condition. Canonical target/liquidation strength distributions overlap;
a strength-60 fixed-lifecycle screen fails the latest 30-day slice. Strength-50
on the hard/recovery interaction removes 19,401 directional bars and lowers
creator eligibility to 14/35. Strength-40 on mature target continuation removes
24 candidate-only eventual targets and only two liquidations.

The exact strength-50 stateful replay was completed to avoid treating the
source/performance screen as an implicit trial gate. It worsened the
hard/recovery control from $2,466.13 and -97.83% drawdown to $244.62 and
-99.37%, despite reducing full liquidations from 39 to 35. Partial
liquidations rose from 15 to 25, creator matches fell from 17/35 to 14/35, and
the latest 30-day slice collapsed to 0.0144x. No strength candidate advances
to runtime.

Detailed evidence, limitations, and falsifiers are recorded in
`docs/plans/2026-07-28-hypervelocity-executable-miss-audit.md`. The missing
creator losing-trade lifecycle remains the highest-information unknown.
The stateful artifact is
`data/logs/research/hypervelocity_hard_recovery_strength50_20260728.json`,
SHA-256
`1b6ad570f187efe1d5c02b9038956dbc5babdc9385e55ab179ad23cc5e19602a`.
