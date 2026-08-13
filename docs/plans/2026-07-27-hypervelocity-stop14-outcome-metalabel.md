# Hypervelocity Stop-14 Outcome Metalabel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether causal regime and Hyperliquid order-book features can distinguish faithful entries that reach the fixed 8% target before a creator-derived 14% gross-margin loss boundary.

**Architecture:** Reuse the immutable 90-day `stop_14pct_margin` replay and the existing point-in-time feature builder. Generalize the annotation-only challenger to accept an explicit binary label column, preserve the existing liquidation model contract, and add a frozen `faithful-stop14` population whose positive class is stop or liquidation risk. Evaluate the unchanged six-candidate baseline ladder with outcome-aware purged walk-forward folds; do not filter, scale, route, exit, install, or otherwise change runtime behavior.

**Tech Stack:** Python 3.13, pandas, scikit-learn logistic regression, LightGBM, verified 0xArchive Hyperliquid L2/trades, pytest, Ruff.

---

## Frozen research contract

- Evidence window: 2026-04-28 00:00 UTC through 2026-07-27 00:00 UTC.
- Replay artifact:
  `data/logs/research/hypervelocity_creator_margin_stop_grid_20260727.json`,
  SHA-256
  `b0e6c9d584db7ffd631da810cdca7ca656025c07af681a36345843e800884b37`.
