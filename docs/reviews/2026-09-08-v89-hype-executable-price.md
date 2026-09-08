# HYPE August 26: historical executable-price reconstruction

The recorded order books support lower entry costs than the adverse fill
assumption for this one source-sensitive HYPE long. At both original modeled
quantities, all **84 post-publication snapshots** contain enough displayed asks.
Their maximum calculated entry price is **$81.888**, versus the modeled adverse
entry of **$81.91002575**. The first snapshot after publication gives **$81.877**.

Confidence is high in this bounded source and arithmetic finding: raw responses
reproduce the normalized archive, independent Decimal calculations agree, and
the source archive reproduces the full report. Confidence is low in any claim
about an achievable strategy fill, revised trade outcome or future profitability.
This is a retrospective counterfactual under V89, not an actual missed order.

## Frozen inputs and acquisition

The earlier [recorded-source study](2026-09-07-v89-recorded-native-source-sensitivity.md)
identified the August 26 02:25 UTC entry. Its native source candle satisfies the
fixed directional-body threshold; the archive candle does not. The modeled
nominal entry survives to maximum hold, while the adverse entry stops at 09:23.
This investigation changes none of those previously recorded outcomes.

The exact source candle was first published at **02:25:21.069494 UTC**. The
frozen native event export contains one matching publication. Its candle fields
and event ID match the first-recorded hybrid input. The next minute's modeled
open is $81.865, and the signal reference close is $81.859.

The original shared report supplies these quantities and prices:

| Case | Modeled quantity, HYPE | Entry price | Original unrounded 80-bps stop |
|---|---:|---:|---:|
| Nominal, 2.5-bps slippage | 30.530448374897052 | 81.88546625000001 | 81.23038252 |
| Adverse, 5.5-bps slippage | 30.52129427513945 | 81.91002575 | 81.254745544 |

Each has $2,500 modeled entry notional. Quantities are preserved exactly; they
are not new live size recommendations. Venue lot-size and stop-price rounding
are outside this reconstruction.

An inventory of 1,027 existing HYPE archive manifests found no book or trade
bundle covering the minute. The predeclared unsigned acquisition covers only
**02:25:00–02:26:00 UTC**, depth 20, at most two book pages and five trade pages.
Both queries completed in one page:

- 131 raw/normalized books; no coalescing or censored zero-size snapshots.
- 506 participant fills normalize to 253 public taker trades; no unresolved
  groups or surrogate trade IDs.
- Original request IDs, raw envelopes and checksums are preserved.
- The book exactly at 02:26:00 is excluded from the end-exclusive analysis,
  leaving 130 snapshots. Maximum observed inter-snapshot gap is 500 ms.

## Publication bracket and fixed offsets

The last book at/before publication is labeled **02:25:21.000**, 69.494 ms before
the saved publication timestamp, and supports $81.888 at both quantities. The
first later book is labeled **02:25:21.500**, 430.506 ms after publication, and
supports $81.877 at both quantities. These signed differences compare recorded
clocks; local/venue clock skew is unmeasured. They are not client latency.

No favorable quote is selected. Every predeclared delay is retained using the
first snapshot at/after its target:

| Delay from publication | Selected book UTC | Nominal-quantity VWAP | Cost from $81.865 open, bps |
|---|---|---:|---:|
| 0 seconds | 02:25:21.500 | 81.877000 | +1.46583 |
| 1 second | 02:25:22.500 | 81.870000 | +0.61076 |
| 2 seconds | 02:25:23.500 | 81.879846 | +1.81345 |
| 5 seconds | 02:25:26.500 | 81.881000 | +1.95444 |
| 10 seconds | 02:25:31.500 | 81.880000 | +1.83228 |
| 30 seconds | 02:25:51.500 | 81.888000 | +2.80950 |

Every selected book is 430.506 ms after its clock-labeled target. Both original
quantities are evaluated separately; the two-second adverse-quantity price is
$81.8798434 because it consumes slightly less depth.

