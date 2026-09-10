# Verified prebuilt cohort TUI launch qualification

The isolated correction at **e8dbdaff68700bd2fe61c4104e4e4d317f429db0** passes
**129 tests in the worktree and the restored source archive**. It adds explicit
`--tui-bin` and `--tui-bin-sha256` selection through both CLI layers, verifies
the executable before supervisor child startup, and rechecks it immediately
before foreground invocation. It is not installed or authorized for live use.

High confidence applies to the measured command and offline lifecycle behavior.
Changed source or executable hashes, lost CLI arguments, changed data arguments,
or a child starting after failed verification would invalidate that finding.
Actual venue state, terminal presentation and financial improvement remain
unverified by this qualification.

## Observed problem and correction

Correction to the earlier deployment readiness assessment: the installation
rehearsal verifies file contents and replacement, but it does not establish that
the supervisor invokes the installed executable. The existing cohort command
unconditionally selects `cargo run`, and the supervisor starts its backend
before invoking that command. The installed binary is present; its Cargo
fingerprint, dependency and build directories are absent after the verified
cache recovery. Cargo's documented command follows a
[build-and-run path](https://doc.rust-lang.org/cargo/commands/cargo-run.html).
No Cargo build or live start was used to reproduce this source-level finding.

Explicit binary selection now uses the absolute verified executable with the
same symbol, cadence, initial view, checkpoint, ledger, inbox and supplemental
display arguments. Backend, checkpoint, dependency, profile and authority
arguments match their prior values across observe, monitor and live modes.
Missing selection components, malformed hashes, absent/non-executable files,
read failures, mismatched bytes and command substitution fail explicitly.
A selected binary never falls back to Cargo. Omitting both new arguments
preserves the existing development path, so the revised release command must
include them.

The selected binary is rechecked before any supervisor child starts and again
at the foreground subprocess boundary. A failure during the backend readiness
wait still reaches the existing owned-checkpoint and owned-backend cleanup
paths in the fake-process tests. Normal shutdown semantics are unchanged.
These checks leave a filesystem check-to-exec race; controlled executable
ownership and a fresh deployment check remain necessary. A matching hash proves
identity, not arbitrary executable safety or successful live presentation.

## Validation and retained failures

The new binary module covers **44/44 statements and 14/14 branches**. The moved
argument/validation module covers 31/34 statements and 7/10 branches; its three
uncovered branches are existing invalid-option paths, not claimed as verified
by coverage. Existing broader supervisor coverage also remains partial.
The 21-file regression selection includes authority, accounting epoch, provider
dependency, checkpoint ownership, run binding, normal shutdown and binary drift.
These are 129 related tests repeated in two source locations, not 258 independent
tests. No signer, order client, backend or trading process is constructed by the
new tests; process boundaries are mocked.

The first 27 failures reproduce absent binary-selection support. An initial
coverage invocation fails during collection with a repeated NumPy import;
path-based coverage works without changing the installed environment. A wider
archive run catches the moved accounting-loader interface and missing local
fixtures. The final implementation preserves that original loader boundary and
moves only parsing/argument validation. An invalid-mode control exposed an
observer fallback in the new helper; it now raises the existing configuration
exception. An initial test expectation of a different exception class was
corrected. The earlier source, logs and archive remain retained.

Eight unchanged local evidence files, totaling 9,315,461 bytes, support three
legacy artifact-dependent checks. Two sets are September 3 accounting-epoch
evidence. The saved current checkpoint is copied opaquely and searched only for
the retired V37 configuration filename by the unchanged legacy test. No
prospective signal, position, trade, return or account-outcome reconstruction
occurs. Retained copies and original hashes match before and after testing.
Those epoch manifests also authenticate their existing local backup references;
this is same-machine qualification, not a self-contained external deployment.

All 5,210 archived Git blobs and modes, and their restored source copies, match.
The corrected archive is **33,105,841 bytes**, SHA256
`4d793e15d4e005bb1c2fda5ecaf7d590393047f01c82b72c482f3e0c3c7b55a7`.
Ruff and the changed files' size, function-length, annotation and public-docstring
checks pass. The supervisor is 483 lines. The existing TUI binary's hash matches
the accepted candidate and its native `--help` returns zero with the required
checkpoint, lifecycle and navigation flags. Argument parsing exits before
terminal initialization; no display or live-acceptance claim follows.

## Proposed release decision

| Required proposal field | Decision and evidence |
| --- | --- |
| Recommendation | Include this qualified launch correction in a superseding combined technical release packet. |
| Why now | Cache removal exposes a launch dependency that the file-installation rehearsal did not cover. |
| Evidence reviewed | Exact command construction, absent build metadata, executable hashes, 129 worktree/archive tests, native help and preserved failed attempts. |
| Applicable market regime | Technical launcher behavior across the unchanged configured routes; no market-regime rule changes. |
| Proposed live change | Five runtime files add authenticated binary selection and retain existing lifecycle behavior; two new test modules and existing-test docstrings accompany them. The combined difference from installed baseline is 60 source/test paths. Installation is pending. |
| Expected upside | Use the retained qualified executable without compiling during the selected release startup. No trade-frequency, win-rate or return improvement is established. |
| Main risks | Incorrect or changed selection refuses launch; drift during readiness triggers existing cleanup; check-to-exec races remain; omitted flags retain Cargo behavior. |
| Validation complete | The bounded command, identity, ownership-cleanup, source archive and native-help checks described above. Profile and Rust/Cargo source remain equal to the prior qualified release. |
| Validation still required | Superseding exact installation and compatible rollback packet, original full economic report, final selected approval, fresh account/order/source checks and all nine TUI views. |
| Success measurements | Exact selected binary at the subprocess boundary, no Cargo invocation for that selection, unchanged backend/data arguments, explicit refusal on identity failure, fresh matching operator telemetry. |
| Failure/rollback triggers | Wrong or changed source/binary identity, unexpected process invocation, lost telemetry binding or changed cleanup behavior. Preserve logs and use only the approved containment scope. |
| Confidence | High for scoped offline contracts; live behavior and economic benefit remain unproven. |
| Explicit approval requested | Deferred to the complete revised release review. This qualification grants no installation, restart or trading authority. |

Leaving the current command unchanged retains the observed build dependency.
Restoring build caches consumes space and still does not explicitly select the
packet binary. The proposed explicit path makes the selected artifact reviewable
and keeps the current development command available when deliberately chosen.

After approval and installation of the complete revised release, the proposed
user-run command is:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui \
  --mode live \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --backtest-lab-root /Users/gestas/Prototypes/backtest-lab/backtest_lab \
  --tui-bin /Users/gestas/Prototypes/hypervector/target/release/tui-regime-detector \
  --tui-bin-sha256 604307380b4b047453e0492a349760e737c58da3a917f37305feb39072af3ea3 \
  --enabled --i-accept-live-risk
```

Both parser layers preserve these exact arguments in a non-executing probe.
The current installed CLI does not yet support the two new options. The old
52-file packet remains unchanged; its deployment procedure must be superseded
before this command is presented as launch-ready. Compatible rollback must also
specify how the prior verified executable is selected without a build.

Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_prebuilt_tui_launcher_qualification_20260910_v1/`.
Use `qualification.json`, `source_commit_v2.json`, `source_archive_v2_verified.json`,
`tests_archive_v2.log`, `coverage_archive_v2.json`, `supplemental_fixture_manifest.json`,
`native_help_verified.json` and `proposed_command_verified.json`. Recorded test
commands describe the completed runs; any future rerun needs fresh output paths
to preserve those immutable receipts. The original financial reporter and
automatic report handoff continue unchanged, and both prospective outcome seals
remain intact.

After qualification, both restored source copies were removed only after
10,430 source/fixture/log files matched retained backups and neither directory
had an open reader. Both source archives, all eight fixtures and the two
test-generated checkpoint logs remain available. Measured free space increased
by 468,942,848 bytes during removal. Reproduction requires restoring the source
archive with file modes normalized to its pinned Git tree (archive mode & 0755)
and copying the eight supplemental fixtures to their recorded relative paths.
The initial cleanup checks stopped before deletion on the unarchived logs and
Git tar group-write permissions; the final plan records their explicit handling.
Use `source_copy_cleanup_plan.json` and `source_copy_cleanup.json` for that proof.
