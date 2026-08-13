# SOL aligned forward evidence — data-quality review

**Observed:** 2026-08-05 06:56 EDT  
**Decision use:** decide whether the inactive
`sol_aligned_range_relaxed_fixed60_bidirectional_v1` provider is trustworthy
enough for the next-flat canary profile.  
**Source:**
`data/runtime/bidirectional_cohort/latest_sol_aligned_range_challenger.json`

## Dataset and grain

The intended grain is one causally selected, non-overlapping SOL candidate
attempt per unique provider `decision_time_ms`. Entry and exit prices are
adverse recorded Hyperliquid BBO estimates, not venue fill confirmations. The
candidate is report-only, uses a fixed 60-minute horizon, $75 notional, taker
fees, observed funding, and a 75-minute accepted-entry rearm.

The final artifact contains five resolved attempts. All five were
portfolio-compatible flat-SOL entries and all five were long.

## Checks performed

| Check | Evidence | Result |
|---|---:|---|
| Candidate-key uniqueness | 5 rows, 5 unique decision times, 5 unique entry times | Pass |
| Required-field completeness | 0 rows missing decision, book, availability, entry, side, or portfolio class | Pass |
| Causal timestamp order | 0 decision/book/availability/entry ordering violations | Pass |
| Entry latency | 21.123–31.515 seconds versus 60-second maximum | Pass |
| Book-context age | 3.740–4.568 seconds versus 30-second maximum | Pass |
| Resolved exit latency | 2.055–3.806 seconds after fixed-hour boundary versus 30-second maximum | Pass |
| Rearm spacing | 76, 125, 76, and 86 minutes versus 75-minute minimum | Pass |
| Portfolio conflicts | 0 capacity, position-state, or same-cycle route conflicts | Pass |
| Source tail integrity | 0 dropped bytes; no incomplete cohort or asset tail | Pass |
| Funding completeness | 8 hourly rows covering 03:00–11:00 UTC | Pass |
| Multi-timeframe regime lineage | 5/5 resolved rows retain 1m, 5m, and 15m states after repair | Pass |
| Direction coverage | 5 long attempts, 0 short attempts | Incomplete |
| Final after-cost result | 3W/2L, -11.5866 bps, PF 0.7959 | Fails promotion hypothesis |

## Findings

### High — no short-side evidence

The frozen contract is bidirectional, but every selected attempt is long. The
final 3W/2L, -11.5866-bps, PF 0.7959 result fails to establish even the
observed long path as positive after cost. It also does not establish symmetric
short behavior.

### Medium — execution remains an estimate

The replay uses adverse recorded BBO, exact observed fee geometry, funding, and
capacity checks. This is stronger than candle-only simulation but weaker than a
venue order acknowledgement and fill. Public top-level liquidity can cancel
between observation and an IOC reaching the venue. The first canary fill must
be compared against the modeled 21–32-second candidate-entry delay and actual
venue acknowledgement/slippage.

### Medium — evidence is concentrated in 5m RANGE

After preserving the backend-authored decision-time tuple, all five resolved
attempts classify as `5m RANGE` and `15m RANGE`; 1m states were one
`TREND_DOWN`, two `RANGE`, and two `TRANSITION`. Their five-minute stance is
neutral rather than trend aligned. This identifies the candidate correctly as
an OPI-aligned range strategy, but the final aggregate is negative and does not
support execution promotion or extrapolation into breakout or trend regimes.

### Medium — sample size and concentration remain fragile

Only five outcomes are resolved and the largest absolute outcome contributes
41.9% of absolute return. The fifth path demonstrates the fragility directly:
its -42.7667-bps net result moved the aggregate from +31.1801 bps and PF 3.2251
to -11.5866 bps and PF 0.7959. The statistics are descriptive, not a forecast
or a reason to stop continued report-only observation.

### Resolved defect — decision-time regime state was dropped

`evaluation_candidates()` previously copied readiness metrics but omitted the
top-level `primary_regime`, `state_1m`, `state_5m`, and `context_15m` fields.
Consequently the artifact reported 0/4 five-minute coverage and lost the rest
of the regime tuple even though the backend had classified every decision. The
transform now preserves all four exact states and rejects conflicting duplicate
fields. Focused signal, execution, forward-report, and provider validation
passed 54 tests. Every live report-only challenger was rotated onto the
corrected transform; the SOL artifact now reports complete 5/5 coverage. The
TUI projection also retains and renders the 1m/5m/15m/primary tuple for generic
challengers instead of requiring HYPE-specific volume fields.

## Temporal and source observations

- Five attempts are correctly separated by at least the frozen 75-minute
  rearm; no duplicate or overlapping selected entry was found.
- The asset and cohort snapshots had stable complete tails at publication.
- The artifact refreshed after the fifth fixed-hour boundary with no pending
  rows. Future pending rows must not be counted as wins, losses, PnL, or profit
  factor.

## Recommendation

Remove the candidate from the inactive next-flat execution profile because its
predeclared PF-at-or-below-one falsifier occurred. Keep the frozen report-only
observer running so later long and short outcomes can update the hypothesis.
Preserve exact RANGE attribution, L2 alignment, fee/funding audit, and
flat-entry compatibility in the research journal.

Do not pool this candidate with the retired broad range-onset strategy and do
not live-test it merely to rescue a failed five-trade aggregate. A future,
separately frozen revision would need a causal mechanism change and new forward
evidence; additional observations of the unchanged rule remain diagnostic.

## Falsifiers and automated checks

- Net PF at or below one on fresh deployable outcomes. **Observed at N=5.**
- A short-side sequence that contradicts the long-only observation.
- Any selected row missing a decision-time regime field that the backend
  supplied, or any duplicate regime field that disagrees with the canonical
  top-level value.
- Duplicate decision identity, causal timestamp reversal, stale book beyond 30
  seconds, entry beyond 60 seconds, exit beyond 30 seconds, rearm below 75
  minutes, same-cycle route conflict, or non-flat SOL entry.
- Real canary friction materially exceeding the modeled fee and BBO path.

The new unit tests automate preservation and conflict rejection for the full
decision-time regime tuple. Existing forward-replay tests cover causal timing,
portfolio compatibility, fee/funding inclusion, top-level capacity, and
report-only authority.

## Assumptions

- Backend event timestamps are the authoritative decision clock.
- Recorded Hyperliquid BBO is valid observation evidence but not proof of a
  fill.
- The current user authorization covers activation only after an independently
  verified flat/no-orders boundary; this report removed one proposed route and
  has no activation authority.
