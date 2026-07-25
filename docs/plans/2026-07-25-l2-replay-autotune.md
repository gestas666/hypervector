# L2 Replay Autotune Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use test-driven-development and verification-before-completion task-by-task.

**Goal:** Use the archived Hypervelocity order-book feature and decision tape to reconstruct BTC trades, classify causal regimes, autotune each lane, and train replay-specific candidate models.

**Architecture:** A replay-data module reads raw or zstd-compressed calibration SQLite without modifying the source, pairs recorded entry/exit events, and assigns regimes using only completed 15-minute book-mid buckets. A research runner performs ungated chronological tuning and walk-forward model comparison, then writes provenance-rich candidate artifacts without installing them into paper or live execution.

**Tech Stack:** Python 3.13, SQLite, pandas, NumPy, LightGBM, scikit-learn, pytest.

---

### Task 1: Correct point-in-time timestamp alignment

**Files:**
- Modify: `src/hypervector/data/book_align.py`
- Test: `tests/test_book_align.py`

1. Add a failing test using millisecond-resolution UTC timestamps.
2. Verify it fails because the current integer conversion assumes nanoseconds.
3. Convert timestamps through explicit epoch units and preserve the original bar index.
4. Verify exact causal matches and the existing alignment suite.

### Task 2: Load and pair replay decisions

**Files:**
- Create: `src/hypervector/research/impulse_replay.py`
- Create: `tests/test_impulse_replay.py`

1. Build a small SQLite fixture with feature and decision samples.
2. Add failing tests for entry/exit pairing, unmatched-event reporting, and causal 15-minute regime assignment.
3. Implement typed loaders for raw SQLite and `.zst` archives using an isolated temporary directory.
4. Export a compact replay-trade parquet plus provenance JSON.

### Task 3: Run ungated lane autotuning

**Files:**
- Modify: `src/hypervector/research/impulse_replay.py`
- Test: `tests/test_impulse_replay.py`

1. Add failing tests that every technically valid trial is reported, including losing trials.
2. Tune long/uptrend, short/downtrend, range-long, and range-short filters chronologically.
3. Report zero-fee and configured-cost metrics, trial counts, parameters, and untouched OOS results.
4. Write JSON boards under `data/logs/research/`.

### Task 4: Train replay-specific model candidates

**Files:**
- Create: `src/hypervector/ml/replay_models.py`
- Create: `tests/test_replay_models.py`

1. Add failing tests for strictly chronological folds and train-only preprocessing.
2. Compare LightGBM with a regularized temporal logistic baseline using the same replay rows.
3. Save both candidate metrics and feature contracts; do not install either model automatically.
4. Record what runtime telemetry is required before execution can consume the winner.

### Task 5: Validate the complete research path

1. Run focused replay/alignment/model tests.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Validate output provenance, chronological boundaries, counts, and source archive immutability.
4. Update `HANDOFF.md` with results and remaining runtime-integration constraints.
