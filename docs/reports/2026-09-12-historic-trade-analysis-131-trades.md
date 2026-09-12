# Historical portfolio evidence: 131 closed trades across 20 profiles

Document: `DOC-HV-20260912-HISTORIC-131-ANALYSIS-V3`  
Revised: September 12, 2026  
Status: source-bound numerical report; causal mechanisms and future profitability remain unproven.

High confidence in the bounded arithmetic below: the frozen checkpoint archive reconciles with 131 closed-order lifecycles and 375 fill events. Entries span August 2–September 11 UTC; closures span August 3–September 11. This population spans 20 profile fingerprints. It is not a single-policy trial, current account balance, or valuation of open positions.

The [independent validation review](/Users/gestas/Prototypes/hypervector-v89-report-audit-20260912/docs/reviews/2026-09-12-v89-historic-report-validation.md) examined original V1 report SHA-256 `c5e2de7d8c7efadcb34c118fce3015c15edb5e9c548db0e644bbc83b3c7f964c`. That hash identifies the reviewed report, not the review itself. V3 corrects the subsequent V2 revision, preserved in the [backup](/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_report_corrections_20260912_v1/backup/report-v2.md). The [source boundary](/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_report_corrections_20260912_v1/source_boundary.json) records both identities and authenticates fourteen original evidence references.

The primary checkpoint is `v89_hourly_chart_acceptance_20260911_v1/checkpoint.json`, under `.audit.portfolio_archive`; its frozen SHA-256 is `6987c92bb561953f844b9c416455f02e28e952a0f0f6af8ac4a606e0118275a5`. Its archive identity is `0195830bb1db9df19ff83b0f36d8472aa082b9ec2dd84cf5ef32bef4e0dbd678`. Frozen rows, queries and checks are retained in the [original audit evidence](/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_historic_report_validation_20260912_v1).

## Observed cash results and denominators

- Closed trades: **131**, with **50 wins**, **81 losses**, zero breakeven; win rate **38.17%**.
- Net realized PnL: **-$379.09**; gross market PnL **-$298.59**; fees **$83.74**; settled funding **+$3.24**. The cash identity is `net = gross - fees + funding`.
- Summed entry margin: **$16,299.04**; `100 × net / summed entry margin = -2.3258%`. Margin can be reused across trades. This ratio is neither time-weighted account return nor a compounded return curve.
- Profit factor: **0.475**, calculated as positive net trade PnL divided by the absolute negative net trade PnL.
- Maximum closed-sequence drawdown: **$394.06**. This uses ordered cumulative closed-trade net PnL and its running peak beginning at zero; it excludes open-position excursions and is not marked-to-market account drawdown.
- Largest winner: **$62.09**. Subtracting it from the observed sum gives **-$441.18**; this is a concentration diagnostic, not an alternative executable history.

Observed gross PnL was negative before fees. Fees increased the loss and net funding partly offset it. These identities do not establish negative future expectancy or identify a regime, entry or execution cause. Confidence in such causal extrapolation is low.

## Current-profile attribution

Only **seven** archived closed trades match configured V89 profile fingerprint `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`; they total **-$49.11**, with zero wins. Eleven rows share currently configured strategy/symbol names, but name overlap does not establish full-contract equivalence. The seven-row sample is too small to establish current expectancy.

The inspected [V89 configuration](/Users/gestas/Prototypes/hypervector/configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml) has SHA-256 `696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`. Both legacy BTC short variants and the named old ETH/SOL range and SPCX gap routes are absent. Configured short-capable routes remain; V2's instruction describing zero unhedged short allocations did not match this configuration. Configuration is not proof of a running process or current exposure.

## Directional attribution

Fees are shown as positive costs and funding as signed cash. The revised direction rows are independently validated against the archived lifecycles; V2's gross/fee attribution was incorrect.

| Direction | Trades | Wins | Losses | Win rate | Gross PnL ($) | Fees ($) | Funding ($) | Net PnL ($) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Long** | 77 | 30 | 47 | 39.0% | -$185.53 | $41.35 | -$1.54 | -$228.42 |
| **Short** | 54 | 20 | 34 | 37.0% | -$113.06 | $42.39 | +$4.78 | -$150.67 |
| **Total** | 131 | 50 | 81 | 38.17% | -$298.59 | $83.74 | +$3.24 | -$379.09 |

The original 1,311 scalar checks cover total, strategy and strategy/asset checkpoint projections. They do not include nested direction projections. V3 separately validates the 24 printed direction/total cells, including funding, in addition to the 238 printed strategy/asset cells below. Printed values are rounded independently.

## Strategy and asset results

These 34 rows retain the verified archive values and ordering. Small profitable groups are observations selected from many historical variants; they are not validated replacement strategies.

