# V89 compact controls, hourly candles, and complete chart evidence

Candidate `05809a9771d207a54f82b6c671f792734e8ab741` combines the previously reviewed funding/checkpoint recovery with three verified display repairs: usable compact OPS controls, BTC's configured hourly candles, and scrollable provider evidence. The installation package contains **44 source, test and documentation files plus the exact TUI executable**. It is not installed; no trading backend was restarted.

**Recommendation:** approve this concrete technical installation package while keeping the backend stopped. Continue fresh checkpoint, configuration-workflow and installed-terminal acceptance. Full live and strategy readiness remain unproven.

**Why now:** native all-asset inspection exposed defects that the earlier initial-screen checks missed. At 100x28 the OPS layout hid action details; BTC's configured `1h` chart was rejected; long ETH/SOL indicator text pushed source and authority information below the chart pane. These are measured software defects, independent of whether a strategy has an edge.

**Evidence reviewed:** the [prior recovery review](2026-09-11-v89-checkpoint-recovery.md); the original recorded V3 checkpoint/ledger suffix; three successive native candidate captures; red/green regressions; final full Rust checks; exact source/executable rollback; and five new public-data observer polls. Evidence is retained under [the final study](../../data/logs/research/bidirectional_cohort/v89_chart_detail_scroll_20260911_v1/) and [fresh provider study](../../data/logs/research/bidirectional_cohort/v89_fresh_provider_readiness_20260911_v1/).

**Observed problem or opportunity:**

| Defect | Final behavior | Validation |
|---|---|---|
| OPS requested 29 body rows where the minimum terminal had 21 | Compact layout retains entry/close/drain effects, review keys and backend command context | Six regressions; all seven assets at three sizes |
| Chart accepted only 1m/5m/15m/30m intervals | Configured `1h` uses the existing exact completed-bucket aggregator | Exact OHLCV, partial edges, gaps and unsupported-interval tests; native BTC now shows five complete hours |
| Chart provider evidence wrapped without scrolling | Page Up/Down and Home/End expose the complete evidence independently of candles; provider changes reset scroll | Three regressions, real ETH/SOL/HYPE scroll endpoints, complete source/indicator/authority parity for all 21 asset-size cases |

The compact candidate's first capture failed because its harness tried to read another frame after `q`; the corrected harness recorded actual exit codes. The first scroll test attempted to inspect a private field; the corrected test used the public scrolling behavior. A later wide fixture fit without scrolling and was expanded for the overflow test, with a separate fit/no-op regression. These test/capture failures are retained and are not labeled production faults.

**Applicable market regime:** accounting and display behavior across regimes. No strategy, route, asset, leverage, sizing, stop threshold or polling parameter is changed. The fresh observer used an isolated output path and the same provider, asset, position-policy, routing-policy and runtime settings as the recorded configuration. Its observe-mode fingerprint is separate from the live fingerprint.

**Alternatives considered:**

| Alternative | Benefit | Cost |
|---|---|---|
| Keep installed version | No deployment | Retains the reproduced recovery and display defects |
| Install earlier a035 candidate | Repairs recovery and stopped-state authority | Retains compact controls, hourly-chart and chart-overflow defects |
| Install this combined candidate | Delivers the verified technical corrections together | Requires exact source/binary installation and remaining operational acceptance |
| Wait for all broader live-readiness work | One later deployment | Defers already validated repairs |

**Proposed live change:** apply only [the exact listed 44 files](../../data/logs/research/bidirectional_cohort/v89_chart_detail_scroll_20260911_v1/installation_candidate.json), then replace the installed TUI with the retained candidate binary. Production base at rehearsal: `bcda570c4a5d6960cf2a8f7ae81b95a0880fb4fe`.

