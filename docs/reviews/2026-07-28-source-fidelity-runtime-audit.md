# Hypervelocity Source-Fidelity Runtime Audit

## Problem restatement

Compare the current faithful runtime and regime detector directly with the
creator-derived evidence in `docs/external`. Separate observed behavior from
the reverse-engineering document's hypotheses, identify remaining mismatches,
and avoid adding filters that move the implementation farther from the source.

No runtime, TUI, configuration, target, allocation, leverage, or ML authority
is changed by this audit.

## Evidence boundary

- The original document summarizes 37 rows over 16 days, but simultaneous
  split rows and later reconciliation produce 35 logical entries.
- Twenty-three entries have visible outcomes; the remaining rows provide
  direction/timing evidence with weaker exit evidence.
- Screenshots are selected and omit losing fill/exit details.
- The Jul 27 supplemental CSV is hash-linked to the position-history image and
  retains the visible Jul 24 short and Jul 25 long. A second image overlaps
  those rows. The remaining active-short image lacks a usable event timestamp
  and resolved exit, so it is visual context rather than a labeled outcome.
- The source document explicitly labels many stop, indicator, sizing, funding,
  15m, orderbook, and leverage rules as inferred or requiring investigation.
  Its later “perfect fit” and “maximum synergy” language is not empirical proof.
- Runtime decisions use completed 1m/5m/15m bars. Source timestamp comparisons
  shift each bar to decision-time availability.

## Traceability matrix

| Behavior | Evidence class | Current runtime | Assessment |
|---|---|---|---|
| BTC at fixed 40x | observed/user-confirmed | 40x venue-capped | aligned |
| 8% margin target | observed/user-confirmed | fixed 8% gross target | aligned |
| maker entry | observed | post-only limit | aligned subject to venue differences |
| 70% isolated margin | user-confirmed | 70%, isolated | aligned; not derived from the old 32% hypothesis |
| one logical BTC position | user-confirmed | one-way, max one | aligned; split rows are treated as one logical position |
| no RANGE entries | user-confirmed | `RANGE` maps to no entry | aligned |
| hold open trade through RANGE | user-confirmed | target remains active | aligned |
| 5m primary direction | measured | 5m structural primary | strongest tested source match |
| 15m direction | inferred context | telemetry, non-veto | source-compatible; hard veto would miss observed reversals |
| 1m tactical trigger | partially inferred | required only for 5m breakout confirmation | three observed breakouts remain overfiltered |
| repeated same-side entries | observed | requires post-trade structural reset | unresolved source mismatch |
| tight/trailing stop | inferred | none | not established; tested simple stops failed |
| opposite-trend exit | inferred | none | rejected by creator holds and stateful replay |
| OBI/orderbook direction gate | inferred | telemetry/execution only | no causal gate supported |
| funding reversal entry | inferred | funding cost only | no entry authority supported |
| dynamic leverage/strength size | inferred | fixed 40x/70%; strength annotation only | no scaling authority supported |
| ML entry filtering | unobserved | observe-only | aligned with current evidence quality |

## Measured detector fidelity

Across all 35 normalized creator entries, canonical 5m structural direction
matches 27 and executable direction matches 24. Five rows have no executable
candidate: two canonical RANGE rows and three same-direction breakouts awaiting
the narrow 1m confirmation. Six executable rows point opposite the creator.

Across the 23 outcome-backed entries, 5m structure matches 20 and executable
direction matches 17. None of the six executable misses is a false RANGE:
three are early reversals against the current 5m/15m state and three are
same-direction 5m breakouts awaiting 1m confirmation.

This is evidence that current RANGE handling is materially stronger than the
rest of the entry-timing reconstruction on the selected source set. It does
not establish population accuracy because losing entries and no-trade market
periods are missing.

## Challengers already falsified

- A hard 15m/opposite-5m exit conflicts with creator holds and reduced the
  stateful control from $2,466.13 to $8.10.
- Relaxing breakout confirmation recovered three source directions but
  worsened the exact source-window portfolio and drawdown.
- Hard BBWP precedence and recovery delay reduced executable creator matches
  from 24/35 to 17/35; neither factor helped alone.
- Strength 50 reduced matches again to 14/35 and worsened stateful final equity
  from $2,466.13 to $244.62.
- Simple OBI, Pine/RSI reversal, stop, timeout, and same-side continuation
  rules were either too broad or economically unstable.
- The source-associated target pullback transition appeared in 9/14
  target-like same-side windows (8 without a 5m reset), but as a stateful
  trigger it doubled full liquidations from 40 to 80 and reduced final equity
  from $3.8034 to $0.00175. It introduced 439 candidate-only resolved
  lifecycles and is too broad for execution.

These results reject the tested implementations, not every possible version
of their underlying ideas.

## Remaining failure modes

1. Runtime blocks same-direction re-entry until the 5m structural side resets,
   while creator evidence contains repeated entries within uninterrupted
   structural episodes. Removing that barrier broadly caused overtrading and
   liquidation; the selective re-entry trigger remains unknown.
2. Three successful creator reversals occur before the current 5m detector
   flips. A broad reversal override marks thousands of bars and is not usable.
