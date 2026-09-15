# Hourly band history correction installed; activation pending user restart

High confidence in the reproduced defect and the bounded correction. Source
`600d1a12e11c5ce9ee492e5da71a5ff884fd23ca` is installed in the operational
checkout, matching candidate `f579cbffb3aa06614902ce6d4ab549b19d0ab1d2`.
The existing backend process was not restarted, signalled or otherwise controlled.
It retains its previously imported calculation. This report does not establish
an improvement in expected returns.

## Problem and evidence

The September 7 hypothesis `v89-hourly-history-parity-20260907` remained a
candidate. Its band correction was absent from the September 14 qualified
release, today's operational source and the authenticated September 15 prestart
bundle. The original test failed against current source before the change.

Identical final 20 hourly closes produced means of `111.75999999999999` and
`111.76000000000002` when older input history changed. At the same final close,
the long/short recipe-exit flags reversed. This is a reproducible calculation
defect, rather than an inference from trading losses. No actual loss has been
attributed to this boundary.

The cause is incremental rolling mean/population-deviation state retaining
floating-point effects from prices that have left the window. The installed
calculation reduces each complete 20-hour window directly with NumPy mean and
population standard deviation. It is the previously validated source correction,
with an additional regression for deviation independently of mean.

The only production module changed is
`src/hypervector/research/hourly_band_reentry.py`. Its new SHA256 is
`814f104de446b25cbfec879922ec8d98fd45abc2e349735916eec868632b9aa4`;
the previous SHA256 is
`f5d7a8268117613ed3ccb10990756d0287e703784f981092c7f512b51d1041ec`.
Period, two-deviation width, ATR calculation, gap reset, completed-hour timing,
entry/exit comparisons, sizing, leverage, routes and execution controls are
unchanged. No tolerance or additional trading gate was introduced.

## Validation

- 36 focused tests passed in both candidate and installed checkouts, including
  provider publication, prefix causality, gap reset and the two history tests.
  The changed module has 37/37 statements and 4/4 branches covered. Combined
  coverage of the changed module and two unchanged shared helpers is 88% when
  branches are counted; uncovered legacy helper error paths remain explicit.
- Three negative controls restored the old mean, old deviation, or entire old
  calculation. All were detected. The first control run exposed that the
  preserved regression alone missed deviation-only corruption; that failed
  validation was retained and a separate regression added before installation.
- Repeated the existing July 21 through September 6 frozen SPCX study using
  current engine source, with full, 333-quarter and 1344-quarter histories.
  Each history has 1,152 completed-hour decisions. The one 333-quarter exit
  disagreement disappears; the other two comparisons remain at zero. Both
  exit flags change at the same single boundary. No entry flags change.
- All fields of all nine cost-case results match exactly, including all 468
  trade records across the repeated cost/history scenarios. These are 52 trades
  per scenario, not 468 independent trades. Nominal, adverse and full-fee cases
  preserve their prior outcomes; this experiment found no economic uplift.
- All 1,181 available complete 20-hour windows have exactly identical candidate
  bands and exit flags whether calculated alone or with the full prior history.
  Full-history entries, exits, ATR and stop prices remain unchanged. Band-value
  differences from the old arithmetic reach approximately `4.01e-11`.
- Reused 1,500 authenticated native SPCX minute candles, ending at the September
  15 19:00 UTC entry boundary. Across their 100 quarter-hour rows, all decisions,
  ATR and stops are unchanged. The entry remains long. Independent Decimal band
  differences are at most `2.85e-14`. This retrospective response is not the
  original unretained startup snapshot and cannot reconstruct its ATR seed.
- Nine alternating local timings per calculation/history: candidate medians
  8.06 ms for 333 quarters and 16.58 ms for 1,344 quarters; prior medians 7.62 ms
  and 14.59 ms. Candidate maximum 18.08 ms. These observations do not bound
  scheduling, API, provider-pipeline or end-to-end order latency.

The fixed study costs are 0.9 bps fees per side with 2.5 bps nominal or 5.5 bps
adverse slippage, and 9 bps fees with 5.5 bps slippage for the full-fee case.
Official supplied funding is assigned exactly in these bar simulations. Frozen
research assumptions include $500 maximum notional and 10x leverage; they are
not new live settings. Conditional candle fills do not model current queue or
depth constraints. No new out-of-sample, portfolio expectancy or profitability
claim follows from reusing these observations.

## Installation, limits and rollback

Three files were installed: the module, regression tests and implementation
plan. Installation preserved 5,530 other files, all three existing TUI binaries
and the identities of CLI 29190, supervisor 29191, backend 30603, reporter 62016
and original TUI 62017. Reverse-patch applicability passed. Financial process
control was not performed. The leverage/exit-side monitor remains unchanged.

Evidence and rollback are under
`data/logs/research/bidirectional_cohort/v89_band_history_install_20260915_v1/`.
`installation/previous/` preserves prior source; `installation/source.patch`
is the exact reversible three-file change. Check reverse applicability before
any later rollback and preserve all subsequent journals and runtime data.
The baseline study's original source-path reference is a timestamped identity;
matching immutable bytes are retained under `baseline/src/` and in the
authenticated prestart archive. Candidate and installed commits identify the
remaining dependencies.

Existing corrective authorization covers this technical source repair. No
additional approval is requested. Activation waits for the next normal
user-controlled backend start. Validate that run's prestart implementation hash
and retained startup candles before claiming the running process uses the fix.
The current process is not evidence of activated correction.

ATR remains recursively seeded and history-dependent: the 333-quarter replay
retains a maximum ATR difference of 0.03575049 and raw stop difference of
4.8551 bps. This fix does not change those results or introduce exact decimal
price arithmetic. Cross-platform NumPy/pandas behavior still needs the retained
regressions. A repeated identical-window discrepancy, changed replay trade,
causality failure or material calculation-time increase reopens this conclusion.

| Alternative | Benefit | Cost / decision |
| --- | --- | --- |
| Keep incremental arithmetic | Slightly faster local computation | Leaves reproduced history-dependent exit; rejected |
| Add comparison tolerance | Small code change | Alters trigger semantics and does not repair bands; rejected |
| Direct window reductions | Removes demonstrated history dependence | Small measured compute increase; installed |
| Retune ATR/history/strategy | Could change economics | Separate hypothesis requiring evidence; not part of this repair |

The highest-value next evidence is a new native lifecycle/protection/fault event
from the already running bounded watcher, and the next user-started run's
implementation/startup-input provenance. Prospective seals remain unopened.
