# Installed V89 strategy, regime and exposure monitor

High confidence in this bounded read-only repair: the installed Rust source and release binary match source commit `1756f8d3f19aa913b22a807297a8be0dce94f697`. The user explicitly requested implementation of the historical audit corrections and then an updated TUI for tracking, monitoring and planning strategy indicators and their corresponding regimes. No additional approval was needed for this monitor update. No strategy, asset universe, leverage, sizing, live configuration, execution behavior or order was changed, and no trading backend was started.

The earlier historical-report corrections remain installed. This change addresses independently reproduced display defects and the user's subsequent monitoring requirements.

| Requirement | Installed behavior | Verification |
| --- | --- | --- |
| Strategy indicators and plan | Screen 2, select a setup and Enter: exact provider and asset, recorded indicators, entry/exit contract, configured sizing, blockers, source, decision time, arrival lag and elapsed evidence age. Full evidence scrolls. | Every published indicator for all seven configured provider/asset pairs was compared with the frozen checkpoint in actual terminal captures. |
| Correct signal chart | Screen 3, Enter: use the matching backend `signal_timeframe` when reported; show the configured source timeframe separately. Hourly strategies aggregate only complete one-hour candles from source one-minute bars. | Regression first reproduced SNDK's erroneous 15m chart. Native SNDK now shows 1H candles, 15M source, completed-hour indicators and excluded incomplete hours. |
| Corresponding regime | Setup inspector separates canonical context available at the recorded strategy decision from the latest recorded canonical observation. Each includes its own date, states and age. | Same coin and exact canonical provider; both decision and observation times must precede or equal strategy evidence. Future, late, foreign and missing evidence tests pass. |
| Whole regime workstation | Screen 8 retains the per-asset 1m/5m/15m matrix, compression/trend diagnostics, label tape, open lifecycle drift and outcome/arbitration pages. Left/right select assets; PgUp/PgDn expose all three pages. | Existing render checks and native captures retain the nine screens, seven asset charts, indicator lists and regime pages at all three supported sizes. |
| Honest open-position monitoring | Footer shows last observed exposure, source age, conditional overdue hold and stopped/unknown/unarmed local exit management. The open-regime pane labels snapshot countdown and last recorded stop. | Timer provenance/arithmetic, malformed/legacy fields, stale extension support, conflicting identities and multi-position warning priority are tested. |
| Reviewable planning | Screen 9 keeps effective settings separate from its next-run draft; existing controls and authority checks remain intact. | Existing configuration, scrolling and request-safety tests pass. This installation did not stage or submit any profile/request. |

## Evidence and implementation

Python already published open-reflection `as_of_timestamp_ms`, the bound `opened_at_ms` and `timer_origin`. Rust discarded those clocks and presented frozen remaining time as LEFT. The new projection retains them and validates checked duration/deadline arithmetic, exact remaining time, supported policies and valid extension intervals. A later wall-clock expiry of old exposure says IF STILL OPEN; an expiry already observed at its source time says AT SNAPSHOT. Old regime support does not silently grant an extension. Legacy absence is explicit, while conflicting partial provenance fails parsing.

The original warning header consumed a content row and caused 21 compact layout regressions. The final warning uses the existing footer bottom border, preserving the original body geometry. A separate multi-position regression demonstrated that an earlier fresh trade could hide another trade's missing clock; the warning now prioritizes evidence needing attention before deadline order.

The hourly providers publish `source_timeframe=15m` and `signal_timeframe=1h`. The original focused chart used only the configured source timeframe. It now uses the matching evaluation's signal metric, keeps legacy configured-timeframe behavior when the metric is absent, and reports malformed explicit metrics as unavailable. It does not borrow another provider's indicators. Arrival-minus-decision delay is labeled ARRIVAL LAG; DATA AGE measures elapsed observation age. Stored indicators are labeled RECORDED.

Canonical context is an as-of join over retained backend telemetry, not a new classifier or entry gate. The inspector reports how far the selected canonical bar precedes the strategy decision. Missing retained history is unavailable; the latest recorded observation stays separate. Provider-specific entry rules and canonical telemetry have separate roles.

## Validation

