# V31 Route-Pruning Forward Baseline Review

## 1. Problem restatement

Establish a reproducible prospective baseline for the proposed v31 authority
change while the exact v25 runtime remains active. The output must show what is
currently executable, what v31 would move to observation-only, the retained
controls, current route evidence, and the live flat/protection boundary.

## 2. Known facts and provenance

- Protocol declaration: `2026-08-09T18:44:02Z`.
- Source checkpoint: `2026-08-09T18:55:53.058605Z`.
- Source profile: exact v25 fingerprint
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- Candidate profile: exact v31 fingerprint
  `b8b330e0d8ee784e08236df41e2b218d2ab01ad2d6292ac6727d589ed040e91a`.
- The checkpoint, journal, source config, and candidate config are hash-pinned
  in the immutable baseline artifact.
- The tracker has no execution or transition authority.

Confidence in the identities: high. A hash mismatch, unknown run identity, or
authority-map mismatch makes the tracker fail rather than publish a fallback.

## 3. Baseline results

| Route | Planned v31 authority | Eligible | Resolved horizons | Closed | Net USD |
|---|---|---:|---:|---:|---:|
| SNDK Swing | Observe only | 1 | 4 | 1 | -1.0932 |
| BRENTOIL Swing | Observe only | 0 | 0 | 0 | unavailable |
| GOLD Swing | Executable control | 4 | 4 | 1 | -0.2424 |
| SNDK Breakout | Executable control | 0 | 0 | 0 | unavailable |
| GOLD Breakout | Executable control | 0 | 0 | 0 | unavailable |
| BRENTOIL Breakout | Executable control | 0 | 0 | 0 | unavailable |

These counts are cumulative from the start of the current v25 run. They are
not all post-declaration observations. The immutable baseline is the numeric
origin for later same-run deltas; a future v31 run receives a separate origin.

At baseline publication, five positions were open: ETH, HYPE, SOL, GOLD, and
SPCX. All five were reported protected, live faults were zero, and the
transition drain was inactive. Therefore the flat-boundary condition was not
met.

## 4. Analysis

The SNDK Swing result remains adverse and is consistent with the v31 proposal.
BRENTOIL has no live eligible or closed sample. GOLD Swing also has one losing
close, so retaining it is supported by historical common-clock evidence rather
than current live confirmation. Four eligible GOLD Swing signals but one close
also demonstrate why signal markouts, actual routed lifecycles, and shared
capital displacement must remain separate.

The baseline does not change the v31 recommendation. It improves observability:
future evidence can now identify whether removed-route losses were avoided,
whether positive opportunities were missed, and whether retained controls
behaved better under the same forward window.

## 5. Uncertainties and failure modes

- Current live samples are one-sided and extremely sparse.
- Cumulative v25 counters include observations before protocol declaration.
- Signal horizons are completed-candle diagnostics, not venue fills or PnL.
- Removing a route can expose another same-symbol intent; isolated route sums
  do not reconstruct that shared-capital path.
- The current open GOLD lifecycle is provisional and excluded from economics.

Confidence in route pruning remains medium. Repeated positive after-cost paths
on both removed routes, especially if retained controls remain negative, would
falsify the candidate. Continued adverse removed-route paths across both sides
would strengthen it but would not independently prove portfolio profitability.

## 6. Validation and next measurement

1. Refresh the bounded tracker from each new complete checkpoint prefix.
2. Create immutable snapshots only at material events: new eligible signal,
   resolved horizon, route close, new side, fault/protection change, flat
   boundary, or transition-state change.
3. Use immutable cohort audit deltas for same-run economic comparisons.
4. At a future v31 launch, require the two removed routes to appear only in the
   observe-only set before accepting the new baseline.
5. Do not compare cumulative v25 and v31 counters as though they were one run.

## 7. Recommendation

Continue v25 unchanged while its protected lifecycles remain open. Keep v31
inactive. The next operator decision remains the verified-flat transition, not
an automatic promotion based on this baseline.
