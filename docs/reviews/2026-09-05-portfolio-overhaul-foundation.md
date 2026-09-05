# Portfolio overhaul: verified foundation and executable capacity

The overhaul remains in progress. No new live profile has been deployed. The September source is preserved at `fac0369`; implementation and verification use the isolated `agent/evidence-overhaul-20260905` branch. The original July `main` checkout and historical ledgers remain intact.

## Evidence and corrections

High confidence, based on source-prefix/hash checks and the September 5 public-wallet-only venue observation: all 11 imported ledger prefixes and all 276 preexisting canonical journal source files matched. The source tree also contains later research records outside that canonical schema. The venue snapshot at 15:30:46 UTC reported $4,857.58724349 equity, seven flat assets and zero orders. These observations are historical snapshots, not evidence that later account state is unchanged.

The latest V86 run, `bidirectional-live-1788585501070`, recorded 1,255 routing cycles without intents, fills or closes. Its 5.3-hour quiet period is insufficient to falsify low-cadence strategies. Across 124 resolved historical closes spanning different strategy versions and sizes, net PnL was −$329.976296: −$251.076035 market PnL, −$81.072513 fees and +$2.172252 funding. This mixed-contract total does not estimate current V86 expectancy; negative gross PnL also prevents explaining the entire historical loss as fees.

Terminal asset workers were incorrectly projected as a healthy backend when the last heartbeat said running. Python now reports the terminal process state as stopped. The Rust TUI recognizes both supported terminal lifecycle forms. STOPPED describes worker control state and does not establish venue flatness. Additional launch-error and isolated-test-fixture fixes preserve live-arm requirements and evidence hashes.

The older ZEC report labeled long pseudo-holdout actually included both sides and a wider sizing contract. A later V84 record already corrected that mismatch through an exact capped long-only replay. Its nine July–August trades returned +$160.726954 nominal, but −$45.979015 after largest-winner removal. Therefore this investigation did **not** discover an unresolved current replay defect. ZEC remains a research gap; the failed V86 UT-Bot short validation and earlier rejected mechanisms are not reopened by this review.

GOLD's September 5 public metadata still omitted `growthMode`. That observation does not establish the lower effective fee required by its prior rejection's reopening condition. The existing rejection remains in effect for this pipeline. Official fee mechanics: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees>.

## Actual executable capacity

The new offline capacity calculation reuses production provider-side sizing precedence and the capped notional function. It excludes observe-only providers and respects one position per symbol and the portfolio position count. Bounds for different metrics are computed independently; with competing routes, their maximizing assignments need not coincide.

At the recorded equity, the exact V86 executable set is:

| Asset | Executable side | Notional cap binding amount | Initial margin | Provider stop |
|---|---|---:|---:|---:|
| BTC | Long, sweep | $2,500 | $125.00 | 60 bps |
| ETH | Long, range onset | $500 | $33.33 | 60 bps |
| SOL | Short, range onset | $500 | $33.33 | 60 bps |
| HYPE | Long, compression alignment | $2,500 | $250.00 | 80 bps |
| SPCX | Long, cash session | $500 | $50.00 | 60 bps |
| SNDK | Short, breakout pressure | $750 | $75.00 | 80 bps |

High confidence under the static, fully occupied assumptions: total executable notional is $7,250 and initial margin is $566.666667, or 11.665599% of recorded equity. Long notional is $6,000 and short notional is $1,250; these different assets do not form a proven hedge. BTC and HYPE contribute $5,000 of $7,250 potential notional. ZEC and two BTC short providers are visible but cannot add executable capacity.

Correction retained for traceability: an intermediate manual sum of $666.67 was wrong. The independent regression expectation failed against the production calculation; the correct sum is $566.67.

| Static simultaneous-stop sensitivity | Loss | Meaning |
|---|---:|---|
| Provider stops + observed taker fees | $55.40 | Zero additional slippage or funding assumed |
| Above + 120 bps round-trip slippage + 20 bps adverse funding | $156.90 | Declared adverse-cost sensitivity, not a measured percentile |

