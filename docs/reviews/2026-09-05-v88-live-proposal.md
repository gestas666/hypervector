# V88 four-core live proposal — pending operator approval

**Recommendation:** Resume mainnet trading with the V88 four-core roster after an explicitly approved, verified-flat transition. Keep BTC long, ETH long, SOL short and HYPE long at their existing executable strategy and risk settings. Remove ZEC, SPCX and SNDK from this deployment and remove the retired BTC short observation rows. Deploy the validated technical and TUI corrections in the isolated overhaul branch. This document does not authorize execution.

**Why now:** The current V86 run ended flat with no orders, and current public-wallet reconciliation agrees. The overhaul found and repaired lifecycle/status, source bootstrap, SNDK repeated-onset and TUI projection defects. Native-source conditional core economics provide a concrete basis for a limited roster recommendation; the inspected HIP-3 alternatives have weaker or unresolved source/economic evidence. Waiting for more unchanged zero-entry checks would not resolve those historical limitations.

**Evidence reviewed:** The detailed source and experiment inventory is in [the foundation review](2026-09-05-portfolio-overhaul-foundation.md). Immutable reports are under `/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/`:

- V86 current-run and all-live lifecycle reconciliation, source-prefix checks, fee/slippage/entry-age/exit and stop diagnostics, with exact-contract attribution separated from incompatible historical trades.
- `overhaul_core_year_extraction_validation_20260905_v1.json`: 1,524,744 evaluations and 1,846 sampled production rolling comparisons with no differences; all 1,404 daily file hashes verified.
- `overhaul_four_core_joint_marking_year_20260905_v1.json` and `overhaul_four_core_year_stability_20260905_v1.json`: 351-day current-contract lifecycle, shared sizing, costs, funding, chronological stability, concentration and marked-path diagnostics.
- SPCX midpoint and native-trade lifecycle sensitivities, official-candle parity comparison, SNDK same-input onset comparison and prospective source continuity. These do not support adding a HIP-3 route to V88.
- `overhaul_v88_four_core_readonly_preflight_20260905_v2.json`: all retained and retired assets flat/order-free; ledger reconciliation and prior-run archive valid; approval missing.
- `overhaul_v88_four_core_observer_audit_20260905_v1.json`: 12 successful unsigned polls, complete four-route coverage, zero intents and execution actions.
- `overhaul_four_core_size_comparison_20260905_v1.json`: declared 1×/2× deterministic capacity and same-fill sensitivity, with higher size deferred.

**Observed problem or opportunity:** V86 includes source-sensitive or economically unresolved HIP-3 routes and nonexecuting placeholders. V88 provides four fully executable routes and fewer data dependencies while preserving each retained entry, exit and sizing contract. It does not increase signal frequency artificially or add an implicit performance gate. HYPE remains the most consequential concentration and execution-fidelity investigation.

**Applicable market regime:** BTC requires its hourly liquidity sweep, reclaim, volume and trend conditions. ETH and SOL retain their range-onset and dual-timeframe entry context, with long and short execution respectively. HYPE retains compression/alignment onset and its existing opposite-recipe/soft-hold/hard-hold logic. Canonical 1m/5m/15m telemetry remains causal and reported. The historical result is mixed across calendar periods; these regimes are not a guarantee of current or future edge.

**Alternatives considered:**

| Alternative | Growth opportunity | Evidence/trade-off | Proposed disposition |
|---|---|---|---|
| Leave the stopped deployment unchanged | No trading exposure | No prospective fills or bankroll growth | Do not select |
| Resume unchanged V86 | Retains six executable routes | Includes the confirmed SNDK v3 onset mismatch and unresolved HIP-3 source economics | Do not select |
| V88, existing core sizing | Retains demonstrated executable mechanisms and current dollar capacity | Conditional historical support, sparse exact live outcomes, concentrated winners | Recommend with disclosed uncertainty |
| V88 mechanics at 2× caps and margin fractions | Twice the modeled dollar exposure | Same-fill scaling is arithmetic, not new edge or large-order fill evidence | Defer pending native higher-quantity execution validation |
| New noncrypto assets, new ML or new strategy family | Potential diversification or new return sources | No reviewed candidate currently clears source and economic validation; disabled legacy metalabel bundle has a library-version mismatch | Keep in research; no deployment |

**Proposed live change:** Use `configs/multi_asset_growth_first_5000_four_core_evidence_candidate_v88.toml`, fingerprint `06e90a0c59b4b767fd14a61f3927553fc00b3017405193170101531204761d5f`. Prior V86 fingerprint is `f454101eadaef46fd026c1a901bb7873bad61d7e7183a4c2e342e477e4e38733`; prior run is `bidirectional-live-1788585501070`.

| Asset / executable strategy | Side | Leverage | Margin fraction / notional cap | Effective stop / target | Exit and maximum hold |
|---|---|---:|---|---|---|
| BTC / `liquidity_sweep_long_1h_stop60_target60_v2` | Long | 20× | 5% / $2,500 | 60 / 60 bps | Fixed target or stop; 24h maximum |
| ETH / `eth_range_onset_long_dual_mtf_v2` | Long | 15× | 2% / $500 | 60 bps / none | Honor recipe exit; 48h maximum |
| SOL / `sol_range_onset_short_dual_mtf_v2` | Short | 15× | 2% / $500 | 60 bps / none | Honor recipe exit; 48h maximum |
| HYPE / `hype_breakout_compression_alignment_bidirectional_v2` | Long | 10× | 8% / $2,500 | 80 bps / none | Honor recipe; 8h soft hold while supported, 24h hard maximum |

