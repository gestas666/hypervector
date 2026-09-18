# Admission audit repair and completed archived cooldown experiments

Recommendation: retain the independent admission-audit repair and completed
cooldown evidence, then qualify exact peer-health read evidence. No live change
is proposed. High confidence is limited to the reproduced defects, controls and
retained offline evidence; financial benefit remains unestablished.

## Demonstrated defect and implemented repair

Research commit `587ce86de7c1897a176fd07174d56100b2503309` fixes fourteen
demonstrated independent-audit false acceptances. Eight privately resealed
deferred records contradicted their cause, policy, schema, authority, registration
or clock. The service's own validator rejected all eight while the previous
independent checker accepted them. Six further controls changed a real admitted
request's registration, time, transport, deferral metadata or ownership linkage.
These were deliberate test mutations, not observed corruption of live orders.

The independent checker now reconstructs capacity/deadline/cooldown priority,
checks recorded facts against the retained policy and broker clock, and links
admitted requests to their original owned registration and subscription. Deferred
requests cannot claim transport or subscription evidence. It does not call the
service validator to reach its conclusions.

Twenty focused controls passed. The wider candidate suite passed 299 tests with
four optional skips in 564.86 seconds under OS network denial. The repaired
checker covers all 59 statements and four measured branches; the three portable
guard modules also retain complete measured coverage. Whole-harness candidate
coverage is 85.29% of statements and 84.14% combined. That measurement excludes
the separately executed sustained scenarios and is not exhaustive corruption
or interleaving proof.

The exact admission-source archive also passed 299 tests with four optional skips
in 602.11 seconds. Its repaired checker and three portable guards retained complete
measured coverage; whole-harness coverage was 85.49% of statements and 84.34%
combined. Candidate and archive counts overlap and must not be added as distinct
tests.

Ten completed evidence sets passed the stronger accounting check, including
the newest archived delayed-header study. A manifest comparison establishes
5,769 identical shared files, exactly two changed audit modules and four added
test/documentation files relative to the delayed runtime source. Original
transport, collector and guard source is unchanged.

## Archived original-loop results

The delayed-runtime archive completed 248 regression tests with four optional
skips, plus four separate sustained qualifications: single native 429, repeated
native 429, peer 503, and delayed peer 429. Each sustained experiment declared
1,300 seconds with all five original collectors and preserved original budgets,
deadlines and cooldowns. All twenty original processes exited normally.

The single-native archived case resumed 450,276 ms after the received 429.
Repeated-native 429 resumed no earlier than 360,034 ms, retained zero native
market observations, and covered slots 0–3. Peer 503 reproduced the original
unknown-weight refusal and later allowed recovery.

| Delayed peer-429 evidence | Candidate | Archive |
|---|---:|---:|
| Explicit peer-429 refusals | 10 | 9 |
| Local attempts | 517 | 529 |
| Admitted / deferred | 229 / 288 | 251 / 278 |
| Transports / shared subscribers | 154 / 75 | 147 / 104 |
| Native requests / indexed observations | 13 / 4,437 | 13 / 4,447 |
| Minimum native spacing | 60,011 ms | 60,013 ms |

Both delayed studies verified all five first caller admissions before the first
429 headers, corresponding worker/header provenance, at least 2,000 ms declared
first-response latency and subsequent original allowed recovery. Sharing and
absolute scheduling phase explain why physical request counts need not match.
The archived study passed 1,339.44 seconds after start, including validation.

Combined archived cooldown coverage is 95.62% across 1,525 statements and 462
branches. The peer-weight verifier, cooldown scenario/clock modules and three
portable guards have complete measured statement/branch coverage. The older
admission checker retains a known uncovered branch and is superseded by this
separately qualified repair. Coverage does not erase its demonstrated defect.

The earlier zero-delay peer-429 study remains a failed intervention-coverage
test. Passing its data/accounting checks does not qualify that missing branch.

## Operational recovery and next investigation

Research synchronization deferred when free space fell below its existing
8 GiB threshold. Four unused legacy build dependency directories were compressed,
verified byte-for-byte against their sources, checked for open users and removed.
Recoverable archives, manifests and exact restore commands remain under
`data/backups/cache_compaction/open_hold_build_deps_20260917T234625Z` and
`legacy_release_deps_20260917T235133Z`. Synchronization returned to `ready`.
The running release TUI binary's checksum remained unchanged.

The highest-value next investigation is
[exact original peer-health inputs](../plans/2026-09-17-original-peer-health-read-evidence.md).
Two reproduced synthetic cases show the original decision follows consumed bytes
even if the disk file changes before parsing. This supports a scoped observer
experiment; it is not full collector integration or a live health-failure claim.

## Proposal boundaries

Applicable regime: acquisition and audit reliability across market conditions.
Expected upside: prevent unsupported input-data and audit claims from informing
later strategy proposals. No sizing, exit, leverage or return improvement is
claimed from these technical experiments.

| Alternative | Trade-off |
|---|---|
| Keep the previous independent checker | Retains demonstrated false acceptances. |
| Reuse the service validator in the audit | Less code, but shared validation assumptions. |
| Keep the independent repair and test exact health inputs | More explicit evidence and maintenance responsibility. |

Validation still required includes exact consumed peer-health evidence,
quarter acquire-to-begin timing, service restart/power loss, real-network capacity
and operational migration. Recorded deferral facts do not independently prove
historical concurrent occupancy. No atomic four-peer snapshot or external-IP
headroom is established. Sealed economic comparisons were not inspected.

Success is faithful original obligations, independently attributable decisions,
preserved data provenance and reproducible qualification. A legitimate original
record rejected, contradictory ownership accepted, altered source, lost obligation,
or archived mismatch updates or falsifies the corresponding claim. Rollback is
leaving these research branches unadopted. No live approval is requested.

At 00:07:01 UTC on September 18 (20:07 EDT September 17), all eleven preserved
process identities matched. The backend reported 6,868 polls, zero faults and
unchanged live configuration. The five collector health ages were below 25
seconds, and the three native comparison jobs remained running without terminal
failure or qualification files. At 00:07:34 UTC, research synchronization was
`ready` and free space was 9,084,481,536 bytes.

Final byte verification matched all 11,542 delayed-source/archive files and all
11,550 admission-source/archive files, with no changes or missing files. The
33,832,750-byte admission archive SHA-256 is
`2e85458f9def2f0c8aa29e2a392f26d1b9a7fd4f4203011051045c077252a174`.
Detailed results, controls and source manifests are retained under
`v89_public_collector_cooldown_delayed_20260917_v1` and
`v89_public_collector_admission_audit_20260917_v1` in the cohort research log root.
