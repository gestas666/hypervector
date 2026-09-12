# SNDK entry follow-through after removing holding-period selection

Including early-exit trades changes the earlier SNDK long cohort's one-hour
mean price movement from **+22.21 to -20.49 bps** and the later cohort's from
**-38.83 to -97.38 bps**. The later long cohort remains weaker, but the earlier
positive mean was conditional on staying open. High confidence applies to the
authenticated historical measurement; causal explanation and future trading
benefit remain unproven.

The [prior study](2026-09-10-v89-sndk-trade-drivers.md) correctly disclosed its
held-bar scope. This extension changes the population used to assess entry
follow-through; it does not replace its valid held-path arithmetic. All 282 old
one-hour observations, including explicit missing values across six cases,
reconcile to the original clock convention.

## Fixed scope and complete observations

The plan was committed at **9afbeb2** before new horizon outcomes were calculated.
Operator source **e0c7700f353d56d887f225a9917a86e92a096b97** was committed before
the original historical run, which exited 0 at **05:53:35 UTC** on September 12.
Final verifier source is **feabbfa6641087692419cebc5f150c192a70f24b** in the clean
isolated `hypervector-v89-sndk-fixed-horizon-20260912` worktree.

All **47 accepted SNDK identities** are retained: **29 longs and 18 shorts**.
The six original control/equal-allocation and nominal/adverse/full-HIP-3-fee
cases share these identities and entry clocks. Their repeated rows do not
create independent samples. Primary results below use original case 08:
control allocation, first core, full-prefix XYZ, recorded clock and full fees.

Horizon lengths were fixed at **15, 60, 240 and 1,440 minutes**. Each target uses
the native quarter-hour bar ending exactly at entry time plus that horizon.
The price movement is signed by entry direction and measured relative to the
case's original modeled entry price. A trade exiting earlier does not remove
that later observation. This is a gross price-path diagnostic, excluding exit
execution, fees and funding; it is not PnL from ignoring a stop or holding longer.

The existing August 18 00:00 UTC entry-cohort split is preserved. All side,
cohort, horizon and all/held/after-exit combinations remain, including empty
groups. There are **1,128 case-entry-horizon rows**, **288 summary groups** and
**96 all-minus-held mean comparisons**. Of the rows, 1,122 have prices and six
are explicitly unavailable: the same one long entry's 24-hour target in each
case. Its target is September 7 05:00 UTC, beyond the retained source end.
No interpolation, forward fill, exit-price substitution or zero-return fallback
was used. All 47 entries have complete one-hour observations.

## One-hour selection effect

| Primary case | All entries | Held at one hour | Original held mean, bps | All-entry mean, bps |
| --- | ---: | ---: | ---: | ---: |
| Earlier longs | 18 | 16 | +22.21 | -20.49 |
| Later longs | 11 | 10 | -38.83 | -97.38 |
| Earlier shorts | 12 | 9 | +80.53 | -11.91 |
| Later shorts | 6 | 5 | +37.28 | -7.17 |

Seven entries were previously excluded at one hour: two earlier longs, one
later long, three earlier shorts and one later short. Five of these subsequent
price moves were negative in the entry direction and two were positive.
Their large magnitudes influence the means. For example, the earlier long
median is still **+1.06 bps**, while the later long median is **-35.39 bps**;
the mean shift does not imply every earlier entry lacked favorable movement.

The later-minus-earlier long mean gap is approximately **-76.89 bps** after
including every entry, versus -61.04 bps in the held-only comparison. This is
consistent with weaker later follow-through, subject to the selected historical
periods and small sample. It does not distinguish signal weakness from the
asset's background movement or other market-condition changes.

## Other predeclared horizons

| All long entries | Earlier mean, bps | Later mean, bps | Earlier/later observed counts |
| --- | ---: | ---: | ---: |
| 15 minutes | +10.98 | -32.49 | 18 / 11 |
| 1 hour | -20.49 | -97.38 | 18 / 11 |
| 4 hours | +65.04 | -148.89 | 18 / 11 |
| 24 hours | -91.74 | -182.26 | 18 / 10 |

At 15 minutes, 10/18 earlier and 2/11 later long moves were positive. At four
hours, those counts were 11/18 and 3/11. The 24-hour later statistic is missing
one right-censored entry and is not presented as complete coverage.

The short side is not a uniform deterioration story: its all-entry four-hour
mean improves from **-123.14 to -5.34 bps** across the same periods, and its
one-hour mean is slightly less negative. All short groups remain in the report.
Control and equal allocations have identical normalized observations within each
cost case, as expected from their shared price paths. Nominal one-hour long
means are -17.50/-94.41 bps; adverse and full-fee cases give -20.49/-97.38 bps.
Modeled entry-price differences explain this sensitivity; full fees are not
deducted from these gross forward-price measurements.

