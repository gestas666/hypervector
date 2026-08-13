# Bidirectional BTC canary source-fidelity checkpoint

Date: 2026-07-31

## 1. Problem restatement

Determine whether the armed BTC source-follow canary is genuinely
bidirectional and document how its executable contract differs from the
creator's observed live-position history and the creator repository's newer
paper-only research cells. This checkpoint is observational. It does not alter
the running process, place an additional order, or grant ML authority.

## 2. Evidence boundary

- The normalized manual-position export contains 37 BTC rows from 2026-07-09
  through 2026-07-24: 17 long and 20 short. Current reconciliation removes one
  duplicate and collapses two true split positions, yielding 34 logical entries
  (15 long and 19 short).
- The later visible position-history rows also contain both directions: four
  long and two short on 2026-07-27.
- Screenshots are selected evidence. They establish observed directions and
  displayed outcomes, but do not provide a complete no-entry population or
  authenticated venue order lifecycle.
- The Hypertrader selective classifier identifies itself as research and paper
  only. Its BTC primary cells are an upward-breakout long and a
  `TREND_DOWN` fade-long. They are not proof of the creator's production entry
  policy.
- A read-only remote audit found Hypertrader `master` at
  `8a784ea1b6bdee982b731ebaa1db5574c774b3df` dated 2026-07-29. Relative to the
  pinned classifier revision, it adds a separate paper-only
  `BREAKOUT/BK_DOWNWARD` short cell. The underlying classifier formula remains
  unchanged in the files already compared by the venue audit.
- Hypertrader `main` points to the older 2026-05-06 commit
  `891b487a6dd349845eadd3709c637cb3756e23bd`. Its commit-local diff only expands
  Polymarket BTC/ETH Up/Down discovery from 15-minute to 5-minute and 15-minute
  windows. It does not modify the Hyperliquid classifier, execution, re-entry,
  exit, or sizing code and supplies no new source-follow strategy evidence.
- The repository's separate `impulse_reentry_engine.py` is explicitly a
  dry-run AI-Agent experiment, not the creator's live strategy. Hypervector
  already reconstructed 4,219 of its BTC simulated lifecycles from 2026-05-05
  through 2026-06-17 and tested uptrend-long, downtrend-short, range-long, and
  range-short lanes out of sample. Every lane remained net negative. Their
  gross moves support only 0.50 through 0.86 bps per side at break-even before
  slippage, below the frozen canary's 1.50 bps maker fee. Its combined L2
  pressure/velocity/cooldown rule is therefore rejected as an executable
  addition, not rediscovered as a missing source-follow trigger. Evidence is
  `data/cache/replay/BTC_impulse_replay_provenance.json` and the four
  `data/logs/research/autotune_l2_replay_*_20260725T081034Z.json` artifacts.

## 3. Armed executable contract

The live process loads
`hypervelocity_source_follow_bidirectional_minrange12_alloc35_live_canary_v1`
and the backend ledger reports `execution_sides=[long, short]`.

| Confirmed completed-5m event | Executable action |
|---|---|
| `TREND_UP` primary onset | long |
| `BREAKOUT/BK_UPWARD` primary onset | long |
| `TREND_DOWN` primary onset | short |
| `RANGE`, `TRANSITION`, `UNKNOWN` | no entry |
| `BREAKOUT/BK_DOWNWARD` | annotation only |

Additional frozen entry conditions are source confidence at least 0.70,
completed-bar range from 12 through 100 bps, one 60-second post-only entry
pulse, one BTC position, and no reversal while a position is open. The canary
uses 35% isolated margin, 30x leverage, a $1,700 notional cap, an 8% gross
margin target, no fixed stop, and a 24-hour maximum hold.

## 4. Alignment and deliberate deviations