3. The creator's losing-trade exit mechanics remain absent. At 70% margin and
   40x, this unknown dominates simulated tail risk.
4. The screenshots come from a different execution venue/application. Entry
   direction can be compared, but private queue rank and exact friction cannot.

## Recommendation and trade-offs

| Option | Source fidelity | Tail-risk evidence | Decision |
|---|---|---|---|
| Keep canonical runtime | highest tested | still catastrophic in 90-day replay | retain as current baseline |
| Promote hard BBWP/recovery/strength | worse | unstable or worse | reject |
| Remove regime-reset re-entry barrier broadly | closer to repeated runs | severe overtrading/liquidation | reject |
| Pullback-transition re-entry | compatible with 9/14 selected windows | doubled full liquidations | reject exact trigger |
| Obtain complete target/no-re-entry logs | highest information value | no immediate runtime change | recommended evidence step |
| Add stop/funding/OBI/15m gates now | mostly hypothesis-driven | tested simple forms failed | do not promote |

The creator screenshots have now been used to test one selective trigger, and
the association did not survive stateful execution. The next source-driven
step requires complete target opportunities, including instances where the
creator did not re-enter. Candidate features must be measured at decision time
and compared with matched no-re-entry opportunities. Any result must retain
the no-trade cases and be replayed statefully before runtime promotion.

Confidence is high that the current canonical entry layer is more faithful
than every tested hard-filter challenger and medium that 5m primary is the
creator's actual internal method. Creator documentation of the exact indicator
or a complete timestamped entry/no-entry ledger would update the latter claim.

## Upstream selective-recipe simulator fidelity

The exact Recipe B/C implementation was traced to Hypertrader commit
`7c26fef054bbf216f9d6a270c06f8c9bc1eef679`, contained in the pinned master
revision. It confirms the displayed sessions, directions, 5m onset semantics,
20-bps/130-point target, maximum holds, and absence of a stop.

The source also resolves why its 26/26 historical headline is not comparable
to the venue replay. The historical runner loads Binance closes, enters at the
nearest 5m close, and tests targets against later nearest closes. It does not
model maker admission, queueing, intrabar liquidation, or a stateful 70%
isolated-margin portfolio. The recipe describes the result as in-sample and
requests forward validation. Consequently, the headline validates the source
screening rule under its own simplified measurement contract; it does not
validate executable Hyperliquid profitability.

The research adapter now pins SHA-256 identities for the recipe implementation
and its historical runner in addition to the classifier dependencies. A source
bundle missing either file, or containing a modified copy, fails validation.
Confidence is high from directly inspected source. Authenticated creator
production fills and account-level liquidation records would be the decisive
falsifier for assumed live equivalence.

Native Hyperliquid 5m candles were also compared with 5m bars resampled from
the venue's 1m candles over the five days available in both local caches. Two
of 1,441 primary labels and 18 secondary labels differed, but the complete set
of nine selective B/C event rows was identical by recipe and timestamp. This
reduces the likelihood that 1m-to-5m aggregation caused the source-replay
discrepancy. Confidence remains medium because five days may not represent
other volatility states.

Post-closure verification passed 1,044 non-network Python tests with four
deselected and 31 warnings, 33 Rust TUI tests, and all task-scoped lint,
format, size, artifact, accounting, hash, and fail-closed status checks.

## Selective-recipe population and execution update

The source's advertised 15-B/11-C population cannot be reproduced from the
committed Hypertrader tree. Its historical runner consumes an uncommitted
SQLite label database and does not regenerate labels. The pinned formula
produces 2 B/77 C events on the reconstructed 90-day series and 1 B/25 C on
the runner's trailing-8,000-row equivalent. None of the five visible source B
rows remains `BREAKOUT/BK_UPWARD` under the reconstructed labels, while all
three visible C rows remain `TREND_DOWN`.

The two reconstructed B events failed a separate authentic replay: one maker
intent canceled and one timed out after four hours, ending at $6,878.74 touch
and $6,853.18 under both book-through and public trade-through. No target or
liquidation occurred, and no fresh B event exists. Conversely, the one fresh
Recipe C event supports the experimental short-follow direction: fade-long
canceled, while short-follow filled and completed its target for +$476.87 net
under public trade-through. One event is not enough to establish forward edge.

Confidence is high in the observed population mismatch and replay accounting,
medium in the current short-follow development lead, and low in any ML model
trained from 25 robust directional labels. A checksum-linked source SQLite
export plus its generating classifier revision would falsify or refine the
population conclusion. Runtime, TUI, faithful configuration, 8% target, and
observe-only ML authority remain unchanged.

Post-update verification passed 1,105 non-network Python tests with four
deselected and 31 warnings, all 33 Rust TUI tests, and 36 focused
source/replay tests. Task-scoped lint, formatting, file/function sizes,
artifact assertions and hashes, diff hygiene, and fail-closed CLI status also
passed.

## Tight-stop closure and new selective-recipe evidence

