# Hypervelocity peak activation 7% sensitivity

Date: 2026-07-29
Status: predeclared, report-only sensitivity

## Hypothesis

The source-exact Tier-0 rule activates at +6% gross margin PnL and locks 55% of
the observed peak. On the completed development blocks it reduced liquidation
and worst drawdown, but clipped 11 trades that later reached the +8% target and
reduced aggregate reset-block PnL by $1,675.78.

Raise only the activation threshold from +6% to +7%. Keep the 55% lock,
0.05%-of-entry minimum stop move, 60-second update cooldown, entry stream,
fees, funding, target, allocation, leverage, and causal mark/BBO semantics
unchanged. The known April 11 reversal reached +7.152% before liquidation, so
this threshold can still address that development failure while reducing the
window in which eventual +8% targets can be stopped early.

This is not an exact upstream Tier-0 setting. It is a one-parameter sensitivity
derived from development evidence and must be labeled accordingly.

## Evidence boundary

The April 18-28 archive remains candidate-unseen at declaration time. Testing
both +6% and +7% on that block creates a two-candidate holdout, so results must
be reported with that multiplicity limitation. No threshold may be changed
after those results are inspected.

## Acceptance and falsification

- Development aggregate PnL must exceed the +6% challenger and be non-inferior
  to control while retaining a meaningful drawdown or liquidation improvement.
- April 18-28 must be positive and non-inferior to control.
- Entry identities and counts must be exact across control and challenger.
- Any failure rejects activation 7 for promotion. Passing remains insufficient
  for live authority and requires fresh shadow validation.

