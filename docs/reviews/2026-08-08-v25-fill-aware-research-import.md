# v25 fill-aware research import acceptance

## Outcome

The rolling research importer now reuses its persisted all-time portfolio
projection when the exact raw execution-fill set is unchanged. The real 34 GB
DuckDB path completed in 2.72 seconds at 287.6 MiB peak RSS, compared with an
observed lower-bound peak of 5.483 GiB for the required one-time rebuild. That
is a measured 94.877% peak-memory reduction for an unchanged-fill cycle.

The change is report-only. The v25 live owner was not restarted, its profile
and run fingerprints remained unchanged, and ETH, SOL, and GOLD retained their
same owned venue stops.

## Exact cache contract

The cache key is a SHA-256 digest over every ordered raw `fill` event identity,
plus the fill-event count. Heartbeats, books, readiness observations, and other
non-fill telemetry do not change it. Any new or changed fill identity forces
one exact archive rebuild before reuse resumes.

A cached checkpoint is accepted only when it declares `report_only=true`,
`execution_authority=none`, the supported archive schema and mode, and an exact
matching fill identity. Missing or mismatched identity cannot produce a stale
success-shaped archive.

## Validation

- 71 focused importer/checkpoint/history tests passed.
- The regression suite proves both non-fill reuse and new-fill invalidation.
- Ruff, format, whitespace validation, and the 500-line production-file limit
  passed.
- The first loaded cycle rebuilt the legacy cache once and persisted 61 fill
  identities with SHA-256
  `7e0f0735ed58a3e62679f91ae91c72b1df4592c44d86db78050457ac81eab911`.
- A subsequent real-database invocation returned
  `archive_status=reused_by_fill_identity`, imported 98 new non-fill events,
  and retained 28 all-time closed lifecycles.

## Confidence and failure modes

Confidence is high that unchanged-fill rolling cycles no longer execute the
multi-gigabyte all-time projection: tests cover the invalidation boundary and
the current production database reproduced the intended low-memory path.
Confidence is medium for long-duration resource stability because only a short
window has been measured.

The assessment is falsified by an unchanged identity causing another full
scan, a new fill failing to invalidate the cache, a mismatch in all-time close
counts after a fill, or any report-side process gaining execution authority.
The next useful validation is the first naturally resolved live lifecycle: it
must change the fill identity, rebuild exactly once, and then return to reuse.

This infrastructure result does not establish trading edge. The live strategy
still requires resolved lifecycle and missed-opportunity evidence before its
profitability can be judged.
