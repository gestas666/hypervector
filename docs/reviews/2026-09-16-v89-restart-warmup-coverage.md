# V89 restart warmup source coverage

The inspected sources cannot supply a complete fourteen-day native one-minute
history for the September 16 startup. Even including acquisition-unknown vendor
caches, they lack **2,024–3,118 minutes per asset**. This qualifies a specific data
limitation; it does not establish a live strategy defect or quantify signal impact.

Confidence is high for the authenticated sources and exact timestamp counts below.
Finding an additional authenticated source covering the declared gaps would update
this result. No provider was evaluated with changed history and no financial
source, process, configuration or execution behavior was changed.

Research tooling is committed and pushed as
`bcc6f4aa245347de53c44ca01ac1020d0ebb7e2d` on
`research/v89-restart-warmup-coverage-20260916`.

## Scope and source identity

The preceding actual-startup audit reproduced the captured initial provider,
regime and chart objects, plus fourteen independently calculated hourly metrics.
It also established that a fourteen-day request retained only about 3.5 days.
This investigation tests whether available sources can support the separate
history-length comparison. It does not repeat the September 8 five-second
provider-clock experiment or reinterpret that experiment's completed result.

The fixed observation is **2026-09-16 14:58:38.179 UTC**, activation
`1789570607378`, run `bidirectional-live-1789569979897`. The requested minute-open
grid runs September 2, 14:59 through September 16, 14:58 UTC inclusive:
**20,160 timestamps per asset**. The current incomplete minute is retained as an
input; a later provider replay must apply the original completion cutoff.

Sources are the original authenticated startup bundle, a fixed-cutoff export of
cohort `market_candles` publications, and fourteen existing 0xArchive native
one-minute bundles. Seven older vendor bundles end September 6, 23:59 UTC;
seven newer bundles end September 11, 15:25 UTC. All fourteen manifests and all
their declared raw/parquet files authenticate. Every inspected vendor candle's
source field is `hl`; this label alone does not prove OHLCV equivalence.

Four older core-asset manifests have exact matching references in local journal
revision `0e6381731f0194f96200cfd14ceefa867f1f43b17b481c25f8dd9e5cd268888b`,
dated September 7, 21:07:56.979606 UTC. The other ten bundles have no matching
pre-cutoff reference in this inventory. Their filesystem modification times are
not substituted for acquisition evidence. The declared `recorded_at_utc` witness
field corresponds to the journal's `created_at_utc`, not an external trusted
timestamp. The final missing-data conclusion holds even if all fourteen bundles
are admitted as potentially available.

The additional nine top-level one-minute caches end no later than August 11 and
cannot cover this window. This is an inventory of the declared source families,
not an assertion that every file in every worktree has been exhausted. Price,
trade-derived, order-book and coarse-frequency bars were not substituted.

## Exact coverage

The dated-source column combines original startup inputs, pre-cutoff cohort
publications and the four dated local manifest references. The potential column
also admits the other ten declared vendor caches without asserting their vintage.
Duplicates and timestamps outside the expected grid cannot increase coverage.

| Asset | Startup minutes | Dated-source union | All declared potential sources | Still missing in potential union |
| --- | ---: | ---: | ---: | ---: |
| BTC | 5,141 | 14,386 | 18,136 | 2,024 |
| ETH | 5,139 | 14,384 | 18,134 | 2,026 |
| SOL | 5,129 | 14,374 | 18,124 | 2,036 |
| HYPE | 5,001 | 14,246 | 17,996 | 2,164 |
| SPCX | 5,198 | 10,723 | 17,056 | 3,104 |
| SNDK | 5,103 | 10,628 | 17,155 | 3,005 |
| Brent | 5,025 | 7,158 | 17,042 | 3,118 |

Every asset has a remaining gap beginning **September 11, 15:37 UTC** and ending
immediately before its actual startup input begins on September 13. That gap is
1,964–2,161 minutes, depending on the asset. The four core assets also lack
September 7, 13:31–13:33 UTC. The noncrypto assets have additional gaps, including
September 7, 00:00–13:33 UTC. Every interval and inclusive minute count is retained
in the machine-readable results; the largest intervals do not replace the full
gap inventory. Missing candles are not automatically attributed to a venue outage
or implementation error.