The calculation holds entry equity/notional fixed and omits rounding. It is not a maximum loss, liquidation model, account drawdown forecast, or execution gate. Stop gaps, price-dependent exit notional, partial fills and failed exits can produce larger losses. Entry and reduce-only IOC caps are execution constraints, not cumulative loss bounds. No capital allocation is changed by this report.

Reproduce the immutable calculation with a new output filename:

```bash
uv run python scripts/cohort_executable_capacity.py \
  --config configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml \
  --venue-snapshot /Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v86_overhaul_venue_snapshot_20260905_v1.json \
  --slippage-bps 120 --funding-bps 20 \
  --out /path/to/new-capacity-report.json
```

## Validation and remaining decision

The foundation changes passed 7,906 offline Python tests and the Rust tests, formatting, Clippy and release build. After adding the capacity module and publication command, the full offline Python suite passed **7,929 tests** (4 network tests deselected, 27 warnings). Capacity-module statement coverage was 97%, including production sizing precedence, caps, lower-equity scaling, mutually exclusive routes, position limits, stop selection, fee rejection, source identity and immutable output. The later bootstrap correction passed 193 related offline tests. A recorded observer fixture rendered all nine TUI setup rows; that is not fresh live acceptance.

A fresh unsigned SPCX collector was started in the isolated worktree. It exposed a writer/consumer mismatch: bootstrap published a cursor and zero-decision status without creating the empty journal required by the consumer. A failing regression reproduced the missing file. Bootstrap now creates the journal without truncating existing bytes or emitting synthetic decisions; a malformed existing journal still raises an error and remains intact. The fresh real collector produced the expected zero-byte journal after the fix. Original live runtime files were not modified; pre-fix isolated cursors/statuses were backed up.

At the 17:15 UTC boundary, SPCX published its first prospective record. The earlier resumed cohort audit retained its real startup gap and correctly reported incomplete continuity. A separate clean observer run, `bidirectional-observe-1788628609645`, covered 17:16:49–17:17:39 UTC and passed its technical audit: four successful polls, zero degraded polls, all nine monitored provider-symbols, no technical gaps, four canonical regime evaluations and zero intents/actions. Its isolated ledger paths change the observer fingerprint; no live profile identity is claimed. This is a 50-second startup/coverage observation, not economic evidence.

The release TUI rendered the clean observer checkpoint at 120×36. Setup showed 9/9 configured routes and disarmed execution; all nine tabs were opened and `q` exited with code zero. The terminal capture is an immutable screen-diff artifact, not screenshots or final live acceptance. The depth view also disclosed stale global HIP-3 metadata; config-generation and prestart-approval fields were unavailable in this observer checkpoint. Those limits remain explicit.

Immutable results are `overhaul_v86_current_observer_audit_20260905_v1.json` (resumed gap preserved), `overhaul_v86_verified_observer_audit_20260905_v1.json` (clean technical pass), and `overhaul_v86_current_tui_smoke_20260905_v1.json`, under the original project's `data/logs/research/bidirectional_cohort/` directory.

| Alternative | Evidence / trade-off | Current disposition |
|---|---|---|
| Keep V86 execution scope | Preserves six existing executable directions; leaves ZEC and retired shorts observational | Baseline for exact portfolio replay |
| Remove uncovered/retired rows from successor roster | Makes every retained row executable; reduces displayed universe without adding an edge | Proposal option, no live change |
| Restore rejected ZEC or GOLD candidate | Adds activity but reuses failed or conditional evidence | Rejected absent its documented reopening condition |
| Increase binding caps | Raises potential use of configured fractional sizing and simultaneous loss | Deferred until exact shared-portfolio replay |
| Add a different asset/mechanism | Could diversify; requires native history, costs, causal validation and implementation | Research option, not a shortcut to readiness |

