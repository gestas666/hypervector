# Package-cache capacity recovery and continuation of the original matrix

The original coordinator exited successfully with an explicit **paused_storage**
result at September 10 12:25:26 UTC: **45/48 cases complete**, three pending,
3.055 GB free, unchanged 2 GiB reserve and 1 GiB per-case reservation. All prior
workers were terminal. Its reporting observer then failed explicitly because
the complete matrix report was absent. Neither event was interpreted as a
complete financial report or a live-readiness result.

The project's inactive compiler caches were already reduced to retained
executables. Eight cached PyTorch wheel builds and their package metadata were
selected for recovery. PyTorch is absent from the active research environment.
A complete archive preserves **102,808 entries**, all logical hashes, modes,
symlinks and macOS AppleDouble metadata. A second inventory confirms the source
was unchanged before cleanup. The retained archive is **508,815,133 bytes**,
SHA256 `94004bd84764dc591ce2273e2a02e88bb47396a0bfeb83f5a26bfcd6a18e18e4`.

The supported package-specific uv cleanup initially waited without changing
anything. Two fourteen-day service wrappers held the global cache lock; each
had only that lock open, and their child Python processes had no cache files
open. Fresh checks found no open consumer of the ten selected cache roots and
no additional uv command. The task's own waiting cleanup was terminated. The
documented, package-specific `--force` option was then used after repeating the
source and process checks. No other service was stopped. This narrow exception
is recorded in `PLAN_addendum.md`; it is not authority for a full cache clean.

The installed uv 0.9.5 removal implementation and metadata schema were checked
against their versioned source. All 753 source-distribution metadata records were
examined: none was PyTorch, and no flat-index cache existed. After cleanup,
all 3,035 unrelated archive directories and all 753 metadata hashes remained.
Protected project environment metadata, configuration and installed TUI hashes
were unchanged. An initial metadata reader expected maps; the actual serialized
structs were sequences. The corrected reader used the versioned six-field schema
and completed before cleanup. The initial failed check remains retained.

At 12:35:04 UTC, actual free space was **4.400 GB**, up **1.914 GB** during
cleanup. This excludes the earlier archive and inventory writes. Logical cache
size and uv's reported 2.7 GiB removal exceed measured physical recovery because
shared storage and concurrent filesystem activity affect capacity. No exact net
causal savings claim is made. Existing backups and installed environments remain.

The unchanged, qualified `--resume` command was then run against the same matrix.
It retains and reauthenticates all 45 receipts, preserving the original case order,
source records, adoption identities, output and technical reservations. Coordinator
**27267** started two workers, **27279/27280**; the final third case remains queued.
There was no overlapping producer. The reporter helper source and full-report
command remain unchanged. A new observer, **27361**, is bound to the resumed
producer's exact PID/start/command digest and the same full-report destination.
Its operator differs only in that PID binding and the explicit immutable helper
path; all 1,955 references authenticate in preflight. Prior observer evidence is
preserved. Its qualified 25-test helper suite was not repeated for identical code.

At **12:46:59 UTC**, the coordinator, two workers and observer are confirmed live,
45/48 receipts remain complete, and free space is **4.094 GB**. No backend, signer,
order or live TUI process was started. The installed technical package is unchanged.

## Updated planning estimate

The same 27 comparable runtimes span 39.7–50.7 minutes. Two current cases followed
by the final queued case give completion scenarios from **09:56 to 10:18 Eastern**.
Adding the retained four-to-six-hour reporting allowance gives a planning target
of **14:00–16:30 Eastern, September 10**, with low-to-medium confidence. This
supersedes the earlier 13:00–16:30 range and is a completed-review estimate,
not a live-start ETA. Insufficient capacity for the final launch, slower cases,
source/integrity failures or slower reporting would require revision.

Confidence is high in the captured file identities, explicit terminal state and
observed continuation. Concurrent new cache activity was the remaining cleanup
failure mode; source reauthentication, bounded package scope and the full archive
provide the recovery basis. Restore to a separate directory under exclusive cache
ownership if needed; do not overwrite an active cache blindly. Changed archive,
runtime or receipt identities would invalidate this acceptance.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_uv_cache_recovery_20260910_v1/`.
Backup:
`data/backups/uv_torch_cache_recovery_20260910_v1/`.
Key records include the two plans, source inventories, `verified.json`,
`cleanup_dry_run.json`, lock observations, `targeted_cleanup_command.json`,
`targeted_cleanup.log`, `cleanup_acceptance.json`, resumed command/start records,
new reporting handoff, `runtime_after_resume.json`, `completion_forecast_v2.json`
and the verified nine-member operator archive.

External references: [uv cache guidance](https://docs.astral.sh/uv/concepts/cache/),
[installed-version removal implementation](https://github.com/astral-sh/uv/blob/0.9.5/crates/uv-cache/src/lib.rs),
and [installed-version metadata schema](https://github.com/astral-sh/uv/blob/0.9.5/crates/uv-pypi-types/src/metadata/metadata_resolver.rs).
