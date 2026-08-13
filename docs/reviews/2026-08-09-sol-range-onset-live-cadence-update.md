# SOL Range Onset Live Cadence Update

Status: observe canonical route  
Execution authority: none  
Runtime strategy changed: false

## Problem and result

The successor sequence ranked canonical SOL Range Onset as the strongest
historical both-side mechanism, but the aggressive portfolio also needs enough
opportunities to learn and compound. This update tests whether the route's zero
live trades came from router occupancy or from its own signal cadence.

The immutable v25 prefix through 2026-08-09 15:14:50 UTC contains 1,772 SOL
Range Onset evaluations and zero eligible signals. Because no eligible intent
existed, the open SOL position, account capacity, and provider priority could
not have suppressed a canonical Range Onset trade in this prefix.

The route remains a valid sparse research candidate, but it is not frequent
enough to serve as the portfolio's sole or primary growth engine.

## Causal evidence

- Observed v25 interval: 29.54 hours.
- Canonical SOL Range Onset evaluations: 1,772.
- Eligible signals: 0.
- Resolved signal horizons: 0.
- Canonical historical cadence: 42 trades over 201 covered days, approximately
  1.5 trades per week.
- Historical direction evidence: long and short were both positive after the
  accepted modeled costs, but long profit was concentrated in a few winners.
- Current compatible-profile SOL execution from other providers: two resolved
  long winners totaling +$2.264001 after actual costs.
- Current SOL lifecycle: open HT-Breakout long; its mark is provisional and is
  excluded from the resolved comparison.

Under a descriptive Poisson-rate approximation, the historical cadence implies
only 0.257 expected Range Onset trades in this 29.54-hour interval and a 77.3%
probability of zero. Regime clustering can violate the Poisson assumption, so
this calculation supports only the normal-sparsity diagnosis, not a forecast.

## Portfolio interpretation

The current SOL route set has two different jobs:

1. Canonical Range Onset supplies a sparse, historically supportive both-side
   hypothesis.
2. HT-Breakout and Hulk supply materially higher live decision and trade
   cadence, but their historical transfer evidence is contradictory and their
   current favorable SOL result is concentrated in two long trades.

Removing the cadence routes would make the portfolio slower without proving a
better economic outcome. Removing the Range Onset hourly cross would create a
different mechanism whose exact prior relaxation lost in prospective evidence.
Neither change is supported.

## Recommendation

1. Keep v25 and the current protected SOL lifecycle unchanged.
2. Keep canonical SOL Range Onset executable and unrelaxed.
3. Do not make Range Onset the exclusive SOL strategy in the successor.
4. Keep HT-Breakout and Hulk as separately attributed cadence routes at their
   current research scale; do not infer durable edge from the two SOL winners.
5. Run a source-bound, shared-slot priority interaction replay comparing the
   current flat-boundary order with a Range-Onset-first order. An already-open
   lifecycle must never be evicted by a later signal.
6. Measure accepted and displaced paths by provider, side, actual or adverse
   BBO cost, funding, MFE/MAE, net result, and result excluding the largest
   winner. Do not pool overlapping counterfactual paths as portfolio PnL.

The priority experiment is a router-selection study, not a signal relaxation,
entry gate, stop change, size change, or live promotion.

## Confidence and falsifiers

Confidence is high that occupancy did not suppress canonical SOL Range Onset
in the measured prefix because its eligible-signal count is exactly zero.
Confidence is medium that the zero count is consistent with historical cadence.
Confidence is low that the optimal SOL provider priority is known because the
current exact live evidence contains only two resolved long outcomes and no
canonical Range Onset lifecycle.

The no-suppression conclusion is falsified by an omitted eligible Range Onset
evaluation, a route identity mismatch, or a withheld canonical intent inside
the immutable prefix. The cadence interpretation updates when new eligible
signals arrive. The tiered-router recommendation weakens if time-aligned
shared-slot replay shows that cadence routes consistently displace superior
after-cost Range Onset paths, or if independent live cadence-route outcomes
become negative without concentration while Range Onset remains positive on
both sides.

## Evidence

- Current immutable audit:
  `data/logs/research/bidirectional_cohort/v25_live_audit_sol_occupancy_20260809T151445Z.json`.
- Prior canonical cadence and relaxation review:
  `docs/reviews/2026-08-08-v25-sol-range-cadence-and-relaxation.md`.
- Canonical historical direction review:
  `docs/reviews/2026-07-31-sol-range-onset-direction-stability.md`.

No live process, route, order, position, stop, target, size, allocation,
priority, transition drain, or protection changed in this analysis.
