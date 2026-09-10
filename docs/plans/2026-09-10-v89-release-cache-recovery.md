# Recover inactive Rust release compilation caches

The original historical coordinator has 42/48 receipts and one worker after
free capacity fell near 3.7 GB. Its frozen scheduler retains 2 GiB plus 1 GiB
per active case. Do not restart it or change those settings. No compiler was
observed. The five release trees occupy about 3 GB of allocated file blocks;
APFS sharing means this is not a guaranteed physical recovery amount.

Reuse the verified September 10 archive/AppleDouble workflow with exact derived
paths and archive-root substitutions. Preserve each complete release tree in
its own zstd archive, then verify every archived file, link and mode against
both the prearchive and current source. Existing 3 GiB archive-write reserve
and 2 GiB archive-size cap stay unchanged. Failed backup/verification preserves
the cache. Retain derivation patches and all previous backups.

Only after verification and fresh open-file/compiler checks, retire and remove
.fingerprint, build, deps, incremental and examples directories. Preserve every
top-level release file, including each TUI executable, libraries and dependency
files. Verify all preserved top-level hashes before and after each cleanup.
Record actual free-space change and coordinator worker count; do not infer
savings from logical or APFS-allocated sums. The backup permits restoration into
an isolated directory followed by selective recovery of removed cache paths.
No live configuration, installed executable bytes, trading process, research
source or financial evidence may change. Do not recreate the removed caches.
