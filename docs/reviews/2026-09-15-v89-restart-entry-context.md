# V89 recorded entry context across reporting restarts

The installed reporting repair restores the original entry indicators and canonical regime for inherited trades. The affected SNDK lifecycle is `xyz:SNDK:545845583477`; its entry evidence had become unavailable after the user restarted the backend, although the earlier checkpoint retained it. Execution ownership, position, stop and costs were already recovered correctly.

## Diagnosis and implementation

The bounded current-run publisher recovered older configuration identities and asset execution receipts but omitted older cohort evaluations. The reflection join therefore could not find the exact source-run/provider/symbol/decision record. A real-publisher regression reproduced the missing readiness before implementation.

The repair recovers only recorded evaluations matching journal entry identities. It streams the historical range from the earliest required configuration boundary to the current run boundary, authenticates the source range and selected rows, validates run/profile identity and causal observation clocks, and rejects contradictory duplicate evaluations. It rereads that bounded range on each publication; a prior-context edit changes the next report and its provenance instead of returning cached content.

Recovered annotations use a dedicated projection event. They populate exact entry lookup only and do not populate latest-state or continuous regime timelines. Complete ordinary telemetry takes precedence over identical recovered annotations. This preserves current-run readiness/routing/health counts, current regime assessments and opposition/path history. Missing legacy evidence remains explicitly unavailable. Independent and legacy canonical providers are alternative sources; an absent legacy alias is not a missing independent canonical assessment.

Three reporting modules changed. The candidate commit is `7d8e7a304086dc5f8fd0a93383b0cbce3d6af47f`; the installed commit is recorded in the accompanying research journal. No strategy, sizing, leverage setting, live execution path or financial process lifecycle changed.

## Validation and results

- The original failure and contradictory-duplicate/timeline failures are preserved in the evidence directory. Final candidate tests: **160 passed**. Installed tests: **160 passed**. Statement coverage across the three affected modules was **98%**; the new recovery module was **98%**, the snapshot integration **100%**, and the reflection index **96%**. This is targeted coverage, not whole-project coverage.
- Tests cover exact identity matching, wrong provider/symbol/time, contradictory fingerprints, future observations/decisions, duplicate agreement/conflict, unavailable legacy context, source replacement/truncation, rereading edited prior evidence, timeline separation and unchanged execution/current-run telemetry.
- A frozen real-input comparison restored **18 evaluations for nine prior entry decisions**: eight closed lifecycles and the inherited open SNDK lifecycle. SNDK's complete recovered entry-context object equals the pre-restart checkpoint's object exactly.
- The only changed audit sections were `open_trade_reflections`, `trade_reflections`, and `entry_alignment_mechanism`. Changes restore entry fields/assessments and their descriptive attribution buckets. Execution totals, current telemetry, current contexts, price paths and continuous opposition evidence remain equal on the same inputs. No threshold or strategy rule was selected from these outcomes.
- The bounded historical scan read **199,744,909 bytes**. Observed publication time was **3.70 seconds cold** excluding comparison work and **1.89 seconds on repeat**, with process peak RSS about **432 MB** during the instrumented two-publication experiment. These measurements apply to the captured ledger size, not an unlimited-history guarantee.
- The installed independent monitor opened all nine panes and the setup and closed-trade inspectors. Actual captures show restored canonical entry states and assessment, SNDK's open entry score `+1.00`, and configured/venue leverage at four terminal sizes from **100×28 through 190×52**. Both open SPCX and SNDK positions display **10x/10x**. Provider fields absent from the original source remain `N/A`; the display does not borrow canonical fields to fill them.
- The terminal run observed **20 fills / 20 projected**, eight closes, two open lifecycles and one current-run fill. Closed net PnL remained **−$25.609303**. These are descriptive accounting totals, not expected returns.
- Validation denied network, credentials and financial/database writes. The owned monitor exited with code 0, restored terminal attributes and reaped its reporter. User PIDs **29190/29191/30603/62016/62017** remained unchanged. Installation preserved **5,503 other files**, both existing executables and the active configuration.

## Use and limitations

The existing combined session still owns its original TUI and loaded reporter. Start the updated independent monitor in another terminal to consume this reporting repair; keep the original session open:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor --independent-monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector-v89-monitor-20260915 \
  --tui-bin-sha256 09066c5c1c1e869866a7e339643b1fce7ab59e02e04dbbd670de4651ba8a9006
```

The executable already contains the verified leverage fix and did not need another rebuild. Independent monitoring requires a fresh same-run shared reporter. Recovering exact entry snapshots does not restore the complete pre-restart regime path or absent exit context. Historical scan cost grows with the required ledger range; materially increased publication latency warrants a separately validated optimization. The ledger contract is append-only; selected records and range hashes provide provenance, and replacement/truncation are rejected.

**Recommendation / why now:** retain the repair because lost entry evidence misstates the operator's strategy/regime comparison and historical attribution. It applies across the seven-asset profile and does not depend on a favorable market regime. The simpler alternative leaves inherited entry evidence unavailable; replaying all historical telemetry adds substantial memory and reporting cost.

**Expected benefit:** accurate monitoring and research attribution. No profitability increase is established by this display/reporting change.

**Confidence / falsifiers:** high for the reproduced defect, tested boundaries and recorded native sample. Wrong source binding, changed financial accounting/current telemetry, recovered snapshots entering continuous timelines, stale reporting or excessive scan latency would reopen the repair. Universal bug freedom and strategy expectancy remain unproven.

**Rollback:** overwritten bytes, source hashes and the exact reverse-checkable patch are under `data/logs/research/bidirectional_cohort/v89_restart_entry_context_20260915_v1/installation/`. Verify `git apply --reverse --check` against that patch before a rollback. Restore only the listed files. This rollback does not require controlling a financial process or replacing either executable.

**Approval:** covered by the existing corrective reporting authorization. No additional approval was requested.

**Highest-value next investigation:** reconcile the newly observed SPCX entry with its recorded provider, causal regime, entry receipt and covering stop; continue tracking the inherited SNDK lifecycle through its eventual exit and net costs. The broader continuous research goal remains active.

All experiment inputs, before/after reports, failed and passing tests, hashes, installed terminal captures and process-preservation receipts are under `data/logs/research/bidirectional_cohort/v89_restart_entry_context_20260915_v1/`.