Across all 84 post-publication snapshots, nominal-quantity VWAP ranges from
$81.85042713 to $81.888, or **−1.78011 to +2.80950 bps** from the minute open.
52 of 84 prices are at/below the nominal modeled entry; all 84 are below the
adverse entry. These are correlated observations of one minute, not 84 trials.
All complete and partial-depth outcomes remain explicit in the analysis API;
no full-size fill is imputed when visible depth is insufficient.

The 172 public trades after publication range from $81.832 to $81.888. Their
aggregate quantity is 6,376.89 HYPE and VWAP is $81.87319425. They contextualize
the interval but do not establish what an additional strategy order could fill.

## What the stop comparison does and does not show

At the observed full-size prices, every unrounded 80-bps stop is below the
recorded **09:23 candle low of $81.242**. The highest such stop is $81.232896;
the first-post-publication stop is $81.221984. The original modeled adverse
stop is above that low. Thus the previously identified candle-based stop switch
depends on an entry price above every observed post-publication depth walk.

This is threshold arithmetic, not a revised lifecycle. The whole causal holding
path, funding, stop rounding, trigger source and exit-side executable prices
have not been reconstructed. Hyperliquid documents mark price as the trigger
for TP/SL orders, so a traded-candle low alone cannot establish the venue stop
event. [Hyperliquid TP/SL documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl)

The historical $24.76 nominal profit and $23.78 adverse loss remain labeled
modeled sensitivities. This study does not replace either with an asserted fill
or promote the current strategy as profitable.

## Validation and reproducibility

Research source revision: `2130d18ad630fd06df3d9044a13c71d05ea563ad`, isolated in
`/Users/gestas/Prototypes/hypervector-v89-storage-spcx-20260908`.

**93 offline tests pass** in both the working source and extracted archive, with
network access denied. The new pricing module covers **151/151 statements and
58/58 branches**. The source wrapper covers 155/157 statements and 52/54
branches; its uncovered paths are the raw participant-count mismatch guard and
module-entry guard. The initial CLI exercised the latter. Combined coverage is
94.52% including the reused depth module and its unrelated conversion helper.
Ruff, formatting, source/function limits, annotations and public docstrings pass.

Independent Decimal walks verify **168 quotes and 336 VWAP/stop comparisons**.
Maximum absolute residual is **2.351996604267e−14 USD**, below 1e−10 USD; stop
classifications agree exactly. The initial and final numerical reports match.

The **5,054-member source archive** contains 5,052 tracked source-commit files
and two verification harnesses. Every member is hash-verified, and the extracted
source replay reproduces the final report exactly. The initial attempt stopped
on an incorrect expected research-origin label; the audit was corrected to the
actual `recorded_native` schema and then completed. No live fault occurred.

Artifacts are under the main repository's
`data/logs/research/bidirectional_cohort/v89_hype_aug26_executable_price_20260908_v1/`.
The immutable journal pins source inputs, downloaded raw data, reports, tests,
independent verification and the source archive.

## Disposition and next investigation

Retain the event-specific entry-price qualification. Missing within-snapshot
changes, unmeasured clock skew and client timing, displayed-depth cancellation,
market impact, unrounded quantities, and the retrospective route all limit its
execution interpretation. A changed checksum, raw/normalized mismatch, different
first publication, failed depth walk or contradictory independent calculation
would falsify the corresponding finding.

The highest-value next investigation is
`v89_hype_aug26_mark_trigger_reconstruction_v1`: qualify archived mark-price
coverage and protective-stop trigger behavior for this same historical trade.
Start with the bounded 09:22–09:24 UTC switch interval and preserve all original
entry-price cases. If a revised lifecycle is considered, extend the verified
mark history over the complete holding interval before making that claim.
Keep exit-side liquidity, actual trigger semantics and stop rounding explicit.
No live change or sealed prospective outcome read is required.

The selected mark-price audit tests an unresolved execution assumption. Leaving
the fill/trigger assumptions unresolved saves acquisition work but retains the
known sensitivity. Parameter tuning or changing HYPE's allocation requires
additional strategy evidence beyond this event. No live strategy, asset, size,
leverage, execution, deployment or process lifecycle was changed by this study.
