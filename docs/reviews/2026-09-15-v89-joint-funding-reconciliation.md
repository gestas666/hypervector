# First joint SPCX/SNDK funding boundary reconciled

The first recorded funding payment on the current SPCX long reconciles independently alongside the inherited SNDK short. All **260 sampled position records** agree with their entry, fee and funding cash arithmetic. This validates one new live accounting boundary; it is not a profitability result or a reason to change the strategy.

## Evidence and findings

The frozen checkpoint cutoff is **September 15, 2026 at 20:28:40.176510 UTC**. The study retains 269 selected records from three ledgers, with exact byte offsets, lengths and hashes. Every selected DuckDB row matches its native ledger record, and the byte ranges were independently re-read after capture. No new account/API request was made.

| Check | SPCX long | SNDK short |
| --- | --- | --- |
| Entry order | 546010609566 | 545845583477 |
| Entry | 3.47 at 144.01 | 0.326 at 1531.7 |
| Reported leverage | 10x isolated | 10x isolated |
| Entry fee | $0.043175 | $0.043142 |
| Funding at 20:00:00.033 UTC | **−$0.003112** | **+$0.003119** |
| Observed net-collateral change | −$0.003112 | +$0.003119 |
| Active-lifecycle funding through cutoff | −$0.003112, one receipt | +$0.012831, four receipts |
| Position records checked | 130 | 130 |
| Maximum accounting residual | $0.000000 | $0.000000 |

Net collateral here means the recorded `margin_used_usd` minus recorded unrealized PnL. The tested identity is entry notional divided by the observed leverage, minus the entry fee, plus the applicable recorded funding cash. This is an empirical identity for these isolated-position samples, not a general definition for every venue margin configuration.

SNDK's entry belongs to the preceding run, `bidirectional-live-1789482753345`. Its four funding rows belong to current run `bidirectional-live-1789497016143`; the current checkpoint attributes all four to that same open lifecycle. SPCX's entry occurred after the 19:00 funding timestamp, and its first captured funding receipt is at 20:00. No missing or doubled funding contribution was found in this selected population.

The two 20:00 payments share the **same venue timestamp and the same zero transaction hash**. Their asset identity keeps them distinct. Their combined cash effect is only **+$0.000007**, so a portfolio-total check alone would be weak evidence. Each asset's cash change was checked separately.

One position observation per asset falls between the recorded settlement timestamp and the later local funding-publication time. Those two transport-interval observations are explicitly classified against the fixed pre/post-settlement cash states. They are not used to claim instantaneous visibility. The two surrounding funding-cursor records are contiguous and include the settlement timestamp; neither records an execution action.

## Independent validation and self-correction

The Decimal validator rejects **11 deliberate corruptions**: missing SPCX funding, missing inherited SNDK funding, a duplicate record, sign error, amount error, cross-asset attribution, entry-fee error, margin error, leverage error, checkpoint funding error and discontinuous funding cursor. A second network-denied run reproduces the complete accepted result and all rejected controls.

Separate DuckDB arithmetic agrees exactly on **1,300 fields across all 260 positions**, rather than merely comparing the final residual. This caught an error in the new analysis script: automatically inferred JSON timestamps were cast to `TIMESTAMPTZ` in the local timezone. The inferred/cast path shifted the tested clock by **+4 hours** in New York and **−9 hours** in Tokyo. Explicit extraction of the original offset-bearing timestamp is invariant across UTC, New York and Tokyo and is used in the final SQL. The earlier parser and timezone failures remain retained as failed evidence, not successful checks.

A scoped inspection of current installed code found that the book/trade importer constructs timestamps from integer epochs, the cohort importer parses explicit offsets, and the inspected historical metrics query does not use timestamp arithmetic. The three report templates provide source-loading queries without the problematic cast. This inspection supports no installed execution/import change; it is not a retrospective audit of every archived analysis.

## Decision, limitations and next action

**Recommendation / why now:** retain the current funding attribution and record this first jointly observed long/short HIP3 settlement as bounded live acceptance. New SPCX funding and SNDK restart recovery made the accounting boundary observable.

**Applicable regime / proposed live change:** accounting consistency applies independently of market regime. No live strategy, asset, route, parameter, leverage, sizing, risk or execution change is proposed or performed.

**Expected upside / alternatives:** exact per-asset validation can detect omissions hidden by nearly offsetting portfolio cash. A total-only comparison would miss that distinction; repeating old entry or strategy-filter studies would not test this new boundary.

**Risks and limits:** the 260 samples are repeated observations around one settlement hour, not 260 independent economic outcomes. The source is recorded backend/venue fields and local ledger bytes; the venue's underlying funding-price calculation was not reconstructed. Offsetting external collateral changes are not independently excluded. Transport timing prevents an instantaneous-accounting claim. No inference about edge, future return or stable funding income follows.

**Success / falsifiers:** exact source identity, asset-specific funding identity, causal timing, contiguous cursors and agreement of collateral and checkpoint costs. Contradictory raw venue evidence, an unaccounted cash flow, changed position ownership or failure of the same calculation on a later boundary would reopen the corresponding conclusion. Confidence is high within the captured population and low for extrapolation.

**Approval:** no new approval is needed for this read-only accounting audit. No financial process was started, stopped, restarted or signalled.

**Next highest-value investigation:** a new native entry, exit, protection change or fault in the current run. A separate read-only watcher starts after existing ledger evidence and waits up to two hours for those events or a backend identity change. It cannot place orders, change settings or control the financial backend. The startup-input capture remains pending the next normal user-controlled start. Prospective outcome seals remain unopened.

All source, fixed inputs, SQL, rejected attempts, reproduction and checks are under `data/logs/research/bidirectional_cohort/v89_joint_funding_20260915_v1/`.
