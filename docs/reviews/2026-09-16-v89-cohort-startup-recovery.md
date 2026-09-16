# V89 cohort startup recovery: validated isolated candidate

## Recommendation and observed problem

Prepare candidate `fb8414c20b39a30d553afbcbba6b1c0e57a4fcc9` for an approved
future startup. It combines the durable-decision and funding recovery reads while
retaining initial ledger validation and validation of every historical row.
It is committed and pushed on `fix/v89-cohort-startup-recovery-20260916` and is
**not installed in the running backend**.

Why now: the approved September 16 restart took about 13 minutes to its first
heartbeat. The native cohort path performs three complete validations: ledger
construction, durable decisions, then funding. This candidate reduces that path
to two passes when the ledger generation remains unchanged. The September 15
streaming memory fix is already installed; this addresses the remaining duplicate
cohort read. Applicability is operational across market regimes.

## Evidence and validation completed

The complete frozen input is the authenticated pre-start cohort prefix:
4,556,975,836 bytes, **625,900 records**, SHA256
`c27dc766955efd1ecbf9a859b0dbac57a6b3dc5535f95c1570849ef3f08f5a9f`.
An APFS copy-on-write clone with a separately verified inode was truncated only
in the owned evidence directory to the backup's exact length. Its full hash
matches the backup manifest. The source ledger was not truncated or edited.

Baseline archive: `708c18ae08c75140ef3dc583b5b3d629b6183b91`, 5,640 files,
archive SHA256 `f454c3071e582752922b27294766e279d16d2061c19c367949924e1b440ad4a8`.
Candidate archive: `fb8414c20b39a30d553afbcbba6b1c0e57a4fcc9`, 5,643 files,
archive SHA256 `faa7e5320dee963489ae1884cae2c37a9f076b468b5c5b17051b00fde4df424a`.
All archived file contents and modes, both archive hashes, six declared experiment
pins and the frozen ledger hash passed final verification.

Both native runs terminated with exit 0. Full recovered objects are exactly equal:
36 maximum-hold decisions, three provider-exit decisions, two profit-lock decisions,
funding cursor `1789565902463`, and the native next-sequence cursor. Canonical
state is 184,185 bytes, SHA256
`b80fd1b868e26c532ae12147dc086f9751dd673d444c0870d657294adb63fc88`.
Equality covers the full object contents, not only counts or hashes.

| Measured component | Baseline | Candidate |
| --- | ---: | ---: |
| Full validated passes | 3 | 2 |
| Records per pass | 625,900 | 625,900 |
| Cohort recovery elapsed seconds | 251.1504 | 166.4964 |
| Peak resident bytes, macOS process metric | 337,461,248 | 333,807,616 |

This one sequential pair saved **84.65 seconds / 33.71%** in the measured
component. Shared-host load and cache order can affect timing. The experiment
excludes asset recovery, backup, provider startup and live execution; it does
not establish a complete restart ETA or improvement in trading returns.

Candidate tests: **162 passed in 5.76 seconds**. Independent Git-archive tests:
**162 passed in 3.99 seconds**. Coverage of the three recovery helper modules is
81/81 statements and 18/18 branches; this is not whole-system coverage.
The native cases exercise all decision families, exact-profile funding, legacy
activation, missing/empty files, repeated queries, append, replacement, deletion,
same-size edits with restored mtime, changes during capture, metadata errors,
corrupt discarded rows and duplicate-decision error precedence. Ruff and scoped
file/function-size checks pass.

Failed attempts are retained. The first RED fixture used a mismatched profile;
after correcting it, three read-count assertions failed before implementation.
A dotted pytest-cov source option caused duplicate NumPy import during collection;
file-based coverage selection resolved that harness issue. An inherited runner
test used an obsolete protocol autospec; its identical failure was reproduced on
unchanged baseline source before correcting the candidate fixture. The first
archive test lacked the sibling backtest provider dependency. All 530 required
provider files were restored outside the source archive from authenticated backup
implementation files, then the archive tests passed without source edits.

## Proposed live change, alternatives and controls

The proposed source installation changes startup recovery only. It retains the
three durable decision families' historical scope and funding's exact-profile
scope. Funding semantic validation remains at the original property boundary.
The selected funding rows are single-use. A changed device, inode, size, mtime
or ctime invalidates reuse and invokes the existing complete recovery reader.
Subsequent queries also use that reader. Errors propagate.

| Alternative | Benefit | Cost or limitation |
| --- | --- | --- |
| Keep installed source | No installation work | Retains the measured duplicate scan |
| Install this candidate for a later approved start | Removes one full cohort scan | Adds instance-local generation bookkeeping |
| Add a persistent index | Potentially larger future reduction | More recovery/versioning complexity; not validated here |

Expected upside is a shorter recovery component, with no expected strategy-edge
change. Main failure modes are stale cached funding under an unsupported filesystem
metadata model or concurrent mutation, increased retained funding rows during
asset recovery, source installation mismatch, and an untested integration path.
Generation checks assume normal metadata behavior and existing exclusive-writer
ownership; they do not provide cryptographic detection of adversarial filesystem
changes. Unchanged complete outputs on one history do not prove every future case.

Validation still required before promotion: approved source installation with
backup/rollback identity, installed-source tests and a separately authorized next
startup acceptance checking position/stop adoption, funding continuity and fresh
heartbeat. Do not restart the currently healthy backend just for this optimization.
Success means unchanged recovered decisions and funding boundaries, complete row
validation, one fewer stable-generation scan, and no adoption or runtime fault.
Any output mismatch, hidden corrupt row, stale-source reuse or startup fault
invalidates acceptance; retain/reinstate the prior source for the next approved
start and inspect exposure before process control. Existing venue stops remain
subject to independently observed venue state.

Confidence is high for the tested recovery behavior and complete frozen equality;
medium for the size of future timing improvement. New evidence of a changed
output, missed mutation or different deployment call order would update that
assessment. Explicit approval is required before installing the candidate in live
source. The completed `approve to unstop it` authorization restarted the existing
version and is not being treated as approval for this separate source change.

## Retained evidence

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_cohort_startup_recovery_20260916_v1/`.
It contains the declared benchmark, immutable archives/manifests, frozen prefix,
complete native logs, coverage reports, failed attempts, provider dependency
authentication and `full_comparison_verified.json`. The journal record pins these
artifacts and this review. Real prospective outcomes remain sealed; ongoing
research jobs and live backend were preserved throughout this experiment.
