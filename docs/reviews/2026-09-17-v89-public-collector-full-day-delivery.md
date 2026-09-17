# Full-day original collector delivery: measured fix and timeout recovery gap

Recommendation: retain the offline delivery increment and fix the now-reproduced
lost-preparation recovery defect next. High confidence applies to the measured
packet, deadline-read and full-day candidate results. The archived replay remains
active; complete timeout/cancellation qualification and deployment readiness are
not established. No live change is proposed by this record.

Source: `research/v89-collector-delivery-20260917`, commit `32c4bee`, in
`/Users/gestas/Prototypes/hypervector-v89-collector-delivery-20260917`.

## Problem, implementation and validation

The former research relay rejected a full 1,440-candle receipt because its
acknowledgement exceeded the 65,536-byte newline-frame bound. Raising that bound
alone would leave pipe blocking and ownership unqualified. The replacement keeps
small control frames and sends larger packets as references to immutable private
files, bounded to 16 MiB. It checks the peer directory, sender direction, filename,
length, regular-file identity and SHA-256 before returning data. Existing corrupt
files are refused rather than overwritten. Original producers still import their
authenticated source trees and retain their scheduling and normalization.

Actual-pipe controls also reproduced a partial-line read that outlived its caller
deadline and a second buffered line missed by select. The new reader preserves
buffered frames, reads nonblocking bounded chunks, and checks the original
absolute deadline. File decoding that finishes after that deadline is refused.
This does not establish bounded filesystem latency during a stalled disk read,
nonblocking outbound writes, or complete timeout recovery.

Completed validation:

- 43 packet/boundary tests, including exact 16 MiB bounds, changed files during
  reads, symlinks, nonregular files, wrong ownership, malformed/nonfinite data,
  nested references and corrupt existing files. Scoped storage/reader coverage
  measured 97%; uncovered branches are not claimed as verified.
- 61 focused controls passed; one full-day test was explicitly skipped in that
  short run and was then exercised in the separate full-day run below.
- The full-day suite passed 34 tests in 1,021.90 seconds. All five original loops
  ran concurrently with real clocks and their original waits. The study declared
  a full day before any child started; requests were not shortened to fit.
- The corrected broad regression passed 887 tests, with 62 explicit fixture-based
  skips, in 345.20 seconds. The initial run retained one failure, 862 passes and
  62 skips. That failure was an existing test's assumption that a candle is
  available in the first five seconds of a minute. It reproduced at 0 and 4,999
  ms. The corrected test chooses an eligible clock and tests all three phases;
  no original five-second collector delay or scheduler policy was changed.
- Ruff, diff whitespace, explicit function annotations, 500-line file and
  50-line function checks passed. All 11,488 source/archive file checks matched
  the 5,744-file manifest after the source archive was created.

Final independent checks of the full-day candidate measured:

| Evidence | Result |
|---|---:|
| Original successful producers | 5 |
| Indexed observations / available raw-row occurrences | 17,634 / 19,988 |
| Local attempts / distinct synthetic transports | 241 / 167 |
| Shared subscribers | 74 |
| Native reservations / historical backfills | 13 / 6 |
| Native slots / minimum spacing | All six / 60,013 ms |
| Original quarter cycles | 2, 18, 2, 18 |
| Retained large packets / largest packet | 22 / 232,658 bytes |
| Native peer checks | 47 |
| Blackout / weight / quiet decisions | 8 / 1 / 38 |
| Actual simultaneous duration | 1,000,765 ms |

Every available requested raw row was independently reconstructed and compared
with its original index and first/latest receipt policy. All retained private
packet content hashes matched. This covers requested rows, not unrequested study
times or future observations. Responses are synthetic and network access was
denied. Transport sharing is not evidence of venue charges or live-IP headroom.

## New counterexample and next investigation

Two isolated original-loop probes dropped one prepared response for producer
43671. Both preserved a failed incomplete receipt and zero observations for that
request. After the unchanged caller deadline expired, the parent still owned the
old request_id and rejected the next durable attempt as overlapping. This is an
offline relay retry defect; the failed response did not become available data.

Next: bind every transport response and cancellation to its original durable
attempt, detach expired ownership without refunding local obligations, and keep
late responses from satisfying checkpoints or later requests. Qualify dropped
and late preparation, lost acknowledgement and repeated identical-payload retries
with all original producers. Reuse existing service cancellation where its
contract applies; do not extend deadlines or cancel another shared subscriber.

Alternatives: leave the size failure (blocks full-day evidence), only increase
the frame bound (leaves blocking/integrity issues), or retain the bounded file
delivery while completing timeout recovery. The third option is the current
recommendation. Applicable market regime: research data acquisition across
regimes. Expected upside: trustworthy research inputs and fewer qualification
failures; financial improvement has not been established.

Remaining work includes the running archived replay, the timeout counterexample,
persistent 429/native cooldown, quarter acquire-to-begin failure gap, service
death/restart, power loss, study-scale recovery costs, operational CLI and
explicit adoption/migration with rollback. The source archive is 33,301,139 bytes,
SHA-256 `36922391b2d5c08430b372c15bfcc0167e6fadafaba7eefb9cd86f0d8cc1718c`.

Success metrics: exact source identity, complete available requested rows,
original receipt versions/obligations, transport conservation and archive
reproduction. Accepted corruption, usable data without complete timely evidence,
missing rows, lost obligations or source divergence falsify the corresponding
claim. Rollback: leave the research branch unadopted. Live approval requested:
none for this offline increment; deployment requires explicit approval.

## Evidence and preserved runtime

Artifacts are in `data/logs/research/bidirectional_cohort/v89_public_collector_delivery_20260917_v1/`.
They include red/green controls, both broad regression results, candidate output,
`full_day_final_independent.json`, both dropped-preparation probes,
`timeout_counterexample_verified.json`, `source_manifest.json`, the source
archive and `archive_pending_after_candidate.json`.

The archive process remains PID 2400, birth 1789680144.718858, tool session 40911.
Resume that exact handle; do not restart on an observation timeout. Its output is
not counted as passed and will need a new immutable completion record.

At 21:29:45 UTC all 11 preserved process identities matched. The backend reported
6,240 polls, zero faults and unchanged configuration; all five source collector
heartbeats were younger than 15 seconds. The three native comparison jobs were
still active with no terminal result or failure. Snapshot:
`v89_captured_provider_assembly_20260916_v1/runtime_snapshot_v48.json`.
