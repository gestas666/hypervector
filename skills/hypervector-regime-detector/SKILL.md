---
name: hypervector-regime-detector
description: >
  Operate and validate the canonical 1m/5m/15m Hypervelocity regime engine and
  its read-only three-screen Ratatui telemetry view.
---

# Hypervector Canonical Regime Engine

## Authority contract

The production classifier is implemented in `src/hypervector/regime/` and the
faithful thresholds are defined by `faithful_regime_config()`. Hyperliquid
candles are open-timestamped. A 5m or 15m aggregate becomes available at the
last constituent one-minute open timestamp; future values must never be shifted
into an earlier decision row.

| State | Backend meaning | Entry effect |
|---|---|---|
| `TREND_UP` | Authoritative 5m positive trend structure | Long eligible |
| `TREND_DOWN` | Authoritative 5m negative trend structure | Short eligible |
| `BREAKOUT` | 5m breakout state | Eligible only when 1m confirms the same direction |
| `RANGE` | 5m range/chop/compression structure | Entry blocked |
| `TRANSITION` | Mixed 5m structure | Entry blocked |
| `UNKNOWN` | Warmup incomplete | Entry blocked |

The 1m state is execution-timeframe telemetry and breakout confirmation; it
cannot replace a non-directional 5m primary state. The 15m state is context and
is not a hard veto. `regime_strength_score` is the mean 1m/5m/15m EMA-gap
strength percentile rank normalized to `[0, 1]`. It is a report-only technical
diagnostic, not a model probability or execution gate.

The faithful thresholds are the strict-Hyperliquid stability Pareto candidate:
EMA 20/50, 240-bar structure lookback, trend/range percentiles 50/40, 1 bp
minimum trend gap, choppiness threshold 85, 3 bp coiling width, and a 90-bar
breakout requiring 5 bp clearance and 2x prior volume. These parameters reduce
false-RANGE/no-entry classifications and churn on the measured 90-day window;
their slower transition response is an explicit monitored trade-off.

## Unified live shadow view

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

The Python command owns the backend lifecycle. The Rust TUI reads the backend
ledger and does not simulate trades. Normal quit preserves the durable shadow
portfolio. A fresh start is explicit and recoverably backed up:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-shadow-reset --yes
```

## File playback

Export snapshots through the canonical classifier, then open them read-only:

```bash
uv run python -m hypervector \
  --data-root data \
  regime-export --symbol BTC --timeframe 1m --bars 1500

cargo run -p hypervector-tui --bin tui-regime-detector -- \
  --symbol BTC --timeframe 1m \
  --file data/exports/regime_snapshots.json
```

Snapshot playback must not manufacture missing prices, OHLCV, timestamps,
microstructure, funding, regime labels, or policy weights. Missing optional
microstructure and funding are explicitly marked unavailable.

## Evaluation and tuning

```bash
uv run python -m hypervector hypervelocity-regime-eval \
  --positions docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv

uv run python -m hypervector hypervelocity-regime-autotune \
  --positions docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv \
  --n-trials 100 --seed 42 \
  --out data/logs/research/hypervelocity_regime_autotune.json

uv run python -m hypervector hypervelocity-regime-challengers \
  --symbol BTC --timeframe 1m --lookback 180 \
  --forward-horizon 30 --seed 42 --n-splits 3 \
  --out data/logs/research/hypervelocity_regime_challengers.json
```

Evaluation is chronological and report-only. Retain every valid trial result,
including losses, sparse trades, weak scores, and poor drawdown. Only a
technical failure may mark a trial as an error. Expanding volatility terciles,
walk-forward GMM, and training-only Wasserstein states are annotation-only.
Optional HMM/MS-AR arms report a missing dependency instead of silently
substituting a non-causal model. Challengers remain non-executable until a
separate decision explicitly changes that policy.

## Verification

```bash
uv run pytest tests/test_regime_classifier.py \
  tests/test_hypervelocity_regime_eval.py \
  tests/test_regime_snapshot_export.py -q
cargo test -p hypervector-tui
```

Falsifiers include prefix non-invariance, disagreement with a venue-native 5m
candle, a 1m trend overriding 5m `RANGE`/`TRANSITION`/`UNKNOWN`, unconfirmed
breakout direction, fabricated TUI values, or a technical score labeled as a
model probability.
