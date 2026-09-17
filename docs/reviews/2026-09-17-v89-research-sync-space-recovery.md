# Research sync disk-space incident and recoverable cache cleanup

At the start of this check the drive had approximately 5.2 GiB available. The
running checkpoint reported research imports deferred because available space
was below its existing 8 GiB requirement. The live backend remained
`running_consistent`, with no recorded fault. This delayed research imports;
the observation does not establish a live order-execution failure.

Two unused Rust debug-output directories were backed up and removed under the
existing disk-cleanup authorization. Neither contained Git-tracked files, and
`lsof` found no open files in either before removal. No Rust compiler or Cargo
process was running at the removal checks. The installed release TUI binary,
live configuration, ledgers, research datasets and frozen source were preserved.

| Source | Verified backup | Files | Archive bytes |
|---|---|---:|---:|
| Main `target/debug` | `data/backups/cache_compaction/debug_20260917T220422Z/` | 22,698 | 897,877,914 |
| Native-account replay worktree `target/debug` | `data/backups/cache_compaction/native_account_debug_20260917T221332Z/` | 32,549 | 1,034,662,684 |

Backup verification checked the exact file set, SHA-256 and byte count for every
regular file, dereferenced hard links, and symbolic-link targets. Source content
was rechecked immediately before each removal. Each directory contains its
manifest, archive digest, verification result, cleanup result and exact restore
command. The first verifier was corrected to account for tar hard-link headers
having zero own size; a sequential verification then checked the actual linked
content. No original was removed before complete verification.

After the first cleanup the sidecar imported 7,361 events and reported `ready`
at 22:12:15 UTC. Creating the second backup temporarily brought free space below
the existing threshold again; that deferral is retained explicitly. After the
second removal the observed free space was approximately 10.8 GiB. The sidecar
then completed another import of 318 events at 22:19:34 UTC and reported `ready`
with no error. This result is retained in
`data/backups/cache_compaction/research_sync_after_compaction_20260917_v1.json`.
No restart or threshold reduction was used.

High confidence applies to the observed cleanup and backed-up bytes. Free space
is a changing system measurement, not a capacity guarantee. Future cache builds,
logs or research output can consume this headroom. Restoring a debug backup also
requires sufficient free space. A changed archive digest, changed live identity,
missing research source or renewed sustained import deferral would require a new
investigation.

Runtime identity check:
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/runtime_snapshot_v51.json`.
No live strategy, order, sizing, leverage or deployment configuration changed.
