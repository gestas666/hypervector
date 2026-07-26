# Regime Authority, Alignment, and Retune Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans, test-driven-development, ml4-trading, and verification-before-completion task-by-task.

**Goal:** Make Hypervelocity's 5m primary and 15m context causally venue-aligned, enforce the configured no-range entry contract, project only backend facts in the TUI, retune on corrected point-in-time labels, and validate a fresh shadow window against real-strategy evidence.

**Architecture:** Open-timestamped 1m candles are aggregated into left-closed venue buckets and become visible only after the last constituent 1m candle completes. The backend's configured state policy is the sole entry authority; 1m remains execution telemetry and cannot silently replace the 5m primary. Live and playback TUI views consume the same backend label vocabulary and measured values, while tuning remains report-only with chronological train/holdout evidence.

**Tech Stack:** Python 3.13, pandas, pytest, TOML, Rust 2021, serde/serde_json, Ratatui, Cargo, Hyperliquid public OHLCV/L2 data.

---

### Task 1: Prove and repair venue-aligned completed-timeframe aggregation

**Files:**
- Modify: `tests/test_regime_classifier.py`
- Modify: `src/hypervector/regime/composite.py`
- Modify: `src/hypervector/regime/hypervelocity_eval.py`

1. Add a failing fixture proving a 5m candle contains 1m opens `00:00` through `00:04`, is first visible on the `00:04` decision row, and never consumes `00:05`.
2. Add the equivalent 15m test and a prefix-invariance test for an incomplete trailing bucket.
3. Run the focused tests and confirm RED against the current right-closed plus shifted implementation.
4. Implement one typed completed-timeframe aggregation helper using left-closed/open-labeled venue buckets and last-constituent availability timestamps.
5. Reuse the helper for the 30m evaluation arm so production and research cannot drift.
6. Run focused tests and `git diff --check`.

### Task 2: Make the configured primary state policy authoritative

**Files:**
- Modify: `tests/test_regime_classifier.py`
- Modify: `tests/test_hypervelocity_profile.py`
- Modify: `tests/test_hypervelocity.py`
- Modify: `src/hypervector/regime/composite.py`
- Modify: `src/hypervector/strategies/hypervelocity_profile.py`
- Modify: `configs/hypervelocity_faithful.toml`

1. Replace the fallback test with failing tests proving 5m `RANGE`, `TRANSITION`, and `UNKNOWN` remain canonical and entry-ineligible even when 1m is directional.
2. Add failing profile tests proving timeframe roles and allowed/blocked states are validated and exposed by the loaded profile.
3. Implement exact policy parsing without adding confidence, drawdown, or performance gates.
4. Keep 15m context non-veto and preserve 1m/5m/15m telemetry separately.
5. Add a ledger-level regression test proving no submit occurs while authoritative 5m is non-entry.
6. Run focused classifier, profile, strategy, and session tests.

### Task 3: Harden regime inputs and telemetry semantics

**Files:**
- Modify: `tests/test_regime_classifier.py`
- Modify: `src/hypervector/regime/classifier.py`
- Modify: `src/hypervector/regime/composite.py`
- Modify: `src/hypervector/paper/session.py`

1. Add failing tests for invalid lookbacks, lengths, percentile ordering/ranges, negative thresholds, non-finite OHLCV, invalid OHLC relationships, negative volume, and non-1m cadence.
2. Implement fail-fast validation with actionable errors at the regime boundary.
3. Rename the averaged trend-strength telemetry field in backend/TUI contracts or explicitly expose its metric identity; do not present it as ML probability.
4. Preserve compatibility only where the stored ledger schema requires it, with an explicit source field.
5. Run focused Python tests.

### Task 4: Make the TUI a literal backend projection

**Files:**
- Modify: `crates/hypervector-tui/src/model.rs`
- Modify: `crates/hypervector-tui/src/backend_market.rs`
- Modify: `crates/hypervector-tui/src/app.rs`
- Modify: `crates/hypervector-tui/src/ui/mod.rs`
- Modify: `crates/hypervector-tui/src/hypervelocity.rs`
- Modify: `crates/hypervector-tui/tests/backend_telemetry_test.rs`
- Modify: `crates/hypervector-tui/tests/regime_cockpit_test.rs`

1. Add failing Rust tests proving labels remain exactly `TREND_UP`, `TREND_DOWN`, `BREAKOUT`, `TRANSITION`, `RANGE`, and `UNKNOWN` without invented funding/coiling meanings.
2. Add a failing test proving the historical distribution is computed from backend snapshots rather than fixed constants.
3. Add a failing test proving technical strength and metalabel probability have distinct labels and values.
4. Implement literal backend labels, real distribution counts, and honest missing-data rendering.
5. Remove state-derived fallback values that look measured in playback mode.
6. Run `cargo fmt --check`, focused Cargo tests, and the complete TUI test suite.