The economic experiment remains a **shared-account replay of the six exact executable contracts at current caps**, including marked exposure, overlapping losses, costs and occupancy. It is frozen in `docs/research-journal/portfolio-overhaul-exact-shared-replay-20260905-v1.json` and indexed in DuckDB. It should establish whether reported isolated evidence survives the actual portfolio before comparing an explicitly preregistered cap change. Already inspected historical partitions must remain labeled as opened data; a replay is a fidelity and interaction experiment, not a new untouched holdout. The later provider-level findings below update its immediate next step. Falsifiers include source/contract mismatch, look-ahead, unmodeled funding/slippage, differing production decisions, and materially worse simultaneous marked loss than the isolated summaries suggest.

No live-change approval is requested at this milestone. The concrete successor, full route-by-route economic review, persistent improvement process, all-screen current-data acceptance, rollback package and approval-ready launch remain outstanding. Confidence is high in the bounded source and arithmetic findings, and low in unmeasured future portfolio profitability.

## Current-provider extraction and confirmed SNDK discrepancy

High confidence from the completed artifact: production crypto collectors generated 308,424 evaluations for decision times **(2026-05-18 00:00, 2026-07-28 00:00] UTC**. This 71-day adapter panel starts on the first full UTC day following SPCX's archive lower envelope; it does not claim maximal verified six-asset coverage or adequate HIP-3 warmup. The extract preserves exit-only evaluations and diagnostic regimes, rather than retaining only entry intents.

| Current provider | Evaluations | Eligible entries | Exit evaluations | Rolling comparisons | Differences |
|---|---:|---:|---:|---:|---:|
| BTC liquidity sweep long | 1,704 | 3 | 0 | 74 | 0 |
| ETH directional range long | 102,240 | 6 | 31 | 104 | 0 |
| SOL directional range short | 102,240 | 3 | 31 | 103 | 0 |
| HYPE compression alignment long | 102,240 | 8 | 4 | 83 | 0 |

The comparisons cover every batch-actionable evaluation plus daily noon controls, including exact execution and regime fields. They do not prove equality at every nonactionable minute: a rolling-only signal outside these checks remains a falsifier. Daily batches use the production lookback plus up to one day of additional history. Seventy of each route's 71 warmup/input windows contain tagged gap-filled minutes; the artifact records these explicitly and does not assert that interpolated prices are executable. These are **20 entry signals, not 20 simulated trades**. No account return, funding, private fill, or joint marked drawdown has been calculated from this panel.

The immutable bundle is `overhaul_v86_core_provider_decisions_20260905_v1/`, with a manifest, 284 daily Parquet files and four complete sampled-parity records. The exact generator is preserved as `overhaul_v86_core_provider_generator_20260905_v1.py` (SHA-256 `53055b75bf36e1c920ecc811b8e5da03a9a2b70b018d5c4c083667949ed9e64b`). After publication, parser/manifest extraction brought the maintained CLI within the function-length standard without changing its contract. Forty focused/integration tests passed; the extraction module's 21 direct tests cover 100% of its statements. The diagnostic integration deliberately records the still-unfixed SNDK mismatch; it is not evidence that SNDK is repaired.

High confidence from source comparison: the 525,436 ETH and 525,417 HYPE observed cache rows exactly match their corresponding 0xArchive candle files for timestamp and all OHLCV values. The cache additionally contains 164 and 183 tagged gap-filled minutes respectively. ETH has one on-disk native L2 window and HYPE has 1,016; each inspected compressed book matches its manifest hash. These selected windows are not continuous position-lifecycle coverage. This updates the earlier registry-only inventory: absence from the main DuckDB bundle tables did not mean native source files were absent. Details and hashes are frozen in `overhaul_eth_hype_native_bindings_20260905_v1.json`.

**Confirmed material defect, high confidence:** the current SNDK v3 provider zeros every prior pressure value, then inserts pressure only on the latest bar before computing `raw & ~prior_raw`. With the actual frozen recipe and 101 continuously falling candles with fresh negative pressure, two successive live-provider calls both emit short entries. The canonical research engine, supplied the same pressure history, emits neither at those two continuing-state boundaries. A symmetric long scenario reproduces the same discrepancy; only short is currently executable. Four of four inspected boundaries disagree. The prior index-provider repair already documented this same failure mechanism, but the inspected SNDK v3 adapter still uses the older path.

