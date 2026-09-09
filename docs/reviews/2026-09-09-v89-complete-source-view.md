# Complete source assembly: historical prefix and actual receipts

The source adapter now joins all eighteen authenticated historical files to the
captured bridge and study observations, preserving separate completed-market and
actual-knowledge clocks. The fixed source-only report has exact independent
agreement on 84 queries: 1,016,012 candle selections, 28,280 funding selections
and 84 metadata selections. These repeated selections are validation counts,
not independent economic samples or trades.

Source: `478b284093fa1ec988611ec902327bd3e11a13e5`, isolated research only.
No provider signals, prospective returns or account outcomes were calculated.
Neither live deployment nor the running collectors' pinned source was changed.

## What the real source checks found

The read-only snapshot taken September 9 at 00:32:35–36 UTC contains 1,336
valid requests, zero incomplete requests and 70,426 individual observations.
Its 13,801,910 raw bytes are exactly the responses named by the consistent
SQLite backup; later or uncommitted responses are outside that snapshot.
The original registration authenticates 143,712 selected historical rows over
August 26–September 7 across eighteen first/latest/common source files.

The opening and snapshot-tail knowledge clocks were fixed by rule, not selected
for strategy performance: study start; +5, +60 and +65 seconds where captured;
the final request's preceding minute boundary; and its actual receipt timestamp.
Each clock checks all seven assets and both first/latest source interpretations.
Each candle window ends at its independent completed-market boundary and spans
fourteen days. Funding queries retain hourly identities and native settlement
offsets; metadata retains its actual receipt, size precision and leverage fields.

At exactly 00:00 and 00:00:05, the last completed warmup candle was unavailable
for every asset. The scheduled request starts just after five seconds, and an
HTTP response is still needed. At the minute boundaries, core assets likewise
lack that minute's just-completed candle. At the final captured knowledge time,
00:32:06.584, all seven requested candle grids and funding-hour identities were
present. The adapter reports the missing opens at earlier clocks; it does not
backfill them into the earlier view or advance its completed-market cutoff merely
because knowledge advanced.

Historical funding files contain hourly timestamps without native settlement
offsets. Their source values therefore retain absent native availability and
receipt clocks, with explicit registered-historical provenance. Captured funding
keeps its native offsets. Historical continuity proxies and their original
provenance columns remain visible; a complete grid is not complete native history.
The registered prefix is usable from study start, without claiming its archive
rows were timely observations at their original market timestamps.

## Verification and corrections retained

Ninety targeted offline tests pass, including source/registration corruption,
missing and duplicated grids, unknown provenance, partial publication, SQLite
integrity and timeout failures, a writer committing after the backup, first/latest
reversions, absent metadata, constructor cleanup, earlier-knowledge rejection,
future-bar exclusion and the exclusive final funding boundary.

An auditor importing no Hypervector or source-view implementation reconstructs
historical rows directly from authenticated Parquet bytes and captured values
directly from raw responses. It examines requests in reverse filename order and
selects actual minimum/maximum receipt occurrences independently. All selected
value hashes, provenance and clocks feed ordered selection hashes; every query,
gap, count and metadata result is compared exactly.

The first independent run rejected equivalent UTC instants because timezone
representations differed in Pandas' strict index equality. The auditor now
compares exact UTC milliseconds, rejecting sub-millisecond truncation; an
equivalent-timezone regression passes. The original auditor source is retained.
A separate corruption test exposed integer/float equality in report counts;
typed count validation now rejects that change. The report itself remained
byte-identical through these corrections. Test-fixture timestamp precision and
the existing metadata parser's exception type were corrected without changing
production parsing or market data.

The frozen source archive contains 5,258 verified Git blobs and passes the same
ninety tests. Its source report and independent audit reproduce byte for byte.
Fresh archive coverage from the tests plus source-only CLI checks is 529/529
statements and 114/114 branches across the seven new implementation modules.
That is not provider-library or complete portfolio-replay coverage. All thirteen
new source/test files satisfy the project's size, annotation, docstring and Ruff
checks. Archive SHA256:
`1bc7f7a9824d0a0e637051b87d8968deb69a6c8a83d1caeeffda8db778210961`.
Complete report SHA256:
`d9df12a4263aaace2f3db261e8751ab26740a14c9fa202a42c5cdceb8d94ccbf`.

## Qualification boundary and next investigation

Confidence is high in the tested source assembly and exact independent agreement,
conditional on the pinned sources and environment. Changed source hashes, lost
provenance, hidden missing rows, future information entering an earlier query,
incorrect native funding time, an independent mismatch or failed archive replay
invalidates that confidence. Future collection completeness and full fourteen-day
provider throughput have not been established.

The full replay remains unqualified. Next bind these source views to the unchanged
providers and the frozen modeled execution/funding clocks, enforcing the existing
30/60-second entry deadlines without silently retiming modeled positions. In
particular, knowing a candle after its close does not prove an attainable fill
at the earlier modeled bar price. Resolve the source-to-model mapping explicitly
before evaluating any sealed outcomes. Full provider/regime, cost-adapter and
24-cell account/source integration remain outstanding.

At 00:51:52 UTC both public collectors were alive. The new collector reported
1,415 valid requests, zero failed/invalid requests and no evaluated outcomes.
All fifteen collector source hashes and the live profile hash were unchanged.
This is timestamped collection health, not live trading or economic performance.

Evidence: `data/logs/research/bidirectional_cohort/v89_complete_source_view_20260909_v1/`.
