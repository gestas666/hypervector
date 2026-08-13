# Hypervelocity BBWP Tactical Trigger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use test-driven development and verification-before-completion task by task.

**Goal:** Replace the canonical Hypervelocity Choppiness Index evidence with causal BBWP compression, apply measurable 21/55, 1 bps, 8 bps, and 2.5x-volume rules, and expose RSI/EMA plus BBWP tactical setup quality without silently overgating new entries.

**Architecture:** The regime classifier remains the source of completed-bar features and the 5m primary state. It publishes causal 1m tactical evidence separately from persistent 5m structural eligibility. The backend enters on 5m trend structure or direction-confirmed 1m+5m breakouts; BBWP/RSI alignment is annotation-only after the strict conjunction failed venue-matched comparison. The TUI remains a read-only projection of those backend fields.

**Tech Stack:** Python 3.13, pandas, pytest, TOML runtime profile, Rust/Ratatui telemetry projection.

---

## Explicit interpretation and constraints

- EMA lengths become 21/55 on every classified timeframe.
- The existing 240-bar structure window and 1 bps EMA-separation threshold remain causal.
- Choppiness Index is removed from the canonical classifier. BBWP uses Bollinger width length 20, a 240-bar percentile window, and compression below 25%.
- A 1m tactical annotation requires the immediately preceding completed bar to be compressed, the current close to clear its causal range boundary by 8 bps, current volume to be at least 2.5 times the preceding 20-bar mean, a same-direction 21/55 gap of at least 1 bps, and an RSI(14) crossover of RSI-EMA(7) on the current completed bar.
- The persistent 5m structural direction, canonical entry eligibility, and one-bar tactical annotation are separate backend fields. Pending maker orders remain valid only while the structural direction remains the same and retain the existing 300-second TTL.
- Empirical falsification: on 129,600 strict Hyperliquid 1m bars and 35 venue-matched historical entries, the strict BBWP+RSI+breakout conjunction emitted 13 annotations and matched 0/35 entries, including zero within 30 minutes. Persistent 5m structural eligibility matched 24/35 exactly and 27/35 within 10 minutes. Therefore the tactical conjunction is not an execution gate in this change.
- The 15m state stays report-only/non-veto because the supplied heading and current project contract say non-veto, despite a contradictory strict-veto bullet.
- No 5m zone-proximity entry gate is added because “pulling back toward a wick-to-close zone” has no numeric zone construction or distance tolerance. Causal structure boundaries will be exposed for measurement before such a gate is considered.
- Existing open positions continue to hold until the 8% margin target; this work changes only new-entry qualification.

### Task 1: Configuration contract

**Files:**
- Modify: `src/hypervector/regime/classifier.py`
- Modify: `src/hypervector/strategies/hypervelocity_contract.py`
- Modify: `configs/hypervelocity_faithful.toml`
- Test: `tests/test_hypervelocity_contract.py`
- Test: `tests/test_hypervelocity_profile.py`

1. Write failing assertions for 21/55, BBWP 20/240/<25, RSI 14/7, 8 bps clearance, and 2.5x volume.
2. Run the two focused tests and confirm failures are caused by the old contract.
3. Replace Choppiness Index settings with typed BBWP and RSI settings and update the faithful TOML.
4. Run the focused tests until green.

### Task 2: Causal classifier features

**Files:**
- Modify: `src/hypervector/regime/classifier.py`
- Test: `tests/test_regime_classifier.py`

1. Add failing tests proving BBWP compression replaces Choppiness Index, prefix invariance remains intact, and 8 bps/2.5x breakouts reject weaker events.
2. Add failing tests for directional RSI cross and prior-bar compression readiness.
3. Implement BBWP, signed EMA gap, RSI-EMA crossover, causal prior range/volume ratios, and structure-boundary telemetry.
4. Run classifier tests until green.

### Task 3: Structural context versus tactical trigger

**Files:**
- Modify: `src/hypervector/regime/composite.py`
- Modify: `src/hypervector/strategies/hypervelocity.py`
- Modify: `src/hypervector/strategies/hypervelocity_runtime.py`
- Modify: `src/hypervector/paper/event_runtime.py`
- Modify: `src/hypervector/paper/session.py`
- Test: `tests/test_regime_classifier.py`
- Test: `tests/test_hypervelocity.py`
- Test: `tests/test_hypervelocity_runtime.py`
- Test: `tests/test_paper_session.py`

1. Write failing tests showing a 5m structural trend remains eligible, an opposite 1m tactical annotation cannot reverse it, a vanished annotation does not cancel a structurally valid pending maker order, and an invalid/opposite 5m context does cancel it.
2. Publish separate structural, eligible-entry, and tactical-annotation directions from the backend classifier.
3. Pass both fields into the pure execution coordinator without changing TP, sizing, fees, liquidation, or open-position range behavior.
4. Run focused strategy/runtime/session tests until green.

### Task 4: Backend telemetry and read-only TUI

**Files:**
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/telemetry.py`
- Modify: `crates/hypervector-tui/src/backend_telemetry.rs`
- Modify: `crates/hypervector-tui/src/chart_view.rs`
- Test: `tests/test_paper_session.py`
- Test: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Test: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Write failing tests for BBWP readiness, RSI/EMA/crossover, structural direction, tactical annotation, clearance, volume ratio, and structure boundaries in ledger telemetry.
2. Add the telemetry without TUI-side signal computation.
3. Render compact backend-authored setup evidence and structure levels on Screen 3.
4. Run focused Python and Rust tests until green.

### Task 5: Evaluation and verification

**Files:**
- Modify: `src/hypervector/regime/tuning.py`
- Modify: `skills/hypervector-regime-detector/SKILL.md`
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `HANDOFF.md`

1. Update the tuner schema so it no longer emits removed Choppiness Index fields.
2. Run chronological regime evaluation on the available venue-matched data and compare state/entry counts against the prior contract; do not treat performance as a technical gate.
3. Run `uv run pytest tests/ -q -m "not network"`.
4. Run `cargo test -p hypervector-tui`, strict Clippy, Ruff, formatting, and `git diff --check`.
5. Confirm the already-running shadow process was not interrupted and state that a restart is required before the new contract applies.
