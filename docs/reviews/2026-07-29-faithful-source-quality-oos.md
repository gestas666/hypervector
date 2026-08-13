# Faithful source-quality out-of-sample review

Date: 2026-07-29

## Problem and acceptance criterion

This review tests whether exact current-source regime agreement, removal of
source `*_WEAK_CHOPPY` states, a four-minute minimum source-state age, or a 25%
gross-margin emergency stop can repair the faithful Hypervelocity entry stream.
All candidates remain report-only. Runtime strategy, TUI behavior, faithful
configuration, and observe-only ML authority are unchanged.

The development window is 2025-10-23 through 2025-11-15 UTC. The independent
falsification window is 2025-08-01 through 2025-09-09 20:00 UTC. A candidate
must reproduce positive execution economics and materially improve drawdown on
the independent, gap-free window. Relative loss reduction alone is not a pass.

## Causal and configuration corrections

Two replay defects were corrected before this comparison:

- Source labels are now computed with all strictly prior bars available while
  decisions remain bounded to the requested interval. No future bar is loaded.
- The replay now uses the faithful runtime's one-bar, 60-second re-entry
  cooldown. An inherited 300-second research cooldown was removed.

The independent run loaded 5,760 prior causal bars, evaluated 57,360 bars, and
loaded zero future bars. Its 956 hourly bundles contain 6,293,000 L2 snapshots
and 11,120,525 deduplicated public trades, with verified checksums and zero
empty book or trade windows. Execution economics are conclusive under the
public trade-through maker-fill model; private queue position remains
unobservable.

## Development results

| Candidate | Fills | Targets | Liquidations | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Strict source control | 45 | 38 | 7 | $2,239.51 | -89.71% |
| Minimum source-state age 4m | 44 | 38 | 6 | $3,551.73 | -84.91% |
| Exclude `*_WEAK_CHOPPY` | 35 | 32 | 3 | $11,016.56 | -62.58% |

The weak/choppy exclusion was the only marginally profitable aggregate. It was
not temporally stable: two fixed slices won and two lost. Because the rule was
selected after inspecting this block, it required independent falsification.

The separate strict-control 25% stop comparison ended at $2,289.65 versus
$2,239.51 without a stop. It replaced seven liquidations with fourteen stops
and reduced drawdown from -89.71% to -82.63%, but every fixed weekly segment
lost. It is rejected as a profitability repair.

## Independent result

| Candidate | Fills | Targets | Liquidations | Target rate | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Strict source control | 73 | 61 | 12 | 83.56% | $502.48 | -98.52% |
| Minimum source-state age 4m | 60 | 51 | 9 | 85.00% | $1,605.43 | -95.38% |
| Exclude `*_WEAK_CHOPPY` | 59 | 50 | 9 | 84.75% | $1,622.00 | -92.02% |

The weak/choppy exclusion and state-age delay reduced damage relative to the
control but lost approximately 84% of initial equity. For the weak/choppy
candidate, five of six fixed chronological slices lost and the one winning
slice occurred last. The predeclared independent criterion therefore fails.

## Assessment and recommendation

High confidence for this replay window: none of the tested source-quality,
timing, or stop variants establishes positive execution economics. That claim
would be updated by an identified defect in causal timing, archive integrity,
fee, funding, liquidation, position sizing, or fill accounting. Public replay
cannot validate private maker queue rank, but queue uncertainty is not a sound
basis for promoting a candidate that loses 84% to 95% under trade-through.

Low confidence that the earlier $11,016 result represented a durable edge. It
failed on the first independent window and is treated as development selection
luck rather than a promotable configuration.

Do not continue threshold-tuning the same entry stream. Finish the one-year
Hyperliquid archive and exact gap audit, then compare materially different,
predeclared entry hypotheses across multiple purged chronological folds. Keep
ML annotation-only until the resolved venue-matched population meets the
existing class and fold requirements. The missing size and exit reason of the
creator's four reported losses remains a major source-fidelity uncertainty.

## Immutable artifacts

- Development quality/timing comparison:
  `3927d74da533f489a25cd9f31566346917b37229ae000b44cee02ee5d2d77c55`.
- Independent quality/timing comparison:
  `81b0c7f92ddece9a5649d5048b66355b4891c166d0f345995b039d59ed6e700e`.
- Development 25% stop comparison:
  `132bf59018885e3b4fa10c32480e5cc86377629b5251ef7f5a8fad3c3e436cf6`.