Four positions maximum, one per asset; isolated margin; mainnet; 15-second polling and 14-day signal lookback. BTC entry age is at most 30 seconds; other routes at most 60 seconds. Opening IOC price distance remains 20 bps and exit IOC distance 100 bps. These distances are order-price constraints, not loss limits. Asset-side declarations preserve source support; the table lists the narrower executable directions. BTC's effective provider stop is 60 bps despite the legacy asset fallback being 80 bps.

At the observed $4,857.59 equity, all four capped entries total $6,000 notional, $441.67 initial margin (9.09% of equity), $5,500 long and $500 short. The declared simultaneous stop-plus-fee scenario is $46.18; adding 120 bps total adverse slippage and 20 bps funding gives $130.18 (2.68%). Gaps, failed exits, liquidation and changing notional can exceed these scenarios. Current venue depth covered each proposed entry at the inspected snapshot; it does not establish future fill availability.

**Expected upside:** Retain four mechanisms whose frozen conditional 351-day joint replay earned $811.20 nominal and $726.58 under higher costs on $4,857.59 initial capital. Portfolio net remained $309.16 / $226.34 after removing its largest trade, but became negative after removing its largest three. These are retrospective measurements, not expected returns. The practical technical upside is fewer unresolved source dependencies and accurate operational evidence. There is no verified profit forecast.

**Main risks and failure modes:**

- Selection and multiple-testing bias remain: historical data and directions were already reviewed during development. Chronological slices are not untouched OOS evidence; no newly fitted model or parameter set is claimed.
- HYPE alone loses money after largest-winner removal. Common crypto exposure and three long routes can lose together; the SOL short is not a guaranteed hedge.
- Eight modeled lifecycles touch tagged minute gaps; one SOL trade is terminally censored. Trade OHLC and funding marks are proxies for continuous venue marks and private fills.
- Sampled rolling parity can miss unsampled discrepancies. Selected native L2 windows do not reconstruct every stop/target/exit, partial fill or latency path.
- A resting stop is not a guaranteed fill price. IOC exits can fail. Protection, ownership and venue reconciliation require continuous observation.
- Historical cadence is sparse; zero signals over a short run does not establish a defect. Disabling valid prerequisites to create trades is not proposed.

**Validation completed:** Full offline Python suite: 7,997 passed, four network tests deselected, 27 warnings. The later source-bound monitor configuration check and related scope regressions passed six tests. Rust tests, Clippy with warnings denied and optimized build passed after Operations/Configuration fixes. Failing regressions preceded each substantive correction. The first real terminal capture exposed the remaining projection defects; corrected captures and final immutable acceptance evidence are recorded in the foundation review. CLI status returns `ok`; its disabled legacy metalabel mismatch is not used by V88. Public-wallet preflight constructed no execution client and required no signing key.

**Validation still required:** Explicit approval, fresh pre-arm reconciliation, verified final prestart bundle, exact-profile live startup, run-bound checkpoint/improvement monitor acceptance, and the first attributable native entry/protection/exit lifecycle for each retained route. Unrecoverable historical private-fill/mark gaps remain uncertainty, not something this proposal claims to have solved. Future data will test execution fidelity and economic repeatability; no paper/live fill is fabricated to satisfy that requirement.

**Success metrics:**

- Exact approved profile/source identity; four current provider rows; no orders outside the four configured sides; zero paper/shadow signing clients or orders.
- Healthy backend, current source/entry timestamps, intact venue-native protection whenever open, reconciled positions/orders, and complete attribution of intended signal, fill, costs, hold decision and exit.
- At each resolved lifecycle, compare measured fee, slippage, latency, funding and net to the frozen contract; distinguish execution deviations from ordinary trade losses.
- Report current and cumulative exact-contract net, drawdown, exposure, concentration, side/regime/time slices and missed/rejected paths. Review confidence as sample size grows; impose no unapproved P&L or trade-count abort rule.
- Publish source-bound improvement digests and append only material changes. Preserve closed hypotheses and name one next investigation. First priority is HYPE native entry/hold/stop/exit fidelity and winner concentration.

**Failure / rollback triggers:** A wrong profile/side, unknown or unprotected exposure, unreconciled venue state, broken causal inputs, rejected protection, or material implementation mismatch requires immediate notification and the existing fail-closed handling. Request operator-directed containment when order intervention is needed; retain known venue protection. No automatic economic retirement, retuning or rollback from several losses is added. Source rollback occurs only at a verified flat/order-free boundary, preserving ledgers and approvals. The prior source/config is retained; restoring V86 trading itself requires explicit approval because it restores retired routes and the prior SNDK behavior.

**Confidence level:** High for the observed technical defects, bounded corrections and present flat reconciliation. Medium for the conditional historical calculations under their stated assumptions. Low for future profitability. Native lifecycle discrepancies, materially different costs, new chronological outcomes or a source/identity mismatch would update these assessments.

**Explicit approval requested:** Authorize deployment of the exact tested source revision, transition V86 to this V88 fingerprint at the verified-flat boundary, start its four specified routes with both live-risk flags, and run the read-only checkpoint/improvement sidecars under [the transition and rollback procedure](../guides/cohort-live-transition-and-rollback-v88.md). This excludes the 2× sizing option, additional assets, new ML, manual strategy bypasses and automatic strategy changes. The later Human control clause in the user mandate requires this approval before changing the live universe or deployment. No operator approval has been received or recorded.

Venue mechanics were cross-checked against the official [fee schedule](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees), [margining description](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining) and [order types](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types). The account-specific fees and current depth used here come from the bound preflight, rather than an assumed universal fee tier. Raw HTML responses and extracted text are preserved locally; the original download filenames ending in `.md` contain HTML, as recorded by their response content type.