| Behavior | Creator evidence | Canary | Assessment |
|---|---|---|---|
| Trade both directions | 17 long / 20 short manual rows | long and short executable | aligned |
| Avoid range entries | user-confirmed and source-compatible | no entry in `RANGE` | aligned |
| Hold an existing trade through range | user-confirmed | target/max-hold remains active | aligned |
| One BTC position | user-confirmed | max one | aligned |
| Maker entry | observed | post-only maker | aligned subject to queue uncertainty |
| 8% displayed target | observed | 8% gross margin | aligned in margin units |
| Target price distance | about 20 bps at 40x | 26.67 bps at 30x | deliberate canary deviation |
| Leverage and margin | 40x and historically larger allocation | 30x and 35% | deliberate canary risk deviation |
| Same-side re-entry | repeated runs are observed | requires a fresh primary onset | unresolved fidelity mismatch |
| Countertrend long | newer paper Recipe C and some later rows support investigation | observe-only | unresolved, not promoted |
| Downward-breakout short | newer paper-only cell | annotation-only | rejected exact cell after venue replay |
| ML filtering or sizing | no executable evidence | annotation collection only; inference inactive | aligned with evidence quality |

The compatibility field `metalabel_mode=observe` does not mean a model is
scoring this canary. The source-follow executor does not load a bundle or emit
probabilities. Its explicit policy is annotation collection with inference,
filtering, scaling, and execution authority all disabled. Model eligibility
remains at least 200 resolved trades, 25 liquidation labels, and five purged
walk-forward folds containing both classes. The prior 213-trade venue-matched
challenger did not beat the fold-local base-rate log loss and was not installed.

The generic project-local bundle is also not a candidate for this canary. Its
metadata contains only 30 samples, 97.22% Binance bars, zero nonzero feature
gains, and mean CV log loss 0.6214 versus a 0.5799 base rate. It is technically
loadable but is neither Hyperliquid/source-follow matched nor economically
qualified. Future training now records exact LightGBM, joblib, and
scikit-learn versions, and calibrator deserialization fails closed on a
scikit-learn version mismatch instead of suppressing the warning.

The exact downward-breakout short cell was not omitted merely to make the
strategy one-sided. Its venue replay produced PF below 0.56 at every tested
20x-40x leverage and lost compounded equity. The result rejects that exact
entry/exit contract, not every possible short-breakout model.

The lack of automatic close-and-reverse is also deliberate. Thirteen
tracker-only creator closures have no authenticated fill, but close-minute
Hyperliquid proxies classify exactly four as adverse, matching a later
four-loss scorecard, and every adverse row precedes an opposite creator entry
by 36 through 143 seconds. The exact source-backed hypothesis was therefore
tested: close only on a fresh executable opposite entry, pay the adverse taker
exit, then submit the reverse maker order. Across seven gap-free reset blocks
it reduced liquidations from 53 to 24 but lowered final-equity sum from
$22,645.61 to $13,483.36, increased fees, and produced zero profitable blocks.
It remains disabled. Exact creator exit fills or a larger frozen forward sample
that separates recoveries from actual losses would update this decision. See
`docs/reviews/2026-07-29-hypervelocity-close-reverse.md`.

One configuration-identity field was found to understate the implemented
breakout contract. The runtime has always routed a breakout only when its
secondary label is `BK_UPWARD`; a bare `BREAKOUT` or `BK_DOWNWARD` cannot enter.
The source profile nevertheless emitted `breakout_requires_direction=false`.
This was a telemetry defect, not an execution defect. The profile now derives
the field from its validated strategy contract, and the bidirectional profile
reports `true`. A reproducing profile test failed before the correction; 51
source-follow profile, classifier-runtime, paper-session, and live-engine tests
pass afterward. The already-running canary is not restarted and retains its
immutable startup identity, so that single field in this run must be read with
this correction. Subsequent runs will emit the accurate value. The live profile
fingerprint previously covered stable profile IDs, the base-profile checksum,
the pinned source revision, and wrapper settings, but not the resolved regime
contract. It now also hashes the resolved position, regime, risk, exit,
execution, cost, and metalabel policies. A regression test proves that changing
the direction requirement while retaining the same profile ID changes the
fingerprint. This prevents future code-level policy drift from appearing under
the current run's configuration identity. A disarmed load of the corrected
canary reports `breakout_requires_direction=true`, execution sides `long` and
`short`, and profile fingerprint
`b6f063d406126de60fa700c9f7132ec82ed76fad3746f0f5f10d5e2279813571`,
distinct from the armed run's prior
`c9d096fead98e918844276b84936e532b88f4a7764f865c6e1a9475d5e130349`.

