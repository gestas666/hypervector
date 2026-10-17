---
name: hypervector-regime-detector
description: Operate and validate Hypervector's causal canonical regime engine and headless JSON telemetry.
---

# Canonical regime engine

The classifier is in `src/hypervector/regime/`; faithful thresholds come from
`faithful_regime_config()`. Use the unified CLI rather than a terminal UI.

## Authority

- Completed 5m structure is primary; 1m is execution telemetry and breakout
  confirmation; 15m is non-veto context.
- A 1m state cannot override 5m RANGE, TRANSITION or UNKNOWN.
- A 5m breakout needs matching 1m direction for structural eligibility.
- Structure strength is a diagnostic, not a model probability.
- Shared-cohort regime alignment is a declared same-coin conflict preference,
  not an implicit rejection gate for a lone provider intent.
- Canonical changes do not independently force exits or change sizing.
- Every recovered intent uses context available at its own decision timestamp.
  Later rows in a batch cannot rewrite earlier decisions.
- UNKNOWN means unavailable evidence; do not manufacture neutral confidence.

Hyperliquid candles are open-timestamped. A 5m/15m aggregate becomes available
at its last constituent minute's open timestamp. Preserve prefix invariance.

## Commands

```sh
hypervector regime classify --symbol BTC --timeframe 1m --lookback 30
hypervector regime eval --symbol BTC --timeframe 5m --lookback 30
hypervector regime export --symbol BTC --timeframe 1m --bars 1500
hypervector regime hypervelocity-eval --positions positions.csv
hypervector regime autotune --positions positions.csv --n-trials 100 --seed 42
hypervector regime challengers --symbol BTC --lookback 180
hypervector cohort monitor --config profile.toml
```

Evaluation and challenger models are chronological and report-only. Technical
failures are errors. Weak scores, sparse trades, losses and drawdown remain
reported results. Optional HMM/MS-AR dependencies must not silently become
another algorithm. No research score alone authorizes an execution change.

Telemetry exports and checkpoints preserve backend values, exact run/profile
identity and accounting epoch. Missing L2/funding/prices remain unavailable.
The retired Rust renderer has no remaining decision or execution authority.

## Validation

```sh
.venv/bin/python -m pytest tests/test_regime_classifier.py tests/test_regime_snapshot_export.py tests/test_canonical_regime_recovery.py tests/test_cohort_canonical_regime_telemetry.py tests/test_regime_component_attribution.py -q
```

Falsifiers include lookahead, disagreement with venue-native completed bars,
1m overriding the primary state, fabricated telemetry, or a technical score
being labeled as an execution-authorizing probability. Historical measured
research remains under `docs/research/` and `docs/research-journal/`; it is not
an assurance of predictive edge or profitability.
