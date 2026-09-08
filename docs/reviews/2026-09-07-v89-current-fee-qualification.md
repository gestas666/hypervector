# V89 current HIP-3 fee qualification

Unsigned venue information captured between **2026-09-07 22:12:57 and
22:12:59 UTC** shows growth mode enabled for SPCX, SNDK and Brent, each with a
deployer fee scale of 1.0. The account has a 4.5 bps base taker rate and a 4%
active referral discount. Under the existing formula, without an aligned-quote
discount, that produces **0.864 bps taker fees per side** for each addition.

Confidence is high for this captured metadata and the conditional calculation.
The observation supports the current replay's 0.9 bps assumption as slightly
conservative for this snapshot. It does not reconstruct fees over the full
historical window or establish the fees of future fills.

## Method and verification

Research source `49cb1e4` sends only `userFees`, `meta` for `xyz`, and `perpDexs`
to the mainnet `/info` endpoint. It loads only the public wallet identity using
the existing wallet-only environment loader. No signing client, exchange
request, order, account mutation or restart is involved. The account identity
is hashed in the report; its value and signing credentials are not printed.

The existing strict metadata parser selects the exact market and dex, while
the existing preflight helper applies the
[official fee formula](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees),
checked September 7. The calculation is:

`4.5 bps × 2 deployer scale × 0.1 growth scale × 0.96 referral scale = 0.864 bps`.

| Market | Growth mode | Deployer scale | Projected taker fee per side |
| --- | --- | ---: | ---: |
| xyz:SPCX | Enabled | 1.0 | 0.864 bps |
| xyz:SNDK | Enabled | 1.0 | 0.864 bps |
| xyz:BRENTOIL | Enabled | 1.0 | 0.864 bps |

All three report collateral token index 0. The existing aligned-quote status
remains `unresolved_conservative_false`; this observation does not claim that
discount is unavailable. An applicable discount could reduce the projected
taker rate further. Realized fills remain the authority for fees actually paid.

The focused fee-parser, fee-model and environment-loader suite passes **15
tests** without network calls. Eight source/response fingerprints match the
captured report. All three native responses were strictly parsed, and the
script passes Ruff and the project file/function limits.

Evidence is retained under the original checkout's
`data/logs/research/bidirectional_cohort/v89_current_fee_evidence_20260907_v1/`,
including the three response objects and `report.json`. Validation output is
`v89_current_fee_validation_tests_20260907_v1.log` in the parent folder.

## Decision and next investigation

Retain the current cost qualification. The full-fee scenario in the
[shared-account review](2026-09-07-v89-seven-asset-shared-marking.md) is an
adverse alternative, not the fee state observed now. Its negative result
remains reported. Do not rerun the entire historical screen using today's
referral rate or growth mode without historical evidence for those inputs.

This narrows one uncertainty without changing a strategy, sizing policy or
live configuration. Doing nothing leaves current fees unresolved; replacing
historical fees with today's snapshot introduces an unsupported time assumption.
Preserving both the frozen stress scenario and the new observation retains
traceability. No approval or live change is proposed by this report.

The **single highest-value next investigation is native source and lifecycle
fidelity**, particularly whether differing candle histories alter eligible
entries, exits or stops under the current recipes. Use retained source pairs
and explicitly bounded substitution experiments; neither feed may be selected
for better PnL. Naturally occurring fills should separately reconcile actual
fees, slippage, latency and funding when they become available.

Changed growth mode, deployer scale, account tier, referral eligibility or
unreconciled observed fill fees would update this qualification. Success means
source-matched causal decisions and explained cashflow differences, not a
prescribed return. Publication rollback preserves this snapshot and appends a
superseding observation. Future profitability and the overall goal remain
unproven.