- Patch SHA-256: `060d4145728173435cd7adcc964c79875a54b8ff8a9503b34987c35f23bb04f5`.
- Candidate TUI SHA-256: `d67d111554e255cf8ad99841b60ee6abc302e0df8f4df9820f5acaf517c5ad16`.
- Previous installed TUI SHA-256: `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.

The optional candle-session candidate `f59d54c` remains excluded. Installation approval covers these artifacts; it does not request a restart, position change or order.

**Expected upside:** accurate recovery and execution scope, usable operator controls, visible hourly BTC data, and reachable provider evidence. No numerical return or win-rate improvement is established.

**Main risks and failure modes:** inherited-context or funding duplication errors from the earlier recovery component; a source/binary mismatch; wrapped-content or key-navigation regressions; and stale observations being mistaken for current execution authority. Existing recovery evidence is preserved, and no successful display check is treated as profitability proof.

**Validation completed:**

| Check | Observed result | Scope |
|---|---|---|
| Final Rust suite | 578 passed, 0 failed, 23 existing ignored | Full crate suite, 72 harness reports |
| Clippy, formatting, release build | Passed | Offline, locked dependencies; all-target warnings denied |
| Python recovery continuity | All 19 proposed Python files match the previously tested candidate | Prior 158 focused Python tests retained; no new Python runtime changes |
| Final native capture | 410 frames, three exits of 0 | Recorded stopped data; all seven assets at 100x28, 120x36 and 190x52 |
| OPS and setup inspectors | 21 asset-size cases each | Complete required controls and inspector endpoints |
| Depth | All 840 distinct asset/size/side/level combinations; 1,106 displayed rows including overlap | Rounded display prices/sizes/cumulatives checked against exact recorded books |
| Chart evidence | 21 cases | Configured timeframe and complete-bar close; all indicator strings, full source paths and component/authority/effect; Home restores first page |
| Visual inspection | Seven hourly-candidate charts, plus five final focused images | Reconstructed native cells; disclosed regular-font fallback for line glyphs missing from Menlo Bold |
| Fresh production collectors | Five polls, 7/7 provider scopes, 10 distinct evaluations, 35 native books, 361 consecutive completed candles per asset | Separate no-submit run from 21:17:37 to 21:18:53 UTC; exit 0 |
| Installation/rollback | 44 files apply/reverse/reapply exactly; executable replacement/rollback/replacement match hashes | Disposable copy only; prior sources and binary retained |

The fresh observer's latest decisions match the current completed bar for each configured clock: BTC 1h; ETH/SOL/HYPE 1m; SPCX/SNDK/BRENTOIL 15m. All were HOLD. BTC lacked its sweep/volume/EMA conditions, ETH/SOL lacked admitted regime and hourly cross, HYPE lacked a new breakout, and the non-crypto providers awaited their hourly setups. This roughly 76-second sample cannot establish trading frequency, an edge, or large positive swings. Startup evaluations include completed-bar context, and three later polls had no new provider bar. The bounded process exited normally; its final retained heartbeat says `running`, so process exit and heartbeat are not conflated. An earlier launch was refused because its output path lacked the required `observe` component; no poll ran in that attempt.

**Validation still required:** fresh observer checkpoint/TUI parity; complete configuration draft/scroll workflow; installed user-terminal acceptance; full-system checks at the final release boundary; and current venue ownership/collateral/precision reconciliation before separately authorized operation. The earlier full-backend recovery replay used scripted empty intents and does not establish new real execution or profitability.

**Success metrics:** no fabricated data or authority, exact provider identity, complete reachable evidence at the supported sizes, correct completed-hour OHLCV, unchanged strategy settings, no financial instruction from observer/capture work, and exact rollback of the reviewed artifacts.

**Failure / rollback triggers:** identity/accounting mismatch, duplicated costs, incorrect current-run fill scope, enabled requests on a stopped snapshot, missing completed bars, unreachable evidence, or a file/binary hash mismatch. Stop the installation procedure on mismatch and restore only the archived source paths and previous executable. Preserve ledgers and venue state.

**Confidence level:** high for the reproduced defects, final tests, recorded-data parity, brief fresh collector coverage and exact offline rollback. Full live readiness and economic improvement remain unproven. A contradictory native frame, changed artifact, non-causal bar, mismatched provider value or unexpected adapter operation would invalidate the corresponding result.

At **21:25:15 UTC**, unsigned native reads found the existing **0.306 SNDK short at 1629.2, 10x isolated**, with unrealized PnL **-$0.5508**. The full-size reduce-only buy Stop Market remained open at **1669.9**, OID **542326955281**. Core was position/order-free. Original trading/TUI PIDs were absent and original terminal records/ledger hashes were preserved. These are sequential point-in-time observations, not a present-tense guarantee.

**Explicit approval requested:** install candidate `05809a9`'s exact source package and TUI while keeping the backend stopped. The objective's Human control clause requires explicit approval before live execution-behavior or deployment changes. No installation or restart was performed in this study.

**Highest-value next investigation:** create a fresh run-bound observer checkpoint and verify complete TUI/configuration workflow against it, then reconcile the remaining live-readiness requirements. Retain the sealed prospective outcomes unopened and continue economic research independently of this technical correction.
