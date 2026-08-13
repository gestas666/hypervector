# Lean successor portfolio comparison

## Objective

Falsify a smaller successor portfolio before changing the active v25 runtime.
The comparison must isolate the marginal contribution of ETH pullback, ETH
dual-MTF Range Onset, and SPCX Swing/HA around a canonical SOL Range Onset
control. It is report-only and has no execution, transition, sizing, or
promotion authority.

## Fixed contract

- Initial account: `$500`.
- Maximum positions: three, with one position per asset.
- Leverage and notional: SOL `$75` at `5x`, ETH `$25` at `5x`, SPCX `$75`
  at `5x`.
- Directions: long and short outcomes remain eligible and separately reported.
- Crypto friction: existing `13 bps` round trip is nominal; stress applies the
  fixed `7 bps` incremental haircut required to reach `20 bps`.
- SPCX friction: use the immutable HIP-3 nominal and stress lifecycle rows.
- No parameter sweep, route-side gate, capital gate, or sealed holdout access.

## Fixed variants

1. `sol_range_control`: SOL Range Onset only.
2. `sol_range_spcx`: add SPCX Swing/HA.
3. `sol_range_spcx_eth_pullback`: add the exact ETH pullback route.
4. `sol_range_spcx_eth_dual_mtf`: add ETH Range Onset with the exact
   `dual_mtf_not_opposed` context policy.

## Evidence windows

- Development common window: entries from `2026-06-13T03:15:00Z` through
  `2026-07-05T12:00:00Z`, half-open.
- Opened final common window: entries from `2026-07-06T00:15:00Z` through
  `2026-07-21T00:30:00Z`, half-open.
- Full opened source history remains descriptive because route coverage begins
  on different dates.

## Required outputs

- Nominal and stress shared-account reports for every window and variant.
- Route, side, rejection, drawdown, concentration, and largest-winner-excluded
  attribution.
- Marginal deltas versus the SOL-only and SOL-plus-SPCX controls.
- Immutable source hashes and current implementation hashes.
- Explicit limitations and `execution_authority = none`.
- A research review and append-only journal revision after validation.

## Validation

1. Unit tests prove one-position-per-asset arbitration and the exact 7-bps
   stress transformation.
2. Script tests bind the fixed variants, windows, route identities, and local
   immutable sources.
3. Focused tests, Ruff, whitespace checks, and line/function-size checks pass.
4. Artifact equity reconciles exactly to accepted lifecycle PnL.
5. The active v25 PID, run ID, profile fingerprint, positions, and venue stops
   remain unchanged by the report-only command.

## Decision boundary

The artifact reports results rather than silently aborting a trial. A future
profile decision should prefer a route only if its marginal after-cost result
is positive under nominal and stress evidence, remains positive without its
largest winner, represents both directions where the source produced them, and
does not depend on a source or implementation identity mismatch. These are
explicit research criteria, not runtime gates.