An exact live decision/lifecycle review also reproduced four timing and
journaling defects in the implementation loaded by this run. Decision
freshness used the loop-start time rather than a new timestamp after venue
reconciliation and REST candle fetching; an operator STOP created during that
work was not rechecked before decision handoff; restart recovery calculated an
existing position's opening fill correctly but discarded it when placing the
replacement target; and a target filled before its first reconciliation could
flatten without a verified target-close event. Failing tests were added for
all four paths. The corrected runner rechecks time and STOP immediately before
handoff, while the lifecycle preserves the venue entry timestamp and attributes
an immediately filled target from matching venue fill identity.

These changes do not alter classification, entry eligibility, sizing, or the
8% target. Sixty-four combined source-follow profile, configuration, regime,
runner, paper-session, and live-engine tests pass. The armed process is not
hot-reloaded or restarted; it retains its startup-loaded implementation. Its
observed decision latency has remained below 20 seconds and it has emitted no
source event, so none of the four corrected edge paths has occurred in the
current ledger. A post-fetch decision entering at or after pulse expiry, an
order after a contemporaneous STOP, a restart-shifted hold deadline, or a
venue-matched target fill without a close event would falsify the correction
in a subsequent run.

The aligned `TREND_UP` long is executable because the final strategy must test
both directions, but it is not a proven edge. Earlier symmetric historical
replay was unprofitable. Exact creator long recipes and adjacent long
challengers therefore continue in an independent no-submit observer so their
forward outcomes can be compared without colliding with live position
authority.

## 5. Live checkpoint

At this checkpoint the armed run is
`btc-source-live-1785528237389`. Four completed decisions have been recorded;
all four are `RANGE`, with zero long signals, short signals, order intents,
fills, fees, funding, realized PnL, or faults. Account value is $153.61038949
and the venue position is flat. The event recorder continues to persist L2,
public trades, and asset context every 30 seconds.

No-trade behavior in this window is expected from the frozen contract and is
not evidence of profitability or failure.

### Active-run venue and RANGE audit

A later explicitly identified run,
`btc-source-live-1785530545992`, was frozen through 21:21:32 UTC in the
report-only artifact
`data/logs/research/source_follow_live_canary_20260731T212115Z.json`.
It contains eight executable completed-5m decisions, all `RANGE`, eight holds,
zero eligible signals, zero order intents, zero fills, and zero faults.

All eight executable candles are covered by independently recorded public
trades and all eight are venue-equivalent on OHLCV. Six are identical under a
deterministic `exchange_ts_ms, trade_id` ordering. The other two have identical
high, low, and volume while their REST open or close is one of several prices
recorded at the same exchange and receipt timestamp. Because the venue tape
does not expose an ordering within those timestamp ties, they are retained as
boundary-ambiguous rather than mislabeled as corrupt. All eight decision bars
also have continuous L2 coverage under the declared six-second diagnostic
threshold, with no negative receive lag and no explicit stream gap.

The 90 warm-history rows predate portions of the continuously running recorder:
63 are therefore explicitly uncovered and are not used to claim recorder
parity. This does not affect the eight executable decisions above.

A separate exact-revision diagnostic replay used the same 30-day/600-bar warmup
and Hyperliquid 5m feed through pinned revision `ad15f2bd`. Raw and confirmed
states both remained `RANGE` for all eight decisions. ADX percentile rank ranged
from 0.073 to 0.303, below the source classifier's 0.40 range boundary, while
EMA alignment was bearish and neither strict range-break direction fired.
This supports a genuine low-strength bearish range interpretation rather than
a stuck hysteresis state. A raw `TREND_DOWN` sequence suppressed into confirmed
`RANGE`, a decision candle not present in the independent trade tape, or a new
creator log classifying the same timestamps as directional would falsify that
assessment.

