# V89 first-entry friction and open-position display acceptance

The first SNDK live entry matches the captured IOC, lot rounding, fee estimate
and native protective-stop identity. A separate display defect was reproduced
and repaired: compact tables clipped native order IDs and notional values, and
the 100x28 dashboard could omit the entire open SNDK row while claiming all
assets were visible. Confidence is high for these bounded observations and
rendered comparisons; one open lifecycle does not establish profitability or
all-route readiness.

## Entry, cost and protection evidence

Unsigned, individually timestamped Hyperliquid Info reads at 01:08:35–01:08:38
UTC on September 8 confirmed entry order 538806415304 filled as IOC, stop
538806460232 open, and a 0.276-unit isolated 10x SNDK long at 1803.4. Only public
order, position and metadata endpoints were requested. No signer or execution
client was created. The Info request shapes were checked against the
[official endpoint documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint).
The account address is not printed; the capture retains its SHA-256 identity.

| Measurement | Result | Interpretation |
| --- | ---: | --- |
| Filled notional | $497.7384 | The requested $500 was rounded to the venue's 0.001 size step |
| Entry fee | $0.043004 / 0.86398799 bps | Within $0.00000060 of the previously captured 0.864 bps fee calculation |
| Historical model fee | 0.9 bps | About $0.00179 above this entry's actual fee |
| Last recorded bid / ask before intent | 1804.2 / 1804.3 | Sample received 6.677164 seconds before the local order intent |
| Reference to sampled midpoint | -18.53286125 bps | Favorable movement from the 1807.6 completed-hour reference |
| Midpoint to ask | +0.27660987 bps | Quoted half-spread on the same reference denominator |
| Sampled ask to fill residual | -4.97897765 bps | Contains later market movement as well as execution effects |
| Total reference to fill | -23.23522903 bps | Exactly reconciles to the three components within 1e-10 bps |
| Local intent to acknowledgement | 1.389193 seconds | Consistent with the checkpoint's rounded 1,390 ms |
| Venue fill to venue stop-open time | 2.761 seconds | Same venue clock; an observed protection gap, not a configured deadline violation |
| Native stop trigger | 1788.6 | Rounded from the requested 1788.620010593465 |

Fifteen native order/position checks match. All 12 frozen reconciliations after
the stop acknowledgement retained that exact reduce-only sell stop, full size
and rounded trigger. The later direct native query independently confirms the
same stop. These samples do not prove uninterrupted order presence between
observations or the eventual stop fill price. The fee and quote calculations
are entry-only; exit costs, funding and complete lifecycle PnL remain separate
qualifications. The 23.24 bps favorable reference-to-fill difference must not be
presented as identified instantaneous market impact or justification for a
negative historical cost assumption.

The arithmetic helper has positive long/short controls and invalid-price,
locked/crossed-book and direction controls: 25 tests pass, with 100% statement
coverage. Research source commit `50f8e80` is retained in the isolated
`hypervector-v89-live-parity-20260907` worktree. The immutable report is
`data/logs/research/bidirectional_cohort/v89_first_entry_friction_20260907_v1.json`.

## Display defect and final behavior

The actual open-position render at 120x36 showed `STOP #5388064602` instead of
`STOP #538806460232`, and `$49.95/$497.` instead of the complete margin/notional
pair. Both failures were reproduced in focused tests before changing the
column widths. A 100x28 render also showed only the four core assets; the
non-crypto panel had a header but no body rows, despite a footer claiming all
seven assets were visible.

The standard compact table now reserves enough width for the native stop ID,
fee/funding pair and margin/notional value. At small dimensions, the dashboard
uses a paged asset table plus exact selected-asset details. Rounded table prices
are labeled with `~`; entry, mark, liquidation, state, size, leverage, target ID,
plan and fault remain available in the selected detail panel. Left/right selects
an asset or page. The footer describes that navigation instead of claiming
unconditional visibility. The small Trades table puts open exposure first and
reports its displayed asset count; Dashboard remains the all-asset/detail view.
The standard-size panels and the existing nine-view navigation are retained.

The trade workspace's short layout no longer forces seven performance rows
when fewer rows are available after position and journal allocation. At the
smallest dimensions the performance summary is shorter; the panel and both
journals remain present, and the exact-contract review remains on Screen 6.
This is an explicit space trade-off that preserves open risk. Large fault text
and extreme future values still require visual regression coverage beyond the
captured cases; no claim is made that every arbitrary string fits every cell.

## Validation, installation and rollback

- Five new layout tests reproduce the clipped fields and missing small-screen
  asset rows, then verify the fix. All 107 cockpit view tests pass.
- Full Rust suite: 512 passed, 23 intentionally ignored, zero failures.
- `cargo fmt --all -- --check` and Clippy with warnings denied pass.
- The first isolated full-suite attempt lacked the existing V86 local fixture.
  Its two files were copied from the original workspace and SHA-256 verified;
  the unchanged historical test then passed. No test was weakened or skipped.
- Twenty-seven final renders use the same frozen cohort prefix and checkpoint:
  all nine views at 100x28, 120x36 and 190x52. The final frozen fixture is
  `v89_open_position_tui_fixture_20260907_v2`; captures are
  `v89_open_position_tui_candidate_20260907_v2`.
- The earlier first-entry render mixed a newer active cohort ledger with an
  older checkpoint. It helped locate clipping but is not the final evidence of
  snapshot parity. Final acceptance uses both inputs frozen together.

Three owned, detached instances of the installed executable also passed:
100x28 Dashboard with SNDK selected, 120x36 Dashboard, and 120x36 Trades.
The terminal streams were reconstructed with pyte 0.8.2 before checking the
visible cells. An earlier plain ANSI-stripping check lost cursor-position
whitespace and incremental edits; `installed_monitor_acceptance_v2.json`
corrects that verifier using the same raw captures. A preliminary invocation
used an invalid zero-based tab argument and exited before opening a monitor;
the supported CLI tab numbers are one-based. All three valid monitor processes
exited normally on their own quit command, and original process lifetimes
matched before and after. No live order backend was stopped by this check.

TUI source commit `a2c6d18` is installed on main as `360db04`. The release binary
SHA-256 is `1036c56c9e5680e4ce4c27953e5b536bf72dcea4e9092459132fd111306bc1d3`.
Installation used an atomic file replacement, preserving the old running
monitor's inode. The original backend, supervisor and reporting processes were
not restarted. Backup binary, original process lifetimes, configuration hash,
installation record and installed-executable monitor captures are retained in
`v89_open_position_tui_install_20260907_v1`.

Rollback is limited to the monitor: restore the preserved `prior_binary` using
another atomic replacement and revert the isolated display commit if needed.
Do not quit the original supervised TUI merely to update its display. A new
detached monitor uses the installed update; its own quit leaves the backend
running. Existing windows do not hot-reload the replaced executable.

The findings would be revised by a native order/fee identity mismatch, a missing
or undersized protective stop, a full causal source replay contradicting the
entry, or a supported-size render hiding the verified open-risk values. The
highest-value next investigation is the first completed lifecycle's exit,
funding and net-cost reconciliation, followed by the already proposed single
faster-entry-clock comparison. The continuous research objective remains
active; this turn made substantive progress and encountered no persistent
external blocker. No live strategy, sizing, leverage or order behavior changed.
