---
name: hypervector-cli
description: >
  Operate the Hypervector perpetuals quant engine CLI, VectorBT vectorized backtester,
  Nautilus event-driven engine, Karpathy/Optuna autotuner, and 4-screen tui-regime-detector cockpit.
  Use when running hypervector commands, backtesting, autotuning, regime evaluation,
  paper/shadow/live checks, metalabel training, or launching the Ratatui TUI cockpit.
---

# Hypervector Perpetuals Quant Engine & Regime Detector CLI

Comprehensive operator skill for **Hypervector** — VectorBT vectorized backtesting, Nautilus event-driven backtesting, Karpathy/Optuna autotuning, LightGBM metalabeling, and 4-Screen Ratatui TUI regime cockpit.

## Hard Safety Rules & Project Charter

1. **Ungated Execution (`SRS_HV1_NO_GATES`)**: Only **technical failure** aborts a trial. No implicit strategy, drawdown, or risk rejection gates unless explicitly configured by the user. Performance, drawdown, trade count, regime confidence, and model scores remain reported trial results rather than implicit abort conditions.
2. **Fail-Closed Safety (`SRS_HV1_HONESTY`)**: Paper/shadow mode **never** constructs live execution clients or places live orders. Default mode is `shadow`. `live-run` is strictly fail-closed and arms **only** on explicit `--enabled --i-accept-live-risk` flags and secret environment variables.
3. **Secret Protection**: Never print secret values (`HYPERVECTOR_HL_WALLET_ADDRESS`, `HYPERVECTOR_HL_API_PRIVATE_KEY`). Only print presence booleans.
4. **Venue Specification (`SRS_HV1_VENUE_SPEC`)**: Strict adherence to Hyperliquid per-asset leverage specifications (BTC 40x max, ETH 25x max, SOL 20x max, Altcoins 10x-15x max).
5. **Mainnet Only**: Mainnet venue parameters only — no testnet path.
6. **TUI Integrity**: TUI is a read-only live telemetry display and paper trading cockpit; CLI owns process lifecycle and execution.

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

Runs high-speed vectorized simulation across 180+ days of 1m/5m data in seconds with venue-restricted leverage scaling, fee presets, and orderbook entry gating:

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

### 5. Hypervelocity Shadow Backend and Read-Only TUI

Use one command to supervise the backend and display its telemetry in the TUI:

```bash
uv run python -m hypervector \
  --data-root data/ops/hypervelocity_visual \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

The Python CLI starts the no-submit backend, waits for its fresh session row,
and opens the TUI in the foreground. Pressing `q` stops the TUI and its child
backend cleanly. Backend output is retained at
`<data-root>/paper/hypervelocity-shadow.log`. A per-data-root process lock
refuses a second Hypervelocity backend.

The TUI does not execute or reconstruct trades. Trade, position, PnL, cost,
and policy fields come from the backend ledger. The current depth visualization
is derived from cached regime snapshot ratios; it is not a raw L2 ladder.

### 6. 4-Screen Visual Microstructure Cockpit (`tui-regime-detector`)

Ratatui 0.29 interactive 4-screen cockpit featuring live stream playback, L2 orderbook depth stack, paper trade journal, and interactive engine configuration:

```bash
# Interactive playback cockpit (1m BTC execution with 15m HTF lock)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m

# Real-time live mode (250ms refresh rate)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m --live --refresh-ms 250
```

#### Cockpit Screen Navigation:
- **`[1]`**: **Regime Classifier Engine** (15m HTF lock, continuous rolling transition audit log).
- **`[2]`**: **Strategy Policy Matrix**.
- **`[3]`**: **Live Shadow Paper Trading Cockpit** ($10k starting capital, L2 orderbook stack, win/loss stats, execution journal).
- **`[4]`**: **Engine & Risk Configuration** (Leverage mode, TP/SL trailing engines, position sizing rules).

### 7. Walk-Forward LightGBM Metalabeling

Train an Isotonic-calibrated LightGBM ensemble on strategy entries:

```bash
uv run python -m hypervector metalabel-train --path data/exports/<export_dir> --install
```

### 8. Inventory & System Status

```bash
uv run python -m hypervector status
```

### 9. Hypervelocity Shadow/Real Reconciliation

Compare one or more explicit backend shadow run IDs with a real-strategy CSV
covering the same UTC observation window:

```bash
uv run python -m hypervector hypervelocity-shadow-compare \
  --shadow-ledger data/paper/decisions/decisions.jsonl \
  --positions path/to/new_real_positions.csv \
  --run-id <long-run-id> --run-id <short-run-id> \
  --entry-tolerance-seconds 120 \
  --out data/logs/research/hypervelocity_shadow_compare.json
```

The command is report-only. It uses live `regime_observation` rows to define
the shadow window, refuses non-overlapping real logs, and reports entry,
direction, RANGE-state, maker submit-to-fill, exit-timing, and price
discrepancies without creating a promotion or execution gate.

---

## Dual Backtesting Architecture

1. **VectorBT Engine (`hypervector backtest` & `hypervector autotune`)**:
   - Used for Phase 1 / Phase 1.5 high-speed vectorized simulation across 180+ days of 1m/5m data in seconds.
   - Calculates portfolio return curves, venue leverage scaling, fee schedules, trailing exit stops, and drives the autotuning engine.

2. **Nautilus Engine (`hypervector phase2-run`)**:
   - Used for Phase 2 event-driven backtesting with order matching, venue fills, and strict export bundle verification.
