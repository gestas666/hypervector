# SNDK ambiguous exit: conditional shared-account replay

The primary hypothetical stop exit reduces the August 7 SNDK loss from
**$26.36 to $13.79**, increasing full 48-day modeled portfolio net from
**$96.12 to $108.68**. The later 20-day loss remains **$87.44**. This resolves
the portfolio effect of one historical modeling assumption; it does not repair
later performance or recover money lost in the live account.

Confidence is high in the recorded samples, input identities and reconciled
arithmetic; medium in the conditional exit-model interpretation; low in actual
fill attainability or future profitability. A changed input, failed replay,
earlier contradictory marks or incompatible sizing would update the respective
conclusion. The 144 scenarios reuse one unique event and are not 144 independent
performance observations.

## Frozen scope and observed event

Hypothesis `v89_noncrypto_ambiguous_exit_event_replay_20260908_v1` was registered
in source commit `3c7ab88` before the additional price/book acquisition. The
accepted ambiguity inventory found only SNDK long `xyz:SNDK|20`, August 7,
among 99 SNDK/SPCX lifecycles in every original source/cost/clock case.

The complete modeled entry window is August 7 **13:00–13:46 UTC**. A new
13:00–13:29 prefix joins the previously verified suffix. Its complete bounded
requests contain 580 price rows and 3,781 books in one and four pages
respectively. The combined half-open window contains **920 marks and 6,007
books**. There are no missing marks/oracles; 23 midpoint values are missing.
Maximum gaps including boundaries are 3.457 seconds for marks and 1.500 seconds
for books. Complete pagination does not prove continuous vendor observation.

Every cost case first contacts its stop at **13:32:22.136 UTC**, mark 1282.2;
the preceding observed safe mark is 1286.6 at 13:32:19.121. The acquired prefix
contains no earlier observed stop contact. None of the cost-specific touches
is left-censored at the first sample. Liquidation contact is observed at
13:40:07.218 for nominal/adverse and 13:40:04.087 for full-fee stress, whose
entry fee changes the original isolated-margin liquidation threshold.

At each of 0, 1, 5 and 30 seconds after the observed stop contact, the model
uses the first book at or after assumed order arrival. Each book has full
closing capacity at the original quantity before the first sampled liquidation
contact. Both raw VWAP and VWAP with additional inherited slippage are retained.
These are hypothetical fills conditional on the original modeled entry and a
resting stop, not reconstructed client arrival or actual venue execution.

For the primary first-recorded/adverse/recorded-clock case, arrival is
13:32:23.136 and the selected book is 13:32:23.500, a 364-ms observation lag.
The preceding book is retained separately. Selling the original
0.3792980274511258 SNDK gives visible VWAP 1282.8. Adding the registered 5.5-bps
friction stress yields 1282.09446, exit fee $0.043766631 and net **−$13.792866947**.
The $0.045 entry fee is unchanged. No hourly funding boundary lies after the
13:00 entry and through this exit; target funding remains exactly zero.

## Full portfolio effect

All 18 original archive/first/latest × cost × exit-clock baselines reproduce
their trade lists, reports, sizing checks, equity paths and independent daily
attribution exactly. The full concurrent account is then replayed for all
eight exit scenarios per baseline: **144 conditional paths**. Only the target
lifecycle changes; other entries, exits, quantities and funding retain their
original contracts. The event-resolved exit does not receive a second 15-minute
shift in late-clock scenarios. The next SNDK entry remains at 14:00 UTC.

First/latest recorded-source results below agree; ranges retain every declared
delay and price assumption. Other source and clock cases remain in the report.

| Cost contract | Original full portfolio net | Conditional portfolio net range | Conditional SNDK target net range |
|---|---:|---:|---:|
| Nominal | +$197.42 | +$210.04 to +$213.01 | −$13.73 to −$10.76 |
| Adverse slippage | +$96.12 | +$108.46 to +$111.57 | −$14.02 to −$10.91 |
| Full HIP-3 fee stress | −$33.18 | −$21.28 to −$18.17 | −$14.82 to −$11.71 |

