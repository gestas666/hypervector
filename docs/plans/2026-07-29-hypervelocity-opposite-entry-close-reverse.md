# Hypervelocity Opposite-Entry Close-and-Reverse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether the creator strategy holds through non-tradable regimes but closes and reverses when a new causally available, opposite Hypervelocity entry becomes executable.

**Architecture:** Add one disabled-by-default research replay flag. While a position is open, only a later opposite `entry_direction` that agrees with the current structural direction may close it; `RANGE`, missing direction, same-side direction, 1m/15m telemetry, and model output cannot. A qualifying signal closes at adverse BBO with taker fees and atomically submits the opposite post-only maker intent, preserving one position per symbol and leaving runtime, TUI, faithful TOML, and ML authority unchanged.

**Tech Stack:** Python 3.13, pandas, dataclasses, pytest, immutable Hyperliquid 1m candles, checksum-verified 0xArchive L2/public trades, and official Hyperliquid mark/funding context.

---

## Frozen hypothesis and evidence

- The thirteen early `closed_no_trade_row` creator positions have exact entry
  and close timestamps but no exact exit fill or realized PnL.
- Hyperliquid 1m candles classify nine of those close minutes as favorable and
  four as adverse using candle close. This is an estimate, not an exact fill.
- The four adverse rows are followed by a new opposite-side creator position
  after 36.2, 116.6, 52.7, and 142.7 seconds. This matches the separate 39W/4L
  scorecard numerically but does not prove the original exit trigger.
- The reverse-engineering source separately states that trend invalidation
  closes and reverses positions. The user requires positions to hold through
  `RANGE`, retain the 8% target, and never hold two positions in one coin.
- The already-rejected `opposite_5m_structural_exit` is not this candidate. It
  closed on 162 structural flips, changed the stateful entry path, and reduced
  $10,000 to $8.10. A structural state alone is therefore insufficient.

## Exact candidate contract

- Control: corrected `strict_source_control`, 60-second normal re-entry
  cooldown, 70% isolated margin, 40x, 8% gross margin target, 300-second maker
  TTL, public trade-through entry/target fills, taker liquidation, authentic
  mark/oracle/funding, and no discretionary exit.
- Candidate: identical except `opposite_entry_close_reverse=true`.
- Trigger: an open long sees a later `entry_direction=short` and
  `structural_direction=short`, or an open short sees the corresponding long.
  The causal signal availability time must be strictly later than the open
  position's fill time.
- Non-triggers: `entry_direction=None`, `RANGE`, `TRANSITION`, `UNKNOWN`,
  same-side direction, structural opposition without entry eligibility,
  model probability, order-book pressure, BBWP alone, 1m state, or 15m context.
- Event priority: authentic-mark liquidation first; qualifying opposite-entry
  close second; configured time/stop exits third; passive target last.
- Close execution: adverse BBO and taker fee. Funding accrued through the close
  remains included.
- Reverse execution: after the close, submit one opposite post-only maker order
  at the same observed book snapshot. The atomic reversal bypasses the generic
  post-exit cooldown because one observed creator reversal filled within 60
  seconds; later unrelated entries continue to obey the 60-second cooldown.
- The reverse order cannot fill on its submission snapshot. Existing causal
  touch/book-through/public-trade-through rules apply only to later evidence.
- One-position invariant: closing clears the open position before creating one
  pending maker intent. No event may leave both an open position and a pending
  entry.
- The fixed candidate set contains only the control and this one candidate. No
  delay, confidence, persistence, stop, target, margin, or regime threshold is
  tuned after results are observed.

## Evaluation protocol

- Development windows: each corrected gap-free strict-source block ending
  before 2025-12-15. Each block starts from $10,000 because archive gaps prevent
  a trustworthy continuous portfolio path.
- Candidate-unseen validation: 2025-12-15 through 2026-01-09. Its target-only
  control result is known, but the close/reverse candidate has not been replayed.
- Forward reserve: 2026-01-09 onward remains unused until the downloader,
  checksum audit, DuckDB import, candles, mark, funding, and source labels cover
  a complete gap-free interval.
- Retain every technically valid result under `SRS_HV1_NO_GATES`, including
  losses and sparse blocks. Economic acceptance is evidence for promotion, not
  a run-abort gate.
- Report each block's submissions, fills, targets, close/reverses,
  liquidations, fees, funding, realized/marked equity, maximum drawdown, open
  state, and lifecycle substitutions versus control.
- A profitable edge is not established unless aggregate development net PnL is
  positive after modeled friction and the candidate-unseen validation also
  finishes above its $10,000 start. A merely less-negative outcome remains a
  rejected or partial result, not a promotion.

## Task 1: Preserve creator close/reverse evidence

**Files:**
- Create: `src/hypervector/research/hypervelocity_creator_close_reverse.py`
- Create: `tests/test_hypervelocity_creator_close_reverse.py`
- Create: `scripts/hypervelocity_creator_close_reverse.py`

1. Write failing tests for exact close-minute lookup, side-aware margin-return
   bounds, consecutive opposite-position latency, missing candle rejection,
   and immutable report output.
2. Run the focused tests and verify they fail because the module is absent.
3. Implement the smallest typed reconstruction using creator timestamps and
   venue candle OHLC without fabricating an exact fill.
4. Store source/candle hashes, estimated outcome counts, all thirteen rows,
   and explicit uncertainty in one immutable JSON report.
5. Run focused tests, Ruff, formatting, and file/function-size checks.

