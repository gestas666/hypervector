# V89 actual startup input and indicator qualification

The September 16 restart's original retained inputs reproduce its initial
published strategy, regime and chart values. This closes the activation check
for the installed startup-candle capture in this run. It does not reconstruct
missing inputs from older trades or establish improved strategy expectancy.

Research tooling is committed and pushed as
`379685adb55ecb8639971dd09ecf16b22cc90893` on
`research/v89-restart-input-replay-20260916`. No financial source or process was
changed in this investigation.

## New evidence and exact scope

Run `bidirectional-live-1789569979897` emitted a `captured` startup receipt at
14:58:45.699190 UTC, before its initial published evaluations. The authenticated
ledger slice contains sequences 625901–625908, from configuration through the
first heartbeat at **14:58:52.292200 UTC**. Earlier restart monitoring first
observed a heartbeat at 14:59:17 UTC; this exact slice establishes the earlier
native event. Slice SHA256:
`7efe89391c59ccf37253f0bc2d3fe569dc78526fee709681f870251415416e7b`.

The bundle contains **35,736 rows / 698,694 bytes**. Manifest SHA256:
`1a0efd1b534de28a942001ff8ea3a0900ab5c56fe906b2f15fb85682b8c680d5`.
Each asset has a verified continuous one-minute grid, including its current
14:58 candle; provider/chart completion cutoffs remain applied during replay.

| Asset | Retained rows | First candle, September 13 UTC | Completed hours in independent audit |
| --- | ---: | --- | ---: |
| BTC | 5,141 | 01:18 | Outside independent hourly scope |
| ETH | 5,139 | 01:20 | Outside independent hourly scope |
| SOL | 5,129 | 01:30 | Outside independent hourly scope |
| HYPE | 5,001 | 03:38 | Outside independent hourly scope |
| SPCX | 5,198 | 00:21 | 85 |
| SNDK | 5,103 | 01:56 | 84 |
| Brent | 5,025 | 03:14 | 82 |

All end at September 16, 14:58 UTC. The recorded request was 14 days; actual
retention is about 3.5 days. The request is not reported as complete 14-day
coverage. These are live diagnostic inputs, separate from sealed prospective
research outcomes.

## Native replay and independent arithmetic

The native replay uses archive `708c18a`; all 1,399 repository implementation
files match the authenticated pre-start backup. It preserves both profile and
run fingerprints, activation `1789570607378`, observation `1789570718179`, all
seven fetch requests and bit-exact retained frames after the native merge.
Only collectors and the candle poller are constructed. The recorded live
configuration preserves execution-authority annotations; no execution client is
constructed. Audit hooks prohibit network access, credential reads, subprocesses
and file mutation. Repeats also run under a macOS sandbox denying networking
and writes outside owned evidence. No network call was used as a test.

Three native runs, including committed Git-archive tooling, reproduce complete
objects exactly: **seven provider evaluations, fourteen regime evaluations,
2,520 chart candles and zero intents**. Regime records cover 14:57 and 14:58 UTC
for each of seven assets. All fields and values are compared, not selected keys.

An independent standard-library Decimal implementation assembles full sixty-minute
hours directly from the original minutes. It recalculates true ranges, the
twenty-hour SMA seed, every subsequent Wilder update, population-deviation price
bands and prior channels excluding the current hour. It resets at gaps.
All **fourteen published hourly metrics** match at declared absolute tolerance
1e-10. The maximum observed difference is **8.671737054490605e-15**.

| Asset | Independent final ATR | Recorded ATR |
| --- | ---: | ---: |
| SPCX | 1.04530570799968597 | 1.0453057079996877 |
| SNDK | 13.01385780236823714 | 13.013857802368241 |
| Brent | 0.65342465820505206 | 0.6534246582050528 |

The full independent hourly bars and ATR traces are retained. This validates
initialization consistency for this captured restart, not the unretained original
seed of Brent's earlier entry.

## Tests, failed attempts and interpretation

Nine hand-calculated controls pass, repeated from the committed tooling archive.
The independent arithmetic module has **83/83 statements and 36/36 branches**
covered. Controls cover incomplete hours, missing minutes, duplicate/misaligned
timestamps, invalid prices, gap resets, a known SMA/RMA update, exclusion of the
current hour, nonzero population deviation and old-segment outliers. These are
artificial controls, not economic observations.

The archived implementation passed **57 startup/poller tests** with its original
project fixtures. The first archive-only invocation passed 56 and failed an older
staged profile test because its separately stored source-follow research fixture
was absent. Rerunning with the original fixture directory resolved the dependency
without changing source or omitting the test. Native V89 replay itself does not
use that staged profile.

The first native replay used observe mode and matched numeric outputs but differed
in three HYPE authority/label fields. Its output and original driver are retained.
Using the actual recorded configuration produced exact full equality; no fields
were normalized away. The first final count assertion mistakenly expected seven
regime records rather than fourteen. The original declaration is retained and
superseded by a correction derived from activation/cutoff clocks. Complete payload
comparison already included all fourteen records and was not narrowed.

Final verification checks seventeen declared pins and all five archived tool
files. Review evidence is in
`data/logs/research/bidirectional_cohort/v89_restart_startup_input_replay_20260916_v1/`.

## Decision and next investigation

Recommendation: retain the installed capture and record this run's activation as
qualified. Why now: the approved restart supplied previously unavailable original
inputs. Applicable regime: operational across all regimes. Alternative: leave
activation unverified, retaining a preventable diagnostic gap. Proposed live
change: none. Expected upside: reproducible diagnosis of initial indicators and
display values, with no demonstrated return improvement from this audit.

Risks and remaining limits: one startup, a finite retained history, shared native
logic in the repeated poller, independent arithmetic limited to fourteen hourly
metrics, later revisions unretained by this initial bundle, and no private-fill
or profitability qualification. Future captures require their own identity,
coverage and output checks. Old missing input histories remain unavailable.

Success metrics are exact source/output identity, all asset/clock coverage,
unchanged requests and independent metric agreement. Changed evidence, a missing
grid, concealed partial history, different outputs or unexplained arithmetic
disagreement falsifies this acceptance. Preserve current bundles and the prior
installed capture source for diagnosis/rollback; no source rollback is indicated
by these results. Confidence is high within this dated tested scope. No new live
approval is requested or exercised.

The highest-value next evidence remains complete native source equality and the
following shared-account qualification from the preserved running research jobs.
Do not repeat this startup audit without a new capture or contradictory evidence.
