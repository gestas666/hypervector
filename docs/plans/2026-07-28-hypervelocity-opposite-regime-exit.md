# Hypervelocity Opposite-Regime Exit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether exiting an open Hypervelocity position only when the authoritative 5m structure confirms the opposite direction can reproduce the source strategy's trend-invalidation losses and produce profitable stateful venue execution while retaining the fixed 8% target and hold-through-RANGE behavior.

**Architecture:** Add one disabled-by-default research replay option that closes an open position at adverse BBO after a causally available opposite 5m structural direction. RANGE, TRANSITION, UNKNOWN, same-side structure, 1m state, and 15m context cannot trigger the exit. Replay the unchanged TP-only control and this single candidate over one checksum-verified Hyperliquid event tape with authentic mark, oracle, and funding context; do not mutate runtime or the faithful TOML.

**Tech Stack:** Python 3.13, pandas, dataclasses, pytest, immutable 0xArchive Hyperliquid L2/public trades, official Hyperliquid price/funding context.

---

## Frozen evidence and contract

- Source behavior: the reverse-engineering record says positions remain aligned
  with the prevailing trend, flip when the trend reverses, and can hold through
  long intervals. The user separately requires that RANGE never force-closes an
  open trade.
- Current authentic TP-only control: hard-BBWP25/recovery-6, 445 fills, 402
  targets, 43 full liquidations, $20.2578 from $120, and -99.4317% maximum
  drawdown. Every prior entry/fill family retained roughly 40-43 liquidations.
- A prior fixed-lifecycle first-opposite-5m screen intercepted 36/41 modeled
  liquidations and cut 47 eventual targets. It improved additive PnL but
  remained negative. That screen did not model stateful exits, re-entry path,
  adverse BBO, authentic funding, or the $10,000 shadow partial-liquidation
  threshold, so it neither validates nor falsifies this exact trial.
- Candidate trigger: the latest causally available `structural_direction` is
  `short` while a long is open, or `long` while a short is open.
- Non-triggers: `None`, RANGE, TRANSITION, UNKNOWN, same-side structure, 1m
  opposition, 15m opposition, confidence, model score, RSI, BBWP, funding, or
  orderbook pressure.
- Execution order at one event: apply authentic mark liquidation first; if the
  position survives, apply the opposite-regime exit at adverse BBO with the
  taker fee before checking a passive target fill. This is conservative when
  both are observable at the same snapshot.
- Preserve one BTC position, 70% isolated margin, 40x, maker entry/target fees,
  taker exit fee, fixed 8% gross margin target, 300-second maker TTL and
  post-exit cooldown, regime-reset same-side policy, and official hourly
  funding.
- Fixed searched set: `tp_only_control` and
  `opposite_5m_structural_exit`. No delay, persistence, buffer, 1m, or 15m
  variant may be added after inspecting results.
- Runtime, TUI, faithful configuration, and ML observe-only authority remain
  unchanged.

## Measurable decision evidence

- Correctness: prefix-stable completed-bar structural projection; RANGE cannot
  exit; same-side structure cannot exit; liquidation has priority; taker fee
  and adverse BBO are exact; output is immutable and both candidates share one
  validated event tape.
- Economics: report submissions, fills, targets, regime exits, full/partial
  liquidations, fees, funding, final realized/marked equity, maximum drawdown,
  and every 30-day slice. Profitability requires final marked equity above
  $10,000 after all modeled costs, but a losing result is retained rather than
  treated as a technical error.
- Fidelity: report source positions for which an opposite 5m direction became
  available while open, the first such timestamp, creator close timestamp,
  lead/lag, and whether the source position remained open through RANGE.
  Missing or unreliable close evidence remains explicit.
- Path attribution: report shared/control-only/candidate-only signal identities,
  target-to-regime-exit and liquidation-to-regime-exit substitutions, stopped
  eventual targets, and liquidations avoided.
- Confidence cannot exceed medium without a fresh sealed venue-matched shadow
  window and complete creator losses with exit reasons.

### Task 1: Add disabled-by-default replay accounting

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay_risk.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write failing tests proving the default never regime-exits, RANGE/`None` and
   same-side structure do not exit, and opposite structure does.
2. Write failing tests proving liquidation wins event-order ambiguity and a
   surviving regime exit uses long bid/short ask, charges the taker fee, and
   records `regime_exited` exactly once.
3. Run the focused tests and observe failures caused by the absent option.
4. Add `opposite_regime_exit: bool = False` to `MakerReplayConfig`,
   `regime_exited` to resolved lifecycle/trade status, and `regime_exits` to the
   report/state contracts.
5. Add one typed risk-boundary helper and invoke it after liquidation but before
   stop/time/target handling at book snapshots. A trade event without a fresh
   BBO cannot fabricate adverse-BBO execution.
6. Run focused tests, Ruff, format, and function/file-size checks.

### Task 2: Add a two-candidate immutable replay report

