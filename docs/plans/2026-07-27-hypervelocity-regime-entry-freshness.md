# Hypervelocity Regime Entry Freshness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether blocking only entries first observed 15 or more one-minute bars into the current 5m structural regime improves the recovery-6 venue replay.

**Architecture:** Add a research-only causal annotation that counts contiguous `state_5m` age and clears `entry_direction` at the already-declared `15+` attribution boundary while preserving canonical regime telemetry. Screen the single candidate in the serial portfolio diagnostic, then replay it through the same checksum-verified Hyperliquid L2/public-trade archive and compare it with the immutable recovery-6 control.

**Tech Stack:** Python 3.12, pandas, pytest, existing streaming maker replay and 0xArchive bundle verifier.

---

## Frozen Contract

- Control: `5m_bbwp_hard_range_25_recovery_6_cooldown_300s`.
- Challenger: control plus `regime_age_5m_bars < 15` for new entry signals.
- Age is zero-based and causal on the canonical 5m state projected at 1m.
- Open positions continue to hold through RANGE until the 8% target or modeled
  liquidation; the age condition affects entries only.
- Canonical regime, structural direction, 15m non-veto context, 70% allocation,
  40x isolated leverage, maker TTL/fill rules, fees, and target do not change.
- Same-direction re-entry remains `regime_reset` plus 300 seconds.
- One declared threshold is tested. No post-result threshold search is allowed
  in this trial family.
- Runtime and TUI remain unchanged; the result is report-only.

The hypothesis is motivated by the predeclared attribution bucket: 15+ regime
age contained 6/36 liquidations (16.7%) versus 33/371 (8.9%) earlier. This is
association, not proof; the 36-trade bucket is small and path-dependent replay
can move later entries.

### Task 1: Causal entry-age annotation

**Files:**
- Modify: `src/hypervector/research/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_precedence.py`

1. Write a failing test for zero-based contiguous age and entry-only masking.
2. Verify the test fails because the annotation does not exist.
3. Implement a positive integer maximum-age-exclusive parameter.
4. Preserve `state_5m`, `primary_regime`, and `structural_direction` exactly.
5. Verify prefix invariance and run focused tests.

### Task 2: Single-candidate serial and event replay

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`

1. Add an explicit optional `--event-maximum-regime-age` argument.
2. Apply it only after hard BBWP25 and recovery-6 annotations.
3. Record masked bars, serial metrics, source-entry alignment, and the complete
   event lifecycle report.
4. Run the exact 90-day public-trade-through replay to a new immutable JSON.

### Task 3: Compare and decide

**Files:**
- Modify: this plan with measured results.

1. Compare submitted entries, fills, targets, full/partial liquidations, final
   equity, maximum drawdown, fees, and completed trades/day with recovery-6.
2. Retain source-log alignment deltas and any lost original entries.
3. Reject promotion if equity or drawdown worsens, liquidation reduction is
   paid for by excessive lost targets, or the improvement depends on a new
   unplanned threshold.
4. Keep the runtime configuration unchanged regardless of this exploration
   result; a favorable result would still require fresh shadow confirmation.

Confidence is low-to-medium before replay. The threshold has a plausible
trend-exhaustion mechanism but only six observed liquidations in the motivating
bucket. Venue replay showing unchanged/worse geometric equity, or fresh shadow
entries succeeding late in regimes, would falsify the recommendation.

## Measured 90-Day Result

The candidate blocked 43,673 of 56,060 otherwise directional signal minutes,
so it was materially broader than the motivating 36 resolved late-age fills.
In the serial diagnostic it reduced completed trades from 488 to 459, reduced
targets from 450 to 419, increased liquidations from 38 to 40, reduced final
equity from $444,855.97 to $43,308.19, and worsened maximum drawdown from
-96.41% to -96.86%. Exact original-log direction matches fell from 17/35 to
7/35.

The full checksum-verified public-trade-through replay confirmed the failure.
The control recorded 407 fills, 368 targets, 39 full liquidations, 24 partial
liquidations, $4,123.47 final equity, and -94.38% maximum drawdown. The
freshness candidate recorded 377 fills, 338 targets, the same 39 full
liquidations, 27 partial liquidations, $1,097.12 final equity, and -95.01%
maximum drawdown. It removed exactly 30 completed targets and no full
liquidations.

Verdict: falsified with high confidence for this exact threshold and window.
Do not promote or sweep adjacent age thresholds. The evidence redirects work
upstream toward transition/range classification fidelity rather than another
entry-age gate. Runtime and TUI remain unchanged.
