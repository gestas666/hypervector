# v25 SOL range cadence and relaxation reconciliation

Date: 2026-08-08

## Problem restatement

Determine why the historically supportive bidirectional SOL range-onset route
has not executed in the active v25 run, whether routing suppressed a valid
signal, and whether removing its hourly-cross condition with aligned L2 order
pressure is a coherent successor mechanic.

Success requires causal live evidence, explicit after-cost execution estimates,
side attribution, concentration measurement, and preservation of the already
frozen forward decision for the exact aligned-range variant. This review is
report-only and does not change v25.

## Canonical v25 route diagnosis

- The immutable prefix spans 12.387 hours, from 09:42:42Z through 22:05:55Z.
- SOL range-onset received 744 provider evaluations and produced zero eligible
  signals. Its only blockers were `5m_regime_not_admitted` and
  `awaiting_hourly_sma_cross`.
- No eligible range intent reached routing, so account capacity, priority, and
  same-coin occupancy did not suppress a canonical SOL range trade.
- The accepted historical cadence is 42 trades over 201 days. Under a simple
  Poisson rate approximation, this live prefix contains 0.108 expected trades
  and an 89.8% probability of zero trades. This approximation is descriptive;
  clustered regime arrivals may violate the Poisson assumption.

Confidence is medium that the zero-trade result is normal event sparsity rather
than a routing defect. An eligible canonical SOL range intent that is withheld
for an undeclared reason, or a verified hourly cross absent from provider
telemetry, would falsify that assessment.

## Current one-blocker execution matrix

Official Hyperliquid funding was refreshed for all nine v25 assets over the
complete 09:00Z-to-23:00Z half-open window. The immutable 60-minute matrix uses
adverse recorded BBO, taker fees, observed funding, the configured $75 notional,
and the 60-bps stop proxy.

For SOL range-onset without only `awaiting_hourly_sma_cross`:

| OPI cohort | Resolved | W/L | Net bps | PF | Net excluding largest winner | Sides |
|---|---:|---:|---:|---:|---:|---|
| Aligned | 4 + 1 pending | 3/1 | +37.6079 | 14.8144 | +9.9882 | 4 long / 0 short |
| Opposed | 4 + 1 pending | 3/1 | +15.5390 | 2.1093 | -12.6333 | 4 long / 0 short |
| All | 5 + 1 pending | 3/2 | +26.6504 | 2.5806 | -1.5219 | 5 long / 0 short |

The aligned cohort is the only one positive after removing its largest winner.
It remains four resolved all-long BBO estimates from one 12-hour market window.
The cohorts overlap and cannot be added as portfolio returns.

## Superseding exact-mechanic evidence

The aligned relaxation is not a new idea. The exact frozen provider
`sol_aligned_range_relaxed_fixed60_bidirectional_v1` additionally used a
75-minute accepted-entry rearm. Its later prospective evidence supersedes the
stale N4 positive scorecard:

- 9 portfolio-deployable paths, all long;
- 4 wins / 5 losses;
- -113.0855 bps after costs;
- PF 0.3472;
- largest absolute contribution fraction 33.24%.

The append-only journal already rejects that exact provider for execution. The
new generic matrix is not identity-equivalent because it selects non-overlapping
source-route paths rather than reproducing the provider's accepted-entry clock.
It therefore cannot rescue or silently reactivate the rejected mechanic.

The current scorecard now projects `prospective_rejected_n9` from
`docs/research-journal/sol-aligned-range-v1.json`; it no longer advertises the
earlier N4 gain.

## Recommendation and alternatives

| Option | Evidence | Decision | Trade-off |
|---|---|---|---|
| Keep canonical SOL range in v25 | Both historical sides positive; no live eligible event yet | Continue unchanged | Sparse, but no evidence of technical suppression |
| Reactivate aligned fixed-60 v1 | Exact prospective N9 is materially negative | Do not reactivate | Avoids recycling a falsified identity |
| Remove hourly cross without OPI | Current endpoint evidence is fragile or negative after concentration | Do not implement | More trades, but weaker causal selectivity |
| Design a genuinely new SOL mechanism | Requires new causal input or exit logic, identity, cutoff, and both-side evidence | Continue research | Slower than parameter relabeling, but empirically distinguishable |

Good enough for a new successor experiment means a new mechanism identity,
complete current-source backup, independently frozen cutoff, after-cost BBO or
venue-fill evidence, both-side attribution, positive result excluding the
largest winner, and no implementation/routing mismatch. It does not mean a
single favorable prefix or aggregate bar PnL.

## Validation evidence

- Immutable v25 audit:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_directional_evidence_20260808T220554Z.json`.
- Immutable execution matrix:
  `data/logs/research/bidirectional_cohort/v25_execution_opportunity_matrix_exlargest_20260808T2216Z.json`.
- Exact rejection journal:
  `docs/research-journal/sol-aligned-range-v1.json`.
- N9 decision review:
  `docs/reviews/2026-08-05-forward-challenger-portfolio-resolution.md`.
- The opportunity-matrix and scorecard tests failed for the missing fields and
  stale N4 state before implementation, then passed. Nineteen focused tests,
  Ruff lint, Ruff format, file-size, and function-size checks pass.

No live process, route, order, stop, target, position, size, allocation, drain,
or protection changed. Confidence is high that the scorecard correction matches
the append-only N9 journal, medium for the canonical cadence diagnosis, and low
that the current four-path aligned gain represents forward edge. A hash
mismatch, side mismatch, exact-provider parity proof, or independent both-side
positive evidence would update the corresponding claim.
