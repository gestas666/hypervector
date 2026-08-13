# BTC Hulk money-flow relaxation forward observer

**Frozen:** 2026-08-05 11:50 EDT / 15:50 UTC  
**Execution authority:** none  
**Live strategy changed:** no

## Problem and hypothesis

The live portfolio has favorable but sparse HYPE breakout evidence and two
positive BTC Hulk closes. It still lacks a second independently supported,
repeatable provider. The live opportunity matrix identified exactly two
pre-cutoff BTC Hulk paths withheld only because `money_flow_not_aligned`; both
finished positive at the fixed 60-minute research horizon for a combined
`+78.8032 bps`. The largest path supplied `85.45%` of absolute contribution,
so those observations are hypothesis formation rather than forward evidence.

The provisional hypothesis is that relaxing only the Hulk money-flow blocker
may increase BTC opportunity frequency without discarding the remaining Hulk
structure. This hypothesis is deliberately frozen before any post-cutoff path
is inspected.

## Immutable prospective contract

| Field | Frozen value |
|---|---|
| Experiment | `v9-btc-hulk-flow-fixed` |
| Candidate identity | `btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1` |
| Source provider | `hulk_expansion_bidirectional_tuned_v2` |
| Symbol and sides | BTC, long and short |
| Single relaxed blocker | `money_flow_not_aligned` |
| Cutoff | `2026-08-05T15:50:00Z` (`1785945000000` ms) |
| Entry proxy | first recorded BBO at/after routing publication |
| Exit proxy | first adverse BBO at/after 60 minutes |
| Stop proxy | 75 bps, matching the deployed structural-stop upper bound |
| Target proxy | none |
| OPI cohort | all; no OPI threshold fitted |
| Notional | `$25` |
| Minimum spacing | 75 minutes |
| Friction | recorded BBO, Hyperliquid taker fees, exact hourly funding |

The observer also records portfolio compatibility. A path is deployable only
when BTC was flat, the shared portfolio had capacity, and no same-cycle route
already owned BTC. Non-deployable paths remain mechanism evidence and are not
added to portfolio results.

## Validation and interpretation

The focused test first failed because the experiment identity did not exist.
After implementation, the complete forward-observer script suite passed 20
tests. A one-shot baseline published
`awaiting_fresh_post_cutoff_candidate`, zero attempts, and zero outcomes. This
proves that the two discovery paths did not leak into prospective results.

The recurring observer is launchd-managed as
`com.hypervector.btc-hulk-flow-challenger` and writes
`data/runtime/bidirectional_cohort/latest_btc_hulk_flow_challenger.json` every
five minutes. It is report-only and has no exchange client or operator inbox.

Ten deployable resolved paths are an early review milestone, not an execution
or trial-abort gate. Twenty to thirty non-overlapping deployable paths across
multiple market states would provide materially stronger evidence. Positive
net return and PF above one would keep the hypothesis alive; negative net
return, PF at or below one, or material outcome concentration would weaken or
falsify it. Results remain reported under the project charter regardless of
performance.

## Risks and failure modes

- Recorded BBO estimates executability but does not prove a real IOC fill.
- The fixed 60-minute exit isolates entry quality; it is not the deployed Hulk
  target/stop/maximum-hold lifecycle.
- A 75-bps proxy stop is intentionally conservative relative to the structural
  20–75 bps source range and can understate tighter-stop performance.
- Sparse paths, one-sided markets, or a single dominant move can create a false
  appearance of edge.
- BTC overlap with another live provider can make attractive mechanism paths
  non-deployable in the shared portfolio.

An outcome timestamp before the frozen cutoff, any order or strategy mutation,
inclusion of a blocker other than `money_flow_not_aligned`, a non-BTC symbol,
or failure to distinguish deployable from overlapping paths would falsify the
observer contract. Confidence is high that the observer is causally frozen and
execution-incapable; confidence in the trading hypothesis is low until forward
paths resolve.
