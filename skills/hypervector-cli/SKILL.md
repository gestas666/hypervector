---
name: hypervector-cli
description: >
  Operate the Hypervector perpetuals quant engine CLI, VectorBT vectorized backtester,
  Nautilus event-driven engine, Karpathy/Optuna autotuner, and tui-regime-detector cockpit.
  Use when running hypervector commands, backtesting, autotuning, regime evaluation,
  paper/shadow/live checks, metalabel training, or launching the Ratatui TUI cockpit.
---

# Hypervector Perpetuals Quant Engine & Regime Detector CLI

Comprehensive operator skill for **Hypervector** — VectorBT vectorized backtesting, Nautilus event-driven backtesting, Karpathy/Optuna autotuning, LightGBM metalabeling, and Ratatui TUI regime cockpit.

## Hard Safety Rules

1. **Paper/shadow never places venue orders.** Default mode is `shadow`.
2. **Live is fail-closed.** `live-run` requires `--enabled` **and** `--i-accept-live-risk` **and** secrets env. Do not arm without explicit user request.
3. **Never print secret values** (`HYPERVECTOR_HL_WALLET_ADDRESS`, `HYPERVECTOR_HL_API_PRIVATE_KEY`). Only presence booleans.
4. **Mainnet only** — no testnet path.
5. **TUI is read-only.** CLI owns lifecycle and execution.

---

## Invocation

Run commands from repo root using `uv`:

```bash
uv run python -m hypervector <command> [options]
```

Or launch the Rust terminal cockpit:

```bash
cargo run -p hypervector-tui --bin tui-regime-detector -- [options]
```

---

## Command Cookbook

### 1. VectorBT Strategy Backtest (Phase 1.5 Vectorized Engine)

Runs high-speed vectorized simulation across 180+ days of 1m/5m data in seconds with leverage scaling ($1\times - 10\times$), fee presets, and orderbook entry gating:

```bash
# Backtest Crown Stack Long on 5m BTC with 2.0x leverage & Maker fees
uv run python -m hypervector backtest \
  --strategy crown_stack_long \
  --symbol BTC --timeframe 5m \
  --lookback 180 --leverage 2.0 --fee-model hl_maker

# Backtest Open Interest Divergence with Orderbook Gating on 1m BTC
uv run python -m hypervector backtest \
  --strategy oi_divergence_long \
  --symbol BTC --timeframe 1m \
  --lookback 90 --book-gate --max-spread-bps 3.0 \
  --book-path data/cache/book/BTC_l2_20260723.jsonl
```

### 2. Event-Driven Nautilus Backtest (Phase 2 Engine)

Executes event-driven backtesting on strict strategy export bundles:

```bash
uv run python -m hypervector phase2-run \
  --path data/exports/<export_dir> \
  --lookback 180 --conviction 0.5
```

### 3. Ultimate Regime Accuracy Evaluator

Measures directional forward return precision, Sharpe ratio, and persistence across market states:

```bash
# Evaluate 5m BTC dataset (180 days lookback)
uv run python -m hypervector regime-eval --symbol BTC --timeframe 5m --lookback 180

# Evaluate 1m BTC with L2 Orderbook alignment
uv run python -m hypervector regime-eval --symbol BTC --timeframe 1m --book-path data/cache/book/BTC_l2_20260723.jsonl
```

### 4. Karpathy & Optuna Dual Autotuner

Runs continuous stochastic sampling (Karpathy) or Tree-structured Parzen Estimator (Optuna) parameter autotuning:

```bash
# Hybrid Karpathy mutation + Optuna TPE sampler
uv run python -m hypervector autotune --strategy crown_stack_long --sampler hybrid --n-trials 100

# Karpathy random-adaptive mutation sampler on Apex Open Interest Divergence
uv run python -m hypervector autotune --strategy oi_divergence_long --sampler karpathy --n-trials 100
```

### 5. Visual Quant TA & Microstructure Terminal Cockpit (`tui-regime-detector`)

Ratatui 0.29 interactive visual cockpit displaying active regime states, MTF alignment, sparklines, orderbook pressure gauges, and policy allocation:

```bash
# Interactive playback cockpit
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 5m

# Real-time live mode (250ms tick refresh)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --live --refresh-ms 250
```

### 6. Walk-Forward LightGBM Metalabeling

Train an Isotonic-calibrated LightGBM ensemble on strategy entries:

```bash
uv run python -m hypervector metalabel-train --path data/exports/<export_dir> --install
```

### 7. Inventory & System Status

```bash
uv run python -m hypervector status
```

---

## Dual Backtesting Architecture

1. **VectorBT Engine (`hypervector backtest` & `hypervector autotune`)**:
   - Used for Phase 1 / Phase 1.5 high-speed vectorized simulation across 180+ days of 1m/5m data in seconds.
   - Calculates portfolio return curves, leverage scaling ($1\times - 10\times$), fee schedules, trailing exit stops, and drives the autotuning engine.

2. **Nautilus Engine (`hypervector phase2-run`)**:
   - Used for Phase 2 event-driven backtesting with order matching, venue fills, and strict export bundle verification.
