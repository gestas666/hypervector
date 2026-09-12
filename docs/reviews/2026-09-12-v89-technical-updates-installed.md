# V89 technical updates installed — 12 September 2026

High confidence in the verified technical corrections: the installed source
matches integration commit `1fba938c7e2067f79190b93d738d6125add71dd5`, and the
installed TUI binary has SHA-256
`eaf4d25836ff0533b6b451f887921d97eed9af9aa021a70fade47408c5aeb9a1`.
The final receipt is
[`installation_verified.json`](../../data/logs/research/bidirectional_cohort/v89_technical_install_20260912_v1/installation_verified.json).
This supersedes the pending-installation status of these technical candidates.
It does not establish strategy profitability or readiness to submit orders.

The user's instruction to analyze, validate and implement critical/high-value
changes authorized this installation. The work applies 69 source, test and guide
files: the staged 65-file recovery/heartbeat/TUI/candle package, the pytest
script-import path correction, and three files for reporter input isolation.
The release executable was replaced atomically after preserving the old binary.
The active trading profile and execution ledgers retained their exact hashes.

| Observed problem | Implemented correction | Validation and limits |
| --- | --- | --- |
| File writes could make a stopped or stale backend appear current | Derive connection health from run-bound backend heartbeats and terminal lifecycle events | Rust health tests, observer lifecycle tests, native stopped-run display; sudden process death still requires the inactivity timeout |
| Restart projections could omit asset/checkpoint/funding context | Install the previously staged asset reconstruction and funding recovery changes | Integrated recovery and accounting tests; historical values remain distinct from fresh venue observations |
| Compact TUI inspection and controls were incomplete | Install chart inspection, scrolling, configuration/control and pagination changes | 48 decoded native frames across 100x28, 120x36 and 190x52; nine views and seven asset inspectors reachable |
| Repeated public candle requests recreated transport sessions | Reuse the candle HTTP session while preserving requests and retry behavior | Prior 16 paired observations favored reuse, with identical candle values; timing results measure data-fetch transport, not fills or profit |
| Full pytest collection could not import a standalone TUI script | Add `scripts` alongside `src` to pytest's import path | Full offline suite completed successfully |
| Research workers failed before database code ran | Give checkpoint and research-worker processes independent standard input | Two behavioral regression cases failed before the fix, passed afterward; fresh installed import completed successfully |

The last defect was reproduced on this Mac. Reporter PID 67205 had descriptor
0 marked `(revoked)` by `lsof`. It was left behind by the first native monitor
acceptance harness when that harness timed out; subsequent monitors reused it.
A minimal terminal-session reproduction produced the identical Python
`init_sys_streams` / `OSError: [Errno 9] Bad file descriptor` failure with inherited
input and exited successfully with independent input. Closing an ordinary PTY
without the controlling-terminal lifecycle did not reproduce it; both negative
probes are retained. The new fix sets `stdin=subprocess.DEVNULL` at both reporting
launch boundaries, retaining output capture, timeout, error propagation and
process ownership. Python documents the input-redirection contract in its
[subprocess reference](https://docs.python.org/3/library/subprocess.html).

Only that failed report-only reporter was stopped. Its replacement had descriptor
0 bound to `/dev/null`, imported successfully at **12:56:55 UTC**, and displayed
`IMPORT OK`. Zero imported events means no new events were found, not a failed
import. The corrected harness quit its owned monitor/reporter and a subsequent
process inventory found neither reporter, monitor nor trading backend running.
No trading process was restarted or armed and no orders were submitted.

Validation evidence is retained under
`data/logs/research/bidirectional_cohort/v89_technical_install_20260912_v1/`:

- Full installed offline Python suite: **8,398 passed, 4 network tests deselected**,
  27 warnings, before the final two-line input-isolation fix. The initial
  collection failure and its import-path correction are also retained.
- Installed affected Python suite after that fix: **74 passed**. Its two new
  regression cases use real child interpreters and require independent input.
- Installed Rust suite: **605 passed, 23 ignored, zero failed**. Formatting and
  Clippy with warnings denied passed. Rust source/binary did not change after
  those checks.
- Native traversal: 48 frames across three sizes before input isolation; 16
  further frames at 120x36 after the fresh successful import. Post-fix frame
  `native_monitor_v4/captures/view_1_120x36.txt` shows `IMPORT OK`,
  `BACKEND STOPPED` and `STOPPED SNAPSHOT` together.
- Exact source/binary hashes, backups and protected-file checks passed.
  Pre-existing unrelated worktree changes were preserved.

Computer-use access to the actual Terminal application was denied by the tool.
The checks used a separate pseudoterminal and decoded native cells; the PNG is
a reconstruction, not a screenshot of the user's window. Some long summary
text clips at compact widths. Reachability and the inspected values passed;
this is not a claim of complete visual acceptance in the original window.

Open the installed monitor from the project directory:

```bash
.venv/bin/python -m hypervector cohort-tui \
  --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector \
  --tui-bin-sha256 eaf4d25836ff0533b6b451f887921d97eed9af9aa021a70fade47408c5aeb9a1
```

Current navigation is `1` portfolio, `2` setups, `3` chart, `4` depth,
`5` trades, `6` log, `7` operations, `8` regime and `9` configuration.
Monitor mode can own a report-only checkpoint process; it does not start the
trading backend. A stopped snapshot is historical even when its research
import is recent. Quit and relaunch an existing TUI to load the installed binary.

Rollback is appropriate if these changes cause reproducible accounting,
health-state or runtime regressions. The complete technical source patch is
`installed_technical_source.patch` in the evidence directory. First check
`git apply --reverse --check` against that patch; apply its reverse only if the
check passes and the installed hashes still match the final receipt. This
refuses conflicting later edits instead of overwriting them. The prior source
archive and addendum backups remain available for file-level recovery.
For the executable, verify the retained
`binary_versions/tui-regime-detector-prior-382253ca` against SHA-256
`382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`, then copy
it to a temporary sibling and atomically replace the release executable while
the monitor is closed. Do not restore ledgers or strategy configuration as part
of this technical rollback. The complete 69-file patch passed a reverse/reapply
rehearsal on disposable copies: reversed files matched the original Git sources,
and reapplied files matched the installed sources byte for byte.

| Alternative | Trade-off | Decision |
| --- | --- | --- |
| Keep the prior installation | Preserves the observed health/import problems | Rejected for these demonstrated defects |
| Install validated technical corrections | Improves reporting, recovery and transport; requires reopening the monitor | Implemented |
| Change strategy thresholds or launch trading | Requires evidence about execution and net returns beyond technical tests | Not part of this installation |

Confidence would decrease if a reporter again inherits revoked input, imports
fail after successful interpreter startup, heartbeat status disagrees with
run-bound ledger evidence, or recovered accounting disagrees with its source.
Investigate such evidence directly rather than masking it with a fresh-file
timestamp. The highest-value unfinished strategy investigation remains the
predeclared SNDK 15-minute endpoint-gap sensitivity study; it was paused for
this installation and has produced no new outcome conclusions. Prospective
outcome seals remain unopened. No further installation approval is pending for
the changes documented here.
