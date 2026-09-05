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

A fresh unsigned SPCX collector was started in the isolated worktree. It exposed a writer/consumer mismatch: bootstrap published a cursor and zero-decision status without creating the empty journal required by the consumer. A failing regression reproduced the missing file. Bootstrap now creates the journal without truncating existing bytes or emitting synthetic decisions; a malformed existing journal still raises an error and remains intact. The fresh real collector produced the expected zero-byte journal after the fix. The full observer additionally requires initial SPCX readiness from a prospective decision, so that boundary remains pending. Original live runtime files were not modified; pre-fix isolated cursors/statuses were backed up.

| Alternative | Evidence / trade-off | Current disposition |
|---|---|---|
| Keep V86 execution scope | Preserves six existing executable directions; leaves ZEC and retired shorts observational | Baseline for exact portfolio replay |
| Remove uncovered/retired rows from successor roster | Makes every retained row executable; reduces displayed universe without adding an edge | Proposal option, no live change |
| Restore rejected ZEC or GOLD candidate | Adds activity but reuses failed or conditional evidence | Rejected absent its documented reopening condition |
| Increase binding caps | Raises potential use of configured fractional sizing and simultaneous loss | Deferred until exact shared-portfolio replay |
| Add a different asset/mechanism | Could diversify; requires native history, costs, causal validation and implementation | Research option, not a shortcut to readiness |

The single next economic investigation is a **shared-account replay of the six exact executable contracts at current caps**, including marked exposure, overlapping losses, costs and occupancy. It should establish whether reported isolated evidence survives the actual portfolio before comparing an explicitly preregistered cap change. Already inspected historical partitions must remain labeled as opened data; a replay is a fidelity and interaction experiment, not a new untouched holdout. Falsifiers include source/contract mismatch, look-ahead, unmodeled funding/slippage, differing production decisions, and materially worse simultaneous marked loss than the isolated summaries suggest.

No live-change approval is requested at this milestone. The concrete successor, full route-by-route economic review, persistent improvement process, all-screen current-data acceptance, rollback package and approval-ready launch remain outstanding. Confidence is high in the bounded source and arithmetic findings, and low in unmeasured future portfolio profitability.
