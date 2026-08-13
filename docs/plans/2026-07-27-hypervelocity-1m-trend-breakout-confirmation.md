# Hypervelocity 1m Trend Breakout Confirmation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether a same-direction 1m trend can causally confirm a directional 5m breakout without requiring a simultaneous 1m breakout label.

**Architecture:** Add one report-only transformation over canonical decisions. It supplies `entry_direction` only when the 5m primary state is `BREAKOUT`, the 5m structural breakout direction is known, the current 1m state is a same-direction trend, and canonical execution is explicitly awaiting 1m confirmation. Apply it after hard 5m RANGE precedence but before the existing recovery-6 mask, so it cannot bypass recovery. Reuse the frozen hard-BBWP25/recovery-6/300-second/$120 event candidate and change no runtime configuration.

**Tech Stack:** Python 3.13, pandas, pytest, verified 0xArchive Hyperliquid L2/public trades.

---

## Frozen hypothesis and acceptance

- Keep 70% isolated allocation, BTC 40x, one position, 8% target, RANGE hold,
  post-only maker entry/target costs, 300-second TTL/cooldown, hard 5m BBWP25,
  and 1m recovery age six.
- Keep 5m primary authority and 15m non-veto context.
- Do not authorize entries when 1m is RANGE, TRANSITION, UNKNOWN, or opposite
  the 5m breakout direction.
- The trade-backed source subset contains 21 reconciled entry decisions. The
  frozen control matches 15/21 and leaves three 5m-breakout entries blocked;
  the challenger matches 18/21 and leaves none of those three blocked.
- The initial cheap screen applied confirmation after recovery and is invalid
  because it could re-enable recovery-masked entries. Rerun the cheap screen
  using the corrected transformation order before authorizing an event replay.
- Event survival requires final equity above the TP-only hard/recovery control
  of $115.40 and maximum drawdown better than -97.52%. Profitability requires
  final equity above $120 after modeled fees.
- A survivor advances to the exact source window. A non-survivor ends this
  mechanism; do not tune a persistence or volume threshold around it.

### Task 1: Add the causal report-only transformation

**Files:**
- Modify: `src/hypervector/research/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_precedence.py`

1. Write a failing test for same-direction 1m trend plus directional 5m
   breakout, and counterexamples for RANGE and opposite-direction 1m states.
2. Run the focused test and confirm the missing-function failure.
3. Implement `apply_1m_trend_breakout_confirmation()` with explicit required
   columns, a telemetry flag, and a reason label.
4. Run the complete focused test file and Ruff.

### Task 2: Make the event run reproducible

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_script.py`

1. Write a failing parser/report test for `--event-breakout-confirmation
   1m-trend` and the candidate identity suffix.
2. Apply the transformation after hard-range construction, then apply recovery
   and all later entry masks before replay.
3. Preserve the default `strict-both-breakout` behavior when the option is
   omitted.
4. Run script tests and Ruff.

### Task 3: Run one full-window $120 event replay

**Files:**
- Create: `data/logs/research/hypervelocity_equity120_1m_trend_breakout_20260727.json`

1. Replay April 28 through July 27 across all 2,160 checksum-verified bundles.
2. Compare submissions, fills, targets, liquidations, final equity, drawdown,
   and lifecycle overlap against the $115.40 control.
3. Run an exact source-window replay only if both survival requirements pass.

### Task 4: Record the decision and preserve runtime

1. Append measured results and the falsifier to this plan.
2. Verify the faithful TOML checksum and model observe-only fields are
   unchanged.
3. Run focused tests, changed-file Ruff, and `git diff --check`.
4. Defer commit/push until explicitly requested because the shared worktree
   contains broader user-approved open changes.

## Measured result and decision

The corrected-order cheap screen authorized one exact replay. The full
90-day replay covered 2,160 checksum-verified archive bundles and produced:

- control: 517 submissions, 447 fills, 406 targets, 41 liquidations,
  $115.40 final equity, and -97.52% maximum drawdown;
- challenger: 513 submissions, 442 fills, 403 targets, 39 liquidations,
  $248.69 final equity, and -97.03% maximum drawdown.

The challenger passed both frozen full-window survival requirements and ended
above its $120 initial equity. Of 450 signals shared with the control, 447 had
the same terminal status. The changed signal timing and serial equity path,
not a broad improvement to individual trade outcomes, therefore account for
most of the final-equity difference.

The required source-window replay did not confirm the improvement:

- control: 74 submissions, 65 fills, 59 targets, 6 liquidations, $114.37 final
  equity, and -77.78% maximum drawdown;
- challenger: 70 submissions, 62 fills, 56 targets, 6 liquidations, $99.48
  final equity, and -80.79% maximum drawdown.

**Decision:** retain the 1m-trend breakout confirmation as a report-only
challenger and do not promote it to the faithful runtime configuration. It
improves the broad replay but degrades the venue-matched source interval, and
both paths retain near-total drawdown. Confidence is medium because the source
interval contains only 62 challenger fills. A separate, chronologically later
venue-matched window that improves both final equity and drawdown would
falsify this rejection. The model remains observe-only and the runtime
configuration is unchanged.
