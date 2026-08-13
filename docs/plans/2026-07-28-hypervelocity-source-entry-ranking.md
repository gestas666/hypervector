# Hypervelocity Creator Entry-Time Ranking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether causal bar/regime features can rank creator-selected entry minutes above other detector-eligible minutes on later days without treating the model as execution authority.

**Architecture:** Construct a positive-unlabeled timing dataset from the hard-BBWP25/recovery-6 decision stream. Creator entries whose side matches the available decision direction mark observed positives; every other eligible minute remains explicitly unlabeled rather than a known loss. Evaluate one regularized logistic baseline and one shallow LightGBM challenger with expanding day-forward folds, fold-local preprocessing, and ranking diagnostics only. Do not install a model, derive an execution threshold, or mutate runtime.

**Tech Stack:** Python 3.13, pandas, NumPy, scikit-learn, LightGBM, pytest, immutable Hyperliquid 1m bars.

---

## Frozen learning task

- Evidence window: first recorded logical creator entry on 2026-07-09 through
  the last currently supplied entry on 2026-07-25.
- Source positives: 35 reconciled logical entry decisions across 12 UTC days.
- Timing-positive eligibility: the completed-bar hard-BBWP25/recovery-6
  `entry_direction` at the source timestamp must equal the source side. Source
  reversals/RANGE misses remain coverage failures and are not silently moved to
  a nearby minute.
- Candidate population: every one-minute decision in the evidence window with
  a non-null hard-BBWP25/recovery-6 entry direction.
- Non-entry candidate minutes are `unlabeled`, not asserted losses. Classifier
  probabilities are therefore scores only and must not be described as entry
  probabilities.
- Features: the existing 13 causal bar/regime features in
  `BASE_FEATURE_NAMES`; no L2, future outcomes, trade PnL, or post-entry fields.
- Models: fixed class-weighted logistic pipeline and fixed shallow deterministic
  LightGBM. No hyperparameter search, temporal/deep model, ensemble, or feature
  selection.
- Baselines: tied/uniform rank and causal `regime_strength_percentile` rank.
- Validation: expanding UTC-day-forward folds. Every learned imputer, scaler,
  and model is fitted only on prior days. The fold is the reporting unit.
- Metrics: positive percentile rank within held-out day/side candidates,
  positive recall in top 1%, 5%, 10%, and 20%, ROC AUC and average precision
  against unlabeled rows as biased diagnostics, candidate cadence, and fold
  stability. Calibration/log loss are not valid for positive-unlabeled labels.
- Runtime, TUI, faithful config, one-position rule, 70% isolated margin, 40x,
  fixed 8% target, and ML `observe` authority remain unchanged.

## Decision standard

- Correctness requires exact completed-bar timestamp alignment, deterministic
  dataset identity, no future-fitted transforms, explicit source coverage, and
  all 35 entries accounted for.
- Association requires both learned models to beat uniform median percentile
  and at least one to beat the strength-only baseline on a majority of held-out
  source days. A negative worst-fold collapse is frozen as any evaluable source
  day whose mean positive percentile is below 0.25 for either learned model.
- Shape requires top-decile recall materially above its 10% nominal selection
  share in a majority of folds; `materially above` is frozen as greater than
  15% before the real-data report is run.
- A survivor remains annotation-only. It advances only to a separately frozen
  online-threshold and venue replay experiment; this task cannot promote it.
- Stop if fewer than three evaluable held-out source days remain, either model
  cannot fit both observed/unlabeled classes in prior data, fold signs are
  unstable, or performance comes from one clustered Jul 24 run.

### Task 1: Define the point-in-time timing dataset

**Files:**
- Create: `src/hypervector/research/hypervelocity_entry_ranking.py`
- Create: `tests/test_hypervelocity_entry_ranking.py`

1. Write failing tests for completed-bar source alignment, exact side matching,
   unmatched-source retention, unique minute/side identity, and no mutation.
2. Run the focused tests and observe the missing-feature failure.
3. Implement typed dataset construction using existing feature names and
   directionalization. Publish `is_observed_entry`, `label_kind`, source ID,
   day, direction, and coverage summary.
