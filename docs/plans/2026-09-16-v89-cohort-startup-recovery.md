# Cohort startup recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the duplicate cohort recovery scan without changing recovered decisions, funding coverage or complete row validation.

**Architecture:** Combine the existing durable-decision and exact-profile funding selectors in one validated `read_matching` call. A single-use, instance-local recovery object retains only those selected records. Its initial funding projection is eligible only when the ledger file generation is unchanged before/after capture and before use; changed or previously consumed snapshots delegate to existing recovery. Keep initial ledger validation and the existing decision/error ordering.

**Tech Stack:** Python 3.13, pytest, native SolLiveLedger, immutable pre-start backup, macOS sandbox.

## Scope and evidence

The September 16 approved restart took about 13 minutes to its first heartbeat.
The September 15 memory fix is already installed and is not being repeated.
The current cohort constructor validation, durable journal loading and funding
property each validate all rows. The frozen pre-start cohort contains
4,556,975,836 bytes; source SHA256
`c27dc766955efd1ecbf9a859b0dbac57a6b3dc5535f95c1570849ef3f08f5a9f`.

No running financial source or process will change in this experiment. Candidate
installation remains a separate approval decision. Preserve ongoing research jobs,
real outcome seals, backup and archived source. Stream the compressed evidence
for reproduction if possible; free disk space does not justify copying all histories.

## Task 1: Reproduce redundant recovery and specify boundaries

Create `tests/test_cohort_startup_recovery.py` using the real ledger/telemetry.
Count actual recovery reads, assert one read for constructor plus first funding
query, and assert exact recovery of all three decision types and owned funding.
Cover a second query, append, same-size edit with restored mtime, replacement,
missing/new files, source changes during capture, malformed discarded rows,
foreign-profile records, legacy activation, malformed latest funding and duplicate
decision error ordering. Use local fixtures only.

Run with ROOT Python and `PYTHONPATH=$CANDIDATE/src:$CANDIDATE/tests`:
`python -m pytest tests/test_cohort_startup_recovery.py -q -m 'not network'`.
Retain the expected RED assertion that two recovery scans occurred instead of one.

## Task 2: Implement and validate one combined recovery pass

Create `src/hypervector/live/cohort_startup_recovery.py` with file generation
identity (device, inode, size, mtime_ns, ctime_ns), combined selected records and
single-use funding retrieval. Missing initial files remain explicit empty sources;
metadata/I/O failures propagate. Changed generations cannot reuse cached records.

Factor the existing selector and record-to-cursor calculation in
`cohort_funding_recovery.py` for shared use. Expose the existing durable selector
from `cohort_durable_decision_recovery.py`. Wire the recovery object into
`multi_asset_cohort_telemetry.py`, preserving decision validation before funding
validation and keeping that file at most 500 lines. No ledger writer changes.

Run focused tests, inherited funding/durable/telemetry tests and related runner
startup tests. Verify all new statements/branches and error paths; run Ruff and
`git diff --check`. Commit the validated isolated implementation.

## Task 3: Authenticate and compare full frozen recovery

Authenticate the pre-start manifest, compressed cohort and decompressed source
stream. Compare original versus candidate on the complete captured cohort, using
existing native JSON/sequence validation and complete recovered decision maps,
funding cursor and source hashes. No live clients or financial writes. Separate
input integrity, output equality and timing measurements; timing is not an ETA.

Reproduce the candidate from its Git archive. Require unchanged complete outputs,
explicitly retained failed attempts and source identities. Test source invalidation
separately; do not use artificial cache-warming to claim end-to-end improvement.

## Task 4: Journal and prepare review

Publish a review with recommendation, measured opportunity, regime applicability
(operational, any regime), alternatives, expected benefit, risks, validation limits,
success/failure criteria and rollback. Append an immutable hypothesis revision to
DuckDB, verify evidence references, commit/push the branch and documentation.
Propose installation only after the complete candidate is reviewable. Do not restart
an already healthy backend merely to activate a startup optimization.
