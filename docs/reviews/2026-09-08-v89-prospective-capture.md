# V89 prospective source collection acceptance

The credential-free SNDK/Brent collector started before the frozen September 8
04:00 UTC block. Its first scheduled 03:15 UTC capture retained both complete
candles within 5.650 seconds of their close. High confidence in this bounded
process, request and timing evidence; the fourteen-day comparison remains
unevaluated and its economic result unknown.

## Frozen collection and process evidence

Source commit `cdd4a93` lives in the isolated
`hypervector-v89-prospective-20260908` worktree. The original prospective protocol
is unchanged. This review supersedes its implementation-pending status without
rewriting that preregistration or changing the rejected live faster-entry
proposal.

The collector loads no wallet address or credentials, constructs no order client,
and accepts only public `candleSnapshot`, `fundingHistory` and XYZ `meta` requests
on the fixed mainnet Info endpoint. `requests.Session.trust_env` is false. The
persistent process has only `PATH`, `PYTHONPATH` and `PYTHONUNBUFFERED` in its
supplied environment; its PID is 75062, parent 1, started September 8 03:11:08 UTC.
Its own output lock is held. It neither acquires the execution account lock nor
writes the main research DuckDB database.

The immutable manifest pins eleven collector/helper files, the frozen protocol,
and four historical Parquet inputs. The two legacy capture manifests additionally
matched all six candle, funding and raw-response file hashes. Each asset has
4,800 historical quarters and 1,200 hourly funding rows from July 19 through the
September 7 bootstrap boundary, with a complete unique timestamp grid.

The initial unsigned capture made nine complete requests, covering the recent
windows and missing historical seam. A second invocation made five requests
and preserved all 274 earlier value versions and receipt identities. Starting
the persistent process made another five complete requests. Its next scheduled
cycle made five more, with no failed or invalid request among those first 24.

| Scheduled source | Candle open UTC | Close UTC | First receipt delay |
| --- | --- | --- | ---: |
| xyz:SNDK | September 8 03:00 | 03:15 | 5.336 seconds |
| xyz:BRENTOIL | September 8 03:00 | 03:15 | 5.650 seconds |

At restart qualification, each asset had 108 bootstrap candles and 28 funding
settlements with zero missing rows. Those historical first receipts are correctly
labeled late; they are warmup evidence and cannot be relabeled as timely
prospective observations. The 03:15 cycle added the next candle for each asset.
The study starts at 04:00 UTC and ends September 22 04:00 UTC exclusively.
No candidate signals, trades or outcomes have been calculated from this block.

## Behavior and validation

Exact request bodies, raw response bytes, SHA-256 values, request and receipt
clocks, HTTP status and bounded retry attempts are retained in immutable files.
The private SQLite index keeps first observations and each distinct later
revision. Recovery validates indexed raw bytes and replays captures left before
index commit. Missing evidence, late first receipts and revisions are separate
fields; backfill cannot repair a timeliness claim.

Polling starts five seconds after completed quarter boundaries. Recent 24-hour
windows detect revisions; at most one earlier missing day per stream is also
requested. Three attempts with ten-second network timeouts and one/two-second
retry delays bound an unsuccessful request. Failed attempts remain evidence;
malformed successful responses fault explicitly. Actual funding timestamp offsets
are retained separately from settlement-hour identities. Unchanged metadata
refreshes its source freshness without replacing the first value receipt.

Sixty-seven offline tests pass, with 98% combined statement/branch coverage.
Request validation, raw transport, scheduling and the observation store each
have 100% statement and branch coverage. Twenty existing process-lock tests also
pass. Ruff checks and the 500-line file/50-line function limits pass. Real capture,
restart preservation, source hashes, actual PID/lock and the scheduled receipt
times provide separate runtime acceptance beyond mocked tests.

Two additional timing defects were caught before deployment: recovery ordering
could retain a later identical receipt, and final reporting could omit the last
candle/funding boundary during its normal grace period. Regression checks now
cover both. A partial funding hour at a request boundary remains optional
coverage because actual settlement timestamps may carry subsecond offsets.
The local Parquet check compares exact timestamp values across timestamp storage
resolutions without truncating precision.

## Evidence and operation

Artifacts are under the original workspace's
`data/logs/research/bidirectional_cohort/`:

- `v89_prospective_market_capture_20260908_v1/`: immutable manifest/raw responses,
  private SQLite index, cycle records and atomic current status.
- `v89_prospective_source_preflight_20260908_v1.json`: legacy source hashes and
  exact warmup grid qualification.
- `v89_prospective_restart_acceptance_20260908_v1.json`: original/restarted status
  and preservation of every earlier value version.
- `v89_prospective_runtime_acceptance_20260908_v1/`: frozen collector/live
  checkpoints, SQLite snapshot, source hashes, process lifetimes and scheduled
  first-receipt proof.
- `v89_prospective_integrity_tests_20260908_v1.log` and
  `v89_prospective_lock_regression_20260908_v1.log`: final automated results.

To inspect collection, read the collector's `latest.json`; do not launch a
second owner. If this collector later stops, the same command resumes its exact
manifest and verifies retained raw evidence:

```bash
cd /Users/gestas/Prototypes/hypervector-v89-prospective-20260908
PYTHONPATH=src /Users/gestas/Prototypes/hypervector/.venv/bin/python \
  scripts/v89_prospective_market_capture.py \
  --output-dir /Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_prospective_market_capture_20260908_v1
```

Rollback stops only this independently owned collector and retains its raw data.
A code or manifest mismatch requires a newly dated revision; it cannot silently
resume as an untouched study. Network outages, machine sleep, clock changes,
late source publication, storage exhaustion and revisions outside requested
windows remain limitations. Candle data cannot identify actual private fills or
native stop ordering. Actual live-account monitoring continues, creating disclosed
market exposure rather than a fully blinded experiment.

A material reporting-storage fault was detected during acceptance and handled
separately in `2026-09-08-v89-reporting-storage-recovery.md`. Live supervisor,
backend, original TUI and reporter lifetimes were preserved. Collection is an
implemented research step, not completion of the continuous improvement mandate
or evidence that the faster-entry candidate should be deployed.
