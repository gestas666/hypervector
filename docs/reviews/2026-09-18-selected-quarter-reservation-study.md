# Durable reservations selected in simultaneous original collectors

The isolated successor `9d077401b2733ea4eeb46190f5a660d7c087f4ec` adds an
explicit versioned reservation selection to the offline five-collector study.
The declaration hash covers the selection, every child receives it, and only
the two quarter-v2 originals activate the durable adapter. Omission preserves
the legacy study; booleans, unknown versions and non-integers are rejected.

High confidence in the tested selection and accounting paths. A 30-second
study used all five original processes and recorded 23 reservations and 23
HTTP begins in each applicable original. Its wall duration was 151.91 seconds
including the recorded wait outside the original native quarter-hour blackout.
The short study does not establish sustained scheduling or recovery behavior.

The new stdlib verifier independently checks declaration/configuration
identity, sealed reservation and binding records, monotonic ordering and
rolling capacity, unique original HTTP begins, checkpoint identities, reported
counts and original in-memory reservations. It does not call production
reservation validators. Nine altered copies were rejected after each pristine
copy first passed. The separate verifier test run passed 11 tests in 44.49 s.
Broader selected/legacy checks passed 66 tests with one sustained test skipped
in 91.23 s. Coverage was 98% for the new verifier and 90% for the existing
coexistence module; the sustained run must exercise rolling expiry.

The broader run retained ResourceWarnings from existing health fixtures.
A targeted regression reproduced five unclosed SQLite connections. Both
fixture writers now explicitly close after their transaction, and 74 affected
health tests passed in 1.34 s without those warnings. This is test-fixture
resource ownership, not a change to the original traffic guard.

At 02:42:09 UTC, candidate and archived-source studies were running as verified
processes 54732 and 56604. Each declares 1,300 seconds, 1,440 minutes of synthetic
history, two-second initial response latency, the delayed peer-429 scenario,
and reservation version 1. Their predeclared stop times are 03:03:05.542 UTC
and 03:03:49.513 UTC respectively, followed by verification and cleanup.
No sustained result is claimed yet. The required evidence includes actual
native refusal and recovery, six original native history slots, repeated
quarter cycles, consumed peer-health bytes, exact request accounting and
independent durable-reservation reconciliation.

The archived candidate has 5,807 files and 11,614 matching working/extracted
file checks, zero changed and zero missing. Its 33,861,832-byte source archive
has SHA-256 `738c58354f6516938ca71642fb625c2dc1673b3452fcd204d4efcd7b02a18958`.
Evidence is under
`data/logs/research/bidirectional_cohort/v89_public_quarter_reservation_coexistence_20260918_v1/`.

The prior supervisor extraction was removed only after its journal-pinned
archive and all 5,802 extracted files were verified, with no open handles or
direct extraction pins. The recovery command remains in this study's
`extraction_compaction_completed.json`. Another unused historical compiler
dependency cache was archived, byte-verified and removed; its recovery records
are under `data/backups/cache_compaction/open_hold_source_replay_deps_20260918T023500Z/`.

Retain the candidate pending both sustained results. Lost/doubled obligations,
an unbacked HTTP begin, changed original admission behavior, false worker
deadlines, accepted unavailable data or a failed replay would contradict the
integration claim. No live strategy, risk, sizing, universe or deployment
change is proposed here, and no economic improvement is inferred from these
infrastructure tests.