Reproduce with `uv run python scripts/sndk_pressure_onset_diagnostic.py --out /path/to/new-report.json`. The immutable result is `overhaul_sndk_current_onset_discrepancy_20260905_v1.json`. The finding establishes a signal-contract mismatch; no current exact-identity realized loss is attributed to it, and suppressing repeated signals has not yet been shown to improve returns. A documented intentional state-entry contract or a same-input collector retaining prior raw state would update/falsify the relevant assessment.

The **single highest-value next investigation** is therefore the SNDK corrective adapter: reuse the existing durable pre-close pressure/cursor implementation, keep recipe, short direction, sizing, stops and hold policy frozen, and compare current versus corrected behavior. Required checks include continuation, genuine reset, restart, missing prior state, stale/future pressure, gaps, historical lifecycle sensitivity and unsigned observer/TUI parity. This is new evidence on SNDK, not reopening a rejected strategy hypothesis. No live change has been applied.

DuckDB revisions: shared replay v2 `77c9f1a25c453283821045aadfe35b3717f927e53938f3343d2a5e468133dc39` is **being tested**; SNDK discrepancy v1 `04d53ff1a6ed53fc5e1b5f41526cdd0d55696949614bb741e319710cd5e84d94` is **accepted for the technical diagnosis only**. The complete portfolio overhaul and live transition remain unfinished.

## SNDK correction candidate, prospective observations and economic sensitivity

The isolated V87 control candidate replaces SNDK v3 with `hip3_breakout_pressure_sndk_fresh15s_bidirectional_v4`. It reuses the existing durable pre-close cursor and journal engine: prior raw state survives restart, pressure age is measured at the exchange boundary, and at least two snapshots plus a complete source scan are required. Short direction, recipe, leverage, sizing, 80 bps stop and 24-hour hold remain unchanged. The new profile has fingerprint `f0c27106da3204a13e4e1bfef5e13858c70f9fdc2691484784cc4f727c6fa046` and a distinct pending approval path; no approval file or live transition was created. Its seven-asset roster is a comparison control, not the final retained universe.

High confidence in the bounded technical correction: failing continuation, restart, unknown-prior-state and writer/consumer tests preceded the implementation. Nine correction/adapter cases passed. The first full offline suite passed 7,972 tests before final candidate metadata and dependency recovery changes. The release Rust tests, formatting, Clippy and build also passed. Final validation after the additional changes is recorded separately when complete.

Unsigned SNDK observations progressed from an incomplete startup window at 18:15 UTC, to a fresh current window with unknown prior pressure at 18:30, to complete prior/current pressure at 18:45. The last record had 161 snapshots and 4,096 ms publication delay. All three records were ineligible; no genuine entry or private fill was observed. `overhaul_sndk_v4_continuity_observation_20260905_v1.json` freezes those records. A missed next boundary, conflicting persisted state, or same-input decision disagreement would reduce confidence in continuity.

The V87 dependency wrapper initially stopped SPCX after a temporary candle delay made its status stale. A regression reproduced that behavior. The wrapper now logs temporary source unavailability while allowing the unsigned collector to recover; entry consumers still require fresh data. A dead or stopped collector remains an error, and cleanup affects only owned children. Real logs subsequently recorded SPCX stale at 18:43:28 and recovered at 18:43:52 UTC. Both cohort audits remain **technically incomplete** because the observed source outages remain in their records; neither has been relabeled as a pass. The immutable audit files end in `observer_audit_20260905_v1.json` and `v2.json` under the common overhaul artifact directory.

The 120×36 release TUI rendered the V4 provider identity, unchanged risk plan, prior-pressure blocker, and “durable onset correction economics pending” research state. Execution was disarmed and `q` exited zero. The focused capture is `overhaul_v87_sndk_tui_inspection_20260905_v1.json`; it used the incomplete observer checkpoint and is not final current-data acceptance of all screens.

