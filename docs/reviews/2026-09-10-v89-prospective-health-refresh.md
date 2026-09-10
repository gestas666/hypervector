# Prospective collection health refreshed at 15:46 UTC

The two unchanged collectors have a fresh independent timing and coverage
reconciliation. Their saved September 10 heartbeats are **15:46:07.237 UTC**
for SNDK/Brent and **15:46:36.527 UTC** for seven assets. All **12,964 committed
raw responses and 23,611 first-observation identities** reconcile with the
read-only SQLite snapshots and saved health reports. No mature prospective
candle or funding identity is missing or late under the frozen 60-second
publication allowance. Reported failed and invalid requests are zero.

High confidence applies to this captured evidence and its independent
reproduction. A changed hash, wrong process ownership, raw/index discrepancy,
missing identity or subsequent collection fault would update the finding.
Market-value correctness, economic outcomes and live readiness are outside this
timing-only observation.

| Capture | Requests | First identities | Mature candles per asset | Funding per asset |
| --- | ---: | ---: | --- | ---: |
| SNDK/Brent | 1,234 | 878 | 239/239 each | 60/60 each |
| Seven assets | 11,730 | 22,733 | Core 2,385/2,385; XYZ 159/159 | 40/40 each |

This extends the earlier 08:58 UTC observation by 1,947 authenticated requests
and 1,835 first identities. Expected coverage excludes the unexpired publication
allowance. All four coverage sections per asset reconcile; late historical
warmup remains distinct from prospective first observations. No warmup backfill
is relabeled as timely forward evidence.

## Verification and preservation

The refresh copies the exact qualified `audit.py`, `timing.py` and
`reproduce_v2.py` source bytes into a new evidence directory. All 74 prior
qualification/source references, including the bounded read-only SQLite backup
helper, match before and after execution. The unchanged timing implementation
reuses its 26 synthetic tests and 97/97 statement, 44/44 branch qualification;
no new test run or new implementation qualification is claimed.

The audit and retained-evidence reproduction both exit successfully. Stable
health bytes bracket each SQLite backup. Indexed raw membership, envelope/body
hashes, raw first timestamps, index first timestamps and the expected grids
agree. Compressed raw archives contain exactly the indexed 12,964 members,
totaling 108,749,030 uncompressed bytes. Reproduction reads the saved archives
and snapshots, rather than requesting fresh market data. The evidence manifest
pins 50 retained files.

All 26 collector source files and both protocols match their frozen manifests.
Collector PIDs 75062 and 15448 retain their original process identities and
writer locks before and after the audit. Both prospective financial outcome
seals remain unchanged: September 22 04:00 UTC for SNDK/Brent and September 23
00:00 UTC for seven assets. No price, funding-rate, signal, position, trade,
return or venue-account evaluation was performed.

## Decision and remaining work

Retain the collectors unchanged. This extended coverage provides no evidence
requiring a collector repair or restart. Keeping only the earlier snapshot
would leave the additional collection interval unaudited; changing or
restarting healthy frozen collectors would add an unnecessary continuity risk.
Repeat this check only when additional coverage, drift or a fault justifies it.

At **15:48:08 UTC**, the original reporter PID 35528 remains active at 99% CPU
with **17/48 case audits complete**. All 48 simulations are finished. Observer
27361 and final-report handoff 40699 remain active; the complete financial
publication and final HTML receipt are absent. The highest-value economic task
remains that original full report. Do not duplicate its preparation or alter
its frozen sources.

The root implementation still matches `b3df618`; the installed TUI SHA256 is
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
No local live backend/checkpoint/TUI matched the bounded process inventory.
This is not a fresh venue position or order check. Free disk space was
3,297,611,776 bytes. The prior **16:00–19:00 Eastern** conditional user-run
live estimate remains low confidence, subject to complete reporting, exact
release approval and fresh account/order/TUI acceptance.

Evidence is under
`data/logs/research/bidirectional_cohort/v89_prospective_collection_health_20260910_v2/`:
`source_reuse.json`, `acceptance.json`, `reproduction.json`, both capture
directories, `runtime_observation.json`, `evidence_manifest.json` and the
terminal audit/reproduction logs. The earlier evidence remains unchanged.
Rollback is an appended correction or superseding observation, preserving all
raw evidence; this refresh grants no deployment or execution authority.
