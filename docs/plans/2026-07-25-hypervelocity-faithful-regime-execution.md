# Hypervelocity Faithful Regime Execution Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans, test-driven-development, and verification-before-completion task-by-task.

**Goal:** Make the backend the single authoritative implementation of the observed Hypervelocity strategy: BTC 1m execution, entries only during directional breakout or confirmed trend, 70% equity margin allocation at 40x, fixed 8% margin take profit, maker-order replay, annotation-only ML, and a read-only TUI.

**Architecture:** A causal multi-timeframe classifier emits canonical `TREND_UP`, `TREND_DOWN`, `BREAKOUT`, `RANGE`, `TRANSITION`, and `UNKNOWN` events. Hypervelocity consumes those events through one backend lifecycle; 1m handles timing, 5m supplies the primary market state, and 15m is context rather than an unconditional veto. Research, paper, CLI, and TUI consume the same decision and ledger schemas without recomputing strategy outcomes.

**Tech Stack:** Python 3.13, pandas, NumPy, VectorBT research, event-driven paper/Nautilus execution, pytest, Rust 2021, serde/serde_json, Ratatui, Cargo tests.

**Implementation status (2026-07-25):** Tasks 1–10 are implemented. Corrected causal evaluation produced 29/35 exact
directions for the selected zero-false-range-at-entry candidate; this is not a
claim that all range intervals are correct because the source log contains
positive entries rather than labeled negative intervals. The bounded maker
replay produced 8 entry fills and 7 completed trades from 32,609 snapshots.
LightGBM, current-row logistic, and three-event lag logistic candidates all
failed to beat the past-only constant log-loss baseline and remain uninstalled,
annotation-only research artifacts.

---

## Fixed contract and explicitly unknown behavior

Fixed baseline facts:

- BTC, 1m execution.
- Allowed new-entry states: `TREND_UP`, `TREND_DOWN`, `BREAKOUT/BK_UPWARD`, `BREAKOUT/BK_DOWNWARD`.
- No new entries in `RANGE`, `TRANSITION`, or `UNKNOWN`.
- `COILING` is preparation, not a confirmed breakout.
- 70% of current equity is allocated as margin; 40x gives 28x equity notional before venue constraints.
- Fixed 8% return-on-margin take profit, equal to a 0.2% price move at 40x before fees.
- Maker/post-only execution is the faithful baseline.
- ML is observation-only and cannot reject or resize baseline trades.
- TUI is telemetry-only and cannot create trades or mutate backend strategy configuration.

Unknowns remain research parameters and must not be silently invented: exact stop/invalidation, breakout lookback/confirmation, regime hysteresis, and split-position exit behavior.

Out of scope for this phase: a future range-trading strategy. It must use a separate strategy identifier, configuration, lifecycle, research board, and model artifacts; it must not enable range entries inside Hypervelocity.

### Task 1: Encode the canonical regime and strategy contract

**Files:**
- Create: `src/hypervector/regime/models.py`
- Create: `src/hypervector/strategies/hypervelocity_contract.py`
- Modify: `src/hypervector/regime/__init__.py`
- Test: `tests/test_hypervelocity_contract.py`

1. Write failing tests for the six primary labels, directional breakout subcodes, allowed-entry mapping, 70% margin allocation, 40x leverage, and 8% margin target conversion.
2. Run `uv run pytest tests/test_hypervelocity_contract.py -q` and confirm RED because the modules do not exist.
3. Implement typed enums/dataclasses with input validation and no `Any`.
4. Define entry mapping exactly:

```python
TREND_UP -> long
TREND_DOWN -> short
BREAKOUT + BK_UPWARD -> long
BREAKOUT + BK_DOWNWARD -> short
RANGE | TRANSITION | UNKNOWN | directionless BREAKOUT -> none
```

5. Run the focused tests and commit `feat(regime): encode faithful hypervelocity contract`.

### Task 2: Build a causal multi-timeframe regime classifier

**Files:**
- Create: `src/hypervector/regime/classifier.py`
- Create: `src/hypervector/regime/composite.py`
- Modify: `src/hypervector/regime/ultimate.py`
- Test: `tests/test_regime_classifier.py`
- Test: `tests/test_ultimate_regime.py`