A later immutable checkpoint through 21:43:08 UTC contains 12 executable
decisions. All 12 remain `RANGE` holds with no onset, order, fill, funding,
close, or fault. Independently recorded public trades cover all 12 decision
candles: 10 are exact under deterministic ordering and two are timestamp-tie
boundary ambiguities, while all 12 are venue-equivalent. L2 is continuous and
quality-usable for all 12 decision bars. Artifact:
`data/logs/research/source_follow_live_canary_20260731T214305Z.json`, SHA-256
`99b7b8de5cf8791cda9f60f70ac852ce1c59f6b4d863a2271c05f59b167a7416`.

The next immutable checkpoint through 22:09:21 UTC contains 17 executable
decisions. All 17 remain `RANGE` holds with no onset, order, fill, funding,
close, or fault. Public trades cover all 17 decision candles: 14 are exact and
three have only venue-timestamp boundary ambiguity; all 17 are venue-equivalent.
All 17 also have continuous, quality-usable L2 with zero explicit stream gaps.
Artifact:
`data/logs/research/source_follow_live_canary_20260731T220700Z.json`, SHA-256
`074aef57185b93951631ae83d4abee2cafde7905c703deb88c56de8a8e500d99`.
The running process predates the newly explicit raw-regime and metalabel-policy
telemetry, so those fields are correctly reported as missing for this session
rather than reconstructed after the fact.

A 23:35 UTC audit then exposed an operational distinction in the evidence
pipeline: immutable recorder parts were current, but the DuckDB research
projection had not imported the newest parts. That preliminary artifact
reported four uncovered decision bars and is preserved as
`source_follow_live_canary_20260731T233500Z.json`; it is superseded for market
coverage, not deleted or rewritten. The recorder itself was not stale: fresh
L2, public-trade, and asset-context parts had continued to land every 30
seconds.

The documented idempotent import added 144 immutable files: 270 L2 rows, 1,568
public trades, and 1,419 asset-context rows. The corrected 23:39 UTC checkpoint
then covered all 35 executable decisions. All 35 were venue-equivalent against
the independent public tape, 30 matched exactly, and five retained only
same-timestamp bar-boundary ambiguity. L2 was continuous across all 35 bars;
34 passed the conservative quality contract. The remaining 23:00 UTC bar is
explicitly censored because the recorder documented a WebSocket disconnect at
23:01:39 UTC followed by reconnection about 1.8 seconds later. The executor
reported no fault, and no decision exceeded the 60-second entry pulse.
Artifact:
`data/logs/research/source_follow_live_canary_20260731T233900Z.json`, SHA-256
`332a17317eb9b4b53a5de1976d0217dbb837ecb8c6a669cc1ae915c985b03e41`.

This checkpoint validates capture, import, and audit as separate lifecycle
stages. Future audits must import recorder parts first; otherwise uncovered
bars diagnose a stale research projection rather than proving lost raw data.

A latency-aware checkpoint through 22:22:15 UTC contains 20 executable
decisions, again all `RANGE` holds with no lifecycle event or fault. Decision
observation latency is 6.395 seconds minimum, 7.957 seconds median, and 19.361
seconds maximum against the frozen 60-second entry pulse. Zero decisions and
zero source events arrived at or after pulse expiry. Independent trades cover
all 20 candles (17 exact, three timestamp-boundary ambiguous, all 20
venue-equivalent), and all 20 have continuous quality-usable L2. Artifact:
`data/logs/research/source_follow_live_canary_20260731T222300Z.json`, SHA-256
`3aa9184863b626a12413f828d189d541a7911910b1e678788458f383b00e35fb`.
This falsifies the provisional suspicion of REST decision delay for the
observed window; a future directional source event observed at or after its
pulse expiry would reopen that failure mode.

