# V89 non-crypto expansion and activity repair

Prepared 2026-09-07 on `agent/frequency-hip3-repair-20260907`, based on `b610f8c`.

The staged V89 profile adds **xyz:SPCX, xyz:SNDK and xyz:BRENTOIL** to the existing BTC, ETH, SOL and HYPE routes. It addresses the requested asset expansion and supplies more frequent, causal hourly mechanisms. Technical confidence is high within the offline tests and bounded unsigned observation below. Economic confidence is **low**: recent history was used for selection, results depend on a few winners, and SNDK lost in the later partition. This is a candidate, not a live deployment or proof that the profitability problem is fixed.

## Concrete change

Candidate: [`multi_asset_growth_first_5000_noncrypto_research_v89.toml`](../../configs/multi_asset_growth_first_5000_noncrypto_research_v89.toml).

| New asset | Completed-hour mechanism | Declared exposure |
|---|---|---|
| `xyz:SPCX` | Recovery inside a 20-hour, two-standard-deviation price band; exit at mean crossing | Both directions, 10x, 2% margin allocation, $500 notional cap |
| `xyz:SNDK` | 20-hour entry channel / 10-hour exit channel | Both directions, 10x, 2% margin allocation, $500 notional cap |
| `xyz:BRENTOIL` | 8-hour entry channel / 4-hour exit channel | Both directions, 10x, 2% margin allocation, $500 notional cap |

All three use ATR20 Wilder × 2 structural stop anchors, clamped to 20–250 bps, no fixed target, recipe exits and a 24-hour fallback. Decisions use completed hourly information projected onto the completed 15-minute source; modeled entries use the next quarter-hour open. Provider contracts reject a different clock, side scope or untested execution shape. The first four assets/providers retain V88's exact parameters; capacity changes from four to seven. The old V88 transition approval is not copied. Declared execution scopes do not arm an observer.

The TUI adds readable aliases and exact provider/asset evidence, including losses and low confidence. Readiness is not presented as a win probability. Public qualification confirmed all three exact mainnet markets on 2026-09-07 at 10:29:30 UTC, with maximum leverage 20x, 10x and 20x respectively; the candidate declares 10x. These are venue perps, not purchases of underlying shares or physical oil.

## Why activity was sparse

The inspected V88 run was polling successfully and remained flat: 4,411 polls over approximately 18.4 hours, with no eligible entries, intents, fills or faults at the inspected checkpoint. The evidence supports restrictive entry conditions rather than a stopped engine. New eligible decisions or a source fault would update that diagnosis.

The existing 351-day four-core replay recorded 108 trades, about one every 3.25 days, with a 37.0% net win rate. Nominal net was $811.20, falling to **−$46.35 after removing the largest three winners**. Sparse trading therefore did not establish that most entries would produce large gains. This is a different observation window from the new 48-day screen and is not a controlled estimate of a frequency improvement ratio.

## Measured candidate results

Public native 15-minute bars and hourly funding cover 2026-07-19 through 2026-09-07 exclusive. Each asset has 4,800 bars and 1,200 funding observations. Two days seed the signals; the continuous evaluation spans July 21 through September 7, **48 calendar days**. Development is July 21–August 18; the chronological extension is August 18–September 7. Both partitions reset flat, so their PnL need not sum to the continuous replay.

The table uses 0.9 bps taker fees per side and **5.5 bps adverse slippage per side**, native funding, and $500 capped notional per asset. The full-fee stress increases HIP-3 fees to 9 bps per side while retaining adverse slippage.

| Asset | Trades / day | Net wins | Adverse net | Development | Extension | Full-fee net | Adverse net excluding top 3 wins |
|---|---:|---:|---:|---:|---:|---:|---:|
| SPCX | 52 / 48 = 1.08 | 61.5% | $43.79 | $25.10 | $13.45 | $1.67 | −$7.05 |
| SNDK | 47 / 48 = 0.98 | 31.9% | $120.85 | $147.08 | **−$24.93** | $83.11 | −$107.38 |
| BRENTOIL | 61 / 48 = 1.27 | 32.8% | $32.86 | $25.76 | $6.25 | **−$16.58** | −$42.41 |

