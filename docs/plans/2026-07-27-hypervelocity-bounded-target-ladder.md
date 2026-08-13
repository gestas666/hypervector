# Hypervelocity Bounded Target Ladder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether a source-bounded number of successful same-direction target re-entries per uninterrupted 5m structural episode restores creator-like cadence and profitable 90-day execution without changing regime thresholds.

**Architecture:** Extend the existing report-only `target_continuation` replay assumption with an optional positive target-completion limit that resets only when the causal 5m structural direction changes. Freeze control/cap-2/cap-3/cap-6 before results, measure compatibility against the reconciled creator episodes, and replay every candidate over the same verified Hyperliquid L2/trade/mark/oracle/funding tape.

**Tech Stack:** Python 3.13, pandas, typed dataclasses, pytest, verified 0xArchive Hyperliquid L2/public trades, authentic Hyperliquid mark/oracle/funding context.

---

## Frozen evidence and invariants

- The current source inventory contains 35 logical entries after merging the
  original reconciled records and the new screenshot-backed rows. Twenty-seven
  align with the causal 5m structural direction.
- Those 27 aligned entries occupy 13 uninterrupted directional episodes. The
  per-episode distribution is six episodes with one entry, three with two,
  three with three, and one with six. Twenty-one aligned entries therefore
  occur in repeated-entry episodes.
- Cap 2 preserves 20/27 aligned source entries, cap 3 preserves 24/27, and cap
  6 preserves 27/27. These are compatibility counts, not performance claims.
- Prior unlimited target-continuation candidates at 0/1/3 bps produced
  845-878 serial trades, 118-129 liquidations, and effectively zero equity.
  Prior cooldown-only and RSI-reconfirmation variants also overtraded and are
  not repeated.
- Frozen candidates: unchanged `regime_reset_60s` control, then
  `target_ladder_cap2`, `target_ladder_cap3`, and `target_ladder_cap6`.
  Challengers use target-continuation, 60-second cooldown, and 0 bps additional
  clearance. A liquidation, stop, timeout, or expired maker entry cannot rearm
  the same direction.
- Preserve the faithful detector, 5m primary authority, 1m execution decisions,
  15m non-veto context, one BTC position, 70% allocation, 40x isolated
  leverage, fixed 8% gross-margin target, maker entry/target fees, public
  trade-through fills, authentic mark/oracle/funding, hold-through-RANGE, and
  no RANGE entries.
- Keep runtime, TUI, faithful TOML, and ML observe-only policy unchanged.
- Retain every technically valid serial and event result regardless of
  performance, drawdown, cadence, or trade count. Only technical failure aborts
  a trial.

### Task 1: Add target-ladder configuration and episode accounting