Correction to the research source export: the first HIP-3 midpoint Parquets omitted their timestamp index. They were identified as unusable before any return calculation. Their bytes remain preserved. `overhaul_hip3_midpoint_inputs_20260905_v2.json` supersedes that export, binds replacement Parquets containing explicit timestamps, and records exact data equality plus timestamp round-trip verification. These remain L2 midpoint proxies, not venue candleSnapshot bars.

A controlled, already-opened-history sensitivity now compares state entries with durable onsets under identical midpoint prices and exchange-age filtering. It freezes current SNDK risk, native hourly funding rates, observed bid/ask quotes, 0.864 bps one-way fees, 20 bps opening IOC distance and 30-second quote expiry. Additional adverse slippage is 2.5 or 5.5 bps per side. It isolates the onset mechanism; it does not reconstruct v3 receipt age, v4 prospective candle revisions, private fills or full shared-account behavior.

| Conditional midpoint sensitivity | State entries | Durable onset | Economic interpretation |
|---|---:|---:|---|
| Candidate short signals | 29 | 27 | Two continuing-state signals removed |
| Trades, 2.5 bps additional slippage per side | 19 | 19 | Trade records are identical |
| Conditional net, 2.5 bps | $69.58 | $69.58 | Includes two unresolved gap exits |
| Net excluding gap exits, 2.5 bps | −$22.45 | −$22.45 | Descriptive subset, not corrected whole-path P&L |
| Trades / conditional net, 5.5 bps | 20 / $54.09 | 20 / $54.09 | Different stop/occupancy path; mechanisms still identical |

High confidence in those artifact comparisons, low confidence in their relevance to future returns. The largest nominal gain, $89.55, is an unresolved gap exit; excluding that trade gives −$19.96. Of 1,704 hourly funding events, 138 have no observed matching bar. An additional intrabar stop/liquidation ambiguity uses the screening engine's pessimistic ordering, not an observed liquidation. Missing stops, marks, funding and quote paths could materially change the results. There is **no demonstrated economic benefit from the onset correction in this sensitivity**, and its positive headline cannot support promotion. The immutable detailed report is `overhaul_sndk_onset_lifecycle_sensitivity_20260905_v2.json`.

The single highest-value next investigation returns to the native-source core-provider lifecycle replay, then the exact shared account. SNDK native-candle/source-path supplementation remains necessary before a live retention recommendation. Technical repair is supported; profitability, the final retained roster, portfolio sizing, all-screen acceptance and explicit live approval remain unfinished. No new performance rejection gate or live configuration change was introduced.

Final correction-stage validation ran the entire offline suite: 7,978 passed and two legacy metadata assertions failed because they expected SNDK's superseded research state. Those expectations now require the confirmed defect, its source record, and the unchanged distinction between predecessor n2 and exact v3 n0. All 35 tests in those two files then passed. This is not reported as a second full-suite pass. Ruff and whitespace checks passed. Research revision 2 is `1e659104c6ceee913ee87f8a2357566fd3677c6ad2761bb0ef26d694ef4d33a8`; its status remains **being tested** and explicitly discloses the export correction, preserved runtime gaps and conditional economics.

## Four-core conditional lifecycle and shared marking

The 71-day decision panel has now been replayed through current fixed BTC/ETH/SOL policies and HYPE's opposite-exit plus soft/hard hold policy. An execution-model discrepancy was caught in the first screen: the generic simulator priced targets at their exact threshold even when a taker target exit was intended. An optional, validated `target_slippage_bps` field now prices adverse target fills and fees on the actual modeled exit notional; its default preserves existing limit-target assumptions. Five direct regression cases and 271 related cases passed. The subsequent **full offline suite passed 7,985 tests**, with four network tests deselected and 27 warnings. Commit `f2d02db` contains this research-only change; no live target behavior changed.

| Exact provider identity, conditional minute-bar fills | Trades | Nominal net at current cap | Main evidence limit |
|---|---:|---:|---|
| BTC liquidity sweep long | 3 | $6.47 | Removing either largest winner makes the sample negative |
| ETH directional range long | 6 | $34.96 | Largest-winner dependence; two winning paths include tagged gap-filled minutes |
| SOL directional range short | 3 | $21.47 | All three entries are in July; one exit is forced at the data boundary |
| HYPE compression alignment long | 8 | $385.52 | One $502.04 winner exceeds total net; June and July are negative |

