# HIP-3 early-adverse HA-flip exit experiment

Date: 2026-08-09
Status: preregistered before experiment execution
Execution authority: none

## Objective

Test whether commodity Swing/HA can avoid failed-onset losses without the
turnover and premature-exit damage observed under unconditional HA-flip
honoring.

## Fixed hypothesis

For hip3_swing_ha_sndk_gold_brent_bidirectional_v1 only, honor a side-specific
HA-flip exit when all three conditions are true at a completed 15-minute bar:

1. no more than eight bars have elapsed since executable entry;
2. maximum favorable excursion since entry is below 20 bps; and
3. current directional close return is at or below -13 bps.

The exit remains close-known and executes at the next adverse modeled open.
The fixed 80-bps stop, 24-hour maximum hold, opposite-intent close, position
size, leverage, fees, funding, and slippage remain unchanged.

## Parameter provenance

- Eight bars equals a two-hour failed-onset window and is not selected from a
  parameter surface.
- Twenty bps represents a meaningful favorable excursion above the roughly
  13-bps nominal round-trip hurdle used in current live opportunity analysis.
- Thirteen adverse bps requires the trade to be beyond that same cost hurdle;
  the policy is not a profitable-position trailing stop.

The rule is post-SNDK development research. The SNDK live loss motivates the
mechanism but cannot be counted as independent confirmation.

## Comparison

Evaluate three exact arms from identical source bars and provider recipes:

- ignore all provider exits, matching the deployed lifecycle policy;
- honor all provider exits, matching the rejected v1 challenger; and
- early_adverse_8bar_mfe20_adverse13, the new fixed mechanism.

Report development and validation separately, nominal and stress friction,
each asset, each side, turnover, net PnL, PF, drawdown, fees, funding, stop
count, signal-exit count, and net result excluding the largest winner. Preserve
the existing chronological holdout as sealed and uninspected.

## Validation and failure modes

Implementation must:

- preserve default shared-simulator behavior when conditional-exit fields are
  unset;
- calculate age, MFE, and current adverse return only from information known
  at the signal bar close;
- execute an admitted exit no earlier than the next modeled open;
- reject negative, non-finite, or internally inconsistent parameters;
- retain all failing result cells rather than aborting on performance; and
- publish immutable source identities with no runtime or execution authority.

The mechanism is weakened by negative validation stress net/PF, materially
worse drawdown, result concentration in one winner, missing either side, or
large turnover growth without after-cost improvement. It is strengthened by
consistent validation improvement over ignore and unconditional honor across
assets and sides, including after removing the largest winner.

No result automatically changes v25, v30, an order, a position, a route,
leverage, sizing, or a research-journal decision.
