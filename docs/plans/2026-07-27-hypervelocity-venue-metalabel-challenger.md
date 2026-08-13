# Hypervelocity Venue Metalabel Challenger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether causal regime and Hyperliquid L2 pressure features can predict liquidation risk for the recovery-6 replay candidate without changing strategy execution.

**Architecture:** Reconstruct the exact 407 resolved public-trade-through lifecycles from the immutable recovery-6 report, join only completed-bar and backward-as-of L2 evidence available at each signal, and evaluate a frozen small model family on identical outcome-time-purged expanding folds. Persist predictions, fold metrics, feature coverage, and model files as annotation-only research artifacts; do not install them or alter the faithful runtime configuration.

**Tech Stack:** Python 3.12, pandas, NumPy, scikit-learn logistic regression, LightGBM, pytest, checksum-verified 0xArchive Hyperliquid L2.

---

## Frozen Research Contract

- Source lifecycle artifact: `data/logs/research/hypervelocity_bbwp_recovery6_20260727.json`.
- Source bars: `data/cache/BTC_1m_90d.parquet` with SHA-256
  `7ecfcf42cafe4143c6bfe525a47209a40f23fd3e53d31f8be572dbb5d4e29e43`.
- Runtime-config SHA-256:
  `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
- Candidate: hard 5m BBWP25 range precedence, six completed 1m bars after
  compression, 300-second re-entry cooldown, 8% target, 70% allocation, 40x
  isolated leverage, public-trade-through maker entry.
- Population: filled lifecycles whose status is exactly `target_completed` or
  `liquidated`; canceled and expired entries are not mislabeled as losses.
- Label: `liquidation_risk = 1` for `liquidated`, otherwise `0`. The measured
  population is 407 trades with 39 positives; this is a rare-event diagnostic.
- Decision time: `signal_time_utc`. A completed 1m bar is shifted one minute
  before it can supply features. L2 alignment is latest snapshot at or before
  the signal and no more than two seconds old.
- Split: three expanding walk-forward test windows. A training lifecycle is
  eligible only when its outcome precedes the first test signal by at least 60
  minutes. No future-fitted transform is allowed.
- Model set: rolling training base rate, regularized logistic using bar/regime
  features, the same logistic with L2 features, lagged logistic with L2
  features, LightGBM using bar/regime features, and LightGBM with L2 features.
  This six-member searched set is fixed before results are inspected.
- Runtime policy remains `mode=observe`, `may_filter=false`, and
  `may_scale=false`. Models are not installed and cannot filter or resize.

## Measurements and Decision Rule

Report each usable fold and aggregate:

- train/test timestamps, rows, liquidations, and liquidation base rate;
- log loss and Brier score relative to the training base-rate forecast;
- liquidation ROC-AUC and average precision, with undefined metrics retained
  as null when a test fold has one class;
- calibration bias and worst-fold log loss;
- top-risk-quintile liquidation lift and feature missingness;
- model-by-model out-of-sample predictions and fold identity;
- base versus base-plus-L2 deltas for logistic and LightGBM;
- whether the model beats both the base rate and logistic in mean and worst
  fold, reported as a diagnostic rather than an execution gate.

The evidence is `REVISE` unless a challenger improves proper scoring rules in
most folds, avoids a materially worse worst fold, and shows risk ordering above
the observed base rate. Even a `PROCEED` result means collect fresh shadow
labels and confirm; it does not authorize runtime filtering or scaling.

Confidence before testing is low. Only 39 liquidation examples exist and L2
MBP shows displayed liquidity rather than queue priority or hidden liquidity.
The hypothesis is falsified if L2 ablations do not improve chronological proper
scores, signs reverse across folds, feature coverage is insufficient, or the
linear baseline matches or beats LightGBM.

### Task 1: Causal order-flow pressure

**Files:**
- Modify: `src/hypervector/research/hypervelocity_attribution_io.py`
- Modify: `src/hypervector/research/hypervelocity_attribution.py`
- Test: `tests/test_hypervelocity_attribution.py`

1. Write a failing test with known best-bid/best-ask size and price changes.
2. Verify it fails because normalized five-second OFI is unavailable.
3. Preserve top-level price/size fields from native L2 and implement the
   Cont-style top-of-book queue-change event using only current and prior
   snapshots.
4. Aggregate events over the backward-only five-second signal window and
   normalize by median top-level displayed depth; leave unavailable evidence
   missing rather than neutral.
5. Run the focused attribution tests.

### Task 2: Point-in-time metalabel dataset

**Files:**
- Create: `src/hypervector/research/hypervelocity_metalabel.py`
- Create: `tests/test_hypervelocity_metalabel.py`

1. Write failing tests for source identity, exact resolved population,
   one-minute completed-bar shift, backward-only L2 join, and explicit missing
   values.
2. Implement typed lifecycle parsing and causal feature construction.
3. Include direction-normalized EMA gap, RSI-minus-EMA, 1m/5m BBWP state,
   regime age, 15m alignment, structural distance, volume ratio, OBI, spread,
   microprice, and normalized OFI.
4. Assert the runtime config still carries the frozen observe contract.
5. Run the focused dataset tests.

### Task 3: Purged walk-forward comparison

**Files:**
- Create: `src/hypervector/ml/hypervelocity_challenger.py`
- Create: `tests/test_hypervelocity_challenger.py`

1. Write failing tests for outcome-time purging, identical folds, fold-local
   preprocessing, rare-class metric handling, and annotation-only metadata.
2. Implement the fixed model family and per-fold prediction ledger.
3. Use median imputation and standardization fitted inside each logistic fold.
4. Use a shallow fixed LightGBM configuration without a hyperparameter sweep.
5. Persist trained research candidates separately from runtime model paths.
6. Run the focused model tests.

### Task 4: Reproducible research command

**Files:**
- Create: `scripts/hypervelocity_venue_metalabel.py`
- Test: `tests/test_hypervelocity_metalabel.py`

1. Write a failing report-assembly test using small local fixtures.
2. Implement explicit source paths, UTC window, output path, and candidate
   directory arguments.
3. Fail if output already exists, source checksums differ, archive verification
   fails, or the model policy is not observe-only.
4. Write a JSON report and Parquet prediction ledger with source evidence and
   the complete searched-set declaration.
5. Run the 90-day experiment once and retain the result regardless of score.

### Task 5: Verification and interpretation

**Files:**
- Modify: `HANDOFF.md`
- Modify: `skills/hypervector-cli/SKILL.md`

1. Run the focused Python tests for attribution, dataset, and challengers.
2. Run `uv run pytest tests/ -q -m "not network"`.
3. Run `cargo test -p hypervector-tui` to verify the read-only projection was
   not disturbed.
4. Compare base/book ablations and logistic/LightGBM fold stability.
5. Document the result, limitations, exact falsifier, and next mechanism.
6. Do not commit or push unless the user explicitly asks.

## Measured 90-Day Result

The immutable run produced 407 resolved public-trade-through fills: 368 target
completions and 39 liquidations. Three outcome-time-purged expanding folds
contained 204 total out-of-sample predictions and 17 out-of-sample
liquidations. Native L2 features covered 405/407 rows; the two unavailable rows
remained missing and were imputed inside each training fold.

The rolling training base rate had the best mean log loss at 0.28948. Shallow
LightGBM without book features improved mean ranking diagnostics to ROC-AUC
0.5567 and average precision 0.1225, but worsened mean log loss to 0.29488.
Regularized base-feature logistic was worse at 0.30148. The temporal logistic
was worst at 0.37143.

Adding displayed-depth OBI, microprice, spread, and causal five-second OFI did
not add stable edge. LightGBM with book features was worse in two of three folds
and increased mean log loss by 0.00476. Logistic book features were better in
two folds, but one adverse fold increased the mean by 0.00275 and worsened its
worst-fold loss to 0.37092. The raw pressure sign was also weak descriptively:
aligned five-second OFI had 16/184 liquidations (8.70%) versus 23/221 (10.41%)
when opposed.

Verdict: `REVISE`. The feature family shows weak rank information in two later
LightGBM folds but does not beat the base-rate probability forecast and does
not support an order-book execution gate. Every saved candidate remains
`annotation_only`, `installed=false`; the faithful runtime hash remains
`801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.

Confidence is medium for this measured window and low for future generality.
Only 17 liquidation labels are out of sample. Fresh venue-matched shadow labels
that make book-feature proper scores consistently better in all folds would
falsify this verdict.
