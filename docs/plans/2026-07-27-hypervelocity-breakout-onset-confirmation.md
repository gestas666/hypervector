# Hypervelocity Breakout-Onset Confirmation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether one same-direction 1m trend event at the causal onset of a 5m breakout from hard BBWP range recovers the observed maker-entry pattern without authorizing every minute of the breakout.

**Architecture:** Add one report-only transformation after hard 5m BBWP range precedence and before the existing 1m recovery mask. It may populate `entry_direction` only on the first 1m row where a directional 5m breakout follows a hard-range row, the canonical classifier is awaiting 1m confirmation, and the current 1m trend agrees with the structural breakout direction. Existing maker replay then decides whether that single submission fills within the unchanged 300-second TTL.

**Tech Stack:** Python 3.13, pandas, pytest, checksum-verified Hyperliquid L2/public trades.

---

## Frozen hypothesis and contract

- The source record at 2026-07-20 18:19:35 UTC is a long after 5m hard BBWP
  range changed directly to a long breakout while 1m was `TREND_UP`.
- The rejected broad challenger authorized 1,525 same-direction 1m trend rows
  throughout 5m breakouts. It improved the 90-day path but worsened the exact
  source-window path, so it must not be reused.
- This candidate emits only the first causal onset row. It does not persist or
  synthesize a later entry signal; pending maker continuity remains owned by
  the existing replay/runtime semantics.
- Preserve hard BBWP25, recovery age six, 300-second maker TTL and post-exit
  cooldown, regime-reset re-entry, one position, 70% isolated margin, BTC 40x,
  8% gross margin target, fees, liquidation model, and RANGE hold policy.
- Keep 5m as the structural authority and 15m as non-veto context. Never
  authorize an opposite 1m trend, 1m RANGE/TRANSITION/UNKNOWN, or a breakout
  that did not directly follow hard range.
- Runtime and TUI remain unchanged. The metalabel stays `observe` with
  filtering and scaling disabled.

## Frozen acceptance

- The cheap serial diagnostic must not worsen final equity or maximum drawdown
  relative to the hard-BBWP25/recovery-6 control. Because this candidate emits
  a single maker-submission event rather than a persistent direction, source
  alignment is measured as a same-side submission within the unchanged
  300-second TTL whose structural direction remains valid through the recorded
  fill. It must improve that trade-backed count above the control's 12/21.
- Only a cheap-screen survivor receives one exact $120 90-day event replay.
- Full-window survival requires final equity above the frozen $115.40 control
  and maximum drawdown better than -97.52%. Profitability requires final equity
  above the $120 start after modeled costs.
- A full-window survivor receives the exact July 9–24 source-window replay.
  Promotion evidence would require source-window final equity above $114.37,
  drawdown better than -77.78%, and no loss of source-direction alignment.
- Failure at either event stage ends this mechanism. Do not add persistence,
  alternate onset ages, or adjacent thresholds after observing the result.

### Task 1: Add the causal onset transformation

**Files:**
- Modify: `src/hypervector/research/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_precedence.py`

1. Write a failing test where hard range changes to a long breakout with a 1m
   uptrend and canonical `5m_breakout_awaiting_1m_confirmation` reason.
2. Add counterexamples for a later breakout row, opposite 1m trend, and a
   breakout whose previous row was not hard range.
3. Run the focused test and verify the expected missing-function failure.
4. Implement `apply_breakout_onset_confirmation()` with required-column and
   index validation, an explicit boolean telemetry flag, and a distinct reason.
5. Run the full focused test file and Ruff.

### Task 2: Expose one reproducible research option

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_script.py`

1. Write a failing parser/report test for `--event-breakout-confirmation
   range-onset-1m-trend` and the candidate identity suffix.
2. Preserve `strict-both-breakout` as the default and the rejected `1m-trend`
   option as historical reproducibility.
3. Apply onset confirmation after hard-range construction and before recovery.
4. Run script and transformation tests plus Ruff.

### Task 3: Screen and run the frozen event sequence

**Files:**
- Create if authorized: `data/logs/research/hypervelocity_equity120_breakout_onset_20260727.json`
- Create only after full survival: `data/logs/research/hypervelocity_source_window_equity120_breakout_onset_20260727.json`

1. Measure event count, serial trades/targets/liquidations/equity/drawdown, and
   reconciled all-source/trade-backed direction alignment.
2. If the cheap criteria pass, replay April 28–July 27 over all 2,160 verified
   bundles using public-trade-through fills and $120 initial equity.
3. Compare lifecycle identity/status against the frozen $120 control.
4. Run the exact July 9 04:00–July 24 16:00 source window only if full survival
   criteria pass.

### Task 4: Record and verify

**Files:**
- Modify: this plan
- Modify if material: `HANDOFF.md`

1. Record every measured result, including failed gates and the causal
   denominator.
2. State the decision, confidence, limitations, and evidence that would update
   it.
3. Run focused tests, changed-file Ruff, the full non-network Python suite,
   and `git diff --check`.
4. Verify the faithful config checksum and observe-only model fields remain
   unchanged. Do not commit or push unless explicitly requested.

## Measured result and decision

The onset transformation emitted 32 events before the existing recovery mask
and 22 effective events afterward. It recovered the intended July 20 source
entry as a long submission 275.68 seconds before the recorded maker fill. The
trade-backed pending-compatible count improved from 12/21 to 13/21.

The cheap serial gate nevertheless failed:

| Metric | Hard/recovery control | Range-onset challenger |
|---|---:|---:|
| Completed trades | 488 | 486 |
| Targets | 450 | 448 |
| Liquidations | 38 | 38 |
| Final marked equity | $444,855.97 | $405,367.88 |
| Maximum drawdown | -96.41% | -96.41% |

**Decision:** do not run the full L2 event replay and do not promote the onset
rule. It explains one source maker-timing case but removes two modeled targets,
removes no liquidations, and worsens serial equity. Confidence is medium for
rejecting this exact event rule because the serial fill model is approximate;
a fresh venue-matched shadow window repeatedly showing profitable fills from
range-onset submissions would update the decision. Runtime configuration and
the observe-only model policy remain unchanged.