- Faithful config SHA-256:
  `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
- Population: exactly 371 resolved fills: 227 targets, 143 stops, and one
  liquidation. Expired/canceled/pending orders are not negative labels.
- Positive label `loss_risk=1`: `stopped` or `liquidated` before the target.
  Negative label `loss_risk=0`: `target_completed`.
- Decision anchor: signal time. Bar features use only the latest completed 1m
  bar; 5m/15m features retain canonical completed-bar availability. Book
  features use only observations available at the signal timestamp.
- Training labels must resolve before the test signal minus the declared
  60-minute buffer. Walk-forward training is expanding; no future fold trains
  an earlier fold.
- Fixed searched set of six candidates: past-only base rate, logistic base,
  logistic base+book, three-prior-signal temporal logistic+book, LightGBM base,
  and LightGBM base+book. No hyperparameter tuning occurs in this trial.
- Feature transforms remain inside each training fold. The linear model is the
  required baseline; LightGBM earns consideration only by improving it.
- Runtime metalabel policy remains `observe`, `may_filter=false`, and
  `may_scale=false`. Full-sample fitted files are research artifacts and are
  never installed.
- This entire window is exploration evidence. No model can be called confirmed
  or promoted from this result.

## Predeclared diagnostics

1. Correctness: exact population/checksums, two classes, causal timestamps,
   ordered rows, feature coverage, and outcome-aware purging must pass.
2. Association: report log loss, Brier score, ROC AUC, average precision,
   calibration bias, worst-fold log loss, and each fold independently.
3. Baseline test: a model must beat the past-only base rate on mean log loss
   and in at least two of three folds. LightGBM must also beat the corresponding
   logistic family to justify added complexity.
4. Stability: an AUC near 0.55-0.60 is potentially meaningful only when its
   direction is consistent across folds. AUC above 0.65 triggers a leakage
   audit rather than a success claim.
5. Economic shape: within each fold, rank OOS predictions by loss risk and
   report the target rate in the lowest-risk half. With an 8% gross target,
   14% gross stop, 40x leverage, 1.5 bp maker, and 4.5 bp taker fees, the
   theoretical break-even target rate is about 70.69%. A liquidation is worse
   than this two-barrier approximation and remains separately counted.
6. Search accounting: searched-set size remains six. Any threshold, feature,
   model, or label change after results becomes a new trial family.

## Mechanism screen already completed

The loss-only cooldown idea is rejected before implementation. Of 143 trades
following a stop, entries within five minutes reached target 12/13 times;
entries within 15 minutes reached target 26/32 times and had positive average
net margin return. A blunt refractory period would preferentially remove the
best recovery cohort. The overall next-trade target rate was 54.55%, and
same-direction returns after a full reset were worse at 43.75%, but neither
observation justifies a time-only runtime gate.

### Task 1: Generalize the challenger label contract

**Files:**
- Modify: `src/hypervector/ml/hypervelocity_challenger.py`
- Modify: `tests/test_hypervelocity_challenger.py`

1. Write a failing test training the existing candidate set with a `loss_risk`
   label and asserting that predictions/metadata preserve that exact name.
2. Run the focused test and confirm failure because the trainer only accepts
   `liquidation_risk`.
3. Add a validated `label_column` parameter through row validation, fold
   evaluation, prediction persistence, full-model fitting, and metadata.
4. Preserve `liquidation_risk` as the default so existing callers and artifacts
   retain their contract.
5. Run challenger tests and Ruff.

### Task 2: Parse the immutable stop-14 population

**Files:**
- Modify: `src/hypervector/research/hypervelocity_metalabel.py`
- Modify: `tests/test_hypervelocity_metalabel.py`

1. Write failing tests for the nested candidate identity, exact 14% stop,
   observe-only policy, and resolved target/stop/liquidation labels.
2. Confirm expired and canceled lifecycles remain excluded.
3. Generalize resolved lifecycle construction to an explicit positive-status
   set and label name without changing the existing liquidation parser.
4. Add `resolved_margin_stop_lifecycles()` with actionable validation errors.
5. Run metalabel tests and Ruff.

### Task 3: Add the faithful-stop14 assembly profile

**Files:**
- Modify: `src/hypervector/research/hypervelocity_metalabel_report.py`
- Modify: `scripts/hypervelocity_venue_metalabel.py`
- Modify: `tests/test_hypervelocity_metalabel.py`

1. Write failing tests for the exact 371/144 population, `loss_risk` label,
   faithful decision profile, backward completed-bar alignment, and CLI choice.
2. Add the frozen population contract and select the correct nested resolver.
3. Rebuild unmodified faithful regime features; do not apply recovery, OBI,
   confidence, age, or 15m gates.
4. Make population validation and report fields use the declared label column.
5. Add per-fold lowest-risk-half target-rate diagnostics and the 70.69%
   theoretical break-even reference.
6. Run report/CLI tests and Ruff.

### Task 4: Run the complete observe-only comparison

**Files:**
- Create: `data/logs/research/hypervelocity_stop14_outcome_metalabel_20260727.json`
- Create: associated dataset, prediction, fold-metric, and research model files.

1. Run the CLI with `--candidate-profile faithful-stop14`, three splits, and a
   60-minute outcome buffer.
2. Retain all six model results even when worse than the base rate.
3. Verify artifact/source hashes, population counts, feature coverage, fold
   boundaries, searched set, and observe-only policy.
4. Compare model ranking, calibration, fold stability, book-feature ablation,
   and economic shape. Do not convert a probability threshold into execution.

### Task 5: Verify and document

**Files:**
- Modify: `docs/reviews/2026-07-27-creator-screenshot-forward-validation.md`
- Modify: `HANDOFF.md`

1. Run focused tests and Ruff on every touched Python file.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Run `cargo test -p hypervector-tui`, `cargo fmt --check --all`,
   `git diff --check`, and `uv run python -m hypervector status`.
4. Recompute the faithful config and result-artifact hashes.
5. Record confidence, unfavorable folds, searched-set size, known replay
   limitations, and the fresh evidence that would falsify the decision.

## Expected failure modes

- The balanced stop label may still be unlearnable because the creator's true
  loss boundary is unknown and the 14% stop is only an economic hypothesis.
- Signal-time L2 may differ materially from the book when the maker order fills.
- Three folds and roughly half-window OOS predictions remain statistically
  small even though the label is less sparse than liquidation.
- A model may rank outcomes while failing the break-even target-rate shape.
- LightGBM may overfit 371 rows and lose to regularized logistic regression.
- The already-inspected 90-day window cannot provide confirmation evidence.

## Execution note

The persistent user goal requests continued testing and tuning, so this plan is
executed immediately in the current worktree. No subagent is used, and git
commit/push remains deferred until the user explicitly requests it.

## Execution result

Completed on 2026-07-27 with no runtime promotion. The frozen population was
371 resolved fills (227 targets, 143 stops, one liquidation); 186 samples and
75 losses were evaluated out of fold. The past-only base rate had the lowest
mean log loss at 0.67861. The closest learned candidate, bar/regime logistic,
scored 0.69819 with mean ROC AUC 0.5047 and improved log loss in only one of
three folds. Its fold-local lowest-risk halves averaged 65.59% targets versus
the predeclared 70.69% fee-adjusted break-even rate. L2 features worsened mean
log loss for both logistic and LightGBM. The metalabel remains observe-only.

Result artifact:
`data/logs/research/hypervelocity_stop14_outcome_metalabel_20260727.json`,
SHA-256
`bd4e36c0ac7e9f4aa5c51113a8bbc816d54512f53454fefe1399b5aa7a239f64`.
