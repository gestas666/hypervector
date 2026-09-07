# V89 candidate TUI installed in the main checkout

The earlier launch command selected V88 in the original checkout. The seven-asset
implementation was still in a separate worktree, so that command could not display
the new candidate routes. This handoff corrects the software installation and
provides an unambiguous candidate launcher.

The original checkout was fast-forwarded from `b610f8c` through candidate commit
`b810154` and launcher commit `15b71a1`. The prior source is preserved at
`backup/pre-v89-tui-update-20260907`. V88's recorded assets were stopped with
`operator_stop` before this installation; no live backend was restarted.

Run from the main checkout:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python scripts/candidate_tui.py
```

This opens BTC, ETH, SOL, HYPE, `xyz:SPCX`, `xyz:SNDK` and `xyz:BRENTOIL` with
fresh public observations. It displays `EXECUTION DISARMED` and `SETUPS 7/7`.
The command has no live-arm option. Each launch uses a separate directory under
`data/observe/candidate_tui/` for decisions, checkpoint, controls and final audit.
Quitting stops only its owned observer. The existing supervisor's diagnostic
backend/checkpoint logs remain shared append-only log destinations.

High confidence in this installed command within the following verification:

- Release build completed successfully in the original checkout.
- 83 focused provider, configuration, launcher and checkpoint tests passed.
- The exact command ran in a real 120×36 terminal. All nine tabs and all seven
  inspectors were visited; the new aliases and assets were present and the
  display remained disarmed.
- Observer run `bidirectional-observe-1788788287859` passed its technical audit.
  Normal quit returned exit code zero and produced the final checkpoint/audit.
- The original V88 checkpoint's SHA-256 was identical before and after the
  complete preview lifecycle.

Artifacts are under `data/logs/research/bidirectional_cohort/`:
`v89_tui_deployed_release_build_20260907_v1.txt`,
`v89_tui_deployed_focused_tests_20260907_v1.txt`, and
`v89_candidate_launcher_terminal_20260907_v1.json`, with its frozen generator.

This is an installed candidate display and unsigned observer. It does not activate
the seven-asset strategy for real-money trading. The low-confidence economic
findings and remaining execution limitations in the
[research review](2026-09-07-frequency-and-noncrypto-expansion.md) still apply.
Text-cell acceptance excludes color judgment; a mismatched profile, fewer than
seven populated routes, or writes to V88's checkpoint would invalidate the
installation acceptance.
