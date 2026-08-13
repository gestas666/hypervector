# Hypervelocity Source-Bounded Maximum-Hold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether a source-bounded maximum holding time can prevent stale faithful Hypervelocity positions from becoming catastrophic losses while preserving the creator's observed trade durations.

**Architecture:** Add an optional report-only maximum-hold assumption to the existing event replay. At the first book snapshot at or after the deadline, liquidation is evaluated first and a surviving position exits at adverse BBO with taker fees. Replay the unchanged faithful decisions for a frozen no-timeout/6h/12h/24h grid over one verified Hyperliquid tape with authentic mark, oracle, and funding context.

**Tech Stack:** Python 3.13, pandas, typed dataclasses, pytest, verified 0xArchive Hyperliquid L2/public trades, authentic Hyperliquid mark/oracle/funding context.

---

## Frozen evidence and invariants

- The reconciled creator source has 33 closed logical positions. Twenty-eight
  close within 6 hours, 30 within 12 hours, and all 33 within 24 hours. The
  maximum observed hold is about 22.12 hours.
- The faithful no-stop event control has 241 targets and 40 liquidations.
  Median target duration is 33.04 minutes versus 215.18 minutes for
  liquidations, but the distributions overlap materially. These observations
  motivate the fixed grid; they do not authorize another duration after the
  result is known.
- Preserve faithful entry and regime decisions, one BTC position, 70% isolated
  allocation, 40x leverage, 8% gross margin target, maker entry/target fees,
  taker risk-exit fee, 300-second maker TTL, 60-second cooldown, regime-reset
  re-entry, no RANGE entries, and hold-through-RANGE before the deadline.
- Preserve 5m primary authority, 1m breakout confirmation, 15m non-veto
  context, and the current range detector. Do not add confidence, L2, model,
  or volatility gates.
- Keep ML `observe` with `may_filter=false` and `may_scale=false`. Do not change
  runtime, TUI, shadow state, or the faithful TOML.
- Retain every technically valid trial and every lifecycle regardless of
  performance, drawdown, or trade count.

### Task 1: Add a typed maximum-hold replay assumption

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay_risk.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Create: `tests/test_hypervelocity_max_hold.py`

1. Write a failing validation test for zero, negative, Boolean, or non-finite
   `maximum_hold_seconds`; `None` remains the unchanged default.
2. Write a failing replay test proving no exit occurs before the deadline and
   the first BBO at or after the deadline closes the position.
3. Write a failing accounting test proving the exit uses adverse BBO, charges
   the maker entry plus taker exit fee, records `time_exited`, and increments a
   dedicated report count.
4. Write a failing ordering test proving a simultaneous liquidation is applied
   before the timeout rather than being hidden as a discretionary exit.
5. Implement the minimal typed state/report changes and a risk helper. Do not
   alter the behavior of `maximum_hold_seconds=None`.
6. Run `uv run pytest tests/test_hypervelocity_max_hold.py tests/test_hypervelocity_maker_replay.py -q`.

### Task 2: Freeze the comparison and source compatibility report

**Files:**
- Modify: `src/hypervector/research/hypervelocity_margin_stop_compare.py`
- Modify: `tests/test_hypervelocity_margin_stop_compare.py`
- Modify: `tests/test_hypervelocity_max_hold.py`

1. Write a failing test requiring exactly `no_timeout_control`,
   `max_hold_6h`, `max_hold_12h`, and `max_hold_24h`.
2. Add `maximum_hold_candidate_configs()` using the same faithful execution
   assumptions as the margin-stop comparison.
3. Extend candidate summaries with `maximum_hold_seconds`, `time_exited`
   counts, average outcome PnL, and chronological 30-day slices without
   changing prior margin-stop results.
4. Add a source-duration summary over reconciled logical positions, explicitly
   reporting missing/open outcomes and the share compatible with each deadline.
5. Run the focused tests and Ruff.

### Task 3: Expose one reproducible immutable command

**Files:**
- Modify: `scripts/hypervelocity_margin_stop_compare.py`
- Modify: `tests/test_hypervelocity_margin_stop_script.py`

1. Add `--candidate-family margin-stop|max-hold`, defaulting to the historical
   `margin-stop` behavior.
2. Select the frozen config factory and stamp a distinct
   `source_bounded_maximum_hold_grid_v1` experiment identity.
3. Require `--creator-positions` for the max-hold family and include its exact
   SHA-256 plus source-duration compatibility in the report.
