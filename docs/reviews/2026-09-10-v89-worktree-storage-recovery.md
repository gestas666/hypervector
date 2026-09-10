# Verified worktree cache recovery

The current historical replay storage shortfall is resolved as of September 10
04:48 UTC, with 15.70 GB free. Two inactive Rust debug trees were removed only
after complete recoverable archives and source rechecks. High confidence applies
to the recorded byte verification and available capacity; further data growth or
other filesystem writers can reopen the capacity issue.

| Inactive worktree | Verified entries | Retained archive bytes | Observed free-space increase during cleanup |
| --- | ---: | ---: | ---: |
| hypervector-overhaul-20260905 | 50,060 | 1,305,174,868 | 4,329,291,776 |
| hypervector-frequency-20260907 | 64,170 | 2,645,311,832 | 9,264,889,856 |

The archives retain regular-file content, modes, links and macOS AppleDouble
metadata. The corrected September 8 verifier was reused with explicit worktree
and backup paths. Each archive was read completely and every original source
file was rechecked. Fresh checks found no open cache files or Cargo/rustc/rustdoc
processes before removal. Each exact tree was renamed to a task-owned retired
path before removal. The installed release TUI SHA-256 remained
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`.
Research data, live ledgers, frozen replay/reporting source and configuration
were preserved. The coordinator continued without a restart or threshold change.

The overhaul archive is
`data/backups/storage_recovery_overhaul_20260910_v1/debug.tar.zst`, SHA-256
`b0c7fc652e4d865710d83967ea1e38f3f0c10c5300709c23e1bd0dca68c315ce`.
The frequency archive is
`data/backups/storage_recovery_frequency_20260910_v1/debug.tar.zst`, SHA-256
`fd7c9685c98a687aa04cadee8314c5c4d689fc44967397eeec578c20f887a7cd`.
Each directory retains its complete manifests, verification and cleanup result.
Operators and explicit derivations from the previously verified workflow are in
`data/logs/research/bidirectional_cohort/v89_worktree_debug_recovery_20260910_v1/`.

Restore an archive only into its corresponding worktree's `target` directory
when `target/debug` is absent and sufficient capacity is available. The archive
root is `debug`; stream `zstd -dc` into `tar -xf - -C <worktree>/target`.
Preserve any newly generated debug tree before restoration. Normal future Rust
debug builds can regenerate the cache without restoration.

The earlier database block-sharing attempt retained exact historical bytes but
did not establish physical savings. Three sampled cached Parquet files also
showed no savings from filesystem compression; a compressible synthetic control
confirmed that the local compression tool worked. Existing duplicate compressed
backups were already consolidated on September 7. These findings ruled out
repeating those operations during this recovery.

Observed cleanup increases total 13.59 GB, while the two new archives occupy
3.95 GB. Concurrent replay and system writes prevent exact attribution of every
free-space movement. Current capacity covers the remaining original matrix at
the measured case sizes with headroom; this does not qualify trading performance
or authorize a live change.
