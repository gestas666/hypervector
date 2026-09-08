# Independent SPCX indicator reconstruction

Independent Decimal calculations reproduce the bands behind both observed SPCX
long entries. Their crossing composition differs: price movement accounts for
90.17% of the first lower-band crossing and 6.78% of the second. Thirteen ATR
updates after the first recorded hourly value also reconcile. The original
startup ATR remains unverified because its complete input snapshot is absent
from the preserved chart ledger. Confidence is high for the band arithmetic and conditional ATR
recurrence, and unresolved for the original ATR initialization.

This is an observation and research audit. Execution authority is `none`; no
strategy, asset roster, sizing, leverage, risk control, execution setting, or
deployment changed. All times below are UTC.

## Inputs and independent calculation

The deployed provider builds its 15-minute input from a retained one-minute
feed. The chart publisher retained only the final 360 completed minute candles
at startup. The subsequent candle records extend that prefix but cannot supply
the missing original warmup history.

The reconstruction combines the previously frozen 4,320 SPCX minute candles
from September 4–6 with a newly captured 2,700-candle public response covering
September 6 at 12:00 through September 8 at 09:00, exclusive. The combined
history contains exactly 6,300 ordered minute candles without gaps or duplicates.
The two sources agree across all OHLCV fields on their 720 overlapping minutes.
The new response also agrees with all 1,166 overlapping minute candles in the
frozen live ledger.

A separate 420-bar native 15-minute response agrees on close, low, and volume
within the stated numeric tolerance. It differs from minute aggregation in
17 opens and one high, with maximum absolute price differences of $0.04 and
$0.01 respectively. The earlier three-day parity report already documented
these counts. Neither source is silently substituted for the other.

The reference calculation uses Decimal rolling means and population variance,
followed by a separate SMA-seeded Wilder ATR recursion. It does not invoke the
production indicator functions. Independent bands match the live entries with
a maximum absolute difference below $1.8e-13, against a $1e-10 tolerance.
The production collector is separately replayed for the initialization cases.
Tests verify that later candles cannot change a computed prefix and that a data
gap resets the ATR warmup.

## What caused each crossing

For a long recovery, the prior close must be below its prior lower band; the new
close must be at or above its new lower band and below the new mean. The change
in close-minus-lower-band equals price movement plus the decline in that band.
These signed arithmetic components describe the trigger, not its expected return.

| Decision | Price rise | Lower-band decline | Price contribution | Band contribution |
|---|---:|---:|---:|---:|
| September 8, 02:00 | $0.40 | $0.04360452 | 90.17% | 9.83% |
| September 8, 09:00 | $0.01 | $0.13747125 | 6.78% | 93.22% |

Both entries satisfy the independent inequalities. The second crossed mainly
because the band moved downward. This does not demonstrate that such entries
perform worse: only the first of these two SPCX positions was closed at the
audit cutoff, and that trade lost despite its larger price contribution.

## ATR evidence and remaining uncertainty

The first retained hourly publication used as the recurrence seed is September
7 at 20:00, with ATR 0.4694843815401276. Using that observed seed and independently
computed hourly true ranges reproduces all 13 subsequent published ATR updates
through September 8 at 09:00 within $1e-10. This validates the updates conditional
on that seed; it does not independently validate the seed itself.

Four fixed starting hours on September 4—00:00, 08:00, 09:00, and 10:00—were
checked for each entry using minute aggregation and native quarter-hour bars.
All 16 cases retain the qualifying long entries, but none reproduces the
recorded ATR exactly. Across these particular cases the rounded stop changes
by at most one $0.01 tick. The cases are sensitivity checks, not an optimization
or a general bound for other histories.

The public API documents availability of only the most recent 5,000 candles.
That limits retrospective recovery of the original startup snapshot; combining
later and earlier captures cannot prove what the live process received then.
[Hyperliquid Info endpoint documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint), checked September 8.

The remaining discrepancy precedes the observed 20:00 seed. Preserved evidence
cannot distinguish an initialization-history boundary, older candle revisions,
or another startup input difference. The missing startup snapshot is not
replaced with a history window selected to fit the recorded ATR.

## Validation, disposition, and next investigation

The audit passes 35 tests with network lookup, connection, and datagram calls
denied. Independent indicator math has 100% statement and branch coverage;
combined replay coverage is approximately 99%. Corruption controls reject
missing/duplicate candles, invalid OHLCV, nonfinite metrics, wrong symbols or
intervals, changed frozen inputs, missing publications, and incorrect bands or
ATR updates. The same tests and real-input report replay pass from a temporary
workspace containing 3,376 verified archive members. The final validated source
reproduces the initial report exactly; both source versions are preserved.

Evidence is under `data/logs/research/bidirectional_cohort/` in
`v89_spcx_indicator_inputs_20260908_v1` and
`v89_spcx_indicator_replay_20260908_v1`, with exact dependencies, source archive,
frozen input hashes, test invocation, coverage, and archive replay retained.

No live change is proposed from these two entries. The next investigation is
one predeclared descriptive split of historical SPCX long recoveries: price
contribution at least 50% versus below 50%. Compare costs, net results,
favorable/adverse excursions, and regime mix under the existing execution
contracts. Previously screened history remains reused exploratory evidence;
an apparent advantage would need untouched forward confirmation before a live
proposal. This study does not authorize an entry filter and must not inspect
the locked SNDK/Brent prospective challenger outcomes early.

A conflicting original candle snapshot, changed frozen bytes, independent band
disagreement, or an inconsistent post-seed ATR update would falsify the
corresponding technical conclusion and require a new journal revision.
