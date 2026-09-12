# SNDK entry follow-through versus matched background hours

Later SNDK long entries retain a substantial one-hour deficit after comparison
with non-entry hours from the same historical cohort and UTC hour. Their native
price return averages **-90.07 bps**, versus **+0.09 bps** in the matched background.
Earlier longs average **-16.10 bps**, versus **+7.82 bps** in their background.
The later-minus-earlier entry change of **-73.98 bps** decomposes into **-7.73 bps**
of background change and **-66.25 bps** of matched-excess change.

High confidence applies to this authenticated historical calculation. The result
is consistent with entry-associated weakness beyond this background comparison;
it does not establish a causal mechanism, a broken strategy, or future profit.
The weekday/weekend sensitivity retains **-61.23 bps** of matched-excess change.
Both methods remain reported; neither was selected after seeing its result.

## Fixed population and measurement

The protocol was committed as **89ce9a6** before background returns were
calculated. Operator and first verifier source **740467c7d99eda98aa248f44d1263ffef517ca48**
was committed before the historical run, which completed at **06:48:20 UTC** on
September 12. Final verifier source is **03f153f131a1b1dcf7d2ca9a4ccfc312315f9f47**
in the isolated `hypervector-v89-sndk-background-20260912` worktree. Its only
post-evaluation implementation change fixes verifier receipt repeatability.
The original operator, protocol and numerical result artifacts are unchanged.

All **47 accepted identities** remain: 29 longs and 18 shorts. Their entry
clocks are 47 unique whole UTC hours. The calendar runs from July 21 00:00 UTC
inclusive to September 7 00:00 UTC exclusive, split at August 18 00:00 UTC.
The 1,152 hourly anchors each retain 15-, 60-, 240- and 1,440-minute targets.

Both entries and controls use the native completed 15-minute close ending at
the anchor, with an exact completed-close target at anchor plus horizon.
No interpolation, forward fill, future baseline, exit truncation or zero-return
substitution is used. These are signed gross price measurements, excluding
execution, fees and funding; they are not a policy backtest or account PnL.

Primary controls match cohort and UTC hour. The sensitivity also matches the
weekday/weekend calendar class, which is not an exchange-session or holiday
classification. Every accepted-entry anchor is excluded from every control
pool, regardless of direction. Controls receive the same direction sign as
their associated entry. Each entry contributes its own control-pool mean;
group means weight complete entries equally, rather than pooling memberships.

All **4,608 calendar rows**, **376 comparisons**, **32 groups**, **16 period
decompositions** and **1,128 six-case price-basis rows** are retained.
There are 4,582 observed calendar returns and 26 targets beyond the source end.
All anchor prices are observed. One unique later-long 24-hour target is missing,
producing two unavailable entry comparisons and six unavailable bridge rows.
The 374 complete comparisons retain the same entry subset in all decomposition
terms. No observed control pool is empty. Eligible pool sizes range from 5 to 27;
6,664 repeated memberships include 6,642 observed control returns. Reused
memberships and overlapping horizons are not independent samples.

## One-hour comparison

| Side and cohort | Entries | Native entry mean, bps | Same-hour background, bps | Matched excess, bps | Median excess, bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| Long, earlier | 18 | -16.10 | +7.82 | -23.92 | +4.20 |
| Long, later | 11 | -90.07 | +0.09 | -90.17 | -34.95 |
| Short, earlier | 12 | -7.61 | -15.49 | +7.88 | +57.01 |
| Short, later | 6 | -1.09 | +0.78 | -1.86 | -1.34 |

Earlier/later long groups use 456/199 repeated control memberships representing
310/147 unique control anchors. Positive excess appears in 9/18 earlier longs
and 4/11 later longs. Individual observations substantially influence the means:
minimum long excess is -759.72 bps earlier and -669.82 bps later. These counts
and medians qualify the means; they are not calibrated future win probabilities.

| Weekday/weekend sensitivity | Earlier excess, bps | Later excess, bps | Background change, bps | Excess change, bps |
| --- | ---: | ---: | ---: | ---: |
| Long | -30.15 | -91.39 | -12.75 | -61.23 |
| Short | +25.97 | -3.89 | +36.39 | -29.86 |

The short side is mixed. Its native one-hour entry mean improves by 6.52 bps,
while its same-hour signed background improves by 16.27 bps. Its matched excess
therefore declines by 9.75 bps. This is not uniform deterioration across sides
and horizons, and does not justify mirroring a long-side diagnosis onto shorts.

## Other predeclared horizons

| Side / horizon | Earlier native mean, bps | Later native mean, bps | Earlier matched excess, bps | Later matched excess, bps |
| --- | ---: | ---: | ---: | ---: |
| Long / 15 minutes | +15.39 | -25.13 | +16.73 | -15.11 |
| Long / 4 hours | +69.49 | -141.63 | +39.60 | -157.75 |
| Long / 24 hours | -87.35 | -174.87 | -189.24 | -246.38 |
| Short / 15 minutes | +82.71 | +10.11 | +80.87 | +3.27 |
| Short / 4 hours | -118.83 | +0.75 | -63.63 | +11.43 |
| Short / 24 hours | +39.79 | -39.31 | +124.11 | +7.03 |

The long 24-hour later mean has 10 observed entries, not 11. Other long rows
use 18/11 earlier/later entries; short rows use 12/6. The day-class sensitivity
also retains weaker later long excess at 15 minutes and four hours. All 32
groups remain in `report.json`; no horizon or matching rule is promoted.

## Bridge to the preceding study

