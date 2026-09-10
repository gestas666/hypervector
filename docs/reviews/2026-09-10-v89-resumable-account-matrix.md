# Qualified resumable original account matrix

The complete 48-case historical matrix is running under the separate coordinator
frozen as `2486adfd9484bdb08f7acb0763e156bb60c19744`. It invokes the unchanged
`69dd84a` replay engine and retains compatibility with the `3400457` reporter.
The first three completed original cases were adopted with explicit report hashes
and fresh independent account audits. Four subsequent original cases are active
as of September 10 04:12 UTC. This establishes actual adoption and worker launch;
it does not yet establish successful completion of a coordinator-launched case.

The coordinator passed 55 focused tests in its worktree and 55 from its verified
archive, covering 459/527 measured statements. Tests exercise ownership across
actual subprocesses, storage pauses and resumption of all 48 fixture cases,
immutable receipts, changed-source rejection and adoption with audit agreement.
Fixtures replace historical financial computation in the orchestration tests.
A separate read-only preflight passed against the actual registered sources.

Each receipt binds all five complete output artifacts and the original case
identity. Resumption authenticates completed files and refuses incomplete or
changed attempts. The inherited owner-lock descriptor prevents an overlapping
coordinator if a parent exits while its worker survives. Storage admission keeps
a 2 GiB reserve plus a 1 GiB estimate per active case, with at most four workers.
Performance does not remove cases or stop trials; technical failures remain
explicit and preserve their evidence. The final original-format matrix report
requires all 48 cases.

Source archive SHA-256:
`9fc6d6a74f117bea51fdb1404d279b6bb360156c735fb33b209c4731edbfbc2f`.
All 5,588 regular archive files and 1,939 implementation members were verified.
Qualification is retained under
`data/logs/research/bidirectional_cohort/v89_historical_account_resume_qualification_20260910_v1/`.
The active output is `v89_complete_historical_account_matrix_20260910_v1/`.
Do not restart session 33137 or modify either frozen implementation while active.

Initial isolated case setup took about 200 seconds, followed by 1,931–2,566 seconds
for account replay and auditing. That supported an initial 8–10-hour planning
range. Current concurrent evidence supersedes that estimate: at 04:20 UTC the
first two workers had completed 23,214/69,121 and 39,260/138,241 event lines after
approximately 24 minutes of worker lifetime. These are complete lines in bounded
compressed-file prefixes, not completed accounts or performance measurements.
The provisional remaining replay range is 16–20 hours at current concurrency,
with low confidence until a full parallel batch completes. Final reporting and
reproduction remain additional work. Shared CPU/I/O, larger variants, technical
errors or reduced storage concurrency can extend it. This is not a live ETA.

The simpler non-resumable runner requires sufficient uninterrupted resources and
would lose reusable progress after a technical interruption. The coordinator adds
state-management complexity to retain completed computation. Full native matrix
completion, final authenticated comparisons and reproduction remain required.
No prospective outcome access or live lifecycle/configuration changes occurred.
