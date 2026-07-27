# Hypervelocity Final Shadow Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the verified 90-day Hyperliquid archive into auditable full-window replay and annotation evidence, fix remaining runtime telemetry defects, and start a recoverably clean final shadow observation session.

**Architecture:** Preserve the live backend as the only execution authority and keep the TUI read-only. Add a streaming research adapter that discovers verified hourly 0xArchive bundles, carries one replay state across bundle boundaries, and writes bounded lifecycle evidence without loading 48 million events at once. Train annotation-only challengers only when the resulting labels contain sufficient resolved examples and both classes; otherwise publish the measured insufficiency rather than manufacturing labels or adding execution gates.

**Tech Stack:** Python 3.13, Pandas, gzip JSONL, LightGBM, scikit-learn, Pytest, Ruff, Rust/Ratatui tests, existing Hypervelocity event and regime contracts.

---

### Task 1: Preserve the current run and correct marked telemetry

**Files:**
- Modify: `src/hypervector/paper/hypervelocity_session_bridge.py`
- Modify: `tests/test_paper_session.py`

1. Gracefully terminate the current shadow backend through its installed SIGTERM handler.
2. Verify the event archive flushes and no backend process remains.
3. Add a failing integration assertion showing an open LONG below entry must retain negative unrealized PnL in an `execution_evidence_uncertain` row.
4. Run the focused test and confirm it fails with recorded `0.0` versus marked negative PnL.
5. Change the bridge to use one authoritative event-account snapshot for both marked equity and derived unrealized PnL.
6. Re-run the focused test and the paper/event-shadow test group.

### Task 2: Discover verified hourly archive bundles without shell-sized argument lists

**Files:**
- Modify: `src/hypervector/data/oxa_archive_audit.py`
- Modify: `tests/test_oxa_archive_audit.py`
- Modify: `src/hypervector/cli.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Add a failing test for a public typed iterator returning chronological `(book_path, trade_path)` bundle pairs from an `OxaArchiveAuditConfig`.
2. Require every returned bundle to pass manifest identity and checksum validation before replay.
3. Represent zero-row book hours explicitly with `None`; do not silently omit their time windows.
4. Add CLI archive-window arguments so the 90-day replay does not require 4,320 repeated path flags.
5. Preserve existing explicit `--book-path` and `--trade-path` behavior for bounded investigations.

### Task 3: Stream replay state causally across hourly boundaries

**Files:**
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `src/hypervector/research/maker_replay_validation.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`

1. Add failing tests in which a pending order starts in hour one and fills in hour two, and an open position starts in hour one and reaches target in hour two.
2. Add failing tests for exact adjacent-boundary duplicates and conflicting duplicate identities.
3. Refactor replay execution to accept an existing typed state and update aggregate counters incrementally.
4. Load and validate one hourly bundle at a time, deduplicate only exact boundary repeats, and preserve chronological book-before-trade ordering at equal timestamps.
5. Carry equity, pending entry, open position, expired direction, regime episode, and last signal across every bundle.
6. Emit the same report schema for in-memory and streaming paths plus archive bounds, bundle counts, empty hours, and checksums-verified provenance.

### Task 4: Emit auditable lifecycle annotations for model research

**Files:**
- Modify: `src/hypervector/research/maker_replay.py`
- Modify: `tests/test_hypervelocity_maker_replay.py`
- Create: `src/hypervector/research/replay_labels.py`
- Create: `tests/test_replay_labels.py`

1. Add typed lifecycle rows for signal, submission, fill, expiration, cancellation, target completion, and right-censored open state.
2. Record decision time, outcome time, direction, prices, fees, net PnL, fill-rule identity, and regime context.
3. Join touch, one-tick-through, and public-trade-through outcomes by signal identity.
4. Mark fill-model disagreements and right-censored examples as unresolved; do not coerce them into class zero.
5. Create conservative labels only where the selected fill assumptions agree on a resolved outcome.
6. Report nominal samples, resolved samples, class balance, overlap, and effective event count.

### Task 5: Run the complete 90-day venue-native replay

**Runtime artifacts:**
- Create: `data/logs/research/hypervelocity_oxa_90d_fill_comparison.json`
- Create: `data/logs/research/hypervelocity_oxa_90d_labels.parquet`

1. Re-run the 4,320-individual-bundle checksum audit (2,160 paired hourly windows) for `2026-04-28T00:00:00Z` through `2026-07-27T00:00:00Z`.
2. Generate point-in-time 1m/5m/15m decisions from the strict Hyperliquid candle cache.
3. Stream all book and trade bundles through touch, through, and trade-through replay.
4. Record completed, expired, canceled, pending, open, censored, and fill-disagreement counts without performance rejection.
5. Save lifecycle labels and report exact provenance and known limitations: historical funding, liquidation, queue rank, cancellations, and genuine local receive latency remain unavailable in this maker comparator.

### Task 6: Train and evaluate annotation-only challengers when empirically defined

**Files:**
- Modify: `src/hypervector/ml/replay_models.py`
- Modify: `tests/test_replay_models.py`
- Create runtime candidates only under: `data/models/metalabel/candidates/`

1. Add the stable runtime 17-feature matrix at each causal signal timestamp.
2. Use expanding walk-forward folds; purge by outcome horizon and fit every transform inside each fold.
3. Compare the past-only constant baseline, regularized logistic/Ridge-style baseline, LightGBM, and lagged logistic on identical folds.
4. Report per-fold log loss, Brier score, AUC where defined, calibration, worst fold, and class/effective sample counts.
5. If labels contain one class or no valid folds, publish a structured `insufficient_resolved_labels` result and do not fabricate a trained model.
6. Keep all successful candidates `observe` only. Do not change entry eligibility, sizing, routing, or exits based on model scores.

### Task 7: Final runtime acceptance and clean session boundary

**Files:**
- Update: `HANDOFF.md`
- Update: `skills/hypervector-cli/SKILL.md` if the canonical command changes

1. Run focused replay, archive, regime, paper, resume, and TUI tests.
2. Run `uv run pytest tests/ -q -m "not network"` and `cargo test -p hypervector-tui`.
3. Run Ruff, formatting, `git diff --check`, CLI status, profile parsing, and shadow no-submit checks.
4. Run `hypervelocity-shadow-reset` first as a dry run, then with `--yes`; verify the prior ledger/log backup exists and raw market archives remain unchanged.
5. Launch the canonical unified command once, verify one backend process, a fresh run identity, live L2/regime telemetry, zero live submit attempts, and correct marked PnL.
6. Quit normally, verify backend reaping and durable state, then provide the same unified command to the operator.
7. Commit intentionally, push, merge to `main`, clean merged branches, and finish on clean synchronized `main`.

## Success criteria and falsifiers

- Archive completeness remains 4,320/4,320 verified individual bundles across 2,160 paired hours; a checksum or identity mismatch is a technical failure.
- Cross-hour replay matches equivalent in-memory replay on bounded fixtures; disagreement falsifies the streaming adapter.
- No future 1m, 5m, or 15m state appears before its decision timestamp; prefix non-invariance falsifies the label set.
- No unresolved or censored lifecycle becomes a negative label.
- Model scores remain annotation-only regardless of performance.
- Shadow creates no live client, no venue submit attempt, and no second backend.
- TUI marked PnL agrees with backend marked equity within floating-point tolerance.
