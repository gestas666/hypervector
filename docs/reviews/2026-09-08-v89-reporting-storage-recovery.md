# V89 research reporting storage recovery

Research imports resumed after a verified backup and removal of unused Rust
debug build artifacts. High confidence in the recorded storage, archive integrity,
process lifetime and successful import evidence. This repairs reporting capacity;
it does not establish trading profitability or eliminate future disk exhaustion.

## Observed failure and correction

At September 8 03:06 UTC, the checkpoint reported a deferred research sync:
available storage was below the unchanged 8 GiB requirement. The last successful
import was 03:04:00.970923 UTC. The live backend remained healthy, with two open
protected positions and zero runtime faults. Subsequent attempts remained
deferred until storage became available.

The original checkout's `target/debug` occupied approximately 8.4 GiB of unique
filesystem blocks. No Cargo/rustc process or open file in that directory was
observed before backup or removal. The running TUI uses `target/release`, which
was preserved.

The complete debug tree was archived to
`data/backups/storage_recovery_20260908_v1/debug.tar.zst` before removal. The
archive is 2,319,543,774 bytes, SHA-256
`2b4b9ef614f0200e154ae1d1a4852518cc799397e37e5878499c4d7aee644d95`.
All 247,990 source entries were verified for content/link identity and mode;
the source inventory, timestamps and hashes still matched after the archive
was read. Repeated hard links explain the larger 30.3 GB summed logical file
sizes. The backup retains those links.

The initial verifier rejected macOS AppleDouble metadata as an unexpected
archive member. Original files remained intact. A separate second verifier
validated the AppleDouble magic/version and source counterpart for all 247,991
metadata entries, then verified every ordinary archive member and original
source again. The first verifier, its failure log and the corrected verifier
remain retained; no failed verification authorized deletion.

After that verification, only `target/debug` was renamed to a task-owned retired
directory and removed. The compressed backup and complete verification manifests
remain. Free space increased by 9,014,059,008 bytes, from 4,065,447,936 bytes after
backup to 13,079,506,944 bytes (approximately 12.18 GiB). The installed release
TUI hash remained
`1036c56c9e5680e4ce4c27953e5b536bf72dcea4e9092459132fd111306bc1d3`.
Supervisor 4954, backend 4965, original TUI 8440, reporting owner/reporter
48894/48897 and collector 75062 retained their process lifetimes.

## Recovery evidence and limits

The importer resumed automatically at 03:19:19 UTC and reported success at
03:19:53.971223 UTC. A subsequent frozen checkpoint confirms another successful
import at 03:22:09.850319 UTC with 293 new events, `state=ready`, no sync error,
two current-run fills and zero runtime faults. The configuration SHA-256 remains
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.
No disk threshold, reporting cadence, live configuration, strategy or execution
process was changed.

Backup evidence and cleanup acceptance live under
`data/backups/storage_recovery_20260908_v1/`. The immutable recovered checkpoint
and report are under
`data/logs/research/bidirectional_cohort/v89_storage_sync_recovery_20260908_v1/`.
The collector acceptance snapshot separately retains the preceding deferred
sync condition. All research data and journals remain at their existing paths.

Future debug builds will recreate this cache. If restoration is needed, reserve
sufficient space first and extract the retained archive into `target`; its root
entry is `debug`. The backup can be streamed with `zstd -dc` into `tar -xf -`.
Clearing derived artifacts provides current headroom, not a durable retention
policy. Continued storage growth or another deferred import would reopen the
capacity diagnosis. Live fill/stop reconciliation remains a separate task.

## Current installed monitor acceptance

Two separately owned, detached instances of the installed release binary were
captured after storage recovery: Dashboard at 190x52 and Trades at 120x36. Both
showed LIVE EXECUTION ARMED, SPCX and SNDK open exposure, the complete native stop
IDs 538846363686 and 538806460232, and all nine view controls. Both exited normally
on their own quit command while all original live and collector process lifetimes
remained unchanged. No new TUI build or source change was needed.

The terminal streams were decoded with the already cached pyte package. An
initial verifier incorrectly required the importer to be idle/READY; a regular
import was running during both captures. The retained displays correctly show
`IMPORT RUNNING` and the last successful import at 23:22:09 EDT with 293 events.
`v89_post_storage_tui_acceptance_20260908_v1/report_v2.json` records that correction
against the same raw captures and validates every position, stop-ID and view
control check. The original verification report remains retained.

Existing TUI windows retain the binary they loaded. Open the current detached
monitor in a new terminal:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml
```

This monitor's quit leaves the backend running. The original supervised TUI is
still associated with the original live supervisor; do not quit that window as
a display-update step.
