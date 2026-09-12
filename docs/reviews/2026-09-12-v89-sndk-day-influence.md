# SNDK matched-background day influence audit

The later-minus-earlier long one-hour matched-excess gap remains negative in
all 48 single-day omissions under both omission modes and both matching methods.
Its size depends substantially on August 19: dropping that date's entry changes
the primary gap from **-66.25 to -8.28 bps**. The corresponding day-class gap
changes from **-61.23 to -3.10 bps**. These results weaken a claim of a large,
stable one-hour regime effect, while retaining a negative historical difference.

Confidence is **high for this bounded historical measurement**, supported by
complete independent SQL membership/arithmetic checks and exact archive replay.
Confidence in a causal regime diagnosis or future profitability remains **low**.
One omitted day is not a trading policy, and the omission ranges are not
confidence intervals. No historical account loss is removed or revised.

## Scope, sample and frozen decisions

The [protocol](/Users/gestas/Prototypes/hypervector-v89-sndk-influence-20260912/docs/plans/2026-09-12-v89-sndk-day-influence.md)
was committed as **c77cfe94eda728266fe4494a34fbbb340af2e22c** before omission
outcomes. Source **0654f937d95ceb9fd3876d6527197844c7d806e3** was committed before
the historical operator ran. It remains isolated in
`hypervector-v89-sndk-influence-20260912`; production source is unchanged.

The study retains the prior 47 accepted identities: 18 earlier longs across
15 dates, 11 later longs across 10 dates, 12 earlier shorts across 12 dates,
and 6 later shorts across 6 dates. Earlier/later split is August 18 00:00 UTC.
All July 21 through September 6 UTC dates are omitted once under each mode,
including dates without entries: **96 scenarios** over the same history.
The 48 omission values are dependent sensitivities, not 48 independent samples.

- **Entry day:** omit signals anchored on that date; retain each surviving
  signal's original price return and complete original background pool.
- **Price-window day:** omit signals and controls whose half-open measurement
  interval `[anchor - 15 minutes, anchor + horizon)` overlaps that date.
  Rebuild remaining control pools with the original accepted-entry exclusion
  flags. Removed signals cannot reappear as controls. This also removes
  cross-day and interior-day exposure; it is broader than entry-date deletion.

The four horizons remain 15, 60, 240 and 1,440 minutes. Matching remains either
same cohort/hour or same cohort/hour plus weekday/weekend class. Equal
complete-entry weighting, native completed-close convention, explicit missing
prices, original costs, modeled exits, sizing and account accounting are fixed.
Warmup days before July 21 and future days outside the 48-day grid are not omitted.

## Full earlier/later gap sensitivity

All values below are gross price **basis points**, later minus earlier matched
excess. Negative counts are entry-day/price-window-day scenarios out of 48 each.
Every reported range has 48 observed values and zero missing range values;
this does not eliminate missing individual price targets.

| Side | Horizon, min | Matching | Baseline | Entry-day range | Price-window-day range | Negative counts |
| --- | ---: | --- | ---: | --- | --- | ---: |
| Long | 15 | Hour | -31.84 | -41.76 to -18.95 | -40.65 to -20.19 | 48/48 |
| Long | 60 | Hour | -66.25 | -109.53 to -8.28 | -109.67 to -8.65 | 48/48 |
| Long | 240 | Hour | -197.35 | -246.78 to -138.46 | -247.84 to -136.98 | 48/48 |
| Long | 1440 | Hour | -57.14 | -208.24 to +34.14 | -193.12 to +25.22 | 44/44 |
| Short | 15 | Hour | -77.60 | -114.50 to -56.74 | -118.49 to -58.63 | 48/48 |
| Short | 60 | Hour | -9.75 | -81.70 to +35.01 | -85.59 to +33.75 | 43/42 |
| Short | 240 | Hour | +75.06 | +26.72 to +157.58 | +19.44 to +148.99 | 0/0 |
| Short | 1440 | Hour | -117.08 | -235.80 to +49.27 | -324.94 to +85.80 | 46/45 |
| Long | 15 | Hour + day class | -27.49 | -37.44 to -16.19 | -36.34 to -16.49 | 48/48 |
| Long | 60 | Hour + day class | -61.23 | -104.92 to -3.10 | -105.14 to -2.89 | 48/48 |
| Long | 240 | Hour + day class | -179.20 | -230.91 to -118.13 | -232.25 to -119.38 | 48/48 |
| Long | 1440 | Hour + day class | -56.00 | -205.79 to +33.42 | -215.60 to +34.91 | 44/43 |
| Short | 15 | Hour + day class | -80.20 | -117.17 to -58.49 | -124.82 to -61.55 | 48/48 |
| Short | 60 | Hour + day class | -29.86 | -102.78 to +13.90 | -110.11 to +11.64 | 46/45 |
| Short | 240 | Hour + day class | +34.70 | -16.25 to +115.70 | -34.83 to +104.94 | 4/2 |
| Short | 1440 | Hour + day class | -140.27 | -263.58 to +29.66 | -341.04 to +16.44 | 47/47 |

