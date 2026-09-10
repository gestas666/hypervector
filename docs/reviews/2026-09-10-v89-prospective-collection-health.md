# Prospective collection timing independently reconciled

The September 10 08:58 UTC snapshots reconcile exactly across saved health
reports, read-only SQLite backups and authenticated raw responses. High
confidence applies to captured first-observation identity/timing and mature
coverage at those clocks. This does not establish prospective financial results
or live readiness. Changed evidence hashes, a raw/index timing discrepancy,
missing expected identities or later collection faults would update this finding.

| Frozen capture | Raw requests verified | First candle/funding identities | Mature prospective candles per asset | Prospective funding per asset |
| --- | ---: | ---: | --- | ---: |
| SNDK/Brent | 1,094 | 808 | 211/211 each | 53/53 each |
| Seven assets | 9,923 | 20,968 | 1,977/1,977 for BTC/ETH/SOL/HYPE; 131/131 for SPCX/SNDK/Brent | 33/33 each |

All mature prospective rows in these snapshots are present and timely under
the frozen 60-second publication allowance. All indexed requests are valid;
reported failed and invalid counts are zero. The expected grid excludes the
unexpired allowance, so these counts do not imply a missing newest candle.
Warmup evidence stays distinct: each pair asset has 108 late warmup candles;
each core asset has 2,625 and each seven-asset XYZ stream has 175. Historical
backfill is not relabeled as timely prospective collection.

Both original PIDs remain active and own their writer locks: 75062, started
September 8 03:11:08 UTC, and 15448, started September 8 19:48:04 UTC.
Their process command hashes, starts and ownership match before/after the
audit. All 26 frozen collector/helper source files and both protocol files
match their manifests. The source clocks are 08:58:37.792 UTC for the pair
and 08:58:36.520 UTC for seven assets. The collector heartbeat cadence is
30 seconds; a heartbeat older than five seconds alone is not a fault.

The existing bounded SQLite backup helper reads each live source in read-only
mode. Saved health bytes match before and after each backup; indexed request
counts match the saved health and no indexed receipt exceeds its heartbeat.
Only committed indexed requests are included. Exact response envelope hashes
and decoded-body hashes are authenticated. The independent reconciler reads
candle symbol/interval/open/close clocks and funding symbol/settlement clocks;
it does not inspect prices, funding-rate values or strategy outcomes.

First receipt selection and actual funding availability timestamps independently
match the index for all 21,776 candle/funding identities. All four coverage
sections per asset reproduce, including missing lists and late/timely counts.
The two raw archives contain exactly 11,017 indexed members, totaling
93,145,740 uncompressed bytes. Streaming archive verification checks membership
and each SHA256. A second reproduction reads only the retained archives and
SQLite snapshots and obtains identical timing and coverage.

The independent timing module passes 26 synthetic 2030 tests, with 97/97
statements and 44/44 branches covered. They exercise inclusive deadlines,
missing and late observations, revisions/ties, query bounds, incomplete candles,
wrong symbols, malformed clocks and altered hashes. No network call or strategy
evaluation is part of these tests. Ruff, explicit annotations, public docstrings
and function/file-size checks pass. The 12-member audit-source archive restores
exact bytes; its SHA256 is
`b7a860625cc624e9828f9e8cdfccda0210651ef007055fadaf6461b2f4398954`.

Limits remain explicit. This audit does not revalidate market-value semantics,
every value-version digest, unindexed in-flight raw files, future uptime, final
window closure, signals, fills, fees, returns or venue account state. Funding
identity is its settlement hour while availability retains the actual timestamp.
Both outcome seals remain unchanged: September 22 04:00 UTC for SNDK/Brent
and September 23 00:00 UTC for the seven-asset comparison. No early outcome
reconstruction, collector restart, source change or live deployment occurred.

At 09:01:21 UTC the original historical matrix has 27/48 completed receipts,
four active workers and the original coordinator/reporting handoff active.
Free space is 9,274,458,112 bytes. No local live backend/TUI matched, and main
code/config/test scope remains identical to b3df618. This is a local process
observation, not a refreshed statement about venue positions or orders.

Retain the unchanged collectors and this evidence. The highest-value economic
step remains the original 48-case comparison and full report; do not repeat
this completed audit without new coverage, drift or fault evidence. Historical
review timing remains provisionally September 10 13:00–19:00 Eastern, with
low-to-medium confidence and no established live-start ETA.

Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_prospective_collection_health_20260910_v1/`.
`acceptance.json`, `reproduction.json`, `evidence_manifest.json`, both collector
subdirectories and `audit_source.tar.gz` contain the frozen evidence. Reproduce
the original results by invoking the retained `reproduce.py` against those
unchanged artifacts in a separately named output copy; its existing result
is immutable and the script refuses to overwrite it.
