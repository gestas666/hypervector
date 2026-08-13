# Hypervelocity Mature-Episode Continuation Plan

**Status:** Completed and falsified as a sufficient repair; research-only.

## Goal

Test whether the creator's rapid repeated entries are better represented by a
successful-target continuation that is allowed only after the authoritative
5m structural episode has existed for at least 30 minutes.

## Evidence and frozen hypothesis

- The merged creator inventory contains 14 direction-matched continuation
  entries after the first entry in an uninterrupted 5m structural episode.
- All 14 occur at least 38 completed 1m bars into that episode; the observed
  range is 38 to 872 bars.
- The Jul 24 screenshots confirm that entries can be only two minutes apart,
  so a long post-exit cooldown would contradict the source behavior.
- The completed cap-2 replay generated 129 second entries: 112 targets and 17
  liquidations. Sixty occurred at episode age 30 or later: 53 targets and 7
  liquidations. These are descriptive annotations, not a standalone replay.

Freeze one challenger before event results:

- Control: `regime_reset_60s`.
- Prior challenger reference: `target_ladder_cap2`.
- New challenger: `mature_target_ladder_cap2`.
- The new challenger retains cap 2, successful-target-only rearm, zero
  additional price clearance, and a 60-second post-exit cooldown.
- It may re-enter only after 1,800 elapsed seconds in the current uninterrupted
  structural-direction episode. Thirty minutes is six completed 5m bars and
  remains below the minimum observed creator continuation age.
- Liquidation and expired maker intent still require structural reset.
- Initial entries are not age-gated. RANGE still blocks entries and does not
  close an open trade. Allocation, leverage, target, fees, fill rule, funding,
  mark/oracle liquidation model, and 15m non-veto context remain unchanged.
- Runtime, TUI, and ML observe-only policy remain unchanged.

## Implementation and validation

1. Add a typed optional minimum structural-episode duration to maker replay
   configuration and fail fast for invalid or incompatible values.
2. Track structural-episode start time in replay state and apply the duration
   only to same-direction target continuation.
3. Add unit tests for the boundary, rapid re-entry after maturity, reset,
   liquidation/expiry behavior, and unchanged default behavior.
4. Add the single frozen candidate to the target-ladder report family and run
   the serial screen followed by the complete verified 90-day Hyperliquid event
   replay without performance aborts.
5. Report all fills, targets, liquidations, fees/funding, final equity, maximum
   drawdown, chronological 30-day slices, source compatibility, and lifecycle
   substitution against control.

## Decision rule and failure modes

The candidate is not promoted merely for preserving creator entries. It must
materially improve geometric equity and drawdown without hiding unresolved
orders, missing context, or a new unplanned threshold. A result that remains
economically catastrophic, loses in each chronological slice, or only shifts
liquidations later falsifies this condition as a sufficient repair.

Confidence is medium that the condition is behaviorally closer to the supplied
creator evidence and low that it is sufficient for profitability. Fresh
creator entries earlier than 30 minutes in a correctly classified structural
episode would directly falsify the source-compatibility claim.

## Measured result

The serial screen moved in the expected direction versus unrestricted cap 2
but remained worse than control. The mature candidate completed 486 trades
(428 targets/58 liquidations), ended at $21.15, and drew down -99.956%. The
unrestricted cap-2 reference completed 492 trades (422/70), ended at $0.0719,
and drew down -99.9999%; the regime-reset control completed 328 trades
(289/39), ended at $173.00, and drew down -99.245%.

The complete verified Hyperliquid event replay then reproduced the prior
control and cap-2 reports byte-for-byte at the replay-object level. Results:

| Candidate | Fills | Targets | Liquidations | Fees | Funding | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| Regime reset | 281 | 241 | 40 | $5,886.41 | $11.88 | $3.8034 | -99.9794% |
| Cap 2 | 409 | 355 | 54 | $10,884.25 | $146.17 | $0.9088 | -99.9975% |
| Mature cap 2 | 415 | 361 | 54 | $6,011.27 | $8.13 | $1.0327 | -99.9969% |

The mature candidate lost money in all three chronological 30-day slices. It
reduced fee churn and improved terminal equity slightly versus unrestricted
cap 2, but it did not reduce full liquidations and remained worse than the
regime-reset control. The 189 candidate-only resolved lifecycles show that the
condition still applies creator-like continuation too broadly across the
archive.

Verdict: do not promote. Mature structural age is retained as a useful causal
annotation because it preserves all 14 observed creator continuations, but it
is not the missing tactical entry signal. The screenshots still support rapid
re-entry inside mature trends; they do not support entering every mature trend
after a target.

Artifact:
`data/logs/research/hypervelocity_mature_target_continuation_20260727.json`,
SHA-256
`6b146c73d0832becb553c946f75c85fbfca17756083df89bce70a5cd991ea7f7`.
Runtime, TUI, faithful configuration, and ML observe-only behavior were not
changed. Confidence is high for this exact 90-day replay result and medium for
the behavioral maturity inference because the creator sample contains only 14
direction-matched continuations.