The older reverse-engineering note's previously untested 2-3% gross-margin
stop was bracketed once at 4% and replayed without changing entries, target,
sizing, re-entry, or regime behavior. Stops at 2%, 3%, and 4% produced target
rates of 15.7%, 23.8%, and 30.5%, and ended at $2.12, $3.29, and $5.38 from
$10,000. Every candidate lost money in every 30-day slice. The family is
rejected; artifact SHA-256:
`17a7aaa306a70fa2e9f6a2fc413d787854916e366ec0048f216ec179a315fb9b`.

New creator screenshots expose a different report-only selective classifier:
BTC Recipe B is an Asia-session upward-breakout arm with confidence at least
0.6 and a four-hour maximum hold; BTC Recipe C is an EU-session long fade of
`TREND_DOWN` with a 24-hour maximum hold. Both target +20 price bps/8% at 40x
and explicitly use no stop. The July search reports B 15/15 and C 11/11, but
the UI also says capital off and to validate forward, so 26/26 is development
selection rather than proven live performance.

Eight visible backtest rows and six newer live position-history rows are
normalized under `docs/external/`. The newer scorecard is retained separately:
43 positions, $408.06, and 39W/4L. The source images falsify the old universal
no-countertrend claim, but do not establish that the live BTC strategy uses
these research recipes. Current 5m structure matches the underlying trend in
all eight visible B/C fills; its strict breakout event does not reproduce the
creator's repeated `BK↑` onsets. The next challenger must therefore freeze a
source-matched onset definition and test B/C independently, not install a
broad trend or confidence gate.

## Symmetric trend-onset closure

The existing `UTC-5` conversion for the six Jul 27 creator-history rows was
validated against exact Hyperliquid one-minute candles: all six displayed
entry prices fall inside the inferred minute at `+5h`, versus zero at the
calendar-Eastern `+4h` conversion. None of the displayed exit prices fit those
same `+5h` minutes. This is high-confidence evidence that the visible rows use
the retained entry-time convention, although authenticated creator trade
timestamps would supersede the inference.

A report-only two-sided extension then preserved source Recipe B, preserved
the profitable experimental EU `TREND_DOWN` short onset, and added the exact
mirrored EU `TREND_UP` long onset. It used the same 60-second maker freshness,
100-bps completed-5m signal-range ceiling, 70% isolated allocation, 40x,
8% target, authentic funding/mark/oracle context, and no stop.

The extension failed all three execution assumptions. Touch ended at
$3,421.74, book-through at $4,749.41, and public-trade-through at $2,885.95;
maximum drawdown ranged from -84.39% to -87.37%. Under strict public
trade-through, 16 long targets were outweighed by six long liquidations and
two total long time exits. The one-sided short control remains profitable
under all three assumptions, including $25,600.17 and 20/20 targets under
public-trade-through.

This rejects simple direction symmetry, not long trading in general. Four of
six strict-fill long liquidations occurred after the source-grounded four-hour
Recipe B horizon, while two occurred within 70 minutes. A frozen four-hour
long follow-up can test whether stale long exposure is the dominant mechanism;
it cannot be promoted from this development observation. Runtime, TUI,
faithful configuration, and ML observe-only authority remain unchanged.

## Four-hour long-horizon closure

The source-grounded four-hour follow-up changed only the mirrored EU
`TREND_UP` long maximum hold. It reduced strict long liquidations from six to
two and improved strict maximum drawdown from -84.39% to -64.82%, but it
created five strict long time exits and worsened long net trade PnL to about
-$17,055.40. Strict final equity improved to $6,207.82 only because earlier
long exits allowed more later short profits. Touch ended at $3,070.07 and
book-through at $4,862.66; all three remained unprofitable.

Hold-duration tuning is therefore closed. The exact pinned source and the
recent creator rows both point back toward selective countertrend/range-recovery
longs rather than symmetric `TREND_UP` following: the four Jul 27 creator longs
occur under pinned `TRANSITION`, `TREND_DOWN`, `TREND_DOWN`, and `RANGE`
states at their validated entry minutes. That association does not itself
authorize an entry rule; it identifies the next bounded source-aligned replay.

## Current-revision short-arm isolation

The remaining source-follow package was decomposed once more so an unsupported
long arm could not mask the short result. The frozen current-revision short arm
uses confirmed `TREND_DOWN` onsets during 07:00-16:00 UTC, a 100-bps
completed-5m range ceiling selected on development evidence, and the existing
60-second maker lifecycle. Its 90-day final equity was $23,366.73 under touch,
$35,678.79 under one-tick book-through, and $25,600.17 under public
trade-through. The strict path contained 20 fills, 20 targets, zero
liquidations, and positive net PnL in each fixed 30-day slice.

Two subsequently available frozen events, Jul 27 and Jul 28, also filled and
targeted. That is supportive but too small for a reliable live expectancy
estimate. The literal legacy fade-long population is rejected: strict replay
ended at $133.39 with 12 liquidations and -99.46% drawdown. No long arm is
validated, so this result is annotation-only and cannot reproduce the source
strategy's full bidirectional cadence. The immutable contract and artifact
hashes are recorded in `configs/research/hypervelocity_source_follow_short.toml`
and `docs/reviews/2026-07-28-source-follow-short-candidate.md`.