4. Preserve immutable output creation and fail if the output path exists.
5. Run parser/report contract tests and changed-file Ruff/format checks.

### Task 4: Execute the full verified event grid

**Files:**
- Create: `data/logs/research/hypervelocity_source_bounded_max_hold_20260727.json`

1. Replay April 28 through July 27 over all 2,160 verified bundle pairs using
   public trade-through fills and the authentic price/funding context already
   bound to the faithful stop artifact.
2. Start each candidate at $10,000 and retain submissions, fills, expirations,
   targets, time exits, liquidations, fees, funding, final equity, marked
   drawdown, and every lifecycle.
3. Compare lifecycle identity/status overlap with the no-timeout control and
   report time exits that replace eventual control targets or liquidations.
4. Report all three 30-day slices. Full-window final equity above $10,000 is
   necessary to call a candidate profitable; slice consistency and creator
   duration compatibility determine confidence rather than aborting trials.
5. Do not run another deadline if the frozen grid loses.

### Task 5: Validate and record the decision

**Files:**
- Modify: `docs/reviews/2026-07-27-creator-screenshot-forward-validation.md`
- Modify: `HANDOFF.md`
- Modify: this plan

1. Record exact results, SHA-256, favorable and unfavorable slices, source
   compatibility, assumptions, and falsifiers.
2. Run focused tests, full non-network Python tests, Rust TUI tests, Ruff,
   formatting, file/function-size checks, `git diff --check`, CLI status, and
   faithful config hashing.
3. Keep runtime unchanged unless a separate explicit promotion is supported by
   profitable event evidence and later fresh shadow validation.

## Failure modes and falsifiers

- Creator close timestamps are observed successes and do not establish that
  losing trades use a clock-based exit.
- A timeout can reduce liquidation labels while realizing repeated large taker
  losses and rearming a worse path.
- Public BBO does not reveal hidden depth, private queue rank, or the creator's
  venue execution.
- Deadline compatibility is not trigger evidence; it only constrains how much
  observed behavior a candidate contradicts.
- Non-positive full-window return, worse geometric drawdown, or time exits that
  disproportionately replace control targets falsify the candidate as a
  profitable repair.

## Execution note

The persistent goal authorizes continued report-only testing. This plan is
executed in the current preserved worktree without subagents. Commit and push
remain deferred until explicitly requested.

## Execution result

Completed on 2026-07-27 against all 2,160 verified hourly bundle pairs. The
immutable artifact is
`data/logs/research/hypervelocity_source_bounded_max_hold_20260727.json`,
SHA-256
`6cab0f15e041f8e03485051041d073f8ea2c0551703379a78c37207f7c9969af`.

| Candidate | Fills | Targets | Time exits | Liquidations | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| No timeout | 281 | 241 | 0 | 40 | $3.80 | -99.979% |
| 6 hours | 312 | 238 | 45 | 29 | $0.80 | -99.997% |
| 12 hours | 286 | 241 | 11 | 34 | $18.17 | -99.929% |
| 24 hours | 281 | 241 | 1 | 39 | $4.47 | -99.976% |

All candidates lost money in every chronological 30-day slice. The 12-hour
candidate was numerically least bad, but still lost 99.82% of initial equity.
Among shared lifecycles it changed five control liquidations and six eventual
control targets into time exits, while also changing later path availability.
The 6-hour candidate changed 14 control liquidations and 21 eventual targets
into time exits and generated 55 candidate-only resolved lifecycles. Source
duration compatibility was 84.85% at 6 hours, 90.91% at 12 hours, and 100% at
24 hours.

Maximum hold alone is rejected as a profitable repair. The runtime, TUI,
faithful configuration, and observe-only metalabel remain unchanged. This
conclusion would be updated by authoritative creator losing-trade fills that
show a repeatable time-based exit, or by an independent venue-matched window
where a frozen deadline is profitable across slices without target
substitution dominating the improvement.

Validation completed with 80 focused replay tests, 950 non-network Python
tests, and 33 Rust TUI tests passing. The nine changed Python files pass Ruff
and format checks; changed modules stay below 500 lines with no function above
50 lines. Cargo formatting, `git diff --check`, CLI status, artifact schema,
artifact SHA-256, and the faithful config SHA-256 also pass. Repository-wide
Ruff remains a known baseline failure with 33 unrelated findings and 88
unrelated formatting candidates; they were not rewritten as part of this
experiment.