Across all 144 cases, net improves by **$11.899832–$15.594401**. The full-fee
recorded portfolio remains negative. The favorable 30-second observation reflects
the observed rebound and is not evidence that deliberate extra latency helps.
Additional slippage may overlap impact already included in a depth VWAP; it
is a declared stress, not an estimated second independent cost.

The primary first 28-day net changes from $183.557816 to $196.121006. The later
20-day net stays −$87.438147, with only floating-point residuals below 3.2e−14.
All daily/asset change is confined to August 7 SNDK; maximum other-cell residual
is 2.85e−14. Higher carried equity is not improved later-period incremental PnL.
Primary close-mark percentage drawdown changes from 3.906405% to 3.896780%,
while maximum dollar drawdown stays exactly $198.691884. The denominator changes
with the additional carried equity; the later dollar decline is unchanged.

Every conditional case preserves configured cap compatibility, with no notional
mismatches. Margin, long/short/gross notional, unreserved cash, daily attribution
and all marked path rows are recomputed. These remain completed-candle and
adverse-intrabar proxies for risk. They do not measure actual intrabar account
equity or validate execution capacity for other trades.

## Verification and data correction

Research source is **`dccce93d7c71d5777f1868e14a08cf54d0cca013`**. The three
original shared-model research helpers are copied byte-for-byte from their
registered source. Live Python, configuration and process state are unchanged.

**79 offline tests pass**; the new pure exit module covers 79/79 statements and
24/24 branches. Tests cover long/short direction, missing or inadequate books,
latency boundaries, liquidation precedence, missing marks, funding cutoffs,
immutable replacement, same-asset collision, boundary conflicts and daily
attribution. Coverage does not describe the entire project or all archive I/O.
Ruff and the new files' function/file, annotation and docstring checks pass.

An independent standard-library audit imports no implementation modules. It
checks 487 source/output identities, 12 first-contact fields, 24 Decimal book
and cost calculations (120 numerical fields), and 144 portfolio entry/funding
contracts. Maximum Decimal discrepancy is 2e−13. A separate vectorized audit
checks drawdown, terminal cash, margin/notional identities and unchanged trades
over **9,999,696 path rows** across all 144 cases.

The source archive's **5,125 Git members** match their blobs. Archive replay
reproduces all 18 controls and 144 conditional cases. All **55 baseline files**
and **433 conditional event/result/path/daily files** are byte-identical. The
aggregate conditional report also agrees exactly after normalizing only its
output-directory evidence keys. All 36 baseline Parquet hashes are reverified.
The independent vectorized audit's largest numeric error is 9.1e−13.

The prefix initially failed raw/publication comparison because a raw `null`
midpoint becomes `NaN` in Parquet. The new research-only reader preserves
nullable semantics before exact comparison; it does not impute a price or
modify the original archive. A regression fixture covers this case. Earlier
failed test runs are retained separately from the passing validation.

## Disposition and next investigation

| Option | Evidence / trade-off | Disposition |
|---|---|---|
| Preserve original liquidation-first attribution | Reproducible control; coarser event sequence | Retain as baseline |
| Retain conditional event-resolved sensitivity | Quantifies a $11.90–$15.59 historical difference | Retain with fill and sampling limitations |
| Change live sizing or exits from this event | One known historical loss; later weakness unchanged | No live proposal |
| Test a fixed allocation benchmark | Current caps concentrate $2,500 each in BTC/HYPE versus $500 in five other routes | Next registered research comparison |

Next is [the fixed equal-cap allocation benchmark](../plans/2026-09-08-v89-equal-cap-allocation.md),
`v89_equal_cap_allocation_benchmark_20260908_v1`. Compare current caps with
$7,500 / 7 per route, preserving total configured notional, all routes and
leverage. This is not equal-risk sizing; potential margin and execution needs
change. Retain original and event-adjusted controls, every cost/source case and
the explored chronological split. Fit no weights and do not promote an in-sample
winner. The sealed September 8–22 experiment remains unopened.

Evidence: `data/logs/research/bidirectional_cohort/v89_noncrypto_ambiguous_exit_event_replay_20260908_v1/`.
