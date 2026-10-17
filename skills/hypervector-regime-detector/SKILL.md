---
name: hypervector-regime-detector
description: Operate and validate hypervector's causal canonical regime engine - classify, evaluate, export telemetry, run challengers, align with recorded entries and tune regime parameters - through the unified CLI.
---

# Canonical regime engine

- **Classifier.** It lives in `src/hypervector/regime/`. The canonical entry
  point is `regime.ultimate.detect_ultimate_regime`.
- **Thresholds.** The Hypervelocity profile takes its faithful thresholds from
  `strategies.hypervelocity_contract.faithful_regime_config()`.
- **Interface.** Everything runs through the unified CLI and prints JSON; there
  is no terminal UI.

## Authority rules

- Completed 5m structure is primary. 1m is execution telemetry and breakout
  confirmation. 15m is non-veto context.
- A 1m state cannot override 5m RANGE, TRANSITION or UNKNOWN.
- A 5m breakout needs a matching 1m direction to be structurally eligible.
- Structure strength is a diagnostic, not a model probability.
- **Regime alignment in the cohort.** It is a declared same-coin conflict
  preference, not an implicit rejection gate for a lone provider intent.
- Canonical regime changes do not force exits or change sizing on their own.
- **Causality.** Every recovered intent uses only the context available at its
  own decision timestamp. Later rows in a batch cannot rewrite earlier
  decisions.
- UNKNOWN means the evidence is unavailable. Never manufacture neutral
  confidence for it.

Hyperliquid candles are open-timestamped. A 5m or 15m aggregate becomes
available at the open timestamp of its last constituent minute. Preserve prefix
invariance.

## Commands

```sh
# Classify: the canonical engine runs on 1m bars and derives 5m/15m context itself
hypervector regime classify --symbol BTC --timeframe 1m --lookback-days 30
hypervector regime classify --detector ema --fast 12 --slow 48 --symbol BTC --timeframe 5m

# Forward-return accuracy and edge of the canonical classifier
hypervector regime eval --symbol BTC --timeframe 1m --lookback-days 30 --forward-bars 15
hypervector regime eval --symbol BTC --timeframe 1m --book-path data/cache/book/BTC_l2_<YYYYMMDD>.jsonl

# Per-bar telemetry snapshots (default <data-root>/exports/regime_snapshots.json)
hypervector regime export --symbol BTC --timeframe 1m --bars 1500 --out snapshots.json

# Annotation-only point-in-time challengers, walk-forward
hypervector regime challengers --symbol BTC --lookback-days 180 --n-splits 3 --seed 42

# Alignment of the Hypervelocity regimes with recorded entries (CSV: open_time_utc, side, symbol)
hypervector regime align --positions positions.csv --forward-bars 30 --out alignment.json

# Tune causal regime parameters against recorded entries, with a chronological holdout
hypervector tune regime --positions positions.csv --n-trials 100 --seed 7 --train-fraction 0.7

# Live regime context comes from the cohort checkpoint
hypervector live monitor --config <profile.toml>
```

- **Canonical detector.** `--detector canonical` is the default and is the same
  classifier `regime eval` scores. It needs `--timeframe 1m`, and `--fast` or
  `--slow` with it exits 2.
- **EMA detector.** `--detector ema` is the EMA crossover, and `--fast` must be
  smaller than `--slow`.
- **History.** Every command loads history through the shared cache-first
  loader and reports `data_provenance`. `--max-cache-age-hours`, `--pin-cache`,
  `--refresh` and `--strict-hl-only` apply.
- **Required input first.** `regime align` and `tune regime` check `--positions`
  before loading any data.
- **Tuning board.** `tune regime` writes an exclusive-create board with its data
  provenance to `<data-root>/logs/research/regime_autotune_<UTC>.json`, or to
  `--out`, which must not exist yet.

Evaluation, challengers, alignment and tuning are chronological and report-only.
Technical failures are errors. Weak scores, sparse entries, losses and drawdown
are reported results. An optional HMM or MS-AR dependency that is missing must
not silently become another algorithm. No research score alone authorizes an
execution change.

Telemetry exports and checkpoints keep backend values, the exact run and profile
identity and the accounting epoch. Missing L2, funding or price evidence stays
unavailable rather than being filled in.

## Validation

```sh
.venv/bin/python -m pytest -q -n 2 -p no:cacheprovider \
  tests/test_regime_classifier.py tests/test_ultimate_regime.py \
  tests/test_regime_snapshot_export.py tests/test_canonical_regime_recovery.py \
  tests/test_cohort_canonical_regime_telemetry.py tests/test_regime_component_telemetry.py \
  tests/test_regime_challengers.py tests/test_hypervelocity_regime_eval_cli.py \
  tests/test_hypervelocity_regime_tuning.py
```

Any of these falsifies the engine and needs a fix plus regression coverage:

- lookahead;
- disagreement with venue-native completed bars;
- 1m overriding the primary 5m state;
- fabricated telemetry;
- a diagnostic score labelled as an execution-authorizing probability.