- **641 Rust tests passed**, with 23 existing tests ignored because they require separately generated historical/runtime QA fixtures. The mandatory V86 screen fixture was copied byte-for-byte and authenticated; it passed.
- **8,470 Python tests passed**, four network-marked tests deselected, 27 warnings. An initial isolated-worktree run lacked ignored on-disk datasets; the unchanged Python suite was rerun successfully against the authoritative root fixtures.
- Formatting and Clippy with warnings denied passed. Changed Rust files remain below 500 lines. New/modified functions satisfy the 50-line limit; an untouched pre-existing 52-line attribution formatter remains outside this change.
- The new strategy-context module measured **94/94 lines and 151/151 regions covered**. Separate matching LLVM test executables avoid the incompatible function-map warning from the initial combined export. The three new hold diagnostic modules also have complete coverage of their reported per-line execution counts when unioned across their matching test executables; this is not a branch-coverage claim.
- **115 native PTY captures passed** at 100×28, 120×36 and 190×52. They include all nine views, seven focused charts, every setup inspector page and all three regime pages. Every native process exited normally, and the binary and source ledger hashes remained stable. The captures compare every recorded indicator for each configured provider/asset pair with the frozen checkpoint.
- A **373-file source archive** rebuilt in Cargo offline mode and passed **369 library, view, checkpoint and hold-contract tests**. Earlier 370-file hold-only reproduction and 51-frame acceptances are retained as earlier version evidence.
- A further **17 native views** passed from the installed root binary at 120×36; quit returned normally and its hash matched the candidate.
- Installation applied **30 source/plan files** and the exact tested binary. All installed hashes match; **96 other protected root files** remain unchanged. The previous root dirty handoff/index and source-propagation documents are preserved.

Native PTY evidence is actual terminal output from the Rust binary, with reconstructed-cell images inspected. It is not a screenshot of the user's original Terminal.app or a substitute for the user's own visual acceptance.

## Operational boundary

The source checkpoint used for acceptance reports a stopped run; its open-position observation is September 11, 15:37:14 UTC. At the fresh unsigned venue check on September 12, **20:29:57 UTC**, the original **-0.306 SNDK short** remained open, with the full-size reduce-only Stop Market at **1669.9** still open. Its unrealized PnL was **+$1.071** at that observation; this is not realized return or later account state. The bound 24-hour decision-clock hold had elapsed. Recorded `operator_stop` does not identify who stopped the process, and this evidence does not establish an active-runner timer-calculation defect. A venue stop's observed existence does not guarantee future execution.

The TUI repair makes the dated evidence visible; it does not resume local exit management, refresh a stopped strategy's indicators, or establish profitability. Strategy and account values may change after these snapshots. Prospective September 22/23 outcome seals remain unopened.

## Use and rollback

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector \
  --tui-bin-sha256 844d7955a2a4498db90413f3ec0d98003e68d4f5b6554835e9fe7da310cab2ae
```

September 12 launch correction: the previous command omitted the required
`--tui-bin-sha256` and reproducibly exited with status 2 before opening the
display. The command above supplies the installed binary's verified hash.
Monitor mode may start a report-only checkpoint writer; it does not restart
strategy execution. See `docs/guides/cohort-strategy-regime-monitor.md` for the
current controls and freshness limits. This corrects the launch instructions;
the original direct-binary native acceptance did not test that launcher command.

Revalidation completed at **2026-09-12 23:01 UTC**: 641 Rust tests passed,
23 existing fixture-dependent tests were ignored, and 39 focused Python launcher
and stale-attachment tests passed. Formatting and Clippy passed. The installed
binary and all 30 installed update files still match their installation hashes.
Forty fresh native views verified all seven strategy inspectors, the signal
charts and regime pages; the corrected documented launcher separately opened
all nine views and quit with status 0. Reconstructed terminal-cell images for
the SNDK inspector/chart and regime/configuration views were inspected.
The runtime ledger, selected live configuration and checkpoint hashes remained
unchanged. No execution runner or TUI process remained after the checks.
Evidence: `data/logs/research/bidirectional_cohort/v89_tui_launch_revalidation_20260912_v1/verified.json`.
These checks validate the installed monitor; the stopped strategy's evidence
remains dated. The original Terminal.app was not inspected.

Use **2 → select setup → Enter → PgUp/PgDn** for the strategy's plan, indicators and corresponding regimes; **3 → Enter** for the focused signal chart; **8 → PgUp/PgDn** for the complete regime workstation; **9** for effective settings and the separate draft. Closing a monitor does not create execution authority.

Evidence resides in `data/logs/research/bidirectional_cohort/v89_open_hold_visibility_20260912_v1`. The installation directory retains `source.patch`, `before_source.tar.gz`, `tui-regime-detector.previous`, and exact prepared/installed manifests. Reverse-patch applicability was checked after installation. Restore only against matching installed hashes; later edits require a new comparison rather than blindly applying an old rollback.

Confidence is high in the demonstrated display behavior and source parity. A wrong provider/clock, future-context join, fabricated current state, missing required panel, altered installed hash or failed native/source reproduction would update that assessment. Doing nothing preserves the known display errors; recomputing unconditional live state from stale evidence would conceal uncertainty. The chosen repair adds explicit clocks and context while retaining the backend's existing authority. The next research priority remains full shared-portfolio and live acquisition/poll-clock parity, not selection of a profitable subgroup from the already studied SNDK sample.
