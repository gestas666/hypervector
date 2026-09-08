# V89 recorded-native source, lifecycle and cadence sensitivity

The current core strategies are sensitive to historical candle provenance.
Replacing only overlapping archive candles with backend-recorded venue candles
adds one HYPE entry on August 26. It leaves BTC, ETH and SOL entry/exit
instructions unchanged. First and latest recorded revisions produce the same
lifecycles and shared portfolio paths in this experiment.

The additional HYPE trade gains at nominal slippage but stops out under the
predeclared adverse slippage case. This changes the adverse seven-asset result
from **+$119.85 to +$96.12** and its close-mark drawdown from **3.32% to 3.91%**.
The favorable nominal result is not selected over the unfavorable sensitivity.

Confidence is high in these frozen comparisons and their accounting identities.
The source history remains hybrid, the sample has already been explored, and
private fills, contemporaneous revisions and historical executable quotes are
not reconstructed. These results do not establish prospective profitability.

## Scope and source integrity

The predeclared plan is
`docs/plans/2026-09-07-v89-recorded-native-source-sensitivity.md`.
Source implementation is committed as `9ec33e6`, with raw extraction and the
storage recovery record in `9c36e5d`. Work is isolated in the V89 research
worktree. No live process, strategy, risk setting, asset or route was changed.

- Raw export: 39,895 mainnet-authority candle events from 80 recorded runs,
  observed before September 7 00:00 UTC; 240,243 core candle observations.
- Unique recorded minutes: BTC 45,910; ETH 41,721; SOL 41,883; HYPE 45,910.
- Seventeen timestamps have conflicting OHLCV revisions; twelve include prices.
  First/latest selection uses observation time, not PnL. Simultaneous
  contradictory versions fail rather than receiving an arbitrary ordering.
- Eleven of sixteen baseline core lifecycles have every holding-period minute
  represented in the recorded source. This does not cover every indicator's
  prior history or prove a point-in-time reconstruction.
- Median first-publication delay is about 17–18 seconds after candle completion;
  startup history can first appear about six hours late. The existing telemetry
  records only previously unseen timestamps, omitting later within-run revisions.
- The exact archive grid, warmup, raw gaps, batch boundaries, cost cases and
  funding dates remain fixed. Native observations at 9–11 missing archive
  minutes per coin are deliberately not inserted. Existing execution gap-fill
  rows remain unchanged and explicitly tagged.
- `source=hl` is retained only for collector compatibility. Every output also
  carries `source_origin`, selected event/run ID, availability and lag. The
  manifest explicitly identifies the archive prefix and uncovered intervals.

Sixteen independent raw/continuity comparisons verify unchanged timestamps,
bit-exact uncovered OHLCV and exact selected replacements. Native millisecond
and archive microsecond timestamps are compared as identical nanosecond instants;
the archive/output timestamp dtype itself remains unchanged.

## Source-to-decision effects

Both substitutions produce the same decision counts as baseline:
BTC 1,145; ETH 69,100; SOL 69,101; HYPE 69,101. Neither adds nor removes a
decision timestamp. Each variant has 246 actionable/noon rolling checks and
zero mismatches. These checks do not cover every minute.

| Route | Changed instructions | Changed regime rows, archive vs first | Interpretation |
| --- | ---: | ---: | --- |
| BTC | 0 | 0 | One actionable reference-price difference |
| ETH | 0 | 177 | Price/confidence and regime differences, same instructions |
| SOL | 0 | 162 | Confidence and regime differences, same instructions |
| HYPE | 1 | 220 | One additional long entry; other differences retained |

On August 26 at 02:25 UTC, the source 02:24 HYPE bar changes from a slightly
positive directional body (**+0.1221538161 bps**) to a slightly negative one
(**−0.6107690804 bps**). The frozen zero-body pullback threshold therefore changes
from absent to satisfied. Independent rolling evaluation reproduces the
archive hold and both recorded-source entries with zero contract mismatches.
This is a source-sensitive counterfactual under today's route, not evidence
that the historical live system missed an order.

The replay's instruction-level changes are separate from close/reference
prices, confidence and regime fields. Regime differences can affect maximum-hold
decisions even when explicit entry/exit instructions do not change.

## Lifecycle and shared portfolio consequences

BTC and SOL have small marked/funding or excursion changes; their net changes
are below $0.000001. ETH's complete lifecycle cases match exactly. HYPE grows
from five to six completed trades. Both source revisions give exactly equal
core lifecycle cases.