The next immutable checkpoint through 22:34:44 UTC contains 22 executable
decisions, all `RANGE` holds with no eligible signal, order intent,
acknowledgement, fill, target, funding, close, or fault. Decision observation
latency remains inside the 60-second pulse: 6.395 seconds minimum, 8.408
seconds median, and 19.361 seconds maximum, with zero late decisions. Public
trades cover all 22 decision candles; 18 are exact and four have only
venue-timestamp boundary ambiguity, while all 22 are venue-equivalent. All 22
also have continuous quality-usable L2 with zero explicit gaps or negative
receive lags. The account remains flat with $153.61038949 withdrawable and no
open orders. The independent long observer has no outcome ledger because no
directional source event has occurred; this is an observed zero-candidate
result, not evidence of long expectancy. Artifact:
`data/logs/research/source_follow_live_canary_20260731T223443Z.json`, SHA-256
`4abd050b2b01be86e17a5a13e87bf1caa8324c52a8cba2fea68c560b9aba33d2`.

A separate disarmed process then fetched a fresh 30-day Hyperliquid REST
warmup and replayed the checksum-pinned classifier through the 12 completed
bars from 21:40 through 22:35 UTC. Primary state, confidence, onset, and source
event matched the armed ledger on all 12 timestamps. Raw and confirmed state
were both `RANGE` throughout; ADX percentile rank ranged from 0.240 to 0.348
against the source's 0.400 RANGE boundary, EMA alignment remained bearish, and
neither directional range-break flag fired. This is fresh-process/feed parity
for the observed window, not an independent validation of the classifier's
economic correctness. A creator directional label on these same timestamps or
an independent replay disagreement would falsify the present RANGE assessment.

Raw-regime reset-and-return was also checked as a possible selective same-side
re-entry event. Six of 20 source re-entry windows contained the raw event, but
all six also contained a normal confirmed reset; hidden raw resets numbered
zero. That mechanism is rejected rather than promoted. Evidence and falsifiers
are in `docs/reviews/2026-07-31-source-reentry-raw-reset.md`.

Fresh recorder timing was also checked from its 20:09:21 UTC process start.
No L2, trade, or context row had a negative receive lag. Twelve trades exceeded
the six-second replay freshness threshold, but every one was a startup backlog
batch received at 20:09:23 UTC. After excluding the first 30 seconds, 1,419 of
1,419 trade IDs were unique and none had negative or greater-than-six-second
lag. The maximum steady-state L2 receive gap was 5.693 seconds and the maximum
asset-context receive gap was 1.500 seconds. This supports using the current
tape for forward attribution; later reconnect gaps can still censor an
affected lifecycle.

### Forward paths after live RANGE decisions

A report-only forward-path audit used the exact active run and independently
recorded Hyperliquid public trades through 23:06:41 UTC. It evaluated the
26.667-bp price move corresponding to the frozen 8% gross-margin target at
30x, without inventing a trade side or fill. Of 28 RANGE decisions, 27 had
quality-usable five-minute paths, 25 had usable 15-minute paths, 22 had usable
30-minute paths, and 16 had usable 60-minute paths. No usable path touched the
target-scale move in either direction. Median absolute ending displacement was
1.75, 4.45, 7.86, and 4.93 bps across those respective horizons.

The report identifies these as one contiguous RANGE episode covering only
2 hours 20 minutes, not 28 independent trials; it therefore does not establish
RANGE accuracy generally. It does show that relaxing RANGE would not have
exposed a target-scale move in this specific forward window. The result is
falsified by a future quality-usable
RANGE path repeatedly reaching 26.667 bps in one direction, or by a matching
creator directional entry during the same timestamps. Artifact:
`data/logs/research/source_follow_range_forward_20260731T231500Z.json`, SHA-256
`bcad53905f3339fb136e878c58d718985193fd0271cd4af76c332e593e07e52c`.

An earlier immutable artifact at `20260731T230600Z` exposed a diagnostic bug:
one-sided excursions could be negative when every trade stayed below or above
the decision reference. A reproducing test now floors maximum favorable
excursions at zero. The `230700Z` artifact corrected that metric but predated
the explicit episode count. Both earlier artifacts remain preserved and are
superseded by the episode-aware artifact above.

