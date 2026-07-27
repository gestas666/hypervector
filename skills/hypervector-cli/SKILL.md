---
name: hypervector-cli
description: >
  Operate the Hypervector perpetuals quant engine CLI, VectorBT vectorized backtester,
  Nautilus event-driven engine, Karpathy/Optuna autotuner, and 3-screen tui-regime-detector cockpit.
  Use when running hypervector commands, backtesting, autotuning, regime evaluation,
  paper/shadow/live checks, metalabel training, or launching the Ratatui TUI cockpit.
---

# Hypervector Perpetuals Quant Engine & Regime Detector CLI

Comprehensive operator skill for **Hypervector** — VectorBT vectorized backtesting, Nautilus event-driven backtesting, Karpathy/Optuna autotuning, LightGBM metalabeling, and 3-screen Ratatui TUI regime cockpit.

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
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

The Python CLI starts the no-submit backend, waits for its fresh session row,
and opens the TUI in the foreground. Pressing `q` stops the TUI and its child
backend cleanly. Backend output is retained at
`<data-root>/paper/hypervelocity-shadow.log`. A per-data-root process lock
refuses a second Hypervelocity backend.

Normal quit and restart preserves the latest durable Hypervelocity shadow run:
cash, realized PnL, any open position, pending maker entry, cooldown timestamp,
and closed-trade journal are restored from the backend ledger. The backend
validates the execution-spec fingerprint and portfolio equity identity before
restoring active state. Empty accidental launches do not replace that portfolio
identity. Reset is explicit and recoverable only through the command below.

After a target closes, the completed direction is consumed for the current
regime episode. A persistent `TREND_UP` cannot immediately create another long,
and a persistent `TREND_DOWN` cannot immediately create another short. A
non-matching canonical regime must be observed before a later fresh same-side
signal can re-arm. This state is durable across normal restarts and is additive
to the one-completed-bar minimum cooldown. An eligible opposite side after exit
remains available after that minimum cooldown.

When an open target or pending maker entry spans downtime, startup reconciles
only completed, venue-matched Hyperliquid candles after the ledger timestamp.
It may fund, fill, cancel, or close that already-active state, but it cannot
create a new historical entry. Hourly boundaries require the matching public
Hyperliquid funding-history row; missing evidence fails startup explicitly.

The TUI does not execute trades. Trade, position, PnL, cost, policy, regime,
isolated liquidation price, and five-level depth fields are projections of
backend ledger telemetry. The TUI displays `LIQ PRICE UNAVAILABLE` when an
older ledger lacks that field; it never derives a substitute from leverage or
entry price. The backend remains the execution and persistence authority.

Reset a completed shadow observation window with a recoverable backup:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-shadow-reset --yes
```

Without `--yes`, the reset is a non-mutating dry run. Confirmed resets acquire
the singleton backend lock, copy decisions and the backend log under
`<data-root>/backups/shadow_reset_<UTC>/`, then clear only those two files.
Screen 3 displays the backend-reported active data root and the complete,
shell-quoted reset command for that same root.

### 6. 3-Screen Visual Microstructure Cockpit (`tui-regime-detector`)

Ratatui 0.29 interactive 3-screen cockpit featuring backend telemetry, a live L2 depth stack, paper trade journal, and a navigable read-only configuration menu:

```bash
# Interactive playback cockpit (1m execution, 5m primary, 15m context)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m

# Real-time live mode (250ms refresh rate)
cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 1m --live --refresh-ms 250
```

#### Cockpit Screen Navigation:
- **`[1]`**: **Dashboard** (backend strategy, position, live L2, PnL, and execution journal).
- **`[2]`**: **Regime Detection** (1m/5m/15m classification and transition audit log).
- **`[3]`**: **Configuration** (selectable effective backend options; read-only).
- On Dashboard, **`[↑/↓]`** or **`[j/k]`** selects a closed trade and **`[Enter]`** opens entry/exit regime, fee, funding, and PnL details.
- On Regime Detection, the same keys select and inspect transition events.
- The canonical regime uses 5m as the authoritative primary. The 1m state
  cannot override 5m `RANGE`, `TRANSITION`, or `UNKNOWN`; it confirms the same
  direction for 5m breakouts. The 15m state is non-veto context.

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

### 10. Hypervelocity Regime Evaluation, Retuning, and Challengers

Use chronological evaluation and tuning against explicit recorded-position
labels. Statistical challengers are annotation-only and cannot filter, size,
route, or exit trades:

```bash
uv run python -m hypervector hypervelocity-regime-eval \
  --symbol BTC --timeframe 1m --lookback 180 \
  --positions path/to/positions.csv \
  --out data/logs/research/hypervelocity_regime_eval.json