Nominal assumptions are the observed current 4.32 bps one-way taker fee repriced across history, plus 2.5 bps adverse slippage per side, native hourly funding rates with opening trade prices as mark proxies, and the current opening IOC price distance. The adverse-cost case uses 5.5 bps additional slippage per side. This does not reconstruct historical private fee tiers, quotes, partial fills or publication latency. The original fixed-route screen v1 is superseded by v2, which adds taker target friction and the actual BTC/ETH/SOL venue leverage maxima. Its exact generator and the HYPE generator are archived alongside the reports.

HYPE's 2,036 inspected soft/hard hold observations across both cost cases agreed with the production hold policy when supplied identical completed provider/canonical states and fresh, zero-delay evidence. All 102,240 frozen HYPE primary regimes equal their 5m state, and its side field preserves structural direction. This validates the conditional policy adapter, not the assumption that live observations arrive without delay. The provider and canonical collectors share the completed-decision builder; independent live polling history may still differ.

The four-core shared reconstruction independently reconciles quantities, fees, hourly funding and final cash against all 20 modeled trades. Its minute-close marked curve returns **$448.42 (9.23%) nominal** and **$435.57 (8.97%) under adverse costs**. Corresponding maximum close-marked drawdowns are $123.11 (2.28%) and $127.99 (2.37%). These are conditional historical path measurements, not forecast returns or worst-case loss bounds. At minute closes, at most two assets overlap and initial margin reaches $283.33. The lowest adverse intrabar equity proxy stays above $4,837, exceeding the $3,125 level needed for all four current notional caps to bind. Under these assumptions, isolated fixed-notional lifecycles are consistent with the shared sizing path. Intraminute sequencing and venue rejection remain unmodeled.

Removing the largest HYPE trade changes shared net to **−$53.63 nominal / −$64.67 adverse costs**. This is a concentration diagnostic, not proof that a trend strategy is broken. Resampling the eleven observed calendar-week marked-P&L blocks 10,000 times with seed 20260905 gives negative totals in 25.75% / 27.50% of resamples; nominal 5th–95th percentiles span −$140.73 to $1,422.64. These small-sample, exchangeable-week resamples are not probabilities of future loss and do not remove selection bias or the partial final week.

Artifacts: `overhaul_core_fixed_lifecycle_screen_20260905_v2.json`, `overhaul_hype_current_lifecycle_screen_20260905_v1.json`, `overhaul_hype_soft_hard_hold_policy_parity_20260905_v1.json`, `overhaul_four_core_joint_marking_20260905_v1.json`, two complete marked-curve Parquets, and `overhaul_four_core_sampling_uncertainty_20260905_v1.json`, in the common original-root overhaul directory. These exclude SNDK and SPCX and therefore do not complete the current six-route account review.

The larger fixed-route experiment is preregistered as `portfolio-overhaul-core-history-fidelity-20260905-v1.json`, revision `aa2b172e6bf32506f5a49f460a36ecf0132f0d01c04937c2fbf03241e3c30be3`, **being tested**. It extends unchanged core providers to (2025-08-11, 2026-07-28] with 14 days of preceding history. It will report monthly/quarterly stability, costs, concentration and shared exposure without parameter fitting or a claim of pristine OOS. All 33,696 native hourly funding rows are bound and chronology-verified. The longer extraction is still running at this update; no cap or final-universe recommendation is made from the short sample alone.

Both SNDK and SPCX published complete prior/current pressure at 19:00 UTC. The bounded observations were archived and both unsigned collectors stopped cleanly afterward; the supervisor stopped only its owned SPCX child. This does not erase earlier SPCX outages. A further source review found that the index observer's auxiliary one-minute profit-lock candle capture runs before its fifteen-minute signal update; a temporary auxiliary fetch failure can therefore delay the signal status. That coupling is an identified follow-up investigation, not yet a repaired or independently tested claim.
