# V89 V3: observed live execution and display acceptance

Evidence captured September 11, 2026 UTC; final runtime identity check at
14:17:08 UTC. This is a dated operational review, not a current account feed.

The user-started V3 run is live. Run `bidirectional-live-1789122347122` first
records backend activity at 10:35:44 UTC / 06:35:44 Eastern. Its first two
completed trades lost **$27.994028 after fees**. A third entry, a SNDK short,
was open and protected in the subsequent native account observation. The
reporting and captured-data display checks below pass within their stated
scope. The original Terminal window remains unverified, and the auxiliary
funding column still lacks producer data. Full visual acceptance is therefore
not claimed.

Technical confidence is high for the identities, retained source comparisons
and observed order/account reconciliation. Confidence in prospective strategy
quality remains low: two closes and three entries are insufficient. A source
mismatch, missing or incorrectly sized stop, stale/missing telemetry, or native
fill discrepancy would update the affected technical finding immediately.

## Runtime and scope

- Installed source remains identical to candidate
  `564d72e81539afdd3e2979beea4086a655ec4350` across `src`, `scripts`, `configs`,
  `tests`, `crates`, `Cargo.toml` and `Cargo.lock`. Installation was committed at
  `4b241ef0b5fe5c5c785ad11804be5417a7bf5dab` with explicit approval.
- Installed TUI SHA256 is
  `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.
  Profile SHA256 remains
  `696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`;
  profile fingerprint remains
  `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
- BTC, ETH, SOL, HYPE, SPCX, SNDK and Brent remain the seven configured assets.
  No strategy, direction, leverage, sizing, asset scope or risk setting changed.
  No order was submitted or canceled by this acceptance work.
- Original owners 20431 / 20432 / 20457 / 21085 / 21086 remained present with
  the same process-birth identities. The backend, primary checkpoint reporter
  and original TUI were not restarted or signaled.
- The run-specific startup backup reverified all **1,928 files**, including
  **1,874 implementation sources**. Its manifest SHA256 is
  `35e43e8a1bf1b8b934251cada2549ed19d9643d7f55b6ed8cf80e60818900f3e`;
  implementation identity is
  `e87c855011c5abdcb7bf6f85d924eee618b10a617b827c520a1987d0321e9cd9`.

Authoritative artifacts: [runtime verification](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/runtime_acceptance.json)
and [prior installation](2026-09-11-v89-v3-installed.md). The installation
review's stopped-state observations remain historically correct; this review
supersedes them for subsequent runtime navigation.

## Actual trade reconciliation

| Observed lifecycle | Result / state | Native protection and timing |
|---|---|---|
| BTC long, 13:00 entry | Gross −$15.571440; fees $2.151045; net −$17.722485 | Full-size reduce-only stop filled at 13:31:56.949; unused target was reduce-only canceled |
| SNDK long, 13:00 entry | Gross −$10.185960; fees $0.085583; net −$10.271543 | Full-size reduce-only stop filled at 13:32:47.604 |
| SNDK short, 14:00 entry | Open in 14:09:55 native account read; 0.306 at 1629.2; 10× isolated | Buy stop-market order 542326955281, reduce-only, full 0.306 size, trigger 1669.9 |

The first five venue fills match ledger symbol, trade/order identity, clock,
price, size, side, fee currency, fees and realized PnL exactly using decimal
comparison. The follow-up matches all six returned fills, including the short
entry. The closed-trade total is gross −$25.757400 minus $2.236628 fees;
account funding returned no payments in the queried window. The short's
$0.043073 entry fee is additional and is excluded from the two closed-trade
results. Its unrealized movement is also excluded.

The three SDK dispatch ages were 18,633 / 27,706 / 21,495 ms against their
30,000 ms limits. Native entry fills occurred 19,719 / 28,601 / 22,977 ms after
the respective decision clocks. These observed entries satisfy the configured
deadlines. Later routing-summary emission timestamps are not SDK dispatch
timestamps and do not establish a late submission.

The short's stop was below its observed liquidation price of 1706.6468938687.
Core account positions/orders were empty, and XYZ had exactly that position
and stop in the sequential follow-up reads. These observations establish
point-in-time coverage; they do not prove continuous historical protection
between requests or future execution quality. Closed trades provide no
guarantee that infrequent entries will produce large positive swings.

Evidence: [first lifecycles](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/first_live_lifecycle_assessment.json),
[follow-up account assessment](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/followup_account_assessment.json),
and the retained unsigned response bodies linked by the evidence manifest.

## Reporting and native display validation