The additional HYPE long enters at 02:25 UTC on August 26:

| Slippage per side | Exit | Holding time | Net return on trade notional |
| --- | --- | ---: | ---: |
| 2.5 bps | Maximum hold at 10:25 | 480 minutes | +99.0458 bps |
| 5.5 bps | Protective stop at 09:23 | 418 minutes | −95.1011 bps |

The recorded 09:23 low is 81.242. It falls between the nominal stop
81.23038252 and adverse stop 81.254745544, explaining the different exits.
The source 02:24 candle was first published at 02:25:21 UTC; the replay's
next-open fill is still a modeled assumption, not a recovered executable fill.

The same seven routes, $4,857.59 initial account, configured sizing and existing
addition trades are replayed through shared cash, settlement and marking:

| Cost case | Baseline net | Recorded-source net | Recorded-source close-mark drawdown |
| --- | ---: | ---: | ---: |
| Nominal | +$172.61 | +$197.42 | 2.75% |
| Adverse slippage | +$119.85 | +$96.12 | 3.91% |
| Full HIP-3 fee stress | −$9.46 | −$33.18 | 4.68% |

Full HIP-3 fees are a separate stress scenario; current growth-mode account
fees were independently qualified in the earlier current-fee review. That
current observation does not establish the fees throughout this historical window.

Both declared exit clocks are retained. All twelve source/cost/clock scenarios
reconcile at 49 daily boundaries, with maximum error below $0.000000000002.
First/latest shared reports, capacity, trade rows, complete paths and dated
daily contributions match exactly. Maximum concurrency remains four and reserved
margin $400, with no configured-notional mismatch. Same-bar trades in the
addition controls retain their previously documented incomplete interior marks.

The adverse case has 72 wins out of 177 trades (**40.68%**). Excluding the largest
winner leaves **+$4.77**; excluding the largest three leaves **−$132.11**. The
result is concentrated and cannot justify expecting large wins from inactivity.

## Measured trading cadence

The revised 48-day replay has 177 trades across 167 distinct entry times:

- Mean: 3.6875 trades per day across the portfolio.
- Median gap between distinct entry times: five hours; 90th percentile: 14.5 hours.
- Longest observed interarrival gap: 26 hours, excluding censored endpoint gaps.
- Of 4,593 four-hour windows ending every fifteen minutes, 2,359 have no entry:
  **51.36%**. A separate brute-force count matches the vectorized calculation.

These overlapping windows are descriptive, not independent trials or a forecast.
The current run's lack of eligible entries is consistent with this sparse design;
it does not alone diagnose a stalled execution process or promise future returns.

## Validation, disposition and next investigation

Eighty-seven focused offline tests pass. The new normalization module has 86%
statement coverage; malformed prices, premature availability, duplicate identity,
revision ambiguity and grid preservation are covered. All new files/functions
meet the project size and annotation checks; Ruff and whitespace checks pass.
The acceptance artifact verifies 1,838 current source/output contracts.

The initial comparison export rounded detailed floats through pandas JSON.
A failing precision test exposed this; the v2 export preserves full Python float
precision. Its twelve comparison summaries exactly match v1. The original v1
script is preserved beside the experiment artifacts; v2 is the authoritative
detail export. Missing inactive rows also have a regression test separating
coverage loss from an invented execution instruction.

Accept the source-sensitivity evidence. Defer a strategy change: this experiment
does not select a new threshold, stop, route, asset or allocation. Raising trade
frequency without independent after-cost evidence would not resolve the measured
source and cost fragility. Doing nothing about source provenance would preserve
an overstated adverse result; treating the hybrid as fully native would overclaim.

The highest-value next correction is to expose research import failures and
freshness in the reporting/TUI path. The measured disk-related import outage
was invisible in the otherwise healthy checkpoint. This should be a report-only
technical correction, separately tested for failure, recovery and legacy data.
Independent strategy validation and prospective execution/source evidence also
remain incomplete; the overall goal remains active.

Changed source hashes, failed rolling reproduction, mismatched daily accounting,
or contradictory native observations would require a superseding assessment.
No live change or additional approval is requested by this report.

Artifacts are under the original checkout's `data/logs/research/bidirectional_cohort/`:
`v89_recorded_native_*_20260907_v1`, plus the authoritative
`v89_recorded_native_decision_comparison_20260907_v2/`.
