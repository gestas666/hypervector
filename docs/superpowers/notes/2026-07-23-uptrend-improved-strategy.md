# Improved uptrend strategy handoff

**Date:** 2026-07-23  
**Status:** Phase-1 cost-aware **positive** + Phase-2 Nautilus **positive**  
**Canonical export (dense autotune):** `data/exports/export_uptrend_autotuned_864`  
**Prior refine:** `data/exports/export_uptrend_best_863` (superseded by denser grid)  
**Do not use:** `export_uptrend_costed_191` (1m loser, superseded)

---

## Direct answers

### Did we autotune properly the first time?

**No.** First pass was a small 90d **1m** grid with high turnover. Fees ate everything. That was incomplete search, not “the strategy is dead.”

### What we did now (real improvement loop)

1. **Regime filter** on crown + trend_ride (`regime_filter=True/False` in grid)
2. **Lower turnover via higher TF:** 15m and **5m** @ **180d**
3. **Full grids** across strategies + **exit modes** (atr / trail / fixed_rr)
4. **Local refine** around winner (BBWP / PMARP / SL mult / RR)
5. **Phase 2 Nautilus** validation on the export
6. Walk-forward metalabel retrain on strategy labels (low n — see below)

---

## Winning configuration (dense autotune — best of 1512 trials)

| Field | Value |
|-------|--------|
| Strategy | `crown_stack_long` |
| Timeframe | **5m** |
| Lookback | **180d** |
| Regime filter | **True** (EMA 12/48 up only) |
| bbwp_lookback | **180** |
| bbwp_threshold | **17.0** |
| pmarp_exit_hi | **95.0** |
| Exit mode | **atr** |
| sl_atr_mult | **2.0** |
| rr | **2.0** |
| atr_length | **14** |
| Costs | HL taker 3.5 bps + 2 bps slip + funding |
| Search | 168 signal × 9 exit = **1512** cost-aware cells; min trades ≥ 15 |

### Phase 1 VectorBT (cost-aware)

| Metric | Value |
|--------|-------|
| net_pnl | **+$443.49** (~**+4.43%**) |
| sharpe | **4.31** |
| trades | **30** |
| win% | **36.7%** |
| max_drawdown | **−1.42%** |

### Phase 2 Nautilus historical

| Metric | Value |
|--------|-------|
| report | `data/nautilus/backtest/` under run for export_uptrend_autotuned_864 |
| bars | 51840 (5m × 180d) |
| orders | **113** |
| **pnl** | **+$382.89** |

Phase-1 and Phase-2 agree on **positive** edge (P2 slightly lower — expected).

---

## How it was selected (autotune evidence)

**Search space (v2):**

- TFs: 15m × 180d (atr/trail/fixed_rr), 5m × 180d atr
- Strategies: `trend_ride_long` (96 cells w/ regime) + `crown_stack_long` (54 cells w/ regime)
- Then refine on 5m: 4×4×3 BBWP/PMARP × 4 exit knobs around winner

**Leaderboard (cost-aware, top):**

1. crown 5m dense autotune → **+$443 / sh 4.31** ← **chosen** (`export_uptrend_autotuned_864`)
2. prior refine → +$398 / sh 3.86
3. coarse 5m → +$228 / sh 2.40
4. crown 15m atr → +$130 / sh 2.17
5. trend_ride all TF/modes → still negative after costs

**trend_ride** was fully searched; best cells still lose after costs. Crown + regime + 5m is the edge in this window.

---

## Run it

```bash
# Validate
uv run python -m hypervector export-validate \
  --path data/exports/export_uptrend_autotuned_864 --strict

# Phase 2 re-check
uv run python -m hypervector phase2-run \
  --path data/exports/export_uptrend_autotuned_864 --lookback 180

# Paper shadow (5m loadout)
uv run python -m hypervector paper-run \
  --path data/exports/export_uptrend_autotuned_864 \
  --mode shadow --max-live-bars 5
```

---

## Metalabel note

Low-turnover winner ≈ 32 entries / 180d → walk-forward sample-starved. Metalabel is **optional** and not required for this export. Prefer fixed conviction until more history/labels exist; `metalabel-train` threshold lowered for sparse strategies but OOS will be noisy.

---

## Caveats (honest, not a shrug)

- Single-window 180d BTC — not multi-asset / multi-year.
- +4% net with 32 trades is real after costs but **modest**; not a license to size live large.
- Live still fail-closed; promote only after paper/shadow soak **you** accept.
- Overfit risk: refine grid saw many positive neighbors (good), but still one market regime.

---

## Files

| Path | Role |
|------|------|
| `data/exports/export_uptrend_autotuned_864/` | **Saved best strategy** (dense autotune) |
| `data/logs/research/autotune_fine_5m_board.json` | Top-50 fine board |
| `data/logs/research/autotune_v2.*` | Coarse multi-TF sweep logs |
| This note | Handoff |

**Paper path next:** shadow soak on this export; only then discuss live.
