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
