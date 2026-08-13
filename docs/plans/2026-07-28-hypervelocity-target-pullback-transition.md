# Hypervelocity Target Pullback Transition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether a fresh causal 1m pullback-state transition selectively rearms same-direction entry after an 8% target while the authoritative 5m trend remains intact.

**Architecture:** Keep canonical initial entries and every exit/risk rule unchanged. Add a report-only maker-replay policy that consumes a completed direction until a new 1m state transition away from the 5m structural direction occurs after the target, cooldown, and 30-minute episode maturity. Bound re-entry to six completed targets per structural episode, matching the largest observed creator run, and replay the control and challenger through one verified Hyperliquid event tape regardless of performance.

**Tech Stack:** Python 3.13, pandas, existing causal regime frames, verified 0xArchive Hyperliquid L2/trades, authentic mark/oracle and funding context, pytest, Ruff.

---

## Frozen evidence and invariants

- Fourteen creator same-side windows follow a visible target-like close of at
  least 6% gross margin return.
- Ten contain a fresh 1m state transition before the next creator entry; nine
  do so while the current 5m structural side never resets. A transition away
  from the 5m direction covers eight of those no-reset windows and represents
  the source document's pullback mechanism more narrowly than “any change.”
- The measured evidence is compatible, not causal proof: the recorded open is
  a maker fill timestamp and may follow an earlier private submission.
- The exact challenger is
  `target_pullback_transition_cap6_mature30`: successful-target-only,
  60-second cooldown, 1,800-second structural maturity, maximum six completed
  targets per uninterrupted episode, and no price-clearance threshold.
- Control is canonical `regime_reset_60s`.
- Both paths use the same canonical decisions, $10,000 initial equity, 70%
  isolated allocation, BTC 40x, 8% gross target, post-only maker entry/target,
  trade-through fill, 300-second TTL, venue fees, authentic mark/oracle
  liquidation, partial liquidation, and official funding.
- Runtime, TUI, faithful config, and ML observe-only authority cannot change.
- The report is completed and retained even if source association, drawdown,
  cadence, or equity is poor. Only technical failure aborts it.

## Measured closure

The implementation passed causal pulse, post-target freshness, cooldown,
pre-target non-reuse, and cross-bundle streaming-parity tests. The creator
compatibility calculation retained all 14 target-like same-side windows. Nine
contain the exact transition-away pulse; eight do so without a 5m structural
reset. This supports the pulse as a selected-source association, not as a
sufficient trade trigger.

The complete 2,160-bundle shared-tape replay rejected the challenger:

| Metric | `regime_reset_60s` | `target_pullback_transition_cap6_mature30` |
|---|---:|---:|
| submitted / fills | 343 / 281 | 655 / 575 |
| targets / full liquidations | 241 / 40 | 495 / 80 |
| partial liquidations | 11 | 4 |
| final equity | $3.803370 | $0.001749 |
| maximum drawdown | -99.979399% | -99.999995% |
| fees on resolved trades | $5,886.41 | $3,407.74 |
| net funding cashflow | +$11.88 | +$30.51 |

The lower candidate fee total is not an execution improvement: its equity
collapsed earlier, shrinking later order notionals. The candidate lost money
in every chronological 30-day slice. Its closed-trade growth multiples were
0.04191, 0.00002276, and 0.18335 versus control values 0.50757, 0.008056, and
0.09301. It improved only the already-losing third slice while materially
worsening the first two and the full path.

Only 136 resolved signal identities were shared. The candidate introduced
439 candidate-only resolved lifecycles and displaced 145 control lifecycles,
so this is broad path substitution rather than selective source repair. The
rule is rejected and remains report-only. Runtime, TUI, faithful config,
fixed 8% target, and ML observe-only authority are unchanged.

Artifact:
`data/logs/research/hypervelocity_target_pullback_transition_20260728.json`,
SHA-256
`53d2ebe947fa0394e7313e7cad3a2988875436f3bda3f7b27e4ad1927931dcb2`.

Confidence is high that this exact pulse/cap/maturity policy is not sufficient
under the frozen replay assumptions. External confidence is medium because
creator fill timestamps can lag private submissions and public trade-through
cannot observe queue rank. Complete venue-matched creator logs showing that
the actual policy uses materially rarer transition events with better losing
outcomes would update the result.

## Task 1: Causal pullback-event projection

**Files:**
- Modify: `src/hypervector/research/maker_replay_signals.py`
- Test: `tests/test_hypervelocity_maker_replay.py`