A fresh-process replay then extended the pinned classifier through the first
non-RANGE decision. Raw state changed from `RANGE` to `TRANSITION` at 22:50 UTC
and remained there; the confirmed state changed at 23:00 after the source
hysteresis. ADX percentile rank had crossed above the 0.40 RANGE threshold,
but EMA alignment remained bearish and neither directional range-break flag
fired. The confirmed transition bar spanned 7.154 bps, below the frozen 12-bp
entry floor, and emitted no source event. This supports retaining the current
RANGE boundary while waiting for a genuine directional onset; a fresh replay
disagreement or a directional creator label on this interval would update that
assessment.

### Frozen-policy event cadence

The exact bidirectional live policy was also audited for signal frequency on
25,920 completed five-minute bars from the verified 90-day Hyperliquid cache.
The cache contains 129,532 native `hl` minutes and 68 explicitly labeled
`hl_gap_fill` minutes. The pinned source revision generated 341 confidence-
qualified directional onsets before the range bounds; the frozen 12-to-100-bp
signal range admitted 175 events: 79 long and 96 short. The trailing 30 days
contained 57 eligible events, split 33 long and 24 short.

Eligible-event gaps had a 9.04-hour median, 15.23-hour 75th percentile,
22.79-hour 90th percentile, and 91.25-hour maximum. This establishes that the
policy is not inherently weekly, but also that multi-day waits occur. Signal
counts do not measure maker fills, one-position suppression, profitability, or
the time of the next event. A live event rate persistently outside this
historical distribution, after equivalent data coverage, would falsify the
operational cadence expectation. Artifact:
`data/logs/research/source_follow_event_frequency_20260731T232800Z.json`,
SHA-256
`ab849710e63b6792c22285f5b6f2e3a04b39bc6e344bde1e4bda9ca3c169d2ea`.

### Range-floor evidence conflict and forward comparison

The 12-bps minimum is not treated as settled. It excluded 165 of the 341
confidence-qualified directional onsets in the 90-day cadence audit, while one
additional event exceeded the 100-bps ceiling. In the older gap-safe replay,
the 12-bps floor improved PF from 1.504 to 2.372 and reduced full liquidations
from five to two relative to a zero-floor control. In the recent exact
2026-04-28 through 2026-07-28 replay, however, the zero-floor control added nine
fills and $7,160.45 of final equity without adding a liquidation or worsening
the measured -12.22% maximum drawdown. The evidence is therefore
non-stationary: 12 bps helped the older tail but overfiltered the recent path.

No second runtime is required to resolve this forward. Each authoritative
decision already records the pre-range `source_event`, completed-bar range,
exclusion reason, and executable `entry_allowed` result. A future sub-12-bps
source event can therefore be evaluated as a no-submit zero-floor challenger
against the same recorder tape without changing or competing with live order
authority. Through the 23:35:13 UTC checkpoint, the run contained 35 decisions,
zero source events, zero eligible signals, and therefore zero blocked
sub-12-bps events. The 12-bps floor remains frozen for this canary; repeated
resolved sub-12-bps challengers outperforming admitted events after comparable
friction would falsify that choice.

### Live lifecycle findings and corrections

The canary exposed execution-chain cases that bar replay does not exercise.
Offline reproductions now cover and correct the following future-run behavior:

- decision freshness is checked immediately before execution rather than at
  the beginning of a loop that may perform network work;
- a STOP file created during market-data work is checked before each decision
  handoff;
- restart recovery preserves the venue entry-fill timestamp for the 24-hour
  maximum-hold clock;
- an immediate target fill emits a verified close instead of silently
  flattening the local lifecycle;
- rejected residual cancellation becomes a durable fault rather than an
  unjournaled process exception;
- rejected target placement triggers a reduce-only close and requires a fresh
  venue-flat reconciliation before the lifecycle can report `FLAT`;
- maximum-hold cleanup re-reconciles after target cancellation, so a target
  fill racing the cancel cannot cause a stale emergency-close request; and