**Files:**
- Create: `src/hypervector/research/hypervelocity_regime_exit_compare.py`
- Create: `scripts/hypervelocity_regime_exit_compare.py`
- Create: `tests/test_hypervelocity_regime_exit_compare.py`

1. Write failing tests for exact candidate identities, shared tape/config
   invariants, lifecycle substitution accounting, 30-day slices, source-exit
   compatibility, observe-only policy, and immutable output refusal.
2. Reuse strict bars, creator-source normalization, verified archive bundles,
   authentic replay context, faithful profile loading, and the existing
   hard-BBWP25/recovery-6 decision construction; do not duplicate them.
3. Replay both configs through `replay_maker_order_grid_chunks` with $10,000
   initial equity and one shared trade-through tape.
4. Hash every input and stamp decision/config/candidate identities,
   `report_only=true`, and `runtime_strategy_changed=false`.
5. Write one immutable JSON report. Do not persist or install a model.

### Task 3: Run the complete venue and source comparison

**Files:**
- Create: `data/logs/research/hypervelocity_opposite_regime_exit_20260728.json`
- Modify: `docs/reviews/2026-07-27-creator-screenshot-forward-validation.md`
- Modify: `HANDOFF.md`

1. Run April 28 through July 27 UTC over all 2,160 verified hourly L2/trade
   bundles using the strict 90-day Hyperliquid bars and authentic price/funding
   paths.
2. Complete the technically valid run regardless of interim equity, drawdown,
   trade count, or regime-exit count.
3. Verify every archive checksum, candidate identity, source hash, and runtime
   observe-only policy before accepting the report.
4. Compare economics, lifecycle substitutions, source compatibility, and
   30-day slices. Explicitly distinguish "less catastrophic" from profitable.
5. Keep runtime unchanged unless a separate future promotion decision is made.

### Task 4: Full verification

1. Run focused tests and task-scoped Ruff/format checks.
2. Run `uv run pytest tests/ -q -m "not network"` and
   `cargo test -p hypervector-tui`.
3. Run Cargo formatting, diff hygiene, file/function-size checks, CLI status,
   artifact assertions, and faithful configuration hashing.
4. Do not commit or push unless explicitly requested.

## Risks and falsifiers

- A confirmed opposite 5m state may arrive only after liquidation at 40x; no
  benefit would falsify the exit latency hypothesis.
- Brief 5m flips may realize losses that would otherwise reach the target;
  excessive target-to-regime-exit substitution would falsify fidelity/economics.
- Stateful re-entry can create a different and worse sequence even if each
  intercepted liquidation looks better independently.
- Public BBO lacks private depth and exact stop-market slippage. A survivor
  would still require fresh shadow and small-capital live-canary validation.
- Complete creator losses showing target-only holding or exits before any
  opposite 5m confirmation would falsify the inferred trend-invalidation rule.

## Measured result and decision

The immutable authentic-context report is
`data/logs/research/hypervelocity_opposite_regime_exit_20260728.json`, SHA-256
`da8dc0fb9bfce3991d955c0423d9d3637e2fa9e73568b6e6ed1fdeebde4a3518`.
It verified all 2,160 hourly archive bundles and retained the faithful config
hash `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.

| Candidate | Fills | Targets | Regime exits | Full liq. | Final $10,000 | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| TP-only control | 408 | 369 | 0 | 39 | $2,466.13 | -97.83% |
| Opposite 5m exit | 577 | 409 | 162 | 6 | $8.10 | -99.96% |

The exit reduced full liquidations but failed economically and behaviorally.
Its 162 regime exits averaged -$350.08 after modeled costs. Among 350 shared
resolved signal identities, 26 control liquidations became regime exits, but
65 control targets also became regime exits. Stateful rearming introduced 227
candidate-only resolved lifecycles and raised total modeled fees from
$13,847.07 to $16,944.12.

The creator compatibility audit also rejects 5m opposition as an authoritative
exit. Twelve of 33 closed creator positions remained open after the current
detector had already made an opposite 5m direction causally available; two
additional open or close-unknown rows also encountered opposition. Eighteen of
35 creator positions encountered RANGE, consistent with the explicit
hold-through-RANGE requirement.

The candidate is rejected and remains disabled. Runtime, TUI, faithful TOML,
8% target, and ML observe-only authority are unchanged. Confidence is high for
the relative replay comparison because the candidates shared one verified tape
and differed by one flag. Confidence is medium for live execution due to public
BBO depth limits and incomplete creator loss/exit evidence. A complete creator
ledger showing that losing positions consistently close on these exact causal
5m reversals would update this decision; the supplied holds currently point the
other way.

Verification after the final refactor passed 1,020 non-network Python tests
with four deselected and 31 warnings, all 33 Rust TUI integration tests, 89
focused replay/comparison tests, task-scoped Ruff and formatting, Cargo
formatting, diff hygiene, file/function-size limits, artifact assertions, the
faithful config hash, and CLI fail-closed status.
