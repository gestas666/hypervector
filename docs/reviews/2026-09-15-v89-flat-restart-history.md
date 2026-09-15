# V89 compatible-history reporting correction — September 15, 2026

The checkpoint omitted completed BTC, SPCX and Brent trades when those assets restarted flat. The correction is installed as `1b82bab190036e6efc7758ed6418e57e9fffc94f` in the live checkout; candidate commit `6e0431c1956eb4a32123b726f1edee14970cfff3`. This changes reporting only. The already running reporter has not reloaded it, so the open TUI still has the historical accounting defect. Source installation is verified; active TUI correction remains pending.

## Observed defect and correction

The current-run checkpoint recovered inherited execution only when current asset events showed an earlier open position, fill, funding or close. Flat restarts without those events retained only the new run, even though the backend's `fill_count` included compatible-profile history. SNDK's inherited close recovered its history; the other three previously traded assets silently lost theirs from exact trade summaries. The existing audit did flag `cohort_fill_projection_mismatch`.

The checkpoint now reads each asset's recorded fill count from the causal cohort snapshot. When current-run fills cannot account for that projection, it recovers the compatible execution history with the existing compact reader. The exact profile/run fingerprint and observation cutoff still apply. Incompatible or insufficient history raises an explicit reporting error. Missing counts in supported legacy snapshots retain their existing behavior; malformed explicit counts and duplicate symbols are rejected.

| Same frozen live evidence | Previous report | Corrected report |
| --- | ---: | ---: |
| Compatible-profile fills | 9 | 18 |
| Backend-projected fills | 18 | 18 |
| Current-run fills | 1 | 1 |
| Closed trades | 4 | 8 |
| Wins / losses | 1 / 3 | 1 / 7 |
| Net P&L after fees and funding | +$1.735446 | −$25.609303 |
| Fees | $0.342066 | $2.751151 |
| Funding | −$0.153028 | +$0.943678 |
| Accounting coverage | Incomplete | Complete |

Independent decimal reconciliation against backend per-asset cash projections gives BTC −$17.722485, SPCX −$7.335140, SNDK +$1.735446 and Brent −$2.287124; ETH, SOL and HYPE have no compatible-profile closed trades. These are historical results under this profile, not an estimate of future returns.

## Validation and installation

- Three original regression cases failed against the prior behavior, then passed with the correction. They cover flat recovery with and without retained recent fills, exact fees/funding, and incompatible prior history.
- The final checkpoint/audit suite passed 146 tests, including explicit count corruption, duplicates and legacy-schema handling. A 22-test subset passed again using modules imported from the installed checkout.
- Baseline and candidate ran on the same authenticated frozen fixture: 164,019 retained native rows and two prior cohort configuration identities. Decimal accounting reconciled to less than $0.000000001 per asset. Fixture hashes remained unchanged.
- Run identity, health, routing, readiness, canonical regime telemetry, current portfolio, risk utilization, maximum-hold decisions and signal outcomes were identical between those reports.
- A separate corrected publication against the actual actively appended ledgers also recovered 18/18 fills and complete accounting coverage. It took 3.047 seconds and peaked at 435,994,624 resident bytes on this machine. Sequential asset captures remain bounded by the cohort observation cutoff.
- Financial execution, credential-file reads and network were denied in these projection experiments. Reports were written to isolated evidence paths, not the active checkpoint.
- Before installation, all prior changed source bytes were backed up. The exact patch and hashes are retained. Installation changed three reporting modules and added one test file; 5,484 protected file paths, including the TUI binary, remained unchanged. Backend PID 93674 retained the same process identity. No runtime process was signalled, started or stopped by this change.

## Current operation and activation limit

The user-started backend is `bidirectional-live-1789482753345`, PID 93674, profile `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`. Its September 15 14:32:33 UTC pre-start backup has manifest SHA-256 `02ee60db545669c228421756f38e1641b4a28a7279c63a3f6d22a2a01f52a1a2`. The 1,922 implementation entries agree with installed source except the three reporting modules deliberately changed afterward. The bounded-memory startup module is present in that authenticated backup.

The inherited SNDK short closed through the existing maximum-hold policy at 14:43:47.921 UTC: 0.306 bought at 1551.7, gross +$23.715, lifecycle fees $0.084097 and funding −$0.127539, net +$23.503364. This is the only current-run fill in the evaluated capture.

At 15:54:13 UTC the backend reported all seven assets flat, zero faults, all seven expected provider/asset pairs observed, 236 provider evaluations and zero eligible entry intents. The router withheld zero intents. Current reasons were absent hourly setups for the three non-crypto assets, absent BTC reclaim/EMA conditions, absent HYPE breakout/compression/pullback conditions, and absent configured regime/cross conditions for ETH/SOL. This supports a lack of configured entry conditions in this window, not a diagnosis of execution suppression or evidence that sparse trading will be profitable.

The combined launcher owns backend, reporter and TUI. The existing reporter has no supported reload mechanism. Quitting this TUI stops its financial backend. Replacing its reporter externally would leave the launcher's original process handle stale and could conflict with final checkpoint publication. That unsupported replacement was not performed. The installed correction will load at the next normal reporter start. The active file must then show complete coverage and reconcile exact fills to projected fills before calling the TUI corrected.

## Decision and next investigation

Recommendation: retain the installed reporting correction under the existing corrective-update approval. Why now: omitted losses changed the apparent sign of compatible-profile P&L. Applicable regime: every regime; this is accounting scope. Proposed live strategy change: none. Expected upside: accurate trade history, cost totals, scorecards and operator decisions; no claimed direct profitability improvement. Explicit approval requested: none for the completed reporting-source repair.

| Alternative | Consequence | Decision |
| --- | --- | --- |
| Keep prior reporting | Omits completed flat-asset history and misstates historical P&L | Rejected |
| Narrow the claimed history scope | Conceals missing requested profile history | Rejected |
| Recover exact projected history | Restores accounting with measured report cost | Accepted and installed |
| Restart the coupled financial backend solely for reporting | Interrupts the current user-run trading session | Not performed |

Confidence is high for the reproduced defect, accounting repair and installation. Activation in the existing TUI is unverified and remains incomplete. Larger histories may change runtime cost; new incompatible or missing source rows must remain explicit errors. An accounting mismatch, altered current-run routing/health, a causal cutoff violation, or source drift would reopen the correction. At the next normal reporter start, verify a fresh same-run checkpoint, 18/18 fills if no further trades have occurred, complete coverage and unchanged financial ownership. If new fills occur, derive expected counts from the new backend snapshot rather than retaining 18 as a gate.

Rollback: validate installed file hashes against the installation receipt, preserve the current version, and restore only the three previous reporting-module bytes from the recorded backup. Do not revert unrelated work, touch financial execution files or reset the repository. A restarted reporting process is required to load either version.

The highest-value next investigation is reporter activation followed by the first newly eligible live entry: reconcile provider decision, corresponding completed-bar regime, route, acknowledgement, fill, protective orders and cash effects. Continue collecting native evidence; this reporting-only correction does not justify repeating the completed historical portfolio experiments or retuning strategy thresholds.

Evidence directory: `/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_live_operational_20260915_v1`. Inspect `projection_invariants.json`, `baseline_projection_result.json`, `candidate_projection_result.json`, `actual_ledger_projection_result.json`, `checkpoint_history_final.xml`, `checkpoint_history_installed.xml`, `active_start_source_validation.json`, `operational_followup_1555.json` and `checkpoint_history_installation/installed.json`. `actual_ledger_corrected_checkpoint.json` is a timestamped corrected report, not the currently attached live checkpoint.