| Strategy ID | Symbol | Trades | Win% | Net PnL ($) | Gross PnL ($) | Fees ($) | Profit Factor | Max DD ($) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2` | `xyz:BRENTOIL` | 7 | 42.9% | **+$20.62** | +$21.78 | $0.89 | **2.06** | $18.71 |
| `hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2` | `xyz:SNDK` | 2 | 50.0% | **+$18.30** | +$18.35 | $0.25 | **3.93** | $6.24 |
| `hype_breakout_compression_alignment_bidirectional_v2` | `HYPE` | 2 | 50.0% | **+$6.34** | +$15.31 | $8.57 | **1.14** | $46.43 |
| `hip3_spcx_cash_session_fresh15_long_v4` | `xyz:SPCX` | 1 | 100.0% | **+$5.94** | +$5.99 | $0.06 | N/A | $0.00 |
| `hip3_breakout_pressure_sp500_spcx_bidirectional_v1` | `xyz:SPCX` | 2 | 50.0% | **+$4.23** | +$4.20 | $0.03 | **7.97** | $0.61 |
| `hulk_expansion_bidirectional_tuned_v2` | `HYPE` | 2 | 100.0% | **+$2.18** | +$2.27 | $0.09 | N/A | $0.00 |
| `hip3_swing_ha_sndk_gold_brent_bidirectional_v1` | `xyz:BRENTOIL` | 1 | 100.0% | **+$2.05** | +$1.92 | $0.01 | N/A | $0.00 |
| `hip3_swing_ha_sp500_spcx_bidirectional_v2` | `xyz:SPCX` | 4 | 50.0% | **+$1.00** | +$1.09 | $0.05 | **1.79** | $0.66 |
| `hulk_expansion_bidirectional_tuned_v2` | `SOL` | 2 | 50.0% | **+$0.68** | +$0.78 | $0.11 | **205.78** | $0.00 |
| `hulk_expansion_bidirectional_tuned_v2` | `BTC` | 4 | 50.0% | **+$0.16** | +$0.25 | $0.08 | **1.90** | $0.18 |
| `hype_breakout_onset_bidirectional_v1` | `SOL` | 9 | 44.4% | **+$0.08** | +$0.68 | $0.58 | **1.03** | $1.88 |
| `hip3_breakout_pressure_sp500_spcx_bidirectional_v1` | `xyz:SP500` | 2 | 50.0% | -$0.06 | -$0.04 | $0.02 | 0.26 | $0.08 |
| `hypervelocity_source_follow_bidirectional_5m_v1` | `BTC` | 5 | 60.0% | -$0.10 | -$0.01 | $0.09 | 0.70 | $0.29 |
| `hype_breakout_onset_bidirectional_v1` | `BTC` | 8 | 50.0% | -$0.17 | $0.00 | $0.17 | 0.53 | $0.28 |
| `hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1` | `xyz:BRENTOIL` | 2 | 50.0% | -$0.23 | -$0.19 | $0.03 | 0.66 | $0.69 |
| `hype_breakout_onset_bidirectional_v1` | `ETH` | 7 | 42.9% | -$0.40 | -$0.25 | $0.15 | 0.49 | $0.57 |
| `hype_breakout_onset_bidirectional_v1` | `HYPE` | 14 | 50.0% | -$0.97 | -$0.38 | $0.60 | 0.72 | $3.24 |
| `hip3_swing_ha_sndk_gold_brent_bidirectional_v1` | `xyz:GOLD` | 3 | 0.0% | -$1.20 | -$0.78 | $0.39 | 0.00 | $1.20 |
| `hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1` | `xyz:SNDK` | 2 | 0.0% | -$1.34 | -$1.32 | $0.03 | 0.00 | $1.34 |
| `hip3_swing_ha_sndk_gold_brent_bidirectional_v1` | `xyz:SNDK` | 2 | 0.0% | -$1.69 | -$1.67 | $0.03 | 0.00 | $1.69 |
| `hourly_donchian_8_4_atr20_bidirectional_v1` | `xyz:BRENTOIL` | 1 | 0.0% | -$2.29 | -$3.27 | $0.09 | 0.00 | $2.29 |
| `hourly_band20_reentry_atr20_bidirectional_v1` | `xyz:SPCX` | 2 | 0.0% | -$7.34 | -$7.19 | $0.17 | 0.00 | $7.34 |
| `zec_donchian_20_10_atr20_long_v1` | `ZEC` | 1 | 0.0% | -$13.20 | -$12.78 | $0.41 | 0.00 | $13.20 |
| `hype_breakout_compression_pullback_bidirectional_v1` | `HYPE` | 2 | 50.0% | -$13.85 | -$5.74 | $8.57 | 0.72 | $49.60 |
| `hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3` | `xyz:SP500` | 8 | 37.5% | -$14.30 | -$12.63 | $2.93 | 0.36 | $22.43 |
| `range_onset_bidirectional_v1` | `ETH` | 2 | 0.0% | -$15.55 | -$10.24 | $4.34 | 0.00 | $15.55 |
| `eth_breakout_precompression_pullback_bidirectional_v1` | `ETH` | 17 | 29.4% | -$20.29 | -$11.10 | $8.93 | 0.70 | $47.68 |
| `hourly_donchian_20_10_atr20_bidirectional_v1` | `xyz:SNDK` | 3 | 0.0% | -$21.77 | -$21.48 | $0.26 | 0.00 | $21.77 |
| `range_onset_bidirectional_v1` | `SOL` | 1 | 0.0% | -$22.35 | -$17.27 | $4.31 | 0.00 | $22.35 |
| `liquidity_sweep_long_1h_stop60_target60_v2` | `BTC` | 3 | 33.3% | -$26.09 | -$16.89 | $9.20 | 0.50 | $52.36 |
| `hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3` | `xyz:SPCX` | 3 | 33.3% | -$45.72 | -$43.41 | $2.58 | 0.32 | $67.08 |
| `hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1` | `xyz:SPCX` | 2 | 0.0% | -$55.59 | -$54.45 | $1.14 | 0.00 | $55.59 |
| `hulk_expansion_short_tuned_v2` | `BTC` | 3 | 33.3% | **-$63.04** | -$48.83 | $15.70 | 0.50 | $125.14 |
| `hulk_expansion_short_robust_v3` | `BTC` | 2 | 0.0% | **-$113.13** | -$101.31 | $12.91 | 0.00 | $113.13 |

## Supported findings and unresolved explanations

**Legacy BTC short concentration.** Five trades in `hulk_expansion_short_robust_v3` and `hulk_expansion_short_tuned_v2` total **-$176.17**, or **46.47%** of the archive's net deficit. Three have protective-stop exits, one a target exit and one a profit-floor exit; one trade is positive-net. Those exact variants are already absent from V89. Counter-trend causality, hedging benefit and the performance of different current short routes are not identified by these observations.

**Named earlier entry families.** The 22 trades in the cited old ETH pullback, ETH/SOL range and SPCX gap groups have mean elapsed entry-to-final-exit duration **400.09 minutes**. Their 14 protective-stop trades have mean **135.22 minutes**, median **65.81**. Neither population reproduces the earlier 32-minute claim. No authenticated source supplied here establishes that number for a different live run either, so that attribution is removed. Low win rates and exit labels alone do not establish premature-breakout causality.

**Historical period change.** A separate previously opened simulation reports earlier-period **+$103.59** and later-period **-$137.03**, with modeled SNDK long deterioration contributing substantially. These are simulation populations, not additions to the 131 closed live/cohort trades. The study does not identify opposing higher-timeframe regime as the cause, establish that momentum disappeared within an hour, or validate a regime veto or profit lock. Profitable modeled SNDK longs reaching the hold limit is an exit-label observation, not an exclusive causal explanation of profits. See the frozen `2026-09-10-v89-historical-period-drivers.md` in the original audit inputs.

**Entry slippage and acknowledgement timing.** The cited compatible-history slice contains **three SNDK entry fills from two orders**, with unweighted mean observed entry slippage **15.3821 bps**. It contains **zero SPCX entry fills**. Six fill-associated acknowledgement observations average **1209.17 ms**, maximum **1732 ms**, but represent **five unique orders** because one acknowledgement repeats across fills. That mean weights fill-associated observations; it is not the mean of five independent order measurements. Signing, transport, processing, price drift and book movement are not separated. These samples do not justify assigning 15 bps to every HIP-3 asset, assuming a transport mechanism removes slippage, or claiming a sub-600 ms execution target has been achieved.

**Positive historical subgroups.** The exact Fresh15s archive identity is `hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2`: nine trades, four wins, five losses, **+$38.921444** net on **$1321.653608** summed entry margin (**+2.944905%**), PF **2.52**. Its largest winner is **$31.685938**, about **81.4% of net**; subtracting it leaves **+$7.235506**. The archived predecessor, a later defective provider and its corrected candidate are different contracts. None is interchangeable with the current hourly SNDK provider merely because asset or family names overlap.

`hulk_expansion_bidirectional_tuned_v2` has eight trades, five wins, three losses and **+$3.020411** net. Its PF **17.41** uses only **$0.184067** of absolute losing-trade net PnL. Both groups warrant bounded investigation; their samples and selection across variants provide low confidence in prospective profitability.

**Separate annual simulation.** The four-core, 351-day model has **108 trades**, net **+$811.20** at **2.5 bps per-side** modeled slippage and **+$726.58** at **5.5 bps per side**. Removing each case's three largest winners gives **-$46.35** and **-$127.15** respectively. Each case has eight gap-affected trades and one terminal-censored trade. These are concentration diagnostics on already-opened data, with venue fills, marks, quotes, rounding and arrival delays incompletely qualified. They do not validate a replacement live portfolio. The separately referenced 177 trades were accepted/closed trades in one account case of a 48-case comparison, not 177 independent cases.

## Applied corrections and investigation status

| Item | Evidence-backed status | Applicable next action |
| :--- | :--- | :--- |
| Historical report arithmetic and population | Revised here; pooled profiles, exact current profile and simulations are distinct | Re-run the source-bound report validator before reuse |
| Audit command success on wrong printed cells | Corrected; mismatched strategy or direction cells now cause nonzero failure after diagnostic files are retained | Keep the failure contract and synthetic regressions |
| Old named roster exclusions | Already present in the inspected V89 configuration | No duplicate purge or disabling different current variants |
| SNDK entry-time context | [Completed for 47 historical entries](/Users/gestas/Prototypes/hypervector-v89-sndk-gap-20260912/docs/reviews/2026-09-12-v89-sndk-entry-context.md); causal and prospective conclusions remain limited | Do not repeat the feature search or fit new thresholds on those outcomes |
| Endpoint timing sensitivity | [Completed](/Users/gestas/Prototypes/hypervector-v89-sndk-gap-20260912/docs/reviews/2026-09-12-v89-sndk-endpoint-gap.md); a 15-minute separation weakened the primary raw association | No entry delay, direction reversal or exit rule selected from that finding |
| TUI, recovery and market-data session reuse | [Technical fixes installed](/Users/gestas/Prototypes/hypervector/docs/reviews/2026-09-12-v89-technical-updates-installed.md) | Session-reuse measurements concern candle acquisition, not proof of faster order submission or better PnL |
| HIP-3 history and candle cadence | [Importer and research-cache guard installed](/Users/gestas/Prototypes/hypervector/docs/reviews/2026-09-12-v89-hip3-candle-history.md) | Preserve exact market family and source lineage |
| Native/archive SNDK differences | [Trade-level diagnostic completed](/Users/gestas/Prototypes/hypervector-v89-sndk-trade-source-audit-20260912/docs/reviews/2026-09-12-v89-sndk-trade-source-audit.md); 3607 matches reproduce three selected archive candles | Next measure unchanged-strategy decision sensitivity across the fixed seven-day overlap |

The highest-value next research step is the fixed native/archive decision-sensitivity comparison, with identical warmup, the configured hourly SNDK mechanism and unchanged parameters. The newly verified trade-source evidence justifies this narrower practical-impact question; repeating the earlier entry-context or source-propagation searches without new evidence does not. Sensitivity outcomes have not yet been computed.

## Recommendation and boundaries

**Recommendation:** use this corrected report and strict numerical validator for decisions; retain the configured strategy contract while the fixed source-sensitivity question is investigated. **Why now:** V2 still combined incorrect direction attribution with unsupported operational instructions. **Expected benefit:** more reliable attribution and explicit failure on wrong tables; no quantified return improvement is claimed.

**Alternatives:** leaving V2 unchanged preserves misleading claims; adopting its combined roster, cost and regime changes would test a different unvalidated system. **Proposed live change:** none from this report. A blanket 15 bps replacement, maker chasing, different submission transport, new regime vetoes, profit locks and new PF/drawdown/trade-count acceptance thresholds are not selected here. These may be separately scoped research hypotheses where evidence supports them. No implicit strategy or performance gate is introduced.

**Validation:** the frozen population and source hashes, independent SQL/Decimal cash, every printed strategy and direction cell, current config identity, and deliberate wrong-cell command failure. **Remaining validation:** practical source sensitivity and any separately proposed strategy's exact-contract evidence with realistic costs, chronological comparisons and explicit failure criteria. **Confidence:** high in the bounded report corrections; low in future profitability or the unverified causal mechanisms. **Failure/rollback:** reject a changed source identity, unreconciled arithmetic, lost failure status or unintended runtime change; restore the preserved V2 only if needed for document recovery, retaining its invalidation notice. No new approval is required for these report/validator corrections under the user's September 12 request; this document is not live deployment approval.

The audit's account observation at **2026-09-12 10:41:11 UTC** recorded a 0.306 SNDK short, a full-size reduce-only stop at **1669.9**, and unrealized PnL **-$0.3978**. This is a dated, sequential observation, not current account state. This report does not refresh the account or start trading. The two prospective outcome seals remain unopened.

A corrected authenticated source population, a failed independent replay or an arithmetic error would update the numerical conclusions. Exact-contract entry-time evidence and predeclared comparative results could update the causal hypotheses. The report does not establish broad live readiness or future profitability.