uv run python -m hypervector hypervelocity-regime-autotune \
  --symbol BTC --timeframe 1m --lookback 180 \
  --positions path/to/positions.csv --n-trials 100 --seed 42 \
  --out data/logs/research/hypervelocity_regime_autotune.json

uv run python -m hypervector hypervelocity-regime-challengers \
  --symbol BTC --timeframe 1m --lookback 180 \
  --forward-horizon 30 --seed 42 --n-splits 3 \
  --out data/logs/research/hypervelocity_regime_challengers.json
```

### 11. Bounded Hyperliquid L2 History from 0xArchive

Configure `OXA_API_KEY` in the gitignored `.env`, then qualify a small UTC
window before widening it:

```bash
uv run python -m hypervector oxa-book-fetch \
  --symbol BTC \
  --start 2026-07-26T23:50:00Z \
  --end 2026-07-26T23:51:00Z \
  --depth 20 --limit 1000 --max-pages 1
```

The command is fixed to Hyperliquid core and stores raw response envelopes,
vendor request IDs, SHA-256 checksums, a manifest, and replay-compatible
`books.jsonl.gz` below `data/cache/vendor/0xarchive/`. It never adds a fabricated
local receive timestamp. A non-null `continuation_cursor` means the explicit
page bound truncated the requested window; it is not success-shaped full
coverage. The measured resumable REST backfill uses compressed hourly bundles;
completed manifests are skipped on restart and incomplete windows fail before
publication.

Acquire matching public trades for the same explicit UTC window:

```bash
uv run python -m hypervector oxa-trade-fetch \
  --symbol BTC \
  --start 2026-07-26T23:50:00Z \
  --end 2026-07-26T23:51:00Z \
  --limit 1000 --max-pages 1
```

Recent 0xArchive trade responses contain participant-side maker and taker
fills. Hypervector preserves every raw row but emits one public trade per
venue `trade_id`, using the `crossed=true` taker row for aggressor direction.
A truncated maker-only participant group is reported as unresolved rather
than guessed. Historical trades never receive a fabricated local receipt time.

Acquire a paired 90-day BTC L2/trade archive with bounded workers:

```bash
set -a; source .env; set +a
uv run python scripts/oxa_backfill.py \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-27T00:00:00Z \
  --workers 4
```

Verify all expected hourly bundles and each declared SHA-256 after acquisition:

```bash
uv run python scripts/oxa_archive_audit.py \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-27T00:00:00Z \
  --out data/logs/research/oxa_btc_90d_archive_audit.json
```

Acquire venue candles and install an exact strict-Hyperliquid research cache.
Missing vendor minutes are continuity-filled only in the installed cache as
`hl_gap_fill` zero-volume bars; the immutable vendor bundle remains unchanged.

```bash
uv run python -m hypervector --data-root data oxa-candle-fetch \
  --symbol BTC --interval 1m \
  --start 2026-04-28T00:00:00Z \
  --end 2026-07-27T00:00:00Z \
  --limit 10000 --max-pages 20 --install-research-cache
```

Replay a verified archive window without constructing thousands of path
arguments:

```bash
uv run python -m hypervector --data-root data hypervelocity-maker-replay \
  --symbol BTC --timeframe 1m --lookback 90 --strict-hl-only \
  --archive-start 2026-04-28T00:00:00Z \
  --archive-end 2026-07-27T00:00:00Z \
  --fill-rule all --initial-equity 10000 \
  --maker-fee-rate 0.00015 --entry-ttl-seconds 300 \
  --labels-out data/logs/research/hypervelocity_oxa_90d_labels.parquet \
  --out data/logs/research/hypervelocity_oxa_90d_fill_comparison.json
```

The archive form verifies manifest identity and SHA-256 before replay, loads
one hourly pair at a time, carries order/position/equity state across hour
boundaries, and compares touch, one-tick book-through, and public-trade-through
fills. Explicit repeated `--book-path` and `--trade-path` arguments remain
available for bounded investigations. The command is report-only.

Conservative labels require the same signal to resolve identically under all
three fill assumptions. Disagreement and right-censored positions stay
unresolved. This maker comparator does not model historical funding,
liquidation, authentic queue rank/cancellations, or genuine local receipt
latency; do not interpret its compounded equity as a portfolio forecast.

---

## Dual Backtesting Architecture

1. **VectorBT Engine (`hypervector backtest` & `hypervector autotune`)**:
   - Used for Phase 1 / Phase 1.5 high-speed vectorized simulation across 180+ days of 1m/5m data in seconds.
   - Calculates portfolio return curves, venue leverage scaling, fee schedules, trailing exit stops, and drives the autotuning engine.

2. **Nautilus Engine (`hypervector phase2-run`)**:
   - Used for Phase 2 event-driven backtesting with order matching, venue fills, and strict export bundle verification.