4. Reject duplicate candidate identities, duplicate source mappings, missing
   features, non-monotonic input, and source times outside evidence bounds.
5. Run focused tests and Ruff.

### Task 2: Add expanding day-forward ranking evaluation

**Files:**
- Modify: `src/hypervector/research/hypervelocity_entry_ranking.py`
- Modify: `tests/test_hypervelocity_entry_ranking.py`

1. Write failing tests proving training days precede test day and preprocessing
   is fitted inside each fold.
2. Add fixed uniform, strength-only, logistic, and LightGBM scores.
3. Compute fold-local day/side percentile ranks with stable tie handling,
   top-k recall, AUC/AP diagnostics, counts, and feature coverage.
4. Retain folds that have no held-out positive as coverage rows, but do not use
   them to flatter ranking metrics.
5. Report searched-set size exactly and make output deterministic.

### Task 3: Build one immutable research command

**Files:**
- Create: `scripts/hypervelocity_source_entry_ranking.py`
- Modify: `tests/test_hypervelocity_entry_ranking.py`
- Create if completed:
  `data/logs/research/hypervelocity_source_entry_ranking_20260728.json`

1. Load strict bars, faithful profile, base/source/supplemental positions, and
   construct the hard-BBWP25/recovery-6 decision stream.
2. Hash every input and stamp feature/model/split identities.
3. Write one immutable JSON report with all folds, source coverage, model
   metrics, limitations, and `runtime_strategy_changed=false`.
4. Fail if the faithful config is not observe-only or the output already
   exists.

### Task 4: Run and decide

1. Execute the full Jul 9-25 source-window ranking report.
2. Apply correctness, association, and shape screens in order.
3. If it fails, archive the result and do not add L2 or tune models.
4. If it survives, freeze a separate L2 comparison before loading book
   features; do not retrofit this trial.
5. Record confidence, failure modes, trial count, and falsifiers in the creator
   validation review and `HANDOFF.md`.

### Task 5: Verify

1. Run focused tests and Ruff/format checks.
2. Run the complete non-network Python suite and Rust TUI tests.
3. Run Cargo formatting, diff hygiene, file/function-size checks, CLI status,
   artifact assertions, and faithful config hashing.
4. Do not commit or push unless explicitly requested.

## Measured result

The immutable report completed at
`data/logs/research/hypervelocity_source_entry_ranking_20260728.json`, SHA-256
`314d890ef7fa6101dd8a167bf83be7d945024637d06c9c83820f9985ed85db6a`.
All 35 source entries were retained: 17 exact hard-recovery direction matches,
four opposite-direction minutes, and 14 minutes with no eligible candidate.
The first matched source day supplied two training positives; 15 matched
entries across seven later source days were evaluated out of sample.

| Candidate | Median positive percentile | Mean top-10% recall | Mean biased ROC AUC | Worst day percentile |
|---|---:|---:|---:|---:|
| Uniform tied rank | 0.500 | 0.101 | 0.500 | 0.500 |
| Regime strength only | 0.699 | 0.524 | 0.780 | 0.397 |
| Regularized logistic | 0.534 | 0.190 | 0.433 | 0.081 |
| Shallow LightGBM | 0.567 | 0.000 | 0.441 | 0.105 |

Both learned models beat uniform on four of seven source days, but logistic
beat strength on only three and LightGBM on zero. Both suffered a predeclared
bottom-quartile collapse; neither passed the shape screen. The learned trial is
rejected and no L2 trial, threshold, model installation, or runtime change is
authorized.

The causal strength-only baseline is retained as a new annotation hypothesis,
not an entry gate. Its result spans multiple days but only 15 out-of-sample
positives and may reflect screenshot-selection bias. Fresh complete creator
logs placing entries near ordinary or weak eligible strength ranks would
falsify the association. No file in `docs/external` was newer than 2026-07-27
19:07:50 EDT at the post-run inventory.

Fresh verification passed 1,009 non-network Python tests with four deselected
and 31 warnings, plus all 33 Rust TUI integration tests. Task-scoped Ruff and
format checks, Cargo formatting, diff hygiene, file/function-size checks, CLI
fail-closed status, artifact assertions, and the faithful configuration hash
all passed.