1. Write a failing test proving a re-entry event appears only when completed
   1m state changes away from the current 5m structural direction.
2. Prove the event series shifts forward exactly one minute with all other
   maker decision projections.
3. Implement `available_reentry_events()` with explicit required columns and
   no fallback or future fill.
4. Run the focused test and retain the red/green output.

## Task 2: Stateful event-only target re-entry

**Files:**
- Modify: `src/hypervector/research/maker_replay_models.py`
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Write failing tests for the new policy identity and invalid combinations.
2. Write a failing replay test proving a persistent 5m trend cannot re-enter
   after target without a fresh pullback event.
3. Prove an event after cooldown and maturity permits one maker attempt.
4. Prove pre-target events do not persist, and liquidation or expired maker
   intent does not rearm from the event.
5. Reuse the existing per-episode target count and maturity fields, allowing
   them only for the two target-continuation policy families.
6. Run all maker replay tests.

## Task 3: Streaming shared-tape parity

**Files:**
- Modify: `src/hypervector/research/maker_replay_stream.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Write a failing parity test showing batch and streaming replay consume the
   same event pulses and produce the same lifecycle result.
2. Thread the causal event projection through the streaming decision cursor.
3. Preserve all existing replay candidate identities and default behavior.
4. Run the focused parity and replay suites.

## Task 4: Creator compatibility and immutable report

**Files:**
- Create: `src/hypervector/research/hypervelocity_pullback_reentry.py`
- Create: `scripts/hypervelocity_pullback_reentry.py`
- Create: `tests/test_hypervelocity_pullback_reentry.py`
- Create after execution:
  `data/logs/research/hypervelocity_target_pullback_transition_20260728.json`

1. Write failing tests that identify target-like creator anchors causally,
   retain reset/censored windows, and count event coverage without inventing
   missing close times.
2. Implement the exact control/challenger configurations and source report.
3. Add a CLI that verifies the faithful config checksum, archive manifests,
   price/funding hashes, candidate identity, and decision hashes.
4. Replay both candidates over all 2,160 verified hourly bundles and write the
   complete immutable report.
5. Report submissions, fills, targets, full/partial liquidations, fees,
   funding, final equity, maximum drawdown, three chronological slices,
   lifecycle substitution, and source compatibility.

## Task 5: Decision record and verification

**Files:**
- Modify: `docs/plans/2026-07-28-hypervelocity-target-pullback-transition.md`
- Modify: `docs/reviews/2026-07-28-source-fidelity-runtime-audit.md`
- Modify: `HANDOFF.md`

1. Record the measured result, uncertainty, and falsifiers without promoting
   from development evidence.
2. Run task-focused pytest, Ruff, formatting, diff hygiene, artifact
   assertions, and faithful config hashing.
3. Run `uv run pytest tests/ -q -m "not network"` and
   `cargo test -p hypervector-tui`.
4. Confirm paper remains no-submit, live remains fail-closed, and ML remains
   observe-only.

## Risks and falsifiers

- Fill timestamps are an imperfect proxy for private signal timestamps.
- A 1m state transition can remain too frequent even when it is event-based.
- The six-entry cap and 30-minute maturity are creator-bounded development
  choices and require later confirmation.
- Broad lifecycle substitution can make fewer entries worse rather than safer.
- New creator logs without pullback transitions in repeated-entry windows
  weaken behavioral compatibility.
- A candidate that does not improve source coverage, full-window equity,
  drawdown, and every chronological slice remains report-only. This criterion
  determines recommendation, not whether the trial is executed or retained.

The measured candidate failed the economic and slice criteria and exhibited
the predicted broad-substitution failure mode.

## Verification closure

- Focused replay/re-entry tests: 89 passed.
- Full non-network Python suite: 1,044 passed, four deselected, 31 warnings.
- Rust TUI suite: 33 passed.
- Task-scoped Ruff lint/format, Cargo format, diff hygiene, file/function-size
  limits, config hashing, artifact hashing, lifecycle accounting, and funding
  arithmetic passed.
- CLI status confirms paper is no-submit and live is fail-closed without both
  explicit risk flags and secrets. ML remains configured as observe-only for
  the faithful profile.
- Final `docs/external` inventory contains no file newer than
  2026-07-27 19:07:50 EDT. The history screenshot's SHA matches the
  supplemental CSV and both visible +8% rows were included. The active short
  screenshot lacks a replayable timestamp and resolved outcome, so no label
  was invented from it.
