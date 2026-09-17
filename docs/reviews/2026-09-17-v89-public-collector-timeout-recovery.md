# Original collector timeout recovery: candidate evidence

Recommendation: retain the offline timeout-recovery increment and finish its
exact archived reproduction before any adoption proposal. High confidence is
limited to the completed synthetic original-loop and saved-evidence checks.
Deployment readiness and financial improvement remain unproven.

## Problem and implemented behavior

Two retained delivery experiments dropped the first prepared response and
reproduced a stale parent request owner: the original caller timed out, but its
next durable attempt was rejected as an overlapping request. The failed receipt
remained unavailable. This was a research transport lifecycle defect, not an
identified defect in the running live order backend.

Commit `f23c3629fc1f6603a8fadebdf5ca05c68c137bbf`, on
`research/v89-collector-timeouts-20260917`, binds transport packets to the exact
original durable intent. It retains the original absolute deadline and emits an
explicit terminal event. The parent cancels only an unprepared subscription;
after preparation it releases relay ownership while preserving the immutable
prepared evidence. Other subscribers retain their shared transport.

Late transport packets from a bounded set of 64 retired identities are logged
and discarded. They cannot satisfy a checkpoint exchange or a later request
with the same payload. Unknown, missing, malformed or evicted identities fail
explicitly. Damaged framing remains a technical failure with unresolved durable
evidence; it is not silently repaired or admitted as data. Original collector
code, local obligations, reservation spacing and receipt deadlines are unchanged.

Why now: a reproduced defect prevented continued research capture after a lost
delivery. Applicable regime: data acquisition across market regimes. Expected
upside: more reliable research inputs and explicit failure provenance. No
financial return estimate is established. Proposed live change: none.

| Alternative | Trade-off |
|---|---|
| Leave the relay unchanged | Preserve explicit failures, but retain the reproduced retry obstruction. |
| Increase the original deadline | Change source timing and invalidate the intended fidelity comparison. |
| Clear all shared state after timeout | Risk erasing immutable evidence or disrupting another subscriber. |
| Release only the exact attempt and scope late messages | Preserve source obligations; requires the additional protocol and evidence checks implemented here. |

## Completed validation

All network-facing responses in these experiments are fabricated within the
existing network-denying sandbox. The five original collector interpreters,
source imports, schedulers, SQL stores and local clocks remain real.

| Check | Result |
|---|---:|
| Relevant regression suite | 909 passed, 63 skipped; 399.34 seconds |
| Dropped/late preparation and dropped/late acknowledgement, all five originals | 4 cases passed; 129.29 seconds |
| Final focused transport controls with child coverage | 32 passed; 7.63 seconds |
| Full original-loop damaged-frame refusal | 1 passed; 11.83 seconds |
| Sustained original native retry with four concurrent original peers | 1 passed; 1,035.83 seconds |
| Actual simultaneous sustained interval | 1,000,972 ms |
| Indexed observations / available raw-row occurrences | 17,556 / 31,744 |
| Local attempts / distinct synthetic transports / shared subscribers | 250 / 174 / 76 |
| Native reservations / available responses / unavailable responses | 14 / 13 / 1 |
| Native slots / minimum reservation spacing | All six / 60,013 ms |
| Retained private packets / largest packet | 38 / 232,711 bytes |

These test counts overlap and must not be added into a unique-test total.
Independent raw/index, requested-grid and accounting verification was rerun on
the retained sustained artifact. The original native store retained exactly one
`http_failure`, classified unavailable as `unconfirmed_delivery`, followed by 13
available responses. It had no unresolved witnesses or fault at completion.
Every retained private packet matched its content digest.

The focused controls cover all 35 statements and 16 branches in the new scope
module. The terminal handler has all 24 statements and 13 of 14 branches covered
there; its timely acknowledged-success branch is exercised by original-loop
tests and will be measured in the combined archived qualification. Focused
coverage does not establish full-harness coverage.

Initial assertions needed two fixture corrections: the native store is
`native.sqlite3` with `http_failure`, and a preparation-integrity test must use a
realistic ten-second deadline rather than an OS-invalid centuries-long select
timeout. Dropped acknowledgement already completed on the baseline once those
native-schema assertions were corrected. Retained red output does not establish
that every tested failure mode was a pre-existing defect.

## Exact source and remaining validation

The saved source archive contains 5,755 files. All 11,510 source/archive hashes
matched after the source commit. Archive: 34,082,043 bytes,
SHA-256 `03eb8d10e41a83ec9df3fd89287db01b70477e6346fa79cda5d9460b6aa383d8`.

The separate archived qualification is pending: PID 35213, creation time
1789683123.397369, tool session 80140. It runs the original-loop suite plus the
same 1,000-second native timeout scenario from extracted source. Inspect this
exact handle and retained result; do not restart it because observation times out.

The next investigation is repeated HTTP 429 recovery under the original
five-minute native and peer cooldown rules. Source inspection shows that the
current independent peer verifier covers healthy responses, forecast bursts
and occupied weight, but not early return on peer 429 or unknown response
weight. Extend that evidence before claiming those scenarios. The original
quarter acquire-to-begin gap, service restart, power loss, study-scale costs,
real-network behavior and operational migration also remain unqualified.

Success metrics: preserve exact original source identity, every failed local
obligation, original timing, unavailable/available separation and unaffected
shared followers. An unauthorized observation, deadline extension, lost
obligation, unscoped discard, shared-follower disruption or archive disagreement
falsifies the respective claim. Rollback: leave this offline branch unadopted.
Explicit live approval requested: none for this evidence increment.

At 22:17:14 UTC all 11 preserved process identities matched. The backend reported
6,429 polls, zero faults and unchanged configuration; all five collector health
ages were below 11 seconds. The three comparison jobs had no terminal failure or
qualification result. Sealed economics were not evaluated.

Artifacts:
`data/logs/research/bidirectional_cohort/v89_public_collector_timeouts_20260917_v1/`.
Key files: `sustained_final_independent.json`, `regression.txt`,
`timeout_green.txt`, `controls_final.txt`, `controls_final_coverage.json`,
`framing.txt`, `source_manifest.json`, `source_integrity_running.json`, and
`archive_process_v1.json`. The unfinished archive log and directory are not
pinned as completed evidence.
