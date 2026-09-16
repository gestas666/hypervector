# Captured allocation comparison and full-window native qualification

The isolated comparison implementation is committed in reporting candidate
`0400e5c` and integrated candidate `e35e8accd7e99b746817e64a82ee4fb377f1829c`.
It preserves the original 24 cells, twelve paired allocation contrasts, fixed
primary scenario, costs, daily boundaries and study seals. It is not installed
in the financial runtime. Confidence is high for the component tests described
below; complete economic or native-strategy qualification requires separate
evidence.

## Changes and evidence

The reporting coordinator authenticates the original economic registration
before accessing case outcomes. Real studies retain their registered seals;
the separate synthetic interface requires explicit unsealed 2030-or-later
controls with unchanged frozen economic metadata. Every case needs a distinct,
absolute pinned report artifact. Missing, duplicated, changed or relabeled
cases reject publication. The completed directory appears only after all case
audits, source rechecks and comparison calculations succeed.

The comparison retains exactly twelve equal-minus-control pairs. It does not
average alternative source, cost or timing scenarios or select a primary from
their results. The primary remains first receipts, adverse cost and the
recorded-bar clock. Daily portfolio and seven-asset cash contributions reconcile
to the declared split periods, marked path and trade cash components. Original
entry margin, exposure, drawdown, fees, funding, holding time and concentration
remain available. Zero activity and losses survive; per-trade ratios remain
unavailable when their denominator is absent.

Fault tests reproduced and corrected a strict-schema issue: Python boolean
`True` compared equal to integer schema version `1`. Other controls cover
changed source bytes, omitted economic/archive provenance, incorrect partitions,
incomplete asset attribution, malformed cash arithmetic and missing cases.

The initial component suite passed **78 tests** in the candidate and **78 tests**
from its archive. The final margin-repair suite passed **143 tests** in the
candidate and **143 tests** in its archived copy. All 415 statements and 114
branches across the four new reporting modules and shared trade-attribution
module were covered. This is bounded implementation coverage, not proof of
complete strategy behavior. The fourteen-day comparison
unit controls contain hand-constructed account summaries. They do not replace
an actual native account replay.

The original account-generation archive has **5,771 verified members**, SHA-256
`d6d6f745c447616a015d353275f11f2c6ecf20bcc29c24299c958d318c08e57d`.
The end-to-end driver uses this archive for actual source-calendar account
generation, independent accounting and full report publication. Its deliberately
programmed provider outputs span two complete synthetic days; their returns
cannot establish strategy performance. All 24 accounts independently reconciled
and all twelve pairs published at 08:09:21 UTC in 1,064.24 seconds. A fresh
recalculation produced 26 byte-identical report files in 95.53 seconds.

That successful reproduction did not establish correct metric semantics.
Direct inspection exposed a zero average-entry-margin result in every case:
the comparison averaged terminal reserved margin, which had been released by
the seven closed trades. The first case's recorded opening margins average
**$32.766289880952385**, not zero. All 24 cases reproduced this defect against
their actual account openings; their cash, fees, funding and P&L still
independently reconciled.

Three new failing regressions cover retained original margin after a close,
the average when all terminal reservations are zero and refusal of reports
missing original entry-margin evidence. Trade contributions now retain
`entry_margin_usd` directly from the recorded opening. Terminal
`reserved_margin_usd` keeps its existing meaning. The comparison averages the
new original-margin field, with no leverage-based reconstruction or silent
fallback. The corrected reporting archive has **5,773 verified members** and
SHA-256 `c013b18fbe04839fd98bd43626a751eec8fa7000b5f8fd57e3f815b466b4ab53`.
The corrected reporter reaudited all 24 retained accounts twice. Every
reported opening margin equals the original account opening; all other case
calculations remain exact. The two complete publications contain **26
byte-identical files**. The combined correction/reproduction check took
191.57 seconds, and the maximum independent account difference across the
24 cases is **$5e-13**. Original account generation was not repeated by this
report-reproduction check.