## Task 2: Add research-only replay semantics

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay_risk.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `src/hypervector/research/maker_replay_stream.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Write failing tests proving default target-only behavior is unchanged.
2. Write failing tests proving RANGE, missing/same-side entry, structural-only
   opposition, and signals available before the position fill cannot exit.
3. Write failing tests proving liquidation priority, adverse-BBO/taker-fee
   accounting, funding retention, atomic opposite maker submission, no
   same-snapshot fill, and one-position state.
4. Run the focused tests and observe the expected missing-option failures.
5. Add the disabled config flag, one typed risk-boundary close helper, explicit
   close/reverse accounting, and minimal snapshot orchestration.
6. Run the focused tests and existing opposite-regime tests to green.

## Task 3: Add immutable two-candidate comparison

**Files:**
- Create: `src/hypervector/research/hypervelocity_close_reverse_compare.py`
- Create: `tests/test_hypervelocity_close_reverse_compare.py`
- Create: `scripts/hypervelocity_close_reverse_compare.py`

1. Write failing tests for the exact two-candidate config diff, shared decision
   and tape identity, lifecycle substitution counts, block aggregation,
   immutable output, observe-only ML contract, and runtime-unchanged stamp.
2. Reuse the existing strict-label verifier, causal warmup, faithful classifier,
   source agreement, DuckDB replay, authentic context, and portfolio summary.
3. Refuse incomplete book evidence, changed hashes, overlapping blocks, or a
   candidate config with any difference beyond the close/reverse flag.
4. Run focused tests, Ruff, formatting, and size checks.

## Task 4: Development replay and candidate-unseen validation

**Files:**
- Create: `data/logs/research/hypervelocity_close_reverse_creator_evidence_20260729.json`
- Create: `data/logs/research/hypervelocity_close_reverse_development_20260729.json`
- Create: `data/logs/research/hypervelocity_close_reverse_validation_20251215_20260109_20260729.json`
- Create: `docs/reviews/2026-07-29-hypervelocity-close-reverse.md`
- Modify: `HANDOFF.md`

1. Generate and hash the creator reconstruction report.
2. Replay every pre-December-15 development block and retain all outcomes.
3. Freeze the implementation and report hash before opening validation output.
4. Replay December 15-January 9 once and retain the result regardless of sign.
5. Compare profitability, drawdown, liquidation substitutions, target losses,
   reversal fill latency, fees, and block stability. State whether the
   hypothesis passed, partially improved, or was falsified.
6. Do not modify runtime/TUI/config/ML authority without a separate promotion
   decision supported by the evidence.

## Task 5: Verification and forward reserve

1. Run task-focused tests and task-scoped Ruff/format checks.
2. Run `uv run pytest tests/ -q -m "not network"` and
   `cargo test -p hypervector-tui` before any completion claim.
3. Verify the shadow and downloader processes remain the same PIDs, runtime
   config hash is unchanged, and no live client or order authority was created.
4. Audit the downloader's complete January-9-forward prefix. Only then define
   the next untouched validation interval.
5. Do not commit or push unless explicitly requested.

## Uncertainties and falsifiers

- The 1m close candle does not reveal the creator's exact exit fill. Exact fills
  could change the estimated magnitude, though all four adverse candles are
  entirely adverse at the recorded close minute.
- A following opposite position does not prove the signal caused the prior
  close. Exact creator exit reasons or order logs showing manual/unrelated exits
  would falsify the inferred trigger.
- If the candidate still liquidates or loses after costs in development and
  candidate-unseen validation, executable close/reverse does not repair the
  current entry/regime edge.
- If many control targets become premature close/reverse losses, the current
  regime detector is too noisy for this exit authority even if liquidations
  fall.
- Public L2 cannot reveal private queue rank, hidden liquidity, or exact market
  impact. A profitable replay would still require a fresh shadow comparison and
  a deliberately bounded live canary before production authority changes.

## Measured result

The candidate is rejected as a global execution rule. Across seven independently
reset, gap-free blocks, target-only control retained $22,645.61 of $70,000
aggregate starting equity, while close/reverse retained $13,483.36. Control had
one positive block; close/reverse had zero. Runtime, TUI, faithful TOML, and ML
authority remain unchanged.

Close/reverse reduced full liquidations from 53 to 24, but added 61 adverse
reversal closes, increased expirations from 73 to 109, and raised modeled fees
from $13,188.25 to $16,892.47. Its initial improvement did not persist: on the
two January 9-February 7 extension blocks it ended at $3,741.29 and $2,942.81,
versus $12,847.15 and $5,029.74 for control.

All 61 reversal closes coincided with the first causally available opposite
source direction, none of 250 candidate targets saw an opposite source direction
before completion, and all 24 candidate liquidations occurred before the source
detector flipped. The trigger was therefore not late relative to the confirmed
5m source classifier. Instead, the classifier sometimes invalidated trades that
later recovered and remained aligned during every remaining liquidation.

Among shared lifecycle identities, 26 control liquidations became reversals, but
17 control targets also became reversals. Gross margin loss at the reversal
overlapped materially: eventual liquidations had a -31.79% median and a
-47.77% to -17.21% range, while eventual targets had a -24.11% median and a
-39.75% to -6.65% range. A post-hoc loss-depth threshold is not promoted.

Confidence is high in the replay accounting and the rejection of unconditional
close/reverse under the tested evidence. Confidence in the creator's actual exit
cause remains medium because exact exit fills and reasons are absent. Exact
creator order logs, or a larger complete creator loss/no-loss ledger showing a
separable invalidation feature, would update this conclusion.