## Independent validation and retained failures

The database export uses one read-only transaction and a fixed observation cutoff.
It contains **6,187 events / 11,113,400 bytes**, SHA256
`231a3c3b99bd7be8905463ee8964fb743464ec312ca6a5cee14c60f8fad444fe`.
Its source prefix is **4,571,109,612 bytes**, SHA256
`78695e444730165182bc16f36caa08315cadc09f1bc096a45277f0f9894ae3ba`.
An independent standard-library pass reads all 627,269 source lines, rechecks
the entire prefix hash, independently applies the selection and compares every
selected full object, including its raw-line event identity. All 6,187 match.

Three primary repetitions have identical complete outputs. Two independent SQL
runs use direct parquet timestamp reads, anti-joins and gaps/islands rather than
the primary Python set/range helper. Every count and every exact missing interval
matches for all seven assets. Two original-ledger passes match exactly. Repeats
include the committed Git archive; all eight archived tool files retain their
declared hashes. Archive SHA256:
`866023d4bbd5240e075aca7bb256e81383f7c03be8b7734febeb91ac8be23365`.

**23 artificial offline controls pass**, repeated from the committed archive.
Controls cover byte changes, omitted/injected/revised events, truncated prefixes,
time cutoffs, timeframe/mode selection, timezone and nanosecond validation,
duplicate/unsorted clocks, missing endpoints and both native parquet timestamp
encodings. The archive replays and tests deny network access and permit writes
only inside owned evidence. No financial implementation is imported by the audits.

Retained failures are explicit: the initial witness SQL accidentally partitioned
on `json_each.path`, returning one global witness; a projected-name CTE corrected
it before any provider computation. Two timestamp controls initially failed
because the research helper accepted naive timestamps and truncated nanoseconds.
The strict helper rejects both and leaves all actual inventory outputs unchanged.
The independent SQL reader first rejected vendor string timestamps; explicit
TIMESTAMPTZ conversion supports both actual encodings. The first sandboxed pytest
invocation could not create its default temporary capture file; in-memory capture
and an owned temporary fixture directory resolved the harness dependency without
weakening the sandbox or omitting tests. Original attempts remain inspectable.

## Decision and next experiment

Recommendation: retain the source inventory and defer this fourteen-day
history-length comparison until the declared source requirement is met.
Why now: the authenticated restart exposed the short retained window.
Applicable regime: indicator initialization across regimes. Proposed live change:
none. Expected upside: prevent an incomplete or mixed-vintage replay from being
mistaken for evidence about strategy correctness. No return improvement is claimed.

| Alternative | Value | Limitation | Decision |
| --- | --- | --- | --- |
| Retain current runtime and record exact source gaps | Preserves validated operation and a concrete next experiment | Signal impact remains unresolved | Selected |
| Re-run the same partial-history comparison | Adds no missing source information | Cannot answer fourteen-day equivalence | Do not repeat |
| Fabricate/fill missing minutes or substitute another price series | Produces a visually complete input | Changes the question and source semantics | Excluded from this qualification |
| Obtain authenticated native history and resolve source conflicts | Enables the intended comparison | Acquisition vintage and native missing-bar semantics must remain explicit | Next requirement |

Minimum next evidence is native source coverage for every retained interval and
either dated acquisition evidence or an explicitly retrospective study declaration.
Then resolve all OHLCV overlaps/revisions, preserve the actual startup frame on
overlap, pin the resulting histories, and compare complete native outputs with the
same observation, activation, parameters and execution-authority annotations.
Shorter histories must not be relabeled fourteen-day coverage. If native sources
confirm legitimately absent bars, declare and test their semantics before changing
the completion requirement; do not quietly fill them.

Success requires independently reproduced source identity, complete declared
coverage and explicit provenance before interpreting signal differences. Changed
bytes, unexplained clock/value conflicts or concealed partial coverage invalidate
the relevant qualification. There is no live deployment or rollback action here;
preserve original evidence and supersede the journal if new data changes the result.
No new live approval is requested or exercised.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_restart_warmup_coverage_20260916_v1/`.
The separate full native source, independent reproduction and shared-account
qualification jobs remain the highest-value running investigations.
