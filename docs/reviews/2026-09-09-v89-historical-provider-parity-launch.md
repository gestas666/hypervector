# Complete historical provider comparison launched

Research source `04ec3a002675aaea759cbefd50929b08ee9d2d23` now runs every
registered core minute through the current rolling provider and compares its
18 archived execution/regime fields. The fixed scope is BTC, ETH, SOL and HYPE,
both first/latest native source variants, over `(July 21, September 7]` UTC:
552,960 comparisons in 384 daily chunks. This is a running investigation,
not completed agreement or a profitability result. Confidence is high in the
verified implementation scope and low in future profitability.

## Observed launch and completed prefix

The run started September 9 at 09:12:04 UTC from the verified source archive.
Parent PID 80776 owns four workers, initially 80786–80789. The retained tool
session is 34414. At 09:16:16 UTC the parent and workers were present and
17 complete chunks contained 24,480 comparisons, with zero differences.
An independent reader verified each published compressed file's hash, every
minute and asset identity, complete counts, and expected/actual disagreement
counts. This prefix does not establish full agreement. The final report did
not yet exist.

The run publishes each complete day atomically and refuses replacement. Partial
or malformed comparison streams cannot become completed chunks. Exact finite
value differences, changed regimes/sides/exits, present/absent disagreements and
source gaps remain visible. Empty BTC decision minutes count toward coverage.
A technical failure preserves previously completed evidence but cannot publish
a complete-run report. A performance or comparison disagreement is a result,
not an abort rule.

## Source and test qualification

The reader authenticates the original registration, first/latest manifests,
native `bars.parquet` files and every archived decision batch. The later
`continuity.parquet` files are not equivalent inputs: they contain proxy bars
where the original native controls have gaps. Genuine gaps are retained.
Some original zero-decision BTC Parquet files have zero columns; the loader
accepts that representation only with an explicitly registered zero count.

Each comparison receives `D − 14 days <= timestamp < D`, `observed_at=D`
and `after_decision_time_ms=D−1`. The completed comparison retains the complete
current provider payload as well as its archived contract comparison. Historical
readiness fields absent from the archived contract are not claimed as verified.

The worktree and archive each pass 129 offline tests. The three source,
comparison and publication modules have 100% measured statement/branch coverage
(213 statements, 56 branches); the orchestration script measures 86%, with
its real process-pool path separately observed in this launch. Eleven changed
Python files pass formatting, Ruff, annotations, docstrings, file/function
limits and statement indentation checks.

All 5,380 Git file objects and executable modes matched the archive before and
after testing. Six critical imports resolve inside the extracted source.
The archive is 30,736,350 bytes, SHA256
`41c2fff53645c77d1766d44a9fd89e3dfdd59e08d6b75c549297875d94b0d7dc`.
A real-input smoke check covered two minutes in each of the eight streams,
with zero differences; it is distinct from the full run.

## Noncrypto evidence and remaining work

The registered noncrypto source files begin July 19, leaving July 7–19 absent
for a full fourteen-day initialization at the July 21 scoring boundary. Earlier
mixed-source rows in that interval contain funding, not candles. Local SPCX
trade-derived bars have not been established as equivalent venue-candle inputs.

Existing `v89_hourly_history_parity_20260907_v1` controls retain 1,152 hourly
decisions per asset for full available history and two bounded-history cases.
Reuse their immutable comparisons instead of repeating their economic study.
The old frequency worktree now contains a later SPCX numerical correction and
an edited runner whose hashes differ from the old report. The current research
indicator modules match the registered indicator hashes. Any new comparison
must retain those identities and cannot assume that the old worktree's current
contents reproduce the recorded version. Full quarter-hour provider publication,
missing-prefix interpretation, canonical conflicts, cross-symbol admission order
and historical HYPE UNKNOWN compatibility remain unqualified.

Both prospective outcome seals remain intact. At 09:16 UTC both collectors had
fresh heartbeats, matching process identities, no reported error and all 26
source pins intact. Both live-profile copies retained their original hashes.
No matching trading engine, reporter or TUI process was found. No venue account
snapshot was read. This milestone changes no live strategy, configuration,
process, execution or TUI.

Next: poll the same running comparison and investigate any measured difference;
finish the noncrypto and routing comparisons in the separate research worktree.
Keep the source archive and its extraction while its workers are active. A changed
source, omitted minute, unauthenticated control, dropped mismatch, failed archive
reproduction or incorrect independent count invalidates the affected claim.
