# Hypervelocity Same-Regime Re-entry Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether bounded cooldown-based same-direction re-entry can reproduce the original strategy’s repeated trend-aligned positions and produce a profitable 90-day Hyperliquid event replay without changing runtime behavior prematurely.

**Architecture:** Add an explicit research replay policy that separates completed-target re-entry from expired-maker re-arm. The existing `regime_reset` policy remains the default, while a `cooldown_only` challenger permits another same-side maker attempt only after the configured cooldown; expired entries remain consumed until regime reset. Screen bounded cooldowns cheaply in the serial bar model, then run only nondominated candidates through the checksum-verified public trade-through event tape.

**Tech Stack:** Python 3.13, pandas, existing Hypervelocity regime classifier, verified 0xArchive Hyperliquid L2/public trades, pytest.

---

## Frozen Invariants

- One open or pending position per symbol.
- BTC isolated margin, 70% allocation, 40x leverage.
- Single fixed 8% margin-return target; hold open positions through RANGE.
- Post-only maker entry/target modeling and existing fee/liquidation assumptions.
- Expired maker attempts still require a non-matching structural regime before re-arm.
- Metalabel remains `observe`, `may_filter=false`, and `may_scale=false`.
- Runtime config and backend behavior remain unchanged until a separate promotion decision.
- Every technically valid trial is retained regardless of performance.

## Source Alignment Evidence

- Thirty-seven source rows collapse to thirty-five logical positions after combining two split-exit pairs.
- Twenty-three raw records are consecutive same-side entries.
- The current completed-direction `regime_reset` policy would allow five and block eighteen of those records.
- Among twenty non-overlapping same-side re-entries, the minimum observed delay is 61 seconds, median is 572 seconds, and eight occur between five and thirty minutes.
- The source therefore contradicts an unconditional same-regime ban but does not support zero-delay re-entry.

## Task 1: Add a Typed Research Re-entry Policy

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write a failing test proving `cooldown_only` permits same-direction submission only after the configured cooldown following a completed target.
2. Write a failing test proving the default `regime_reset` behavior is unchanged.
3. Write a failing test proving `cooldown_only` does not alter expired-entry regime-reset behavior.
4. Add `same_direction_reentry_policy: Literal["regime_reset", "cooldown_only"] = "regime_reset"` to `MakerReplayConfig` with fail-fast validation.
5. Make completed-direction blocking conditional on the research policy; leave expired-direction blocking unconditional.
6. Run `uv run pytest tests/test_hypervelocity_maker_replay.py -q`.

## Task 2: Add the Same Policy to the Cheap Serial Diagnostic

**Files:**
- Modify: `src/hypervector/research/hypervelocity_portfolio_eval.py`
- Test: `tests/test_hypervelocity_portfolio_eval.py`

1. Write failing tests for default regime-reset and cooldown-only re-entry.
2. Add the same typed policy to `SerialPortfolioConfig`, expressed in completed 1-minute bars.
3. Preserve one position, next-bar entry, compounding, liquidation, and drawdown behavior.
4. Run `uv run pytest tests/test_hypervelocity_portfolio_eval.py -q`.

## Task 3: Screen a Bounded Cooldown Matrix

**Files:**
- Create: `src/hypervector/research/hypervelocity_reentry_compare.py`
- Create: `tests/test_hypervelocity_reentry_compare.py`

1. Define exactly four candidates before inspecting results: current `regime_reset/60s`, and `cooldown_only` at 60s, 120s, and 300s.
2. Report candidate identity, trial count, completed trades, targets, liquidations, final marked equity, maximum drawdown, and trade cadence.
3. Add original-log alignment metrics: cooldown-eligible same-side re-entry count, median eligible delay, and logical positions per day.
4. Retain all candidates and select event-replay candidates only by a documented nondominance rule; do not abort losing or sparse trials.
5. Run focused tests.

## Task 4: Run Verified Hyperliquid Event Replays

