# Historical backup preservation and unresolved storage capacity

At September 10 04:15:05 UTC, the historical August 7 backup was replaced by a
byte-identical image sharing unchanged blocks with the current database. A separate
verified recovery image was retained before replacement. High confidence applies
to preserved bytes and checked metadata. No physical space recovery is established.

The full read-only scan compared 36,849,332,224 bytes and identified 727 differing
ranges totaling 401,358,848 bytes at 4 KiB granularity. A separate candidate was
cloned from the current image, truncated to the original historical size and patched
only within those ranges. The original backup, full candidate, final backup and
retained recovery all matched SHA-256
`41cab11e072fd374ea70eddad77cb9780ff186cd758e315e46ce0c32f9bcfa13`.
Mode, owner, group, modification timestamp, flags, xattr hashes and ACLs also
matched. The current database's scanned file identity remained unchanged throughout
the operation, under read-only database locks; no financial rows were decoded.

The isolated helper is frozen as `b9419e104d261f05c08103b6f3f2aaa9e27409d2`.
Twenty tests passed in the worktree and from the retained source copy, covering
114/126 measured statements. They exercise actual local clone isolation and
metadata preservation, complete image hashes, incorrect ranges, missing space,
changed inputs, corrupt recovery, failed replacement and overwrite refusal.
Cloning does not fall back to a complete copy if unsupported. This follows the
documented [Apple clonefile behavior](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/man/man2/clonefile.2).

Candidate construction took 93.73 seconds and moved observed free space from
7,090,774,016 to 6,674,259,968 bytes. Replacement and recovery verification took
108.38 seconds; observed free space moved from 6,917,713,920 to 4,789,932,032 bytes.
At 04:15:54 UTC it was 5,167,357,952 bytes. System swap was allocated 2 GiB with
976.31 MiB used. Concurrent disk activity and possibly pre-existing block sharing
prevent attribution of these free-space changes to this operation. Ordinary file
allocated-block counts cannot distinguish shared physical ownership.

The hypothesis that this operation would resolve matrix storage pressure is
unconfirmed. Do not repeat it without new physical-space evidence. The backup
preservation requirement passed; the storage capacity requirement remains open.
Keep both historical images. The recovery image is
`data/research/backups/market-before-hip3-symbol-repair-20260807.shared-recovery-20260910-v1.duckdb`.
Recovery would require verifying that image and atomically restoring its clone;
do not overwrite either path with different bytes or discard historical evidence.

The four historical workers continue, with technical reservations that can reduce
later concurrency. Another output drive remains the simpler capacity solution;
the existing user question is pending. No live strategy, parameters, execution,
deployment configuration or prospective outcome access changed.

Evidence is retained under `data/logs/research/bidirectional_cohort/`
`v89_snapshot_block_sharing_20260910_v1/`: source and scan records, test logs,
explicit build/replacement launch records, operator, and complete result records.
