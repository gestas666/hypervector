# Venue-native 1m order-flow impulse development plan

Status: implementation pending  
Execution authority: none  
Live mutation: prohibited

## Objective

Test whether a completed one-minute same-asset price impulse, supported by
public-trade flow and causal terminal L2 state, contains enough short-horizon
movement to survive measured Hyperliquid friction. This is distinct from the
rejected five-minute expected-return, cross-asset propagation, and aggressive
flow-exhaustion contracts.

## Frozen development contract

- Assets: BTC and SOL only. ETH and HYPE remain unavailable for historical L2
  inference until their archive coverage is acquired and validated.
- Scored interval: `2025-07-28T00:00:00Z` through
  `2026-01-28T00:00:00Z`.
- Warmup: 10,080 completed one-minute bars.
- Decision time: source-bar open plus one minute.
- Entry: next one-minute open with two adverse basis points of modeled
  slippage.
- Exit: 30-bps target, 20-bps stop, or 15-minute maximum hold. If target and
  stop touch in one bar, the stop wins.
- Nominal round-trip friction: 13 bps, comprising 9 bps taker fees and 4 bps
  adverse slippage.
- Stress round-trip friction: 20 bps.
- Official funding is applied when an hourly funding event falls inside a
  lifecycle.
- One position per symbol; overlapping later events are recorded as displaced.
- Both long and short outcomes are retained.

## Predeclared event family

A base event requires:

1. absolute one-minute close-to-open return at or above its prior seven-day
   90th percentile;
2. public-trade volume at or above its prior seven-day 75th percentile; and
3. signed public-trade flow aligned with the completed price move.

Every base event produces these fixed, fully reported arms:

1. `continuation_all`: trade in the completed price direction;
2. `continuation_l2_aligned`: continuation only when at least two of terminal
   depth imbalance, microprice displacement, and one-minute depth-imbalance
   change agree with the move;
3. `reversion_all`: trade opposite the completed price direction; and
4. `reversion_l2_opposed`: reversal only when at least two L2 components oppose
   the completed move.

No nearby threshold sweep is permitted in this development pass. L2 variants
that reduce cadence remain reported rather than treated as technical failures.

## ML challenger boundary

Ridge and shallow LightGBM are annotation-only. They may rank the fixed base
events using decision-time features under outcome-time-purged expanding
walk-forward folds. Models do not receive execution, filtering, sizing, or
promotion authority. All predictions and negative results remain serialized.

## Validation requirements

- Prefix-invariance test for feature and event rows.
- Future-book rejection test.
- Next-bar entry and pessimistic same-bar barrier tests.
- Exact nominal/stress friction tests.
- Funding-direction test.
- Per-symbol occupancy and side-attribution tests.
- Immutable JSON report and Parquet event sidecar with SHA-256 identities.
- Review and append-only research-journal revision.

## Decision rule

The experiment reports every valid result. A route is recommended for a later
shared-account successor replay only if its after-cost behavior is positive
across non-adjacent walk-forward folds, is not dependent on one winner, and
retains both adequate event coverage and implementation parity. Failure to meet
that recommendation rule is an economic result, not a technical abort.

## Failure modes and falsifiers

The result is invalid if a feature uses a book or trade after decision time,
entry uses the signal bar, a missing market minute is silently filled, funding
direction is inverted, overlapping signals are double-counted, source bytes
change, or live execution is mutated. A weak development result does not prove
all order-flow alpha absent; it rejects only this frozen family.