- an accepted close acknowledgment is insufficient when venue exposure does
  not subsequently reconcile flat.

The profile identity now hashes the resolved execution, risk, cost, exit,
regime, and metalabel contract. The reported breakout policy was also corrected
to match the runtime's directional-break requirement. The focused profile,
runtime, config, paper, runner, and engine suite passes 68 tests. The running
canary was intentionally not restarted and does not hot-reload these changes;
its old fingerprint remains useful as an immutable boundary. A controlled
future restart must report the new fingerprint before any corrected behavior is
claimed live. Venue behavior contradicting any mocked lifecycle transition
would falsify the corresponding offline correction.

The 00:12 UTC research refresh imported another 204 immutable recorder parts:
375 L2 rows, 3,310 public trades, and 1,979 asset-context rows. The resulting
current-run audit covers 42 executable decisions. All 42 decision candles were
venue-equivalent to the independently recorded trades; 37 were exact and five
had only timestamp-boundary ambiguity. All 42 had continuous L2, with the
known 23:00 UTC reconnect bar conservatively marked unusable. There were two
non-directional primary onsets, zero source events, zero eligible entries,
zero orders/fills, and zero faults. Artifact:
`data/logs/research/source_follow_live_canary_20260801T001236Z.json`, SHA-256
`ad8641ee354c0e472ae487d351c62410cc4953823ff2310d22d24419674e9c90`.

The expanded RANGE-path audit contains 37 decisions across two contiguous
episodes. No usable 5-, 15-, 30-, or 60-minute path reached the 26.667-bp move
corresponding to the frozen 8% gross-margin target at 30x. This supports the
specific no-trade decisions in this window but does not establish general
RANGE precision because the observations overlap and represent only two
episodes. Artifact:
`data/logs/research/source_follow_range_forward_20260801T001236Z.json`, SHA-256
`ef8fa887aa82e8588e7b4583b186e6cccc84ddb78959a265b45c61580f82d26a`.

The running process started at 16:42 EDT, before raw-regime diagnostics were
added to the source adapter and live telemetry at 17:39 and 18:06 EDT. That
explains why its 42 decisions lack the nested diagnostic payload even though a
fresh checksum-pinned classifier process emits it. Screen 2 now projects the
per-bar raw state, confirmed state, hysteresis result, ADX percentile and RANGE
boundary, EMA alignment, and both breakout flags. The TUI rejects diagnostic
authority or confirmed-state inconsistencies rather than displaying them.
All 60 Rust tests pass, as do formatting and warning-denying Clippy checks.
These fields will appear only after a controlled backend restart; the running
canary was not touched.

A predeclared source-event forward observer now separates runtime-admitted
onsets from below-minimum, above-maximum, and other excluded directional
onsets. It measures side-aware favorable/adverse excursion and target-scale
follow-through from the decision reference while explicitly refusing to infer
orders, maker fills, costs, or PnL. Its first current-run artifact correctly
reports zero directional source events. The observer derives measurement
parameters from the run's own startup identity and proves that its 12-to-100
bps bounds and 26.667-bp target match the current config. It reports, rather
than hides, the expected old-process versus corrected-current fingerprint
mismatch. Artifact:
`data/logs/research/source_follow_event_forward_20260801T003438Z.json`, SHA-256
`e9a97bc29a270514b216aa32295dbd1277ddf1ee06fd715e63fb7622c47e5c95`.

The 00:43 UTC checkpoint imported 78 additional immutable recorder parts: 145
L2 rows, 941 public trades, and 769 asset-context rows, with no reported stream
gaps. The executable sample remains 48 decisions: 43 RANGE and five
TRANSITION, with two non-directional onsets and no directional source events.
All 48 decision bars are venue-equivalent to the independent public-trade
tape; 43 are exact and five have only boundary ambiguity. All 48 have
continuous L2, while the known reconnect makes one bar conservatively
unusable. There remain zero order intents, fills, closes, or faults. Artifact:
`data/logs/research/source_follow_live_canary_20260801T004357Z.json`, SHA-256
`1130c1201c157c021db734f869c5c38696f88531f9278f3bc5549696d3a7cc33`.

