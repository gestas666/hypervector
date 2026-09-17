# Original collector timeout recovery: archived reproduction completed

Recommendation: retain the offline timeout-recovery candidate at
`f23c3629fc1f6603a8fadebdf5ca05c68c137bbf` and proceed to original cooldown
qualification. High confidence is limited to the completed synthetic transport,
original collector, and saved-evidence checks. Live adoption and financial
improvement remain unproven.

This is a new completion record for the archived experiment described as pending
in the [earlier review](2026-09-17-v89-public-collector-timeout-recovery.md).
The earlier evidence and journal revision remain unchanged.

## Completed evidence

The original archived process (PID 35213, creation time 1789683123.397369,
tool session 80140) completed with exit status zero. Its retained pytest output
reports **170 passed, 4 skipped in 1,487.51 seconds**. The explicitly selected
native timeout scenario ran for a measured simultaneous interval of 1,000,870 ms
with all four original peer collectors. Optional experiments not selected in
this archive invocation remain skipped, not qualified by its pass count.

At 22:52:50 UTC the extracted source independently reverified the archived
raw files, original stores, requested observation grids, native reservations,
peer checks, and service accounting. The same check rehashed every source and
extracted archive file: **11,510 matched**, with no differences.

| Archived sustained evidence | Result |
|---|---:|
| Indexed observations / available raw-row occurrences | 17,505 / 19,859 |
| Local attempts / distinct synthetic transports / shared subscribers | 224 / 146 / 78 |
| Native reservations | 14 |
| Native available / unavailable responses | 13 / 1 |
| Native slot coverage / history backfills | All six / 4 |
| Minimum native reservation spacing | 60,011 ms |
| Actual peer checks | 48 |
| Original quarter collector cycles | 2 / 18 / 2 / 18 |
| Retained large packets / largest packet | 22 / 232,712 bytes |

The failed original native request remained `http_failure` and unavailable as
`unconfirmed_delivery`. Subsequent scheduled requests recovered, and the native
producer finished without unresolved witnesses or a fault. Different row totals
from the earlier candidate run reflect separately declared real-wall windows;
each run was verified against its own raw data and request boundaries.

Combined archive coverage measured 1,396 of 1,440 statements and 392 of 434
branches (95.41% combined). The new transport-scope module covered all 35
statements and 16 branches. The terminal handler covered all 24 statements and
14 branches, including the timely acknowledged-success branch absent from the
smaller focused measurement. Full coverage of these modules is not a claim of
complete system correctness.

Source archive: 34,082,043 bytes; SHA-256
`03eb8d10e41a83ec9df3fd89287db01b70477e6346fa79cda5d9460b6aa383d8`.

## Interpretation and next investigation

Observed problem: a dropped prepared response previously left stale relay
ownership after the original caller deadline, obstructing its next attempt.
The archived candidate confirms recovery without extending that deadline,
discarding another subscriber, or treating unavailable delivery as market data.
This defect was in the research transport path, not established in the running
live order backend.

Applicable market regime: data acquisition across regimes. Expected upside:
reliable research provenance and continued acquisition after the tested timeout.
No return, profitability, venue-capacity, or live reliability estimate follows
from synthetic transport results. Proposed live change: none.

The highest-priority next investigation is the predeclared original cooldown
qualification: native single and repeated 429, peer 429, and peer unknown recent
response weight. Those independent experiments have started in a separate
worktree and are pending; their source and results are not represented as
completed by this revision. Exact health-byte failure reconstruction, the
quarter acquire-to-begin gap, service restart, power loss, study-scale cost,
real-network behavior, and operational migration remain separate requirements.

| Alternative | Trade-off |
|---|---|
| Retain baseline research transport | Preserves the reproduced retry obstruction. |
| Adopt the candidate immediately | Exceeds the present offline evidence and deployment authority. |
| Retain candidate and complete missing failure experiments | Advances the research pipeline while preserving explicit evidence boundaries. |

Success metrics remain preservation of original source, failed local obligations,
receipt deadlines, unavailable-data exclusion, shared followers, and reproducible
stored evidence. Any contrary raw/index, timing, identity, or accounting result
updates or falsifies the relevant claim. Rollback is to leave this offline
candidate unadopted. No live approval is requested for this journal update.

At 22:51:53 UTC all 11 preserved process identities matched. The live backend
reported 6,569 polls, zero faults, and unchanged configuration. The three native
comparison jobs were still running without terminal failure or qualification
files. Sealed economics were not evaluated.

Artifacts under
`data/logs/research/bidirectional_cohort/v89_public_collector_timeouts_20260917_v1/`:
`archive.txt`, `archive_coverage.json`, `archive_final_independent.json`,
`archive_completion_reverified_v9.json`, `source_integrity_after_archive.json`,
and the completed `archive_tmp/` evidence. Journal revision 9 pins the completed
archive artifacts and this review; it does not rewrite revision 8.
