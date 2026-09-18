# Exact original peer-health evidence: completed research qualification

The candidate and its exact archive completed all declared health-evidence
qualifications. This is an offline research result, not deployment authority.

Source: `a575c2ea1b8646f45daf2fa4e9d2c4b85320b7db`, pushed on
`research/v89-collector-health-reads-20260917`. After all runs, 5,785 candidate
files and their archive copies yielded 11,570 matching hashes, zero changes and
zero missing files. The source archive SHA-256 remains
`ce34e6bf7dee04d25a23cc8698abeeadb7d63c1b8ed9df0d95f73ff63abb59d1`.

## Completed results

| Qualification | Candidate | Exact archive |
|---|---:|---:|
| Full regression | 387 passed, 4 skipped; 427.28 s | 387 passed, 4 skipped; 426.62 s |
| Sustained delayed-peer-429 study | Passed; 1,359.23 s including setup/checks | Passed; 1,339.04 s including setup/checks |
| Declared original-loop duration observed | 1,301.426 s | 1,301.426 s |
| Original native peer checks | 57 | 56 |
| Exact consumed health reads | 172 | 166 |
| Native requests / history backfills | 13 / 6 | 12 / 6 |
| Native slots exercised | All six | All six |
| Minimum native reservation spacing | 60,017 ms | 60,016 ms |
| Local attempts / admitted / deferred | 553 / 277 / 276 | 552 / 282 / 270 |
| Unique transports / shared subscribers | 175 / 102 | 198 / 84 |

Both studies used all five exact original collectors, original clocks, waits and
ten-second request deadlines. All five producer exit codes were zero in each
study, with no original faults. Both preserved at least two cycles in each
quarter collector. Counts differ because each declaration uses its actual start
time and concurrent coalescing; matching source and invariants do not imply
identical wall-clock event sequences.

Independent verification reconstructed raw responses, authorization, original
indexes, repeated-value grids, local/shared accounting, scheduling and each health
decision. Across both studies it verified 113 checks and 338 consumed health
reads. Refusal paths included peer HTTP 429, unknown recent response weight,
occupied peer budget and the original quarter-hour blackout. The largest measured
peer weights, 1,174 and 1,086, were reported as occupied budget; they were not
interpreted as permission for a new native request.

Every original first caller admission preceded the first peer-429 response header.
All corresponding worker-to-header delays met the declared 2,000-ms minimum.
Physical first transports were five in the candidate and four in the archive
because sharing can coalesce callers. These studies exercise peer cooldown;
they do not replace the separate earlier native-429 qualifications.

The complete study verifier rejected all six in-memory corruption controls for
each completed study: missing health data, missing version, changed digest,
reordered health reads, false result and an extra unread health record after an
early refusal. Original artifacts were preserved. All twelve challenges rejected
the forged evidence, and the unaltered complete studies passed first.

Combined measured coverage across full and sustained groups is 95.98% candidate
and 95.80% archive. Statement coverage is 97.30% and 97.18%; branch coverage is
91.43% and 91.02%. Both new health modules cover all 117 statements and 26 branches;
the repaired admission verifier and three portable attempt/bridge/status modules
also retain full measured coverage. Callback measurement limits and direct replay
are documented in the prior progress report. These counts do not imply exhaustive
system correctness.

## What is fixed and what remains

The research observer now retains the exact health bytes consumed by the original
guard, including early-refusal prefixes and read/parse failures. Its independent
verifier requires those bytes when the new study/runtime version declares them.
Legacy evidence retains its weaker stated claim. The isolated-child import defect
caught during qualification was repaired and independently regression-tested.

High confidence for these tested research properties. Missing actual consumed
bytes, altered original return/exception behavior, leaked profiling state, source
mismatch or a contradictory archive replay would update that confidence. This
does not prove an atomic multi-peer snapshot, external IP headroom, real-network
capacity, whole-service restart, power-loss durability or improved trading returns.

While these studies ran, the next documented reservation boundary was tested.
Both frozen quarter-v2 collectors lose an in-memory 21-unit local reservation if
killed after acquisition but before durable begin. Six initial and six archived
kill/restart controls reproduced the classification, with zero service transports
or usable observations. The narrower after-begin obligation protection still
holds. See `2026-09-18-quarter-acquire-boundary-findings.md` and the separate
`v89-quarter-budget-acquire-boundary` journal hypothesis. Qualifying durable local
reservation storage is the highest-value next investigation.

The source remains a research candidate for any operational migration. Existing
backend, TUI, original collectors, long native comparisons and live strategy
configuration were preserved. At 01:12:42 UTC, all eleven recorded process
identities matched; the backend reported 7,130 polls, zero faults and
`running_consistent`. All five collector health ages were below five seconds.

Primary evidence:
`data/logs/research/bidirectional_cohort/v89_public_collector_health_reads_20260917_v1/qualification_completed.json`,
`completed_studies_independent.json`, combined coverage reports and retained
candidate/archive study directories. No further live approval is requested until
a concrete operational change has passed its required qualification.