Long differences retain their negative sign at 15 minutes, one hour and four
hours under every tested single-day omission. Long 24-hour differences can
reverse sign. Short one-hour and 24-hour signs are sensitive to omissions;
short four-hour sign stability also depends on the matching method. These
horizon and method differences do not support a single broad regime conclusion.

## One-hour group sensitivity

| Group | Matching | Baseline excess, bps | Entry-day range | Price-window-day range |
| --- | --- | ---: | --- | --- |
| Earlier long | Hour | -23.92 | -45.02 to +19.36 | -42.97 to +19.51 |
| Later long | Hour | -90.17 | -103.27 to -32.20 | -103.02 to -32.58 |
| Earlier short | Hour | +7.88 | -32.92 to +79.83 | -28.84 to +83.73 |
| Later short | Hour | -1.86 | -35.82 to +42.89 | -36.24 to +41.63 |
| Earlier long | Hour + day class | -30.15 | -50.09 to +13.53 | -46.12 to +13.75 |
| Later long | Hour + day class | -91.39 | -106.16 to -33.25 | -105.55 to -33.05 |
| Earlier short | Hour + day class | +25.97 | -15.46 to +98.89 | -8.29 to +106.22 |
| Later short | Hour + day class | -3.89 | -42.18 to +39.87 | -41.84 to +37.62 |

Dropping **August 19** produces the least-negative one-hour long earlier/later
gap in all four mode/matching combinations. In the primary entry-day result,
the shift is **+57.97 bps** and the later-long mean moves from **-90.17 to
-32.20 bps**. Price-window omission leaves the gap at **-8.65 bps**, and the
day-class counterpart at **-2.89 bps**. The mean remains sensitive despite
retaining its sign.

Dropping **August 7** reverses the earlier-long one-hour excess sign in both
modes and matching methods, and produces the most-negative long gap. Both
short cohorts' one-hour group ranges include negative and positive values.
All tied extrema, all 48 dated values per range, 64 group ranges and 32 gap
ranges remain in the complete machine report; no favorable subset is selected.

## Validation and reproducibility

The retained offline run passes **65 tests**. Failing controls preceded new
logic. Tests cover midnight boundaries, cross-day windows, retained original
entry exclusions, unchanged/rebuilt pools, missing prices, empty groups,
complete rosters, duplicate dates, ties, finite shift overflow and corrupted
results. A count-preserving attempt to reinsert an excluded window is rejected.
Ruff, formatting, function/file limits and explicit annotations pass.

| New module | Statements covered | Branches covered |
| --- | ---: | ---: |
| Omission and range arithmetic | 72/72 | 28/28 |
| Operator | 91/96 | 20/22 |
| Independent SQL construction | 34/35 | 5/6 |
| Independent verifier | 100/109 | 24/26 |

Coverage is complete for the new arithmetic; other module coverage remains
partial as shown. This research did not rerun the full production test suite.

Independent SQL starts from the original entry JSON and native Parquet,
filters original entry/calendar tables separately, and reconciles **35,246
included comparisons**, **850 exclusions**, **3,072 groups**, and **1,536
decompositions**. Included and excluded rows cover all **36,096 baseline roster
slots**. Every scenario contains its full fixed group/decomposition grid.

Range summaries are independently recomputed from stored scalar means only
after those means reconcile to SQL. This preserves exact stored floating-point
tie identities. Decimal separately checks each scalar shift; the largest
residual is **2.842170943040401e-14 bps**. These checks establish consistency of
the frozen inputs and computation, not the correctness of the external price feed.

