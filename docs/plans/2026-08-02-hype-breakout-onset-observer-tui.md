# HYPE Breakout-Onset Observer and TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one bidirectional, observe-only HYPE 5-minute breakout-onset challenger and expose its exact backend-authored state across the four-screen cohort TUI without granting execution authority.

**Architecture:** The provider consumes the existing shared Hyperliquid 1-minute candle frame and derives completed-bar 1m/5m/15m regime telemetry through the existing causal range decision builder. It emits one annotation only when the authoritative 5-minute state transitions into `BREAKOUT`, chooses long or short from the existing hourly structural direction, and remains outside `execution_symbols`. The Rust TUI only parses and renders the new configuration/evaluation rows; it does not classify bars or infer missing fields.

**Tech Stack:** Python 3.12, pandas, existing Hypervector live-provider contracts, pytest, Rust/Ratatui, cargo test, cargo clippy.

---

### Task 1: Freeze the causal provider contract

**Files:**
- Create: `tests/test_hype_breakout_cohort_provider.py`
- Create: `src/hypervector/live/hype_breakout_cohort_provider.py`

**Step 1: Write the failing tests**

Add deterministic completed-decision fixtures proving:

- a non-`BREAKOUT` to `BREAKOUT` transition emits one long or short annotation;
- a persistent `BREAKOUT` does not re-emit;
- leaving and later re-entering `BREAKOUT` permits a new annotation;
- neutral structural direction remains ineligible with an explicit blocker;
- the startup seed exposes readiness but emits no retroactive intent;
- only `HYPE` is accepted and decision times remain strictly causal.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/test_hype_breakout_cohort_provider.py -q`

Expected: collection fails because `hype_breakout_cohort_provider` does not exist.

**Step 3: Implement the minimal provider**

Create `HypeBreakoutOnsetCollector` with a typed callable contract returning `IntentBatch`. Use existing `build_completed_live_decisions`, inspect the prior completed 5-minute state before each candidate row, and expose exact regime, confidence, structural direction, readiness, and blocker telemetry. Do not add position sizing, exits, order adapters, or threshold selection.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/test_hype_breakout_cohort_provider.py -q`

Expected: all provider tests pass.

### Task 2: Wire the provider into the disarmed cohort

**Files:**
- Modify: `configs/multi_asset_bidirectional_canary.toml`
- Modify: `src/hypervector/live/multi_asset_live_config.py`
- Modify: `src/hypervector/live/multi_asset_intent_poller.py`
- Modify: `tests/test_multi_asset_live_config.py`
- Modify: `tests/test_multi_asset_intent_poller.py`

**Step 1: Write failing configuration and polling tests**

Require the fourth provider identity `hype_breakout_onset_bidirectional_v1`, exactly one symbol (`HYPE`), both sides, a 1-minute source clock, and an empty execution scope. Update first-cycle coverage from nine to ten provider/symbol evaluations while retaining four shared market-data fetches.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/test_multi_asset_live_config.py tests/test_multi_asset_intent_poller.py -q`

Expected: failures report the missing provider/config/collector and nine-versus-ten coverage mismatch.

**Step 3: Implement configuration and poller wiring**

Add the provider constant, strict source contract, one-minute timeframe, readiness seed horizon, default collector, and TOML provider row. Keep `execution_symbols = []`; the existing SOL range provider remains the only configured execution pair.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/test_multi_asset_live_config.py tests/test_multi_asset_intent_poller.py -q`

Expected: all configuration and polling tests pass with four fetches per cycle and ten evaluations.

### Task 3: Preserve audit and backend telemetry parity

**Files:**
- Modify: `tests/test_multi_asset_observer_audit.py`
- Modify: `tests/test_cohort_observer_checkpoint.py`
- Modify only if required by failing tests: observer/audit parsing modules under `src/hypervector/research/`

**Step 1: Update expected identity coverage tests**

Require ten expected provider/symbol pairs, explicit observe-only authority for the HYPE challenger, and complete causal 5/15/30/60-minute path accounting without fill/PnL claims.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/test_multi_asset_observer_audit.py tests/test_cohort_observer_checkpoint.py -q`

Expected: fixtures that still declare nine pairs fail.

**Step 3: Make the smallest parser/audit changes required**

Prefer fixture-only changes if the generic provider contract already handles the fourth provider. Do not add execution outcomes or success-shaped defaults.

**Step 4: Run tests to verify GREEN**

Run the same focused command and require zero failures.

### Task 4: Render the tenth provider at the acceptance floor

**Files:**
- Modify: `crates/hypervector-tui/src/cohort_widgets.rs`
- Modify only if layout evidence requires it: `crates/hypervector-tui/src/cohort_router.rs`
- Modify: `crates/hypervector-tui/tests/bidirectional_cohort_view_test.rs`

**Step 1: Write failing Rust render assertions**

Add the backend identity and evaluation fixture for the HYPE provider. Require alias `HYPE BK ONSET`, `EVALUATED 10`, all ten setup rows at 120x36, `OBSERVE ONLY` on screen 4, exact provider provenance, native candlestick bodies/wicks on screen 3, and no clipped leading-setup panel.

**Step 2: Run tests to verify RED**

Run: `cargo test -p hypervector-tui --test bidirectional_cohort_view_test`

Expected: alias/count/render assertions fail before Rust rendering support is added.

**Step 3: Implement compact rendering support**

Add the provider alias and only adjust vertical/table constraints if the 120x36 snapshot proves clipping. Preserve exact IDs in wide/provenance layouts and preserve the read-only execution label.

**Step 4: Run tests to verify GREEN**

Run the focused Rust test and require zero failures.

### Task 5: Verify the complete system and perform a controlled rollover

**Files:**
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `docs/reviews/2026-08-02-measured-hypervelocity-tui-acceptance.md`

**Step 1: Run static and focused validation**

Run:

```bash
uv run ruff check <touched-python-files>
uv run pytest <focused-python-tests> -q
cargo fmt --all -- --check
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo test -p hypervector-tui
```

Expected: zero failures and zero lint errors.

**Step 2: Run full regression validation**

Run:

```bash
uv run pytest tests/ -q -m "not network"
```

Expected: zero failures; retain and report any pre-existing warnings.

**Step 3: Inspect the real 120x36 render**

Run the visual snapshot test with `HYPERVECTOR_VISUAL_SNAPSHOT=1` and inspect all four screens for clipped rows, overwritten borders, ambiguous authority, or fabricated data.

**Step 4: Roll the observer only after green validation**

Stop the owned disarmed observer and checkpoint sidecar cleanly, publish the immutable audit for the old run, then start a fresh observer with the new profile fingerprint. Verify the first poll reports ten unique provider/symbol evaluations, `execution_authority=none`, and zero routed actions.

**Step 5: Document evidence and falsifiers**

Record the actual commands/counts and state that two historical HYPE onsets justify measurement only. Falsifiers are retroactive startup intent, any HYPE execution scope, missing tenth-row telemetry, duplicate candle fetches, clipped 120x36 output, or fresh HYPE onset paths that remain negative after sufficient independent observations.

**Step 6: Commit only on explicit user request**

Do not commit or push as part of this task unless the user separately authorizes it.