The authoritative corrected matrix report SHA-256 is
`593977a37134d57bc86b3eb6f0910c9ea16ead873379bc511e856b420fd16a8c`,
under `matrix_margin_corrected_v1/report.json`. The earlier zero-margin reports
remain preserved as defect evidence and are superseded for that metric.

## Full-window native work

Candidate `76f4b50cdb0ad979977e7bc2dc8f9d566da80ac3` adds only two test files.
They generate the remaining thirteen days and twenty-three hours after the
existing one-hour native control, using deterministic rising/falling prices,
separate completed-candle receipt clocks, signed funding rates at native
17-millisecond settlement offsets and hourly metadata. The real store,
normalizer, receipt tape and study binding process these fabricated records.

The eight new fixture tests passed in both the candidate and its source
archive. They verify every asset's entire remaining grid, valid OHLC geometry,
separate availability/receipt times and deterministic nonconstant prices. The
archive has **5,773 verified members**, SHA-256
`d75f6c1e92b9e96b5590181f23209e9ee269853b44a84a285cdf53766d780306`.

A separate process started at 08:05:20 UTC on September 16, using only its own
newly generated data. It prepared the complete sources in 132.11 seconds.
Expected scope is **84,679 native
publications and 2,352 funding observations per variant** over all fourteen
days. The test-only clock changes only inside that isolated process; no real
prospective captures are read. A tracing wrapper forwards unchanged native
arguments and results and records progress. Its first 756 publications took
604.79 seconds. The measured rate projects approximately 38 hours for both
variants, exceeding the initial 36-hour research deadline. This is a local
throughput estimate, not a completion promise.

The verified owned research process was deliberately terminated at 08:17:51
UTC, before spending hours on an insufficient time budget. Its identity,
measured progress and intact source preparation are retained in
`full_native_v1_transition.json`; it is not marked successful. At 08:18:00 UTC,
replacement PID 29346 / tool session 49265 started from the same archived
native implementation and authenticated complete fabricated sources. Its
external research deadline is 72 hours. Both complete variants are still
required. No financial process was signalled, and no strategy, source clock
or economic model changed.

Complete source objects are retained as hashed, locally generated pickle
artifacts for subsequent calendar/account work. These are trusted-local
qualification artifacts, not a general import format. Their generation is not
yet claimed complete. Full-window account runs, independent accounting and
archive reproduction remain required even after native sources finish.

## Interpretation and remaining limits

The reported prices and bar clocks remain conditional model assumptions,
not evidence of achievable private fills or continuous venue protection. The
frozen shared barrier precedence is liquidation, then stop, then target when a
bar hits multiple boundaries. HYPE's frozen replay does not define a liquidation
trigger. That limitation remains explicit; a complete allocation report does
not establish equal liquidation coverage across all routes. Original special
exit costs and marked terminal inventory are retained without invented closing
fees. No economic rules are changed by this qualification.

Recommendation: retain the qualified comparison/reporting work and continue
the full native study preparation. Expected benefit is a more trustworthy
allocation decision, not a forecast return increase. Keeping only component
fixtures would leave source-to-account integration unverified; changing live
allocation now would not supply the missing evidence.

The highest-value next investigation is the running full-window native source
qualification, followed by native calendar/account controls, including
nontrivial route and HYPE holding behavior. Real seven-asset study outcomes
remain sealed until September 23 and October 7 on their original terms. The
separate SNDK/Brent study retains its September 22 seal. Positive simulated
returns would not grant live promotion, and losses are not technical aborts.

Reopen a claim if original seals or economics change, a source revision leaks
backward, a native publication differs, a funding/position boundary is lost,
independent cash arithmetic fails, source hashes change or archive results
disagree. Rollback concerns isolated research commits and retained artifacts;
it requires no financial process control. The backend, supervisor and original
TUI remain user-owned. Live strategy, sizing, leverage, risk, execution and
deployment changes require the user's explicit approval under the mandate's
human-control paragraph.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/`.
The exact comparison and native process receipts, test logs, archives and
reproduction records take precedence over this narrative's point-in-time status.