The [fixed-horizon study](2026-09-12-v89-sndk-fixed-horizon.md) measured against
original modeled entry prices. This comparison uses a common native anchor for
entries and controls. All 1,128 modeled-entry returns are reconstructed from
the same target and original entry price before their basis difference is saved.
For primary case 08, the old-minus-native one-hour differences average -4.40/-7.31
bps for earlier/later longs and -4.30/-6.08 bps for earlier/later shorts.
Thus the earlier -20.49/-97.38 bps long means reconcile to the current
-16.10/-90.07 bps native means. This is a price-basis change, not revised fees,
fills, realized profit or an improvement to the strategy.

## Validation, reproducibility and limitations

The original input qualification authenticates **2,375 references**, including
the complete prior lineage and the 4,800 native bars. Eleven additional pinned
prior-study artifacts bind the six result cases and their verification.
Independent verification also requires derived source-reference rosters and
the native-price reference to match their original authenticated provenance.

**67 offline tests pass.** Matching arithmetic covers 78/78 statements and 20/20
branches. The operator covers 104/109 statements and 30/32 branches; SQL query
construction covers 16/16 statements; verifier orchestration covers 80/92
statements and 19/24 branches. Full orchestration branch coverage is not claimed.
Nineteen deliberate report/provenance corruption cases cover clocks, missing or
duplicate rows, entry inclusion, membership omission, signs, false nulls/zeros,
means, aggregation, bridge values, authority fields and reference rosters.

Separate SQL reconstructs all calendar endpoints, memberships, entry-weighted
groups, decompositions and price-basis rows from original JSON and Parquet.
Decimal checks all 4,582 observed native returns; maximum residual is
**2.84e-12 bps**. The fixed comparison tolerance is 1e-8 bps.

The first archive replay reproduced all seven data files but exposed a changing
verifier digest. Default parallel SQL aggregation changed 144 floating values
between two diagnostic runs, with maximum difference 1.85e-13 bps. Three
single-threaded SQL reconstructions were identical. A repeated-receipt regression
test failed before the one-line thread-setting fix and passes afterward.
The original failed replay, archives, receipts and diagnostics remain retained.
The final 15-file source archive matches its Git blobs. Seven data files and
the final independent receipt now reproduce byte-for-byte. Ruff and source-size
checks pass; tests make no network calls.

This is previously explored history, not a fresh holdout. Pools use the full
cohort, including dates after individual entries, so this retrospective baseline
is not available at decision time as constructed. Matching controls only cohort,
hour and optionally calendar class. Volatility, liquidity, news, trend and other
conditions remain uncontrolled. Controls overlap and are reused, later samples
are small, and large moves influence averages. No causal treatment effect,
independent-row confidence interval or profitable trade rule is claimed.

## Recommendation and next decision

**Recommendation / why now:** retain the matched-background diagnosis. A broad
same-hour asset drift alone does not account for the observed later-long gap
under either fixed matching method. Before assigning a stable regime or signal
cause, quantify the influence of individual entry days on this new matched gap.

**Applicable regime:** only the stated July 21–September 7 historical window.
**Proposed live change:** none. **Expected upside:** reduce the chance of fitting
an entry rule to background movement or to a few influential observations.

| Alternative | Value and trade-off | Disposition |
| --- | --- | --- |
| Keep the prior all-entry diagnosis only | Simplest, but leaves asset-background attribution unresolved | Superseded for this attribution question |
| Retain both fixed background comparisons | Removes holding-time selection and uses a common native basis; still retrospective | Retain |
| Predeclare a day-level influence audit | Tests robustness of this newly measured gap; does not add fresh market evidence | Highest-value next investigation |
| Fit a filter or change long sizing immediately | Could suppress losses and winners; economic benefit is unvalidated | No proposal from this study |

**Validation still required:** a fixed influence protocol retaining every day
omission, then a separately specified causal policy and appropriate out-of-sample
or prospective evidence if a live change is proposed. Do not repeat the completed
held-path, fixed-horizon, background or historical-matrix calculations as new trials.
**Success metrics:** complete source-bound attribution and correctly disclosed
sensitivity; this report has no profit target. **Failure triggers / falsifier:**
changed input identity, wrong clock or sign, omitted controls, wrong weighting,
unexplained reconciliation error or failed archive reproduction invalidates the
affected measurement. Different periods or influence results may update the diagnosis.
**Rollback:** no runtime change to roll back; retain original artifacts and both
verifier versions. **Confidence:** high for measurement, limited for causal or
prospective interpretation. **Explicit approval requested:** none for this
research-only result; the existing installation questions remain pending.

## Runtime boundary and retained evidence

At **06:47:14 UTC**, seven authenticated unsigned HTTP-200 responses show core
flat and order-free, and the existing **-0.306 xyz:SNDK** position at **1629.2**,
10x isolated, with **-$0.7956 unrealized**. Its full-size buy reduce-only Stop
Market order **542326955281**, trigger **1669.9**, remains open. Sixteen funding
cash-flow rows sum to **+$0.092131**; the bounded fill query contains the original
entry only. Original trading PIDs are absent and all seven terminal rows plus
installed profile/binary/ledger hashes are unchanged. Process visibility has
permission limits. This is a timestamped observation, not a continuing state claim.

The 64-file heartbeat/lifecycle candidate and separate two-file session candidate
remain unchanged and uninstalled. No orders, deployment or strategy changes were
made. Both prospective hypothetical outcome seals remain unopened.

Evidence root: `data/logs/research/bidirectional_cohort/v89_sndk_background_20260912_v1/`.
Use `report.json`, `calendar.json`, `comparisons.json`, `bridge.json`,
`independent_final.json`, `reproduction_verified.json`, `source_v2.tar.gz`,
`source_archive_v2_manifest.json` and `artifact_manifest.json`. Original inputs
remain at their pinned absolute paths; reproduction requires the same local
Python environment and a fresh output directory containing both prepared files.
