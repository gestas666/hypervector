# Original peer-health evidence: candidate qualification in progress

As of 2026-09-18 00:51 UTC. Research only; execution authority is none.

## Finding and implementation

Earlier sustained studies retained peer health publications and the receipt lists
returned to the native traffic guard. A nearby publication cannot establish the
exact health bytes the original guard consumed. The previously retained two-case
read/replacement experiment demonstrated this distinction.

Candidate `a575c2ea1b8646f45daf2fa4e9d2c4b85320b7db`, pushed on
`research/v89-collector-health-reads-20260917`, adds a scoped return observer for
the original `Path.read_bytes` calls. It retains ordered bytes and SHA-256 values,
read failures, check time, original results and original exception types. It
restores the prior profiler and leaves original read methods and guard policy
unchanged. A separate verifier reconstructs health validity, blackout precedence,
receipt prefixes and early refusals. Study declarations and child configurations
both bind evidence version 1; missing traces cannot receive the new claim through
the legacy receipt-only path.

The first full qualification caught a candidate integration error: isolated
producer interpreters import `sustained` as a standalone module, whereas unit
tests import it through the research package. Commit `cbab6f1` used a package-only
import and failed before the original loops started. Its full result was
24 failed, 362 passed and 4 skipped; its sustained test failed at startup.
The successor uses the existing protocol module's explicit `__package__`
dispatch. A regression test reproduces the exact isolated child environment and
verifies that the original guard still loads from its frozen source directory.
Failed evidence remains retained rather than relabeled as qualification.

## Completed validation

- 111 focused health and receipt-verifier checks passed before the isolated
  import correction. After the correction, all 88 health/import checks passed
  under OS network denial. Ruff and `git diff --check` passed.
- Cases cover healthy/stale/future/boolean/absent heartbeat inputs, health errors,
  wrong authority, malformed/empty/invalid-Unicode/non-object JSON, missing files,
  directory read errors, exact blackout and heartbeat-age boundaries, actual
  SQLite receipt cooldown boundaries, forged traces, post-read replacements,
  prior-profiler restoration and Python 3.13 cProfile coexistence.
- Combined focused coverage is 117/117 statements and 26/26 branches across the
  two new health modules. Python does not line-trace profiler callbacks while
  invoking them; a separate direct replay of real captured return frames covers
  those callback branches. Actual scoped callbacks are independently asserted
  by the original-read tests. This is not whole-system coverage.
- A real 20-second five-collector smoke run returned five zero exit codes and
  passed raw/index/grid checks. Its one peer check fell in the original blackout,
  so it proves isolated startup/shutdown and no-read precedence, not a healthy
  four-peer read.
- Independent verification of captured in-progress prefixes subsequently passed
  nine candidate checks and six archive checks, including four-peer healthy reads
  and one-peer HTTP-429 early refusals. Those prefixes contain 27 actual health
  reads. These are partial observations, not completed sustained qualification.
- A local interleaved benchmark used 250 measured calls per variant, after five
  warmups. Healthy four-peer median time was 0.588 ms original and 1.485 ms with
  observation, including evidence append; added median time was 0.897 ms.
  Observed p95 was 1.864 ms. All paired results matched. Blackout median added
  time was 0.041 ms. Empty receipt indexes, warm filesystem caches and shared
  host scheduling limit extrapolation.
- The exact Git archive contains 5,785 files; candidate/archive comparisons found
  11,570 matches, zero changes and zero missing files. The 33,843,214-byte archive
  SHA-256 is `ce34e6bf7dee04d25a23cc8698abeeadb7d63c1b8ed9df0d95f73ff63abb59d1`.

## Pending qualification and next action

Four jobs run the pushed candidate and its exact archive: the full regression
suite for each and a separate 1,300-second five-original-collector delayed-429
study for each. Original ten-second request deadlines, scheduling, cooldowns and
source identities remain part of verification. The candidate declared stop is
01:08:12 UTC; the archive stop is 01:10:25 UTC on September 18. Completion and
independent checks occur afterward and must be observed before qualification.

Next: poll the existing handles, authenticate all terminal results, independently
recheck complete raw/index/grid/health evidence and first-header ordering, then
exercise missing-health corruption through the complete study verifier. Preserve
any failure and update the diagnosis before a further candidate. No deployment
or strategy change follows automatically from a passing research study.

## Operational preservation and limits

At 00:51:24 UTC, all eleven recorded process identities matched. The live backend
reported `running_consistent`, 7,045 polls and zero faults; five collector health
ages were 14.75–17.80 seconds. Native comparison progress was 49,644 baseline,
49,896 reproduction and 64,260 candidate decisions, with no terminal result or
failure files. Live configuration matched its prior checksum. Sealed economic
comparisons were not opened.

To restore research disk headroom, six completed, inactive source extractions
were pruned after authenticating 34,548 files against both their manifests and
journal-pinned compressed archives. No extracted file was directly journal-pinned;
process/open-file checks found no users. Only disposable Python/pytest caches
were additional files. Compressed source archives, manifests, worktrees and
evidence remain. The measured free-space increase was 1,402,236,928 bytes; free
space after cleanup was 9,827,909,632 bytes. Exact restoration commands are in
`extraction_compaction_completed.json`. Future reproduction must restore a
pruned extraction from its retained archive before using its prior path.

Confidence is high for the bounded completed checks and medium for full producer
qualification, which remains pending. Missing consumed bytes, changed original
behavior, leaked profiling state, source mismatch or failed archive reproduction
would falsify the corresponding claim. This work does not prove an atomic
four-peer snapshot, global IP headroom, historical concurrent occupancy,
real-network capacity or improved returns. The rollback is leaving this research
candidate unadopted. No live approval is requested at this stage.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_public_collector_health_reads_20260917_v1/`.