Across the 43 current RANGE decisions, no usable 5-, 15-, 30-, or 60-minute
path touched the 26.667-bp target-scale move. The respective usable row counts
are 41, 37, 31, and 19; these overlapping observations still represent only
two RANGE episodes and are not an independent sample of 43 regimes. Artifact:
`data/logs/research/source_follow_range_forward_20260801T004357Z.json`, SHA-256
`18da2ba24d72a7a04e39160896822a87ffb3cf811412e75d579d4760eb61c8d8`.
The corresponding source-event audit again contains zero directional onsets:
`data/logs/research/source_follow_event_forward_20260801T004357Z.json`, SHA-256
`aff9fb66b679602ddbc4659486035c8361da9e0cda3766915636aaf2aeab4397`.

A separate checksum-pinned classifier reconstruction through the 00:40 UTC
bar reproduced the live decision exactly: RANGE, confidence 0.60, range 1.906
bps, and no onset. Across the last twelve completed bars, raw and confirmed
state were both RANGE on every bar, the ADX percentile rank declined from
0.1777 to 0.0035 against the 0.40 RANGE threshold, and neither upward nor
downward breakout fired. EMA alignment was bearish, but the classifier
correctly treated EMA direction alone as insufficient while trend strength was
extremely low. A raw/confirmed disagreement, ADX rank above the trend boundary,
or a directional breakout on these same inputs would falsify this explanation.

The validated `ad15f2bd` source also resolves the multi-timeframe authority
question. Its label contract declares confirmed 5m state as the sole capital
source of truth; its state machine explicitly prevents 1m and 15m advisory
lanes from scheduling resolver or executor work, and its policy resolver reads
5m rather than composite state. Therefore a 15m hard veto would reduce source
fidelity and add an unmeasured gate. Advisory 1m/15m visualization remains a
separate future telemetry option, but it must not silently gain execution
authority. A creator-confirmed production rule or causal entry ledger showing
that 15m actually vetoed orders would falsify this constraint.

The observe-only long monitor now defaults to the bidirectional shadow profile
used beneath the live wrapper. Its economic inputs were already identical to
the former short-only profile, so this is a provenance correction rather than
a signal, sizing, or execution change. The running observer was not restarted
and the armed strategy was not touched. Ten focused monitor/config tests pass.

## 6. Confidence, risks, and falsifiers

- High confidence that the armed process is bidirectional: process arguments,
  immutable profile identity, and ledger execution sides agree.
- High confidence that the creator's observed history contains both longs and
  shorts: normalized source rows directly record both directions.
- Medium confidence that `TREND_DOWN` onset is the current short lead: venue
  replay and two prior forward tape targets support it, but live private-order
  evidence is still absent.
- Low confidence that the executable long arm has positive expectancy: its
  fresh resolved sample is zero and the simple historical mirror failed.
- Low confidence that onset-only re-entry matches the creator. Broad persistent
  re-entry overtraded and liquidated historically, but the creator's selective
  same-side reset condition remains unknown.

The bidirectional implementation is falsified by a qualified `TREND_UP` or
upward-breakout decision failing to emit a long intent while flat. Strategy
edge is weakened by forward PF at or below one after costs, liquidation or
drawdown outside the frozen envelope, materially worse maker conversion than
the public queue model, or repeatable regime/direction disagreement with new
creator logs. A complete timestamped creator entry and no-entry ledger would
materially update the re-entry and long-direction hypotheses.

## 7. Next validation

Keep the live recipe frozen while this canary remains armed. Reconcile the
first qualifying long or short lifecycle against the venue, backend ledger,
TUI, and native event tape. Resolve any sub-12-bps source onset as a no-submit
zero-floor challenger from the same ledger and tape. Continue the independent
long observer and retain every resolved outcome. Do not promote countertrend
longs, downward-breakout shorts, same-side continuation, or ML authority
without new causal evidence.