### Task 5: Unify playback, evaluator, documentation, and operational contracts

**Files:**
- Modify: `tests/test_regime_snapshot_export.py`
- Modify: `src/hypervector/regime/snapshot_export.py`
- Modify: `skills/hypervector-cli/SKILL.md`
- Modify: `skills/hypervector-regime-detector/SKILL.md`
- Modify: `docs/guides/acceptance-visual-and-holistic.md`
- Modify: `HANDOFF.md`

1. Add failing snapshot tests proving exports use the faithful profile and corrected completed-timeframe helper.
2. Remove duplicated resampling and heuristic confidence that diverges from the backend.
3. Update project skills and guides to state 5m authority, non-veto 15m context, no 1m range override, exact label meanings, and report-only retuning.
4. Run snapshot, CLI, and documentation consistency checks.

### Task 6: Retune and falsify on corrected labels with model-based challengers

**Artifacts:**
- Create: `data/logs/research/hypervelocity_regime_tuning_aligned_20260726.json`
- Create: `data/logs/research/hypervelocity_regime_eval_aligned_20260726.json`
- Create: `data/logs/research/hypervelocity_regime_challengers_20260726.json`
- Create: `docs/reviews/2026-07-26-regime-alignment-retune-review.md`

1. Freeze the decision-time contract, source dataset, position labels, cost assumptions, search space, seed, chronological split, and trial count in the review artifact.
2. Run corrected regime evaluation against the supplied manual-position CSV.
3. Add a report-only expanding-window volatility-tercile diagnostic as the simplest point-in-time state benchmark; it cannot filter or size Hypervelocity.
4. Evaluate GMM and Wasserstein-distribution state features inside chronological folds using the installed scikit-learn/SciPy stack. Fit scalers, cluster definitions, and state ordering inside each training fold only.
5. Record HMM filtered probabilities/entropy/duration and MS-AR as explicit optional challenger arms. If `hmmlearn` or `statsmodels` is unavailable, report the technical limitation rather than substituting smoothed/full-sample labels or silently adding a runtime dependency.
6. Keep every challenger annotation-only. No challenger state, probability, entropy, or score may alter entry, sizing, leverage, or exits.
7. Run chronological Hypervelocity regime autotuning with every technically valid trial retained; performance never aborts a trial.
8. Compare the selected candidate with the fixed current baseline on train and holdout, including direction recall, no-entry-at-known-entry count, breakout/range quality, churn, transition latency, regime-sliced performance, and cost sensitivity.
9. Do not promote parameters merely because they win the search. Update the faithful profile only if corrected holdout evidence and fixed-contract invariants support it; otherwise retain the baseline and record the result.
10. Re-run the corrected evaluation using the selected or retained profile.

### Task 7: Fresh shadow validation and full completion audit

**Files/Artifacts:**
- Modify: `docs/reviews/2026-07-26-regime-alignment-retune-review.md`
- Runtime evidence: `data/paper/decisions/decisions.jsonl`
- Runtime evidence: `data/paper/hypervelocity-shadow.log`

1. Stop the old shadow daemon cleanly after preserving its ledger.
2. Run the recoverable shadow reset command and verify the generated backup before starting the corrected backend.
3. Launch the corrected no-submit shadow backend and verify fresh session, regime, L2, funding, and entry-execution telemetry.
4. Assert from the new ledger that no `submit_entry` occurs when `state_5m` is `RANGE`, `TRANSITION`, or `UNKNOWN`.
5. Compare the fresh observation window with new overlapping real-strategy logs when available; if they are absent, record that empirical comparison as missing evidence rather than claiming completion.
6. Run the complete verification matrix:

```bash
uv run pytest tests/ -q -m "not network"
cargo fmt --check
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo test -p hypervector-tui
uv run python -m hypervector status
uv run python -m hypervector paper-check
git diff --check
```

7. Review every changed file for the 500-line file, 50-line function, type-safety, error-handling, security, and documentation constraints.
8. Audit each plan requirement against direct evidence, list any missing evidence, and only then commit, merge, and push according to the user's Git workflow.

## Completion and falsification criteria

- Venue-aligned fixtures match native open-timestamped 5m/15m membership and causal availability.
- 5m `RANGE`, `TRANSITION`, and `UNKNOWN` never become entry-eligible through 1m fallback.
- Configured state/timeframe roles are validated backend inputs rather than decorative TOML.
- TUI labels, scores, distributions, and missing values are literal backend projections.
- Corrected retuning is chronological, report-only, reproducible, and compared with a fixed baseline.
- A corrected fresh shadow ledger proves execution-policy invariants.
- Real-log alignment remains provisional until an overlapping venue-matched log exists.

Evidence that would update the design includes native Hyperliquid candles contradicting the open-timestamp aggregation contract, source-strategy evidence explicitly permitting 1m entries during a 5m range, or overlapping real logs showing the corrected policy systematically misses authentic trades.
