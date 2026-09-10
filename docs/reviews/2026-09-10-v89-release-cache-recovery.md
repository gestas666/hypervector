# Release compiler-cache recovery and revised completion forecast

At 11:27 UTC the original historical matrix had 42/48 completed receipts and
one worker after free capacity fell near 3.7 GB. The frozen coordinator reserves
2 GiB plus 1 GiB per active case. Its source confirms that insufficient capacity
reduces new launches and can produce an explicit storage pause when no worker
remains. The original coordinator and reporting handoff were preserved.

Five inactive Rust release trees were archived and completely verified before
removing only .fingerprint, build, deps, incremental and examples directories.
Every top-level release file, including installed and candidate TUI executables,
libraries and dependency files, was preserved and hashed before/after cleanup.
Fresh open-file and compiler checks preceded removal. Existing backups,
research data, ledgers, live controls and frozen source were preserved.

| Worktree | Verified entries | Retained archive bytes | Free-space increase during removal |
| --- | ---: | ---: | ---: |
| Technical release | 3,378 | 339,771,028 | 585,621,504 |
| Main | 1,550 | 167,807,635 | 506,126,336 |
| Storage/SPCX | 1,587 | 138,329,343 | 426,553,344 |
| Overhaul | 1,511 | 141,647,552 | 408,940,544 |
| Frequency | 1,509 | 130,254,635 | 409,051,136 |

The archives retain all 9,535 original entries, modes, file/link contents and
macOS AppleDouble metadata. They occupy 917,810,193 bytes. Removal intervals
show 2,336,292,864 bytes of free-space increase, excluding the earlier archive
writes; concurrent writers prevent exact attribution of net system savings.
The reused backup/verifier differs only in explicit worktree/backup paths and
the release archive root. Those derivations are retained as patches.

The new cleanup command defaults to a verified dry run. A duplicate dry-run
attempt correctly refused to overwrite its prior record; it changed no cache.
Each execution followed a successful dry run and fresh checks. Directories were
renamed to task-owned retired paths before removal. Restore only needed cache
directories from an archive extracted into a separate location; do not overwrite
the retained top-level executable files or recreate caches during this research.

At 11:42:21 UTC, free space is 5,381,586,944 bytes and the original coordinator
has increased to three workers, with 42/48 receipts. The installed TUI remains
SHA-256 95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f.
Main runtime/configuration bytes still match baseline b3df618. No restart,
reservation adjustment, live transition or deployment occurred.

## Revised planning estimate

The retained 27 comparable worker runtimes are 39.7–50.7 minutes. Scheduling
the six remaining original identities, subtracting the three active elapsed
times and allowing subsequent concurrency of two or three, gives worker-finish
scenarios from 09:00 to 10:09 Eastern. Two-worker scenarios permit the existing
third worker to finish before enforcing the lower subsequent launch count.
Every scenario includes each remaining identity once, in the original order.

Adding the existing four-to-six-hour reporting allowance gives a revised
complete-review planning target of **13:00–16:30 Eastern, September 10**.
Confidence is low-to-medium. These are observed-duration scenarios, not
probability intervals or a live-start ETA. Fewer than two sustained workers,
further disk pressure, slower cases or authentication/reporting delays would
require another update. No additional cache removal is assumed in this estimate.

High confidence applies to the verified archives, preserved bytes and captured
process counts. Changed archive hashes or source identities would invalidate
recovery acceptance; subsequent resource growth can reopen the capacity issue.

Evidence:
`data/logs/research/bidirectional_cohort/v89_release_cache_recovery_20260910_v1/`
and `data/backups/release_cache_recovery_{technical,main,storage,overhaul,frequency}_20260910_v1/`.
Each backup retains release.tar.zst, source_manifest.json, appledouble_manifest.json,
verified_v2.json, cleanup_dry_run.json and cleanup_acceptance.json. The operator
folder retains the fixed plan, derivations, logs, runtime acceptance and updated
completion_forecast.json. Earlier timing evidence remains unchanged.