The 24-file source archive reproduces **104 files byte-for-byte**, including
all 96 trial payloads and the independent receipt. A fresh prepublication
reverification repeats the complete SQL audit and all 104 byte comparisons.
The source archive, prior input/result pins, retained failures and coverage logs
are retained. Journal publication authenticates the full 2,375-reference prior
lineage, 10 baseline result/input pins, 12 operator source pins and all 21
normalized database fields. The publication receipt provides exact totals.

## Decision and highest-value next investigation

**Recommendation / why now:** retain this influence diagnosis and stop treating
the -66.25 bps mean gap as evidence of a uniformly large one-hour deterioration.
The sign survives single-day deletions, but one date accounts for much of its
magnitude. Do not turn an omitted date or a selected range into a live filter.

| Alternative | Benefit and limitation | Decision |
| --- | --- | --- |
| Do nothing beyond the earlier mean comparison | Simplest; leaves magnitude sensitivity unquantified | Superseded for this question |
| Retain all fixed omission results | Makes concentration and sign sensitivity explicit; adds no new market sample | Retain |
| Delete influential losses or fit a date/volatility filter | Can improve explored history mechanically; no causal or prospective evidence | Do not propose |
| Qualify an independent price source and reconcile the August 19 path with the original exit | Can separate feed disagreement and post-exit price movement from actual modeled loss | Single next investigation |

The next study should first qualify historical SNDK source coverage and
independence, including existing 0xArchive data. The native baseline's identity
alone cannot establish price truth, and prior core research found cross-source
disagreements. Reconcile the influential date's original entry, stop exit and
fixed one-hour target without changing them or choosing a source by PnL.
A second source from the same underlying trade feed is corroboration, not
independent proof of mark-price or stop-trigger semantics.

**Expected upside:** better diagnosis before any strategy proposal; no measured
return improvement. **Applicable conditions:** the explored July–September
history only. **Remaining validation:** independent source qualification and
path reconciliation; any policy derived afterward requires distinct prospective
or out-of-sample validation with realistic execution costs.

**Success / falsifier:** exact provenance and complete dated ranges make this
measurement reviewable. Changed source identities, membership/arithmetic
mismatches, a failed archive replay or journal mismatch invalidate it. New data
can change the interpretation. A feed mismatch would require correcting affected
research before relying on the inferred entry weakness.

**Live change and rollback:** none proposed. Existing source/results remain
available; a failed future audit requires superseding this research record.
**Approval requested:** none for this research result. Existing installation
questions remain pending under the standing Human control clause.

## Account and installation boundary

At **September 12 07:47:23 UTC**, seven authenticated unsigned venue responses
show the existing **-0.306 SNDK short**, entry **1629.2**, **10x isolated**,
**-$0.306 unrealized**, and its full-size buy reduce-only Stop Market OID
**542326955281** at **1669.9**, still open. Seventeen funding cash rows sum to
**+$0.091831**, computed from `delta.usdc`. The bounded fill query contains one
original entry at 1789135222977 and no additional fill. Core is flat/order-free.

Original runner PIDs are absent; all seven terminal rows and installed
profile/TUI/ledger hashes remain unchanged. Process permissions limit
machine-wide absence claims. These are timestamped observations, not a guarantee
of later account state. No signing credentials were loaded or orders submitted.

At **07:58:53 UTC**, both isolated installation candidates remain clean at
**1b5eaa90118b868e5084cd750fb0fa96faabbd40** (64-file heartbeat/TUI package) and
**f59d54cf40cf80111b1691a86395326693b0c103** (separate two-file candle session).
Neither was installed in this study. Both prospective outcome seals remain
unopened. The continuous research objective remains active.

Evidence: [complete report](../../data/logs/research/bidirectional_cohort/v89_sndk_day_influence_20260912_v1/report.json),
[independent verification](../../data/logs/research/bidirectional_cohort/v89_sndk_day_influence_20260912_v1/independent_verified.json),
[archive replay](../../data/logs/research/bidirectional_cohort/v89_sndk_day_influence_20260912_v1/reproduction_verified.json),
[journal source](../research-journal/v89-sndk-day-influence-20260912-v1.json).