## Validation and limits

The operator authenticates **2,375 references**: eight directly pinned prior
artifacts plus all 2,367 references from the existing SNDK diagnosis. The native
source retains 4,800 quarter-hour bars. Input qualification requires the exact
six scenario axes, ordered identities, sides, clocks and source metadata.

**68 offline tests pass.** The metric module covers 78/78 statements and 28/28
branches; input qualification covers 58/58 statements and 28/28 branches. The
operator covers 73/80 statements and 17/18 branches. Independent verification
covers 113/124 statements and 36/40 branches; broader branch completeness is
not claimed. Fourteen synthetic verifier-corruption controls reject altered
values, counts, coverage, clocks, selection labels, aggregate duplication,
nulls and nonfinite scalars. Initial fixture and coverage failures are retained.

Separate DuckDB queries reconstruct original target joins and every summary.
Decimal arithmetic independently checks all 1,122 observed returns; maximum
SQL/Decimal residual is **2.39e-12 bps**. All 1,128 rows, 288 groups, 96 selection
effects and 282 prior-hour comparisons agree. A control found that the draft
verifier accepted a duplicated aggregate case; exact six-case roster enforcement
now rejects it. Final numerical results are unchanged.

Ten source/plan files match their Git blobs and archive. Nine output files
reproduce byte-for-byte using the archived source; its independent verification
receipt also matches. Nine operator/test files meet file/function-size and
annotation checks. Ruff check and format checks pass. Tests make no network
calls. Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_sndk_fixed_horizon_20260912_v1`.

These already explored entry cohorts are not a fresh holdout. Horizon labels
overlap, scenarios repeat entries, and means are sensitive to large price moves.
The after-exit labels are retrospective and must not become live decision inputs.
No confidence interval assumes independent rows. The sampled closes are not
continuous extrema, executable fills or venue mark-price stop paths. The existing
stop/clock studies and original account results remain separate evidence.

## Recommendation and next investigation

**Recommendation / why now:** retain the complete all-entry diagnostic and stop
using the selected held-only mean as a proxy for unconditional accepted-entry
quality. The measured selection effect is substantial in both directions.
**Evidence reviewed:** fixed prior cases, original native bars, source pins,
all horizon/selection groups, independent arithmetic and corrupted controls.
**Applicable regime:** the original July 21–September 7 historical market window,
split on August 18; the cause of the period difference remains unresolved.

| Alternative | Value | Disposition |
| --- | --- | --- |
| Keep only the original held-hour average | Describes positions that remained open | Retain for that conditional question |
| Use all fixed-horizon accepted entries | Removes holding-duration selection from this diagnostic | Accepted measurement |
| Fit a new stop, hold time or entry filter now | Economic benefit unmeasured; risks fitting explored samples | Not selected |
| Compare fixed calendar-hour background windows | Tests whether deterioration is entry-specific or shared by the asset | Highest-value next investigation |

**Proposed live change:** none. **Expected upside:** a better-supported diagnosis
before designing a policy experiment, not a claimed return gain.
**Main risks:** selection of historical periods, overlapping horizons, sparse
later cohorts, outlier sensitivity and interpreting post-exit prices as actual
trade PnL. **Validation still required:** predeclared background controls using
the same causal close convention, followed by separate policy validation only
if a concrete mechanism is supported. No threshold is fitted here.
**Success metrics:** complete identity/coverage disclosure and reproducible
independent arithmetic, regardless of the sign of returns.
**Failure / rollback triggers:** changed input identities, mismatched clock or
survival labels, unexplained residuals, duplicated samples, or nonreproducing
files invalidate the affected measurement. The isolated research source can be
revised without changing production. **Confidence:** high for the arithmetic;
low for a causal or prospective trading conclusion.
**Explicit approval requested:** none for this authorized research. Existing
two-file session and 64-file heartbeat/TUI installation decisions remain pending.

At **06:01:13 UTC** on September 12, seven authenticated unsigned responses
showed core flat/order-free and the existing **0.306 SNDK short at 1629.2,
10x isolated**, with **-$1.53 unrealized**. Its full-size buy reduce-only Stop
Market OID **542326955281** at **1669.9** remained open. Sixteen funding cash rows
sum to **+$0.092131**. The bounded fill query contains the original entry.
Original trading PIDs remain absent; terminal records and installed profile,
binary and ledger hashes are unchanged. Process visibility is limited and these
sequential reads do not prove continuous protection. No installation, restart,
order request, strategy/risk change or prospective sealed-outcome evaluation
occurred. Full live and economic readiness remain unproven.