1. Write failing synthetic-series tests for trend up/down, range, coiling, confirmed upward/downward breakout, warmup `UNKNOWN`, and no-lookahead completed-bar joins.
2. Add a failing test proving compression alone is not `BREAKOUT`.
3. Add a failing multi-TF test proving:
   - 5m is primary state;
   - 15m is recorded context, not a mandatory veto;
   - confirmed 1m+5m directional breakout may override stale 15m trend;
   - disagreement without breakout becomes `TRANSITION` only when structure is actually mixed.
4. Run focused tests and confirm RED.
5. Implement percentile-based trend/range structure and strict prior-range directional breakout using only completed bars.
6. Keep confidence as telemetry; do not turn it into an entry threshold.
7. Replace the misleading compression-as-breakout and nonzero range/transition policy in `ultimate.py`.
8. Run focused tests and commit `feat(regime): add causal multi-timeframe classifier`.

### Task 3: Add a Hypervelocity regime acceptance evaluator

**Files:**
- Create: `src/hypervector/regime/hypervelocity_eval.py`
- Modify: `src/hypervector/cli.py`
- Test: `tests/test_hypervelocity_regime_eval.py`
- Fixture: `docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv`

1. Write failing tests for manual-entry direction recall, false-range count at known entries, false-breakout rate, label churn, transition latency, state distribution, and venue/source provenance.
2. Implement a report-only `hypervelocity-regime-eval` CLI command. A weak score is a result, never a technical failure.
3. Compare 5m-primary/15m-context, hard-15m, and 30m-context research arms without changing the fixed strategy contract.
4. Mark results from mismatched venues as limited-evidence rather than silently pooling them.
5. Run focused tests and commit `feat(cli): add hypervelocity regime evaluation`.

### Task 4: Replace guessed Hypervelocity signal gates with canonical backend decisions

**Files:**
- Modify: `src/hypervector/strategies/hypervelocity.py`
- Modify: `src/hypervector/strategies/registry.py`
- Test: `tests/test_hypervelocity.py`

1. Write failing tests proving range/transition/unknown produce no entries, directional trend/breakout produce the correct side, and no RSI/pullback/second-EMA gate suppresses an otherwise valid canonical event.
2. Write a failing test for a unified long/short lifecycle rather than the current long-only generic registration.
3. Preserve the legacy inferred EMA strategy under an explicitly named research-only identifier if needed for reproducibility.
4. Make the faithful strategy consume canonical regime decisions and emit reasons for every candidate and no-entry decision.
5. Run focused tests and commit `feat(strategy): consume canonical hypervelocity decisions`.

### Task 5: Implement faithful sizing and a single exit lifecycle

**Files:**
- Create: `src/hypervector/strategies/hypervelocity_lifecycle.py`
- Modify: `src/hypervector/sweep/metrics.py`
- Modify: `src/hypervector/nautilus/sizing.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_hypervelocity_lifecycle.py`
- Test: `tests/test_nautilus_sizing.py`
- Test: `tests/test_paper_session.py`

1. Write failing tests for 70%-of-equity margin allocation, 28x-equity BTC notional at 40x, venue cap enforcement, compounding after realized PnL, and fixed 8% margin TP.
2. Write a failing regression test showing Hypervelocity exits are not passed through a second ATR/RR engine.
3. Represent stop/invalidation as an explicit required research policy. Do not default silently to ATR.
4. Ensure range blocks new entries but does not force-close an open position unless the selected exit policy explicitly says so.
5. Run focused tests and commit `feat(strategy): add faithful sizing and lifecycle`.

### Task 6: Add causal maker/post-only order replay

**Files:**
- Modify: `src/hypervector/paper/order_intent.py`
- Modify: `src/hypervector/paper/fill_models.py`
- Modify: `src/hypervector/research/impulse_replay.py`
- Test: `tests/test_paper_order_intent.py`
- Test: `tests/test_paper_fill_models.py`
- Test: `tests/test_impulse_replay.py`

1. Write failing tests for post-only intent, resting orders, causal fill/no-fill outcomes, maker fees, partial fills, cancellation, and stale/missing L2 provenance.
2. Ensure the old 10%-TP `WOULD_*` tape is feature evidence only and is never treated as an authentic 8%-TP outcome label.
3. Export every unfilled opportunity and rejected technical event; do not retain only successful trades.
4. Run focused tests and commit `feat(replay): add faithful maker order lifecycle`.

