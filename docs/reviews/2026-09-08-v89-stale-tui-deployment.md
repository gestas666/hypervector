# Approved V89 TUI status update: deployment acceptance

The user approved the exact TUI-only proposal. The candidate's two source commits
were applied to main as `c83f984` and `02dd3b9`. Main's complete Rust workspace,
Cargo manifest and lockfile match source `d10b05b` byte for byte. The approved
release binary was installed atomically at `target/release/tui-regime-detector`.
The prior executable remains preserved in the original evidence bundle.

The new detached monitor is PID 88441, Terminal window 5958, at 160x50. The
previous detached monitor, PID 25240, exited through its normal q action and
its old window closed. Visible portfolio acceptance confirms seven assets,
nine navigation views, five closed trades and −$21.12, with CHECKPOINT STALE,
AT SNAPSHOT RUNNING CONSISTENT, and IMPORT STALE // WAS OK. The frozen 79-second
age is absent. The previously validated candidate has 521 passing Rust tests
and 27 headless renders spanning all nine views; the installed Rust source and
binary match that candidate, so those tests were not repeated after copying.

High confidence in the observed installation and portfolio display. The
configuration and checkpoint hashes are unchanged, and no backend or reporter
process is running. This display update did not resume trading. The portfolio
and market values remain a historical snapshot, and shutdown attribution remains
unresolved. Contrary process identity, source/binary hashes, or visible values
would invalidate this acceptance.

The approval covers this TUI update. The entry-deadline and mapped-reader
proposals remain separate and pending. The next economic investigation is the
latest SNDK short and SPCX long stop-execution reconciliation.

Evidence: `data/logs/research/bidirectional_cohort/v89_stale_tui_deployment_20260908_v1/`.
The manifest pins the approved preflight, exact launch script, visible Terminal
capture, replacement verification and final source/configuration acceptance.