Pooling these three independent asset replays gives **160 trades, 3.33/day**, with entries on all 48 calendar days. The median entry gap is five hours; the maximum is 30 hours. Adverse-cost net is $197.50, with 67 wins and 93 losses (**41.875% wins**). Mean win/loss is +$13.11 / −$7.32; median win/loss is +$6.85 / −$6.43. Removing the top three winners changes net to **−$30.73**. Nominal net is $241.87; full-fee net is $68.20 and becomes −$22.42 after removing the largest winner.

This pooling is **not a seven-asset shared-account simulation**. It does not validate combined drawdown, margin contention, liquidation interactions, or diversification against the retained crypto routes. There is no empirically supported schedule for future trades; entries remain conditional on signals.

## Alternatives and selection limits

| Option | Evidence and trade-off | Disposition |
|---|---|---|
| Retain V88 unchanged | Existing configuration preserved; sparse, concentrated historical results remain | Prior live profile, now stopped |
| Add SPCX alone | Smaller implementation/exposure increment; strongest observed win fraction, but little full-fee surplus | Simplest prospective investigation |
| Stage SPCX + SNDK + BRENTOIL | More observed activity and different price mechanisms; concentration, later SNDK losses and oil fee sensitivity remain | V89 technical candidate |
| Add SP500 | All three newly tested mechanisms lost under the screen | Not selected; results retained |
| Add GOLD | Prior standard-fee rejection retained; no changed fee evidence justified reopening it | Not selected |
| Replace core routes with hourly challengers | Core results were mostly negative; no sufficient evidence for replacing the four contracts | Not selected; results retained |

The screen retains **216 valid case cells**: three mechanisms across eight assets, three costs and three windows. No negative performance result aborted a valid trial. The second mechanism family was specified after the first results; Brent was an additional asset alternative after the initial screen. These are sequential exploratory comparisons, not a single untouched preregistration. No window is labeled pristine out of sample. Prior exposure, multiple comparisons and selection on aggregate outcomes weaken economic inference.

SPCX recovery and the channel systems encode different price behaviors; no regime filter was added. Regime labels do not establish predictive accuracy or alter these routes. Cash-session holidays and thin external-market hours remain in the observations; calendar-day activity is not a cash-session-normalized result.

## Validation and remaining failure modes

- Offline regression and causal truncation tests cover hourly projection, gaps, stop anchors, entry/exit publication, duplicate prevention, strict contracts and unchanged core configuration. The final focused run passed **44 tests**. Coverage of the four new provider/contract/band/activity modules is **98%**; contract and band business logic are 100% covered.
- The full offline Python run initially passed 7,759 tests and failed 275 because ignored historical fixtures were absent from the isolated checkout. Independent APFS copies restored the fixtures: 262 then 12 affected tests passed. The remaining legacy revision-hash test passed against the new source while retaining its original absolute fixture location. **8,034 distinct tests passed across these runs; four network tests were deselected.** No historical journal hash was rewritten.
- Rust format, all-target Clippy with warnings denied, the full `hypervector-tui` test suite and the debug TUI build passed. The initial Rust fixture failure was resolved by copying its historical ledger/checkpoint into the checkout.
- Independent arithmetic reconciled all **8,304 trade records** across the 216 overlapping case cells: direction, quantity, entry/exit prices, fees, funding and net sums, within $0.0000001. These are repeated scenario records, not 8,304 independent observations.
- Native 1-minute versus native 15-minute source comparison covered September 4–7 for each addition. Reconstructed OHLC had small differences, including opens up to 2.68 bps apart. The last day's 96 provider decisions per asset had zero entry/exit mismatches and identical stop anchors under the same three-day history. This does not establish native fill parity or full-history versus rolling-history equivalence.
- A fresh uninterrupted unsigned observer completed **10 polls with 7/7 provider/asset coverage**, zero order actions, zero intents, no future or duplicate evaluations and `technical.complete=true`. Run: `bidirectional-observe-1788779897219`. Profile fingerprint after observer ledger rebinding: `df8cc4242df8060f2a9a370c792b392759a1dd0a5398f13ada1a8d940ab0b96e`. A prior stopped/resumed test correctly reported a heartbeat gap; that evidence is retained.
- Actual terminal captures at **120×36, 100×28 and 190×52** navigated all nine tabs and all seven inspectors, retaining `EXECUTION DISARMED` and exiting normally. Exact rendered provider IDs verified the three new aliases, $500/10x contracts and low-confidence evidence. Capture metadata initially assumed configuration order; the separate terminal review resolves the actual sorted rows from their displayed provider IDs. At 100×28, identity, risk and research summaries fit, but lower inspector indicators/blockers fall below the visible panel. Full new-provider details were inspected at 120×36 and 190×52. Text-cell inspection does not validate colors or constitute human visual sign-off.