### Task 7: Restrict autotune to unknown detector behavior

**Files:**
- Modify: `src/hypervector/strategies/hypervelocity.py`
- Modify: `src/hypervector/sweep/autotune.py`
- Modify: `src/hypervector/sweep/search.py`
- Test: `tests/test_autotune.py`

1. Write failing tests proving autotune cannot change 70%, 40x, 8%, allowed states, maker baseline, or ML observation-only mode.
2. Expose only unknown parameters: breakout lookback/clearance/volume confirmation, range thresholds, confirmation bars, minimum duration, 5m/15m/30m context arm, and explicit stop-policy experiments.
3. Report every technically valid trial, including losing/low-trade trials.
4. Use chronological walk-forward folds with separate manual-entry recall and market-outcome reports.
5. Run focused tests and commit `feat(autotune): tune only hypervelocity unknowns`.

### Task 8: Train annotation-only model alternatives

**Files:**
- Modify: `src/hypervector/ml/labels.py`
- Modify: `src/hypervector/ml/replay_models.py`
- Modify: `src/hypervector/ml/train_bundle.py`
- Test: `tests/test_replay_models.py`
- Test: `tests/test_ml_walk_forward.py`

1. Define the event label as: a causally filled candidate maker order reaches +8% margin before the selected authentic stop/invalidation/timeout.
2. Compare regularized logistic regression, LightGBM, and one temporal candidate such as a TCN when dependencies permit; keep the same purged walk-forward folds.
3. Keep every model uninstalled and `observe` only. Report calibration, AUC, log loss versus baseline, Brier score, class balance, and temporal stability.
4. If a temporal dependency is unavailable, record the technical limitation and continue the other arms rather than failing the experiment.
5. Run focused tests and commit `feat(ml): add hypervelocity annotation candidates`.

### Task 9: Make backend telemetry the only runtime truth

**Files:**
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/report.py`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `crates/hypervector-tui/src/hypervelocity.rs`
- Test: `tests/test_paper_acceptance_matrix.py`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Test: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Add failing parity tests for regime primary/secondary, context timeframes, reason, order lifecycle, position, equity, realized/unrealized PnL, strategy ID, run ID, and annotation fields.
2. Remove any remaining TUI trade-generation or strategy-policy mutation path.
3. Preserve last confirmed backend snapshot as stale on disconnect; never synthesize fallback trades.
4. Run Python and Rust focused tests and commit `fix(tui): render canonical backend hypervelocity telemetry`.

### Task 10: Configure, document, and verify the complete system

**Files:**
- Modify: `configs/default.toml`
- Create: `configs/hypervelocity_faithful.toml`
- Modify: `docs/guides/acceptance-visual-and-holistic.md`
- Modify: `HANDOFF.md`

1. Add explicit config keys for the fixed contract and research-only unknown parameters. Default paper/shadow mode remains no-submit; live remains unarmed.
2. Run:

```bash
uv run pytest tests/ -q -m "not network"
cargo test -p hypervector-tui
uv run python -m hypervector status
uv run python -m hypervector paper-check
git diff --check
```

3. Run a bounded historical maker replay and a bounded shadow session.
4. Verify exact backend-to-TUI parity and zero new entries during `RANGE`, `TRANSITION`, and `UNKNOWN`.
5. Record unresolved stop/split-exit uncertainty and all empirical results without promotion language.
6. Commit documentation and verification evidence separately.

## Completion and falsification criteria

The implementation is not considered faithful merely because tests pass. It must also demonstrate:

- zero range/transition/unknown entries in deterministic fixtures and replay;
- no current known manual entry mislabeled as range under the selected candidate, subject to explicit venue-data caveats;
- directional breakout requires an actual prior-range break and direction;
- no 15m hard veto unless a separate research arm earns that choice;
- exact 70%/40x/8% arithmetic and maker accounting;
- one exit lifecycle rather than stacked strategy and portfolio barriers;
- annotation-only ML leaves baseline decisions and sizing unchanged;
- paper/shadow never constructs a live execution client;
- TUI numbers and reasons equal backend ledger values exactly.

Evidence that would update the design includes authentic stop/invalidation rules, a complete account ledger for the 14 unreconciled positions, or point-in-time Bitget/Hyperliquid bars showing that another higher timeframe materially improves manual-entry recall and false-range performance.
