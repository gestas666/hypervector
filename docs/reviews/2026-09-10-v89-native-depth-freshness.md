# Native TUI depth correction

The isolated TUI candidate now identifies a backend book snapshot, shows its
current age and dated venue timestamp, distinguishes checkpoint health from
book age and receive delay, and exposes every reported level through bounded
scrolling and paging. It is not installed and does not authorize execution.

High confidence applies to the measured synthetic and historical display
behavior. Source is `564d72e81539afdd3e2979beea4086a655ec4350`; executable SHA256
is `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
This correction changes 13 Rust source/test paths relative to the prior candidate.
Combining them with the V2 proposal selects 72 paths. That combined installation
and rollback still require their own rehearsal; the old V2 packet is preserved.

| Proposal field | Recommendation and evidence |
| --- | --- |
| Recommendation | Include this qualified TUI correction in the next exact combined release review. |
| Why now / observed problem | A native replay labeled the retained September 4 book LIVE, omitted current book age and had no navigation to cropped levels. Twelve baseline checks failed across three terminal sizes. |
| Evidence reviewed | Actual native PTYs, saved terminal bytes and cells, unchanged historical inputs, 320 passing Rust tests, helper coverage and source/binary hashes. |
| Applicable regime | Display behavior across backend-authored books; no strategy or market-regime assumption is required. |
| Proposed live change | Replace the TUI only as part of the next selected source/binary package. Preserve the V89 strategy, symbols, allocation, routes and execution policy. |
| Expected upside | Make retained data identifiable and all reported depth levels reachable. No improvement in return, win rate or trading frequency is established. |
| Main risks | Narrow numeric columns retain existing formatting limits. Historical observer connection text identifies loaded ledger state and does not prove a running backend. Clock skew and unavailable evidence remain explicit. |
| Alternatives | Leave the installed display unchanged and retain its defects; enlarge the terminal, which does not correct freshness; or select the tested correction with a new composition/rollback review. |
| Validation completed | Twelve native depth checks now pass; fifteen native paging checks pass; all nine views are reached at 100x28, 120x36 and 190x52; seven historical fixture books are selected individually. All 24 non-Depth view texts equal the original captures. |
| Validation still required | Complete the original financial review, rehearse the new exact combined package, obtain selected release approval and verify fresh account/order/owner and same-run TUI evidence. |
| Success metrics | Correct dated age/context, exact bounded level ranges, source-consistent values and cumulative totals, unchanged other panes, correct executable identity and no execution authority in observer replay. |
| Failure / rollback triggers | Incorrect freshness, missing source levels, changed numeric meaning, identity drift or other-pane regression rejects this display qualification. Preserve the prior binary and use the separately rehearsed compatible rollback at a qualified maintenance boundary. |
| Confidence | High for the scoped offline evidence; current live reliability and financial performance remain unestablished. |
| Explicit approval requested | Deferred to the complete combined review under the objective's Human control instruction. This document grants no deployment, restart, signing or order authority. |

## What was verified

The unchanged September 4 V86 observer fixture contains six ledger rows, all
`execution_mode=observe`, `live_armed=false`, `execution_authority=none`.
Its seven assets are BTC, ETH, SOL, HYPE, ZEC, SPCX and SNDK. It predates the
prospective outcome seals and does not substitute for current V89 or Brent
acceptance. Ledger/checkpoint bytes and original mtimes remain unchanged.

The native child runs only the Rust display, with the normal `--live`, MULTI
and 1m display flags, explicit isolated inputs and a minimal environment. It
has no backend process or checkpoint writer. The configured OS sandbox denies
network and file writes except terminal devices; no adversarial negative-control
test of that sandbox was performed. The retained native processes exited zero,
the terminal decoder reported no unsupported sequences and no inbox was created.

At the three acceptance sizes, the ladder shows respectively 1, 9 or 16 levels
per side. Arrow keys reach all twenty levels; Page Up/Down use the actual visible
capacity. Headings state the visible range. Cumulative size remains measured
from the best level, while TOTAL ALL explicitly includes the complete backend
book. Tests cover unequal sides, shrinking books, resizing and asset changes.
Independent Decimal reconciliation checks 4,424 displayed price, size,
cumulative-size and order-count fields against the retained backend books
across 70 native frames. Prices and order counts match exactly; observed size
and cumulative-size residuals are zero in this fixture. This does not establish
lossless formatting for arbitrary future values in narrow columns.

The native replay retains all nine panes, nine setup selections, setup
inspectors, seven chart and depth selections, regime pages, below-minimum size
notice and restored layout. The earlier baseline navigation operator failed to
reset the shared selector before its depth sweep. That capture sequence is
preserved; corrected sweeps verify actual selected symbols rather than key count.

The 320 distinct passing Rust tests comprise 155 library tests, six new depth
render tests, four navigation tests, 116 cohort view tests, four CLI tests,
fifteen configuration tests and twenty entry-deadline tests. Three existing
active-v55 tests compile and remain explicitly ignored; no current ledger was
loaded to satisfy their historical profile assumptions. Initial render-test
fixture identity and zero-padding assertions were corrected without relaxing
numeric equality. The existing pane-preservation comparison now normalizes only
elapsed book age and adjacent title padding; all other displayed content remains
compared. Its full 116-test target passes after the final test refactor.

The clock and viewport helpers have 77/77 production coverage regions exercised.
This is not full UI or branch coverage. All changed files remain under 500 lines
and changed functions under 50 lines. Two pre-existing longer runtime functions
are byte-identical and were left outside this correction.

The Rust workspace archive authenticates 354 Git blobs and modes. Its SHA256 is
`07da3ebe9e7fdf9ef94d0a0a5bdadf68ac30539ca2c3174de41c1a03384ccde8`.
Only 2,539 verified third-party build-cache members were restored to a separate
directory from the preserved archive. Installed executable SHA256 remains
`95f87cdcd49e5aa0068b7ebf8d4bef2b18d5f3efa7692291fc9aeabc83623d8f`;
main runtime/configuration bytes still match baseline b3df618.

Changed source identities, contradictory native captures, an unexplained value
change or missing source level would invalidate the affected acceptance claim.
The fixed historical replay cannot establish present venue positions, order
protection, fills, performance or future profitability. Both prospective outcome
seals remain intact. No installed source, live configuration or live process changed.

Evidence: `data/logs/research/bidirectional_cohort/v89_native_tui_acceptance_20260910_v1/`.
The authoritative records include qualification.json, source_archive_acceptance.json,
depth_candidate_manifest.json, native results, raw bytes, cell captures, all test
attempts and unchanged_views_comparison.json. PNGs reconstruct recorded terminal
cells and are not OS screenshots; font reconstruction can introduce glyph artifacts.
