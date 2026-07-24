---
name: hypervector-regime-detector
description: >
  Operate the Ultimate 5-Tier Multi-Timeframe Microstructure Regime Engine and the
  tui-regime-detector 4-Screen Ratatui terminal cockpit. Use when analyzing market regimes,
  evaluating regime accuracy, operating the 4-screen TUI cockpit, or configuring strategy policy and risk parameters.
---

# Hypervector Ultimate Regime Engine & Visual Cockpit Skill

Dedicated skill for the **Ultimate 5-Tier Multi-Timeframe Microstructure Regime Engine** ([`src/hypervector/regime/ultimate.py`](file:///Users/gestas/Prototypes/hypervector/src/hypervector/regime/ultimate.py)) and the **`tui-regime-detector` 4-Screen Terminal Cockpit** ([`crates/hypervector-tui`](file:///Users/gestas/Prototypes/hypervector/crates/hypervector-tui)).

---

## 🏛️ 5-Tier Regime Architecture & Hypertrader Label Mapping

| Primary TA Label | Microstructure State | Trigger Condition | Policy Sizing ($W_{\text{Long}}, W_{\text{Short}}$) | Hyperliquid Max Leverage Cap |
| :--- | :--- | :--- | :--- | :--- |
| `TREND_UP` | `BULL_MOMENTUM_EXPANSION` | 15m/5m Bullish + ADX > 25 + OPI > +0.20 | $W_{\text{Long}} = 2.0\times, W_{\text{Short}} = 0.0\times$ | **40.0× (BTC)** / **25.0× (ETH)** |
| `TREND_DOWN` | `BEAR_MOMENTUM_EXPANSION` | 15m/5m Bearish + ADX > 25 + OPI < -0.20 | $W_{\text{Long}} = 0.0\times, W_{\text{Short}} = 2.0\times$ | **40.0× (BTC)** / **25.0× (ETH)** |
| `BREAKOUT` | `VOLATILITY_COILING_COMPRESSION` | BBWP Percentile < 20.0 (Coiling) | $W_{\text{Long}} = 1.5\times, W_{\text{Short}} = 1.5\times$ | **20.0× (SOL)** / **15.0× (Alts)** |
| `TRANSITION` | `FUNDING_CARRY_REVERSAL` | Funding Z-Score $|Z| \ge 1.8$ | $W_{\text{Long}} = 2.0\times$ (if negative Z) or $W_{\text{Short}} = 2.0\times$ | **20.0× (SOL)** / **15.0× (Alts)** |
| `RANGE` | `RANGE_CHOP_HIGH_FRICTION` | Choppiness > 55 or Spread > 6.0 bps | $W_{\text{Long}} = 0.25\times, W_{\text{Short}} = 0.25\times$ (0.0x if spread > 6bps) | **10.0× (Default)** |

---

## 🖥️ Launching the `tui-regime-detector` 4-Screen Cockpit

```bash
# 1. Interactive playback cockpit (1m BTC execution with 15m HTF lock)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m

# 2. Real-time live mode (250ms tick refresh rate)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m --live --refresh-ms 250

# 3. Playback historical parquet or JSON snapshot file
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --file data/exports/regime_snapshots.json
```

---

## ⌨️ 4-Screen Terminal Cockpit Keybindings

### Global Screen Switcher & Controls
| Key | Action |
| :--- | :--- |
| `[1]` / `[2]` / `[3]` / `[4]` | Jump directly to Screen 1, 2, 3, or 4 |
| `[Tab]` | Cycle screens (`1 -> 2 -> 3 -> 4 -> 1`) |
| `[Space]` | **Play / Pause** real-time stream or historical playback |
| `[← / →]` | **Scrub Backwards / Forwards** through historical time |
| `[s]` | **Cycle Playback Speed** ($1.0\times \to 2.0\times \to 5.0\times \to 10.0\times$) |
| `[t]` | **Cycle Timeframe** ($1\text{m} \to 5\text{m} \to 15\text{m}$) |
| `[r]` | **Reset** playback scrub position to start |
| `[q / Esc]` | **Quit** terminal cockpit |

### Screen `[4]` Engine & Risk Configuration Keybindings
| Key | Action |
| :--- | :--- |
| `[↑ / ↓]` or `[j / k]` | **Select Parameter Option Row** |
| `[Enter]` or `[c]` | **Cycle Active Setting Value** |
| `[+]` or `[=]` / `[→]` | **Increase Leverage Multiplier** by +1.0x up to asset venue max cap |
| `[-]` or `[←]` | **Decrease Leverage Multiplier** by -1.0x (returns to Dynamic ML when $\le 1.0\times$) |

---

## 📊 Running Regime Forward Accuracy Evaluator

Evaluate classification precision, forward return edge, Sharpe ratio, and persistence across market states:

```bash
uv run python -m hypervector regime-eval --symbol BTC --timeframe 5m --lookback 180
```
