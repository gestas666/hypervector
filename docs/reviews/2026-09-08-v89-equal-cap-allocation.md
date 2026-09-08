# Fixed equal-cap allocation: higher modeled return and greater exposure

Equal route caps increase full 48-day modeled net in all 36 comparisons, and
increase maximum dollar drawdown in all 36. In the recorded-source/adverse
original-exit comparison, net rises from **$96.12 to $369.09**, while maximum
drawdown rises from **$198.69 to $288.19**. The later 20 days still lose
**$52.43**. Under full HIP-3 fee stress, that later loss worsens from $137.28
to **$159.23**. Retain a research candidate; this evidence does not establish
a live sizing recommendation or future edge.

Confidence is high in reproduced accounting and fixed-contract comparisons,
medium in the exposure interpretation, and low in future profitability or
executable fills at the changed quantities. Changed input identities, failed
proportional reconciliation, incompatible sizing, different independent replay
or insufficient observed depth would update the respective claim. This is a
single allocation rule tested on already explored history, not 36 independent
experiments.

## Registered change and controls

Hypothesis `v89_equal_cap_allocation_benchmark_20260908_v1` was preregistered
in commit `0561860e141fae15ec45f40c7b9c83a6b12979aa` before alternative returns
were calculated. The original summed caps are **$7,500**: BTC/HYPE $2,500 each,
and ETH/SOL/SPCX/SNDK/Brent $500 each. The single challenger assigns
**$7,500 / 7 = $1,071.428571...** per route. It fits no weights or thresholds,
retains all seven routes and changes no leverage, entry/exit price or signal.

Quantities, fees, funding and initial isolated margin scale by new-cap/old-cap.
Margin fractions scale by the same ratio, preserving each route's original
equity floor for the cap to bind. Sum of potential isolated margin changes from
**$591.67 to $625.00**, because leverage differs across assets. This is an
equal-cap benchmark, not equal-risk sizing or constant deployed exposure.

All 18 original source/cost/clock controls and 18 previously registered
one-second-plus-additional-slippage SNDK event controls are reproduced exactly
before the 36 corresponding allocation cases. Original and event-adjusted exits
remain separate; the event price is not reselected at the new size. Its inherited
unit-price assumption is one of the execution limitations to qualify next.

## Recorded-source comparison

First/latest recorded-source chronological statistics agree in all 12 pairs.
Tables use the recorded-bar clock; every archive and late-clock result remains
in the machine report. Amounts are modeled USD over July 21–September 7, 2026.

| Cost / SNDK exit model | Original-cap full net | Equal-cap full net | Original-cap maximum dollar drawdown | Equal-cap maximum dollar drawdown |
|---|---:|---:|---:|---:|
| Nominal / original | +197.42 | +491.38 | 141.15 | 265.20 |
| Nominal / sampled stop | +210.27 | +518.92 | 141.15 | 237.65 |
| Adverse / original | +96.12 | +369.09 | 198.69 | 288.19 |
| Adverse / sampled stop | +108.68 | +396.01 | 198.69 | 277.19 |
| Full HIP-3 fee / original | −33.18 | +92.01 | 233.99 | 366.48 |
| Full HIP-3 fee / sampled stop | −21.06 | +117.99 | 233.99 | 366.48 |

Original-exit adverse close-mark percentage drawdown rises from **3.9064% to
5.5123%**. Under full-fee stress it rises from 4.6810% to 7.0634%. These are
completed-candle model diagnostics, not observed venue account drawdowns.
No unfavorable case was suppressed or rejected as a technical trial failure.

| Cost, original exit | First 28 days: original → equal | Later 20 days: original → equal |
|---|---:|---:|
| Nominal | +215.30 → +483.10 | −17.89 → +8.28 |
| Adverse | +183.56 → +421.52 | −87.44 → −52.43 |
| Full HIP-3 fee | +104.09 → +251.23 | −137.28 → −159.23 |

The sampled-stop control changes only the earlier partition; later incremental
totals agree with the corresponding original-exit results. The fee-stressed
later result worsens in all 12 retained source/clock/exit cases. Higher full-window
returns depend on the stronger earlier period and do not establish stable
performance through the later conditions.

## Capital use and contribution