**Files:**
- Modify: `src/hypervector/research/hypervelocity_portfolio_eval.py`
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `src/hypervector/research/maker_replay_risk.py`
- Test: `tests/test_hypervelocity_portfolio_eval.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write failing validation tests proving the optional episode target limit is
   `None` or a positive non-Boolean integer and is only valid for
   `target_continuation`.
2. Write a failing serial test proving cap 2 permits two target completions in
   one structural episode and blocks a third.
3. Write a failing serial test proving a non-matching structural state resets
   the count and permits a new same-side episode.
4. Write equivalent event-replay tests, including proof that liquidation does
   not consume a successful-target slot or permit same-side re-entry.
5. Implement the smallest typed state/config changes. Preserve exact behavior
   when the limit is `None`.
6. Run focused tests and Ruff before continuing.

### Task 2: Freeze candidates and creator episode compatibility

**Files:**
- Modify: `src/hypervector/research/hypervelocity_reentry_compare.py`
- Modify: `tests/test_hypervelocity_reentry_compare.py`

1. Write a failing test requiring exactly control, cap 2, cap 3, and cap 6.
2. Add a point-in-time source episode summary using completed-bar availability,
   logical record reconciliation, and the supplemental screenshot merge.
3. Write failing tests for the measured distribution and cap preservation
   calculation on a compact fixture.
4. Add serial summaries for all four candidates without survivor filtering.
5. Retain candidate identity, cadence, targets, liquidations, equity, drawdown,
   source compatibility, and every serial trade in the in-memory result.

### Task 3: Expose one immutable authentic replay command

**Files:**
- Modify: `scripts/hypervelocity_margin_stop_compare.py`
- Modify: `src/hypervector/research/hypervelocity_margin_stop_compare.py`
- Modify: `tests/test_hypervelocity_margin_stop_script.py`
- Modify: `tests/test_hypervelocity_margin_stop_compare.py`

1. Add `target-ladder` to `--candidate-family` and stamp experiment identity
   `source_bounded_target_ladder_v1`.
2. Require both `--creator-positions` and `--supplemental-positions` for this
   family; bind both SHA-256 values into source evidence.
3. Include the creator episode distribution and preservation counts in the
   report.
4. Include candidate-specific policy, clearance, and target limit in each
   summary rather than claiming one shared re-entry policy.
5. Preserve immutable output creation and the exact faithful config hash.
6. Run parser/report tests and task-scoped Ruff/format checks.

### Task 4: Execute the complete verified grid

**Files:**
- Create: `data/logs/research/hypervelocity_bounded_target_ladder_20260727.json`

1. Replay April 28 through July 27 against all 2,160 verified bundle pairs and
   the exact authentic price/funding context used by the stop and timeout grids.
2. Start every candidate at $10,000 and retain submissions, fills, expirations,
   targets, liquidations, fees, funding, marked drawdown, all lifecycles, and
   three chronological 30-day slices.
3. Report lifecycle identity/status substitutions against the unchanged
   control. Do not run adjacent caps or clearances after seeing results.
4. Full-window equity above $10,000 is required to call a candidate profitable;
   slice consistency, source cadence, and source episode compatibility determine
   confidence but do not suppress results.

### Task 5: Record and validate the decision

**Files:**
- Modify: `docs/reviews/2026-07-27-creator-screenshot-forward-validation.md`
- Modify: `HANDOFF.md`
- Modify: this plan

1. Record exact artifact SHA-256, all candidate results, segment behavior,
   source compatibility, lifecycle substitutions, limitations, and falsifiers.
2. Run focused tests, the full non-network Python suite, Rust TUI tests,
   task-scoped Ruff/format, Cargo format, file/function size checks,
   `git diff --check`, CLI status, config hashing, and artifact schema checks.
3. Keep runtime unchanged unless a challenger is profitable on the complete
   event tape and later corroborated in a fresh venue-matched shadow window.

## Failure modes and falsifiers

- Source episode counts describe observed entries but do not prove the creator
  explicitly uses a ladder counter.
- The screenshot set is win-heavy and does not reveal the losing-trade exit
  mechanism.
- A cap can reduce churn while leaving rare liquidation losses economically
  dominant.
- Public trade-through cannot reconstruct private queue rank or hidden depth.
- Non-positive full-window return, losses in all chronological slices, cadence
  far above source, or heavy substitution of control targets falsifies a cap as
  a profitable repair.

## Execution note

The persistent goal authorizes continued report-only testing. Execution remains
in the current preserved dirty worktree because the candidate depends on its
uncommitted replay/context stack. No subagents are used. Commit and push remain
deferred until explicitly requested.

## Execution result

Completed on 2026-07-27 against all 2,160 verified hourly bundle pairs. The
immutable artifact is
`data/logs/research/hypervelocity_bounded_target_ladder_20260727.json`, SHA-256
`32f66644265552083d0f990910fdcbfacc960d7125942bfd2f4d18c2a0cd9a61`.
The control exactly reproduced the prior authentic result.

| Candidate | Fills | Targets | Liquidations | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|
| Regime-reset control | 281 | 241 | 40 | $3.8034 | -99.9794% |
| Target ladder cap 2 | 409 | 355 | 54 | $0.9088 | -99.9975% |
| Target ladder cap 3 | 504 | 427 | 77 | $0.000432 | -99.999999% |
| Target ladder cap 6 | 637 | 540 | 97 | $0.000009 | -99.99999998% |

Every candidate lost money in every chronological 30-day slice. Cap 2 raised
the target rate from 85.77% to 86.80% but increased liquidations by 14 and
created 198 candidate-only resolved lifecycles while removing 70 control
lifecycles from the later path. Caps 3 and 6 expanded the path further and
were monotonically worse. The serial screen correctly anticipated the event
direction, but all event trials were retained and executed as required by the
project charter.

The creator evidence proves repeated same-direction entries occur within one
5m structural episode, but this result falsifies an episode counter as the
missing standalone trigger. Selective continuation timing remains unknown.
Runtime, TUI, faithful TOML, and observe-only ML remain unchanged. An
independent window where a frozen cap is profitable across slices, or creator
execution evidence that identifies a conditional ladder trigger, would update
this conclusion.

Fresh post-refactor validation completed with 976 non-network Python tests and
33 Rust TUI tests passing. The 13 task-scoped Python files pass Ruff and format
checks; all touched source modules remain below 500 lines with no function over
50 lines. Cargo format, `git diff --check`, CLI fail-closed status, artifact
schema, artifact SHA-256, and faithful config SHA-256 also pass. The full suite
retains 31 known dependency/deprecation/model warnings and four deselected
network tests.