**Files:**
- Create: `scripts/hypervelocity_reentry_compare.py`
- Create: `data/logs/research/hypervelocity_reentry_comparison_20260727.json`

1. Verify all 2,160 archive bundles and checksums.
2. Reconstruct faithful full-BBWP decisions from strict Hyperliquid 1-minute bars.
3. Replay the current control and each nondominated cooldown challenger through public trade-through evidence.
4. Publish one atomic report containing every serial screen, every selected event replay, source/config hashes, and limitations.
5. Do not mutate `configs/hypervelocity_faithful.toml`.

## Task 5: Decide or Continue

**Files:**
- Modify: `docs/plans/2026-07-27-hypervelocity-reentry-alignment.md`

1. A candidate is profitable only when final equity exceeds the $10,000 start after modeled maker/taker costs; smaller losses are not success.
2. Report maximum drawdown, liquidation count, target rate, trade cadence, and original-log alignment alongside profit.
3. Reject promotion if gains depend on missing evidence, lookahead, fabricated fills, or a change to the frozen target/allocation/leverage contract.
4. If no candidate is profitable, record the falsification and move to the next mechanism rather than tuning cooldowns beyond the predeclared matrix.

## Verification

```bash
uv run pytest tests/test_hypervelocity_maker_replay.py \
  tests/test_hypervelocity_portfolio_eval.py \
  tests/test_hypervelocity_reentry_compare.py -q
ruff check src/hypervector/research/maker_replay_models.py \
  src/hypervector/research/maker_replay.py \
  src/hypervector/research/hypervelocity_portfolio_eval.py \
  src/hypervector/research/hypervelocity_reentry_compare.py \
  scripts/hypervelocity_reentry_compare.py
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
```

## Rollback

The new policy is research-only and defaults to current behavior. Rollback removes the challenger/report files and the optional replay/serial configuration fields. The faithful runtime configuration requires no rollback because this plan does not modify it.

## Execution Note

The active goal explicitly requests continued autonomous testing and tuning, so implementation follows immediately. Git commit/push remains deferred until explicitly requested.

## Measured Result

- The current `regime_reset_60s` serial control completed 328 trades (289 targets/39 liquidations), ended at $173.00, drew down -99.24%, and modeled 3.64 trades/day. It aligned with 5/20 non-overlapping original same-side re-entries.
- Corrected exact-entry alignment requires the candidate's causal
  `entry_direction` to match at the recorded source open, not merely that its
  re-entry policy would permit another attempt. Under that corrected measure,
  `cooldown_only_60s` aligns with 17/20 source re-entries; its policy alone
  permits 20/20. It expanded to 1,270 trades (1,073/197), 14.11/day, and
  effectively zero equity.
- `cooldown_only_120s` aligns exactly with 16/20 (policy permits 19/20) but
  expanded to 1,239 trades (1,049/190), 13.77/day, and effectively zero equity.
- `cooldown_only_300s` aligns exactly with 15/20 (policy permits 17/20) but
  expanded to 1,174 trades (1,003/171), 13.04/day, and effectively zero equity.
- The source contains approximately 2.27 logical positions/day. Every cooldown-only challenger therefore overshot source cadence by more than fivefold while increasing liquidations by more than fourfold.
- No cooldown-only candidate advanced to the expensive event replay. The serial stage retained every trial and falsified the mechanism before an execution-assumption comparison could plausibly rescue it.
- Runtime behavior, the faithful configuration, the 8% target, allocation/leverage, and metalabel observe policy were not changed.

## Decision

Cooldown alone explains most source permission to re-enter but not the source
timing or direction. The next bounded mechanism must require a successful target
followed by fresh directional price continuation; a liquidation or expired
maker attempt must still require regime reset. This follows the source evidence
that 12/15 known same-side re-entries occurred beyond the prior exit in the
trade direction, with a median 2.34 bps additional continuation.