A post-result descriptive calculation covers every scenario without adding
allocation variants. It clips each position to the same chronological periods
and weights holding time by quantity × entry price, not changing market marks.
For recorded/adverse/original exits, average entry-notional exposure rises from
**$871.82 to $1,763.33**, and average initial margin from **$84.80 to $171.63**.
The caps sum is fixed, but average capital use roughly doubles because the
longer-held noncrypto routes receive larger caps. This is not evidence of newly
created signal quality.

| Asset | Equal-cap full net | Full net change from original caps | Equal-cap later net |
|---|---:|---:|---:|
| BTC | +1.76 | −2.35 | −3.11 |
| ETH | −19.26 | −10.27 | −7.99 |
| HYPE | −42.54 | +56.72 | −30.63 |
| SOL | +5.91 | +3.15 | −7.63 |
| Brent | +70.41 | +37.55 | +14.50 |
| SNDK | +258.97 | +138.12 | −56.98 |
| SPCX | +93.84 | +50.05 | +39.40 |

SNDK supplies $258.97 of the $369.09 full net, and $138.12 of the $272.97
improvement. Its larger later loss partly offsets the benefit of reducing
HYPE exposure. Removing the three largest positive marked-day contributions
as descriptive concentration arithmetic leaves **−$27.51**. This is not a
portfolio simulation that omits those days.

Adverse equal-cap full-window price PnL is +$417.75, fees $47.25 and funding
−$1.41. Later price PnL is already **−$32.37 before costs**, with $18.60 fees
and −$1.46 funding. Fees are not the sole explanation for later weakness.

Every modeled entry remains compatible with the declared caps. Across the
36 allocation cases, minimum unreserved cash is $4,405.53, maximum reserved
margin $428.57, and maximum marked gross notional $4,392.90. Maximum concurrency
is unchanged at four. These results validate the fixed-lifecycle sizing
assumption within the model; they do not prove real liquidity or future solvency.

## Verification

Research source **`60b8817eae9a6223f23eb1002895a23d72fbacd4`** is isolated from
live execution. **92 offline tests pass**. The pure allocation module covers
42/42 statements and 14/14 branches, including a deliberately corrupted scaling
function to verify the independent cap-budget check. Funding/fee cutoffs,
resolved exit clocks, side policies, source immutability, capacity mismatches,
daily proportionality and adverse-peak accounting have offline regressions.
Coverage does not represent the entire project or all source I/O.

The independent audit imports no model implementation. It verifies 359 evidence
files, 32,376 Decimal fields, 6,360 repeated lifecycle identities, 67,448 repeated
hourly settlements, 12,204 daily Decimal fields and **2,499,924 challenger path
rows**. Maximum scaling/path discrepancies are 1e−12, funding discrepancy
1.19e−15 and daily discrepancy 1.21e−13. Counts repeat the same economic events
across sensitivity controls and must not be treated as sample sizes.

Independent SQL checks all 4,968 post-result exposure fields, with maximum
residual 1.17e−10. New source files pass Ruff, type-annotation/docstring and
file/function limits. All **5,135 archived Git members** match their blobs.
Archived replay repeats all 36 controls and 36 challenger cases: **217 output
files are byte-identical**; the aggregate report agrees after normalizing only
its output-directory evidence keys. Initial failing and passing logs are retained.

## Disposition and next action

| Option | Evidence / trade-off | Disposition |
|---|---|---|
| Retain current caps | Lower historical drawdown; smaller full-window net | Preserved control |
| Equal caps at the same summed budget | Higher full-window net; more deployed exposure, larger drawdown and worse later fee stress | Research candidate |
| Search nearby weights | Would fit the already explored sample after seeing this result | Not part of this experiment |
| Qualify exact changed quantities against books and costs | Resolves a material execution assumption without claiming strategy edge | Next registered study |

Next is [bounded quote and cost feasibility](../plans/2026-09-08-v89-equal-cap-quote-feasibility.md),
`v89_equal_cap_quote_feasibility_20260908_v1`, preregistered in `e762d26`.
Compare both cap assumptions across exact configured sides using current,
unsigned mainnet metadata and a fixed 36-round book sample. Retain failed or
insufficient observations and independently replay rounding, depth and costs.
This cannot establish historical fills or future return. A concrete inactive
allocation/prospective proposal still requires those checks and an independent
observation boundary before any live deployment request.

No live profile, strategy, size, leverage, trading/reporter process or TUI was
changed. The September 8–22 sealed experiment remains unopened.
Evidence: `data/logs/research/bidirectional_cohort/v89_equal_cap_allocation_benchmark_20260908_v1/`.
