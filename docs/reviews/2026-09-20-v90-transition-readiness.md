# V90 transition and sizing review — corrected proposal

Date: 2026-09-20. Execution authority: none. This review does not activate V90.

September 21 update: the drain completed at 14:00:20 UTC; unsigned venue
preflight at 14:22:35 UTC confirms zero positions/orders and reconciled ledgers.
This satisfies the maintenance scheduling boundary, not V90 approval. Review
`2026-09-21-recent-trade-giveback.md` for confirmed SOL, BRENTOIL and SNDK profit
retracements; monitoring repairs do not alter the exit-policy behavior.

## Decision and confidence

**High confidence in the identified operational defects and their local regression
coverage. Low confidence in forward return, the exact uptime trade multiplier,
or current execution quality at enlarged notional.** The operator authorized
monitoring/capture implementation when flat, followed by this proposal review and
code review. That maintenance authorization is separate from selecting V90's new
allocation.

The September 21 protected candidate supersedes the unprotected allocation.
See `2026-09-21-v90-profit-protection-readiness.md` for the amended exit contract,
27-trade delayed-exit comparison and fresh unsigned sizing/depth snapshot.

The candidate loads with fingerprint
`b34fd819076cd8b0cf143d9d4cae9a0e6637a508daf2ed35f6570cfb245025d2`.
The pending approval's profile identities and retirement mappings match the
candidate and V89. Pending status must continue to be rejected by live transition
validation. Recompute evidence hashes after any document change.

## Corrected findings

1. The original watchdog crashed on the observer's standard unavailable payload
   (`markets: null`) and could report malformed fresh JSON as healthy. Monitoring
   must validate availability, lifecycle, schema and embedded observation times.
2. The original restart allowance was in memory. Launchd could restart the
   supervisor after give-up and reset its allowance. Durable, command-bound
   accounting and terminal holds address this; every launch is charged before
   spawning, including launches interrupted by supervisor failure.
3. Editing a plist and calling `kickstart` does not reload its registered
   definition. Boot out/bootstrap and inspect exact registered arguments. The
   supplied live supervisor remains V89; changing it to V90 is a separate explicit
   transition with verified backup, approval and flat/order-free reconciliation.
4. The old observer did not retain premium/oracle history. The capture extension
   uses the same context response, records the complete returned xyz universe,
   keeps nulls distinct from zero, labels timestamps as local receipt times and
   appends daily durable history. Premium/oracle fields also exist on core perps;
   their existence alone does not establish a HIP-3-specific trading edge.
5. The reported 3.06x ratio mixes entries/day with closes/day over different
   periods. It is not a validated estimate of the effect of restoring uptime.
   Measure matched entry rates, downtime and missed eligible opportunities before
   forecasting a multiplier. Watch/observer installation alone provides no
   automatic backend restart.

## Intended-size liquidity experiment

Ran the existing read-only liquidity profiler at $500, $1,950, $2,600 and $3,500
notional against `data/research/hip3_market.duckdb`. Output:
`data/logs/research/v90_review_sndk_depth_20260920.json`, SHA-256
`f18b9717ecda922c59b989ca65f0a0263e2c6460f98bc0a0664419a706a65e16`.

The sample ends **2026-08-06**, 45 days before this review. It contains 43,754
book snapshots accepted under the 15-second boundary-delay limit. These are
historical visible-depth measurements, not current fills or fill probabilities.
Fees, funding, latency and adverse selection are excluded.

| SNDK notional | Both sides fully covered by visible depth | Buy cost p99 | Sell cost p99 | Round-trip visible cost p99 |
| --- | ---: | ---: | ---: | ---: |
| $500 | 99.9954% | 31.40 bps | 31.20 bps | 59.94 bps |
| $1,950 | 99.9177% | 42.64 bps | 42.57 bps | 79.16 bps |
| $2,600 | 99.8514% | 46.50 bps | 46.61 bps | 85.62 bps |
| $3,500 | 99.7417% | 49.53 bps | 51.29 bps | 90.80 bps |

The proposed SNDK size is 3.9x the current $500 cap at the plan's reference
equity. The screen's $500 cost assumptions do not validate that increase. Fresh,
entry-time and exit-time depth/fill observations could update this assessment.
These results are reported evidence, not a newly imposed trading gate.

The original suggested depth command supplied only some fee options; the CLI
requires the complete fee evidence bundle or none. This experiment deliberately
omitted all fee options so that depth could be measured without inventing fees.

## Options and trade-offs

| Option | Benefit | Cost / uncertainty |
| --- | --- | --- |
| Leave operations unchanged | No deployment | Known observer outage and restart defects remain |
| Repair operations at V89 sizing | Isolates availability improvements; preserves current allocation | Existing strategy evidence remains weak; trade multiplier unknown |
| Adopt V90 at a verified boundary | Reallocates capacity and increases SNDK size | Simultaneous route, leverage and sizing changes confound attribution; enlarged-size execution and edge unvalidated |

September 21 status: read-only operational repairs are deployed and verified.
The backend remains stopped for the operator-requested profit-protection review.
Evaluate protected V90 as an explicit allocation decision using the corrected record.
This is a recommendation, not an automatic risk or performance gate. Reduced
leverage at fixed notional requires more collateral; it is not free exposure.

## Required operational evidence and falsifiers

Before treating rollout as accepted, retain: fresh flat/order-free unsigned venue
reconciliation; exact source/plist backups; registered launch arguments; current
profile identity; restored roster observations; at least two context samples and
history retained after observer restart; durable budget and operator-stop tests;
and full-diff code review results. No armed backend is killed for acceptance.
A duplicate owner, a restarted terminal hold, malformed data reported healthy,
missing research history, or signing capability in an observer falsifies acceptance.

The local flat checkpoint is a scheduling signal only. Positions and orders must
be read again immediately before the operational handoff. No liquidation,
market-close or strategy change is authorized merely to reach that boundary.