| Component | Measured evidence | Limit |
|---|---|---|
| Reporting continuity | 181 process samples over 900.01 seconds; all five original births retained | Fifteen-minute interval only |
| Checkpoint source integrity | 31 captures, 28 distinct publications, 248 exact source-hash comparisons across eight ledgers | Three captures repeat identical checkpoint bytes; they are not new publications |
| Freshness and health | Maximum captured checkpoint age 33.856 s; heartbeat age at publication ≤17.206 s; complete coverage and no reported runtime faults | Checkpoint publication and underlying market clocks are separate |
| Research sync | Eight distinct successful-sync timestamps; no reported sync error | Sampled output; not exhaustive profiling of every worker |
| Reporter I/O | 83,001,344 physical write bytes (79.16 MiB); 36,864 physical read bytes | Not net filesystem growth, all descendant I/O, or a controlled comparison with the old version |
| Reporter memory | RSS 613.94→643.30 MiB; observed range 607.56–646.13 MiB | Decoded current-run history can grow; indefinite memory stability is unproven |
| Snapshot capacity | Largest raw snapshot 29,867,256 bytes, below the 128 MiB mapped capacity | Descriptor sampling found no named snapshot/spill file; transient spill absence is unproven |
| Nine native views | 27 view captures at 120×36, 190×52 and 100×28; normal renderer exit; no unsupported terminal sequences | Captured inputs in an isolated renderer, not the original Terminal window |
| Seven-asset depth | All visible price/size/cumulative/total fields matched source precision; all 20 Brent levels reached at all three sizes | Compact layouts display fewer levels/decimal places at once |
| Book age | Compared independently against venue exchange timestamps | Held replay input ages naturally while navigating |
| Auxiliary roster | Existing Info-only observer restored; fresh reports and native `HIP-3 LIVE` / `CURRENT` panels for the three configured HIP-3 assets | Hourly funding remains `N/A`: the producer omits the optional field |

The rendering harness used the exact installed executable with network and
file writes denied, captured checkpoint/ledger/roster inputs and detached
lifecycle. Original input truth fields were retained, including the live-run
arming state. The isolated renderer had no execution authority or access to a
working operator inbox. Images explicitly identify their captured, isolated
scope; reconstructed font glyphs are not proof of the original terminal's
pixels. Selected views, setup inspectors, trade results, configuration identity
and restored depth were visually inspected from retained native cells.

An initial harness run omitted the auxiliary roster argument and is retained
as incomplete input coverage. A separate corrected run supplied the actual
production input. The 100×28 viewport needed twenty single-level pages to
reach every Brent level; those additional captures are retained. Two initial
analysis assumptions were also corrected: repeated checkpoint captures need
not be distinct publications, and displayed book age uses venue exchange time,
not local receive time. Neither correction changed production code or data.

Twelve focused observer/factory tests passed. All eleven capture/analysis
operators passed Ruff and the project function/file length checks; no new unit
coverage claim is made for these observation scripts. The 354 installed Python
regressions and 320 native Rust tests belong to the authenticated prior release
qualification and were not rerun as part of this operational observation.

Evidence: [reporting assessment](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/reporting_assessment.json),
[display assessment](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/display_assessment.json),
[restored SNDK depth](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/native_display_restored_roster/captures/sndk_depth.png),
and [observer restoration](../../data/logs/research/bidirectional_cohort/v89_v3_live_acceptance_20260911_v1/roster_restoration_assessment.json).

## Decision and next investigation

Retain the approved trading configuration while analyzing naturally occurring
execution. Two losses alone do not justify retuning. The single next technical
investigation is the confirmed missing hourly-funding field in the Info-only
roster producer: build a source-backed correction in an isolated checkout,
test absent/invalid/stale responses and exact display units, then verify native
rendering. Also trace how that auxiliary observer should be supervised at the
next approved deployment; this restoration did not change startup policy.

| Alternative | Benefit | Cost / decision |
|---|---|---|
| Retain current trading settings and repair report-only data | Preserves execution continuity while addressing a verified missing field | Selected; funding and original-window acceptance remain explicit gaps |
| Leave auxiliary feed stopped | No observer resource use | Rejected for display operation: preserves stale account/book metadata |
| Retune from the first two losses | Immediate strategy change | Unsupported sample; not selected or implemented |

No additional execution or deployment approval is requested by this report.
The independently restored observer is PID 37491 and was started with signing
credentials removed; it reads Info endpoints and writes only its report/log.
The prior report is preserved. If this observer itself fails, diagnose that
specific producer while preserving the trading owner and the explicit stale/
unavailable display state. It is not a trading-process rollback instruction.

Both original prospective collectors remained live. Their compared hypothetical
outcomes remain sealed until September 22 04:00 UTC and September 23 00:00 UTC,
respectively. Actual-account operational monitoring and market exposure in
this review are disclosed; no claim of complete analyst blinding applies.
The completed 48-case historical pipeline was not restarted or reinterpreted
as fresh holdout evidence. The broader research/improvement goal remains active.

Computer Use rejected access to `com.apple.Terminal` with: “Computer Use is not
allowed to use the app 'com.apple.Terminal' for safety reasons.” The original
window was not accessed through another GUI method. The separate native CLI
test harness does not establish original-window acceptance.
