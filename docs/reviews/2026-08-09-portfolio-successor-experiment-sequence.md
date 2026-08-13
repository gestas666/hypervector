# Portfolio Successor Experiment Sequence

Status: report only  
Execution authority: none  
Automatic promotion: false  
Active runtime: `multi_asset_bidirectional_complete_portfolio_canary_v25`

## Problem restatement

The objective is not to select the largest historical winner. It is to construct
an aggressive shared-capital portfolio whose route-side signals survive venue
friction, remain useful outside one favorable interval, and can be monitored and
revised from reconciled live evidence.

The current v25 run is an evidence-generating cohort. V26, v28, and v29 are
retired forensic artifacts and grant no launch authority. A successor needs a
new source-bound generation, transition contract, current implementation backup,
append-only research revision, and renewed explicit live-risk authorization.

## Current facts

- The immutable v25 prefix contains 11 compatible-profile closes: 6 wins, 5
  losses, +$3.063513 net, profit factor 3.2811, and 0.3035% maximum drawdown.
- Those closes are distributed across different provider-symbol routes. They are
  not 11 samples of one strategy.
- No exact route has compatible-profile closes on both sides.
- Refreshed side-aware triage assigns 0 routes to PROCEED, 10 to REVISE, and 14
  unchanged exact contracts to STOP.
- SOL Range Onset is the only active exact route with supportive historical
  evidence for both long and short, but it has no compatible-profile close.
- ETH Pullback has one small long winner; its short evidence is contradictory.
- SPCX Swing has two long closes, +$0.91083 and PF 2.3866, but its development and
  validation side results conflict.
- The first post-cutoff HYPE-long candidate lost $0.330216 after costs. Mixed
  profile HYPE-long results remain slightly positive, while the exact deployed
  shape is negative historically.

## Sequence

### Stage 1: complete v25 without hot mutation

Preserve current route, risk, sizing, stop, hold, and order ownership while any
v25 lifecycle remains open. Continue recording fills, fees, funding, slippage,
regime context, route decisions, withheld opportunities, and venue protection.

Success evidence:

- one identity-bound v25 drain;
- all nine assets flat;
- no owned open orders;
- closed ledger reconciles with venue state;
- immutable final v25 audit and prefix delta.

Failure modes:

- inherited exposure;
- missing reduce-only protection;
- route or profile fingerprint drift;
- an open mark counted as a resolved trade.

### Stage 2: define a new source-bound successor generation

Do not launch or repurpose retired v26, v28, or v29. After the route experiments
below identify an exact candidate, assign a new generation and bind its current
configuration and implementation bytes. Create a fresh prestart backup at
transition time.

Acceptance evidence:

- new transition tests pass against current source and configuration;
- the first applicable HIP-3 decision reports numeric causal L2 imbalance;
- Swing decisions report numeric Heikin-Ashi and order-block directions when the
  causal source values are numeric;
- ledger, checkpoint, and TUI agree on route identity and readiness;
- every intended strategy, risk, sizing, and authority difference is explicit
  and source-bound rather than inherited from a retired profile.

Rollback:

- if any mechanical acceptance item fails, drain the new generation to flat,
  preserve its evidence, and follow its newly reviewed rollback contract; do not
  substitute a retired profile or compensate by changing another parameter.

### Stage 3: run three independent successor experiments

These experiments must not be pooled until their route-side behavior is
individually identifiable.

#### A. SOL canonical Range Onset, long and short

Preserve the hourly SMA cross and admitted 5-minute regime requirements. Record
both directions at current 5x leverage and existing notional authority. Do not
promote the relaxed `awaiting_hourly_sma_cross` challenger: its five-path result
was positive in aggregate but became negative after excluding the largest
winner.

Measure:

- actual after-fee/funding PnL and return on margin by side;
- entry and exit slippage;
- favorable and adverse excursion;
- time in position;
- missed canonical opportunities and portfolio displacement;
- profit factor and net result excluding the largest winner;
- non-adjacent time-window stability.

#### B. ETH Pullback mechanism split

Preserve the current precompression-pullback mechanic as the long reference.
Treat short as a distinct research mechanism rather than assuming the long rule
can be mirrored. Evaluate the current short path and separately report 5m/15m
context, compression state, directional body, cost clearance, and occupancy.

Do not turn regime alignment into a global veto. It is an explanatory and sizing
feature until same-route evidence demonstrates stable separation.

#### C. SPCX Swing mechanism split

Preserve the canonical pivot requirement and separate long and short results.
Do not promote the relaxed-pivot fixed-60-minute challenger; its first three
resolved long paths were all negative after modeled venue costs.

Continue reporting ignored HA-flip/alignment-loss exits. One large continuation
after an ignored exit is insufficient to replace the current lifecycle policy.

### Stage 4: construct the economic successor

Only exact route-side mechanisms supported by their own evidence enter the
successor interaction replay. STOP-exact-contract routes require a new mechanism
identity; changing an exit overlay or leverage does not repair a negative signal.

Portfolio replay must use:

- one shared capital balance;
- one position per asset;
- actual route priorities and occupancy conflicts;
- venue-specific fees, funding, slippage, depth capacity, and acknowledgement
  latency;
- chronological processing with no look-ahead;
- current isolated-margin and venue leverage constraints;
- both total performance and performance excluding the largest winner.

Aggressive scaling should first increase notional on a demonstrated route rather
than increase leverage globally. Leverage, stop distance, and notional must be
evaluated together because identical notional with more leverage changes margin
return and liquidation distance without improving the signal.

## Rejected immediate changes

| Change | Evidence | Decision |
|---|---|---|
| Portfolio-wide or HYPE profit lock | Rescues the latest HYPE loss but reduces mean HYPE normalized return across 13 lifecycles | Do not promote |
| Relax SPCX pivot blocker | 0 wins from 3 resolved paths, -163.77 bps total | Reject |
| Relax SNDK pivot blocker | First resolved path -21.02 bps | Keep report only |
| SOL continuation without a fresh onset | First resolved path -12.04 bps | Keep report only |
| Global regime-alignment gate | HYPE aligned and opposed cohorts both contain losses | Do not promote |
| Global leverage increase | No evidence that leverage repairs route expectancy | Reject |

## Review cadence and update rule

Review after every five new route-side closes or 72 hours, whichever occurs
first. This is an analysis cadence, not an automatic execution or performance
gate. Every review must publish an immutable prefix, exact route-side delta,
missed-opportunity matrix, and append-only journal revision.

The successor hypothesis strengthens when a route remains positive after actual
costs, outside one time block, and without its largest winner. It weakens when
costs consume the gross edge, opposing sides cancel the route, position occupancy
causes adverse selection, or a result depends on one event.

## Confidence

- High confidence that retired v26, v28, and v29 must not be launched because the
  current operator skill and regression test explicitly enforce that lineage.
- Medium confidence in prioritizing SOL Range, ETH Pullback, and SPCX Swing as the
  next mechanism experiments because each has some supportive evidence but lacks
  complete both-side live validation.
- Low confidence that any current route already establishes durable portfolio
  profitability. That claim would require additional resolved, route-matched,
  after-cost evidence.