One SNDK adverse-cost trade has a same-bar ambiguous liquidation/stop path (2026-08-07 13:00–13:30 UTC, modeled −$26.36). Native intrabar sequence was not observed. No selected continuous case had a terminal or gap-censored exit. Candle-based marks, modeled fills and funding conversion do not establish private execution quality. Current public 1-minute history limits also leave recursive ATR startup sensitivity unresolved across a rolling production history versus the 50-day research input. The data-source comparison above does not remove that uncertainty.

The highest-value next investigation is a **fixed, prospective SPCX lifecycle observation** using the exact production source and independently reconstructed decisions, recording completed entries, stop anchors, exits, actual available depth, fees and funding. It should compare the rolling history against retained native history and report source differences, rather than selecting new parameters from the same history. Full seven-asset joint marking and prospective SNDK/Brent validation remain necessary before calling the whole candidate economically ready.

A source timestamp/side mismatch, duplicate decision, unexpected contract override or inability to honor the tested stop/exit shape falsifies technical readiness. Different prospective cadence, negative cost-adjusted outcomes or larger concentration updates economic confidence. These are reporting and investigation criteria, not newly introduced implicit trial-abort gates.

## Evidence and preservation

Large immutable artifacts are under `/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/`:

- `frequency_hip3_public_qualification_20260907_v1.json`
- `frequency_repair_native_inputs_20260907_v1/manifest.json` and `frequency_repair_brent_inputs_20260907_v1/manifest.json`
- `frequency_repair_native_screen_20260907_v1.json`, `frequency_repair_reversion_screen_20260907_v1.json`, `frequency_repair_brent_screen_20260907_v1.json`
- `frequency_repair_reconciliation_20260907_v1.json` and its version 2 generator
- `frequency_repair_native_minute_parity_20260907_v1/report.json`
- `frequency_repair_observer_audit_20260907_v1.json` and `frequency_repair_observer_audit_20260907_v2.json`
- `frequency_repair_terminal_acceptance_20260907_v2.json` and `frequency_repair_terminal_review_20260907_v1.json`
- `frequency_repair_v88_final_state_20260907_v1.json`
- Python/Rust validation logs with the `frequency_repair_` prefix
- `frequency_repair_preformat_sources_20260907_v1/manifest.json`

The source bundle freezes 27 exact files used during the experiments, before mechanical formatting/refactoring. Resolve original report source hashes against that bundle, not subsequently formatted working copies. **Correction:** the first Brent protocol draft reversed SNDK's partition characterization. The accurate values are development +$147.08 and extension −$24.93. The exact original draft is preserved in the source bundle; the tracked protocol explicitly records the correction. Parameters and original results were not rewritten.

Research scripts write new immutable outputs and use unsigned public data or local inputs. The append-only research revision records evidence hashes and has `execution_authority=none`, `automatic_promotion=false`, and `runtime_strategy_changed=false`.

## Deployment state and rollback

No live backend was armed, restarted, stopped or changed by this repair. The staged candidate is isolated from the original V88 checkout, whose tracked files remain clean. Its configured profile remains `multi_asset_growth_first_5000_four_core_evidence_candidate_v88`; the original TOML SHA-256 is unchanged at `c56175ea2596aeeca99528a6a84049fc6c7899f0b03e9a8d2fc5cc2621df8f36`.

**Final runtime correction:** the final read-only check found that V88 had stopped at **2026-09-07 10:27:11 UTC (06:27:11 Eastern)**. All four asset ledgers report `operator_stop`, zero position size and no last fault; the previously observed backend, supervisor, checkpoint and TUI PIDs are absent. The last cohort heartbeat still says running, but the checkpoint explicitly classifies the state as `stale_running_heartbeat_after_asset_stop`. This supersedes the earlier observation of healthy ongoing polling. High confidence in the recorded stopped state; the records do not identify who or what initiated the stop. No restart was attempted.

Rollback of this preparation means retaining V88 and discarding the separate candidate; no runtime rollback is needed. Live promotion and real-money trade execution remain operator actions. There is no approval request to activate an economically validated seven-asset system here: that validation has not been completed, and this report does not claim otherwise.
