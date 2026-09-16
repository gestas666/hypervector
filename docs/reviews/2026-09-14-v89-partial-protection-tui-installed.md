# Qualified partial-protection TUI installed

The latest monitor is installed in the main project at commit
`cb536602e01983b57c3ab08d777632d6f4b6fecb`. Its complete TUI source tree matches
candidate `d01abba1deb2c54141ef88a9b8dce2a6ff95335f`; tree identity is
`dca0d702179d132c7a4b8dd7dde9a07698a96ec8`. The installed executable is
10,212,656 bytes with SHA256
`eada0b1359d6ea16e84dfb3d35b46538f95b6dd04cc1945f1a64d0614b5c3d9e`.

Confidence is high for this bounded display installation and its recorded
checks. Backend release validation continues separately. No Python execution
code, strategy, sizing, leverage, configuration or financial transaction was
changed by this installation. The full release is not yet qualified for launch.

## What the monitor improves

When corresponding backend evidence is available, partial protective exits now
show remaining quantity, original opening time, partial fill progress and
whether the remaining position has stop coverage. Pending uncovered exposure
is visibly identified instead of being presented as a protected or completed
position. Venue-synchronous position marks remain separate from strategy
reference prices. Partial-progress details appear when the backend supplies
the corresponding evidence fields.

The existing nine panes and strategy/regime inspectors remain available.
Recorded SOL evidence displays one completed losing lifecycle and four fill
legs separately, with net -$3.56, fees $0.43 and funding +$0.0022. Recorded July
data is appropriately marked stale under the actual September clock.

## Validation and installation evidence

Evidence root:
`data/logs/research/bidirectional_cohort/v89_native_candle_portfolio_20260914_v1`.

| Check | Observed result |
| --- | --- |
| Full candidate Rust suite | 647 passed, 0 failed, 23 pre-existing ignored local-capture cases |
| Actual recorded ledger and checkpoint rendering | 81 headless frames: nine panes, three sizes, three lifecycle phases |
| Candidate executable in native PTYs | Four processes; open/closed phases at 100x28 and 190x52; nine panes and paged setup inspector; normal exit 0 |
| Installed executable in native PTY | Additional 100x28 closed-trade check; all nine panes, inspector and normal exit 0 |
| Installed source files | All 16 changed TUI files match the candidate |
| Complete TUI source tree | Installed Git tree equals candidate Git tree |
| Preserved sources and existing dirty documents | 1,868 protected files unchanged during installation |
| Rollback applicability | Reverse patch checked successfully |

The native display processes ran under the retained `sandbox-exec` policy
denying network access and file writes, apart from terminal device output.
They had no command inbox or trading backend. Captured live-shaped headers are
offline scenario data. These checks inspect actual terminal cells and keyboard
events; they are not a claim about every terminal emulator or profitable trades.

Exact receipts are `tui_installation/prepared.json`, `installed.json`,
`commit_verified.json`, `native_recorded_tui/verified.json`, and
`installed_native_tui/verified.json`. Previous source bytes and executable are
preserved in `tui_installation/before_source.tar.gz` and
`tui_installation/tui-regime-detector.previous`. Navigation documents were
backed up separately before their current command was updated.

## Start monitoring and rollback

Use the command in [the monitor guide](../guides/cohort-strategy-regime-monitor.md).
It supplies the installed executable and its current hash together. It starts
monitoring and does not arm or start trading. When the backend is stopped, a
refreshed analysis checkpoint does not make older strategy decisions current.

Rollback requires matching the installed hashes before restoring the preserved
binary and reversing the exact source patch. A later edit requires a new
comparison; do not blindly reverse this installation over subsequent changes.

A source or binary mismatch, incorrect quantity/mark/protection status, missing
pane, broken navigation or failed quit would falsify the corresponding acceptance
claim. The next required work is completing and independently reconciling both
native portfolio runs, followed by full backend release reproduction and
installation. No strategy-performance conclusion follows from this TUI update.
