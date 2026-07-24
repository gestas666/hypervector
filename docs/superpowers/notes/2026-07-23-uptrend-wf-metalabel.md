# Research note — uptrend tournament + walk-forward metalabel

**Date:** 2026-07-23  
**Symbol / TF:** BTC 1m · lookback 90d  
**Export (cost-aware Phase 1):** `data/exports/export_uptrend_costed_191`  
**WF bundle:** `data/models/metalabel/wf_crown_stack_long_20260723T163303Z`  
**Installed to:** `data/models/metalabel/` (via `metalabel-train --install`)

## Pipeline run

1. Expanded grids: `trend_ride_long` (48), `crown_stack_long` (18), `ma_cross_long` (4)
2. Cost-aware VectorBT sweep-up (HL taker + 2 bps slip + funding)
3. Exit outer loop on crown (atr / trail / fixed_rr)
4. Export best costed trial → Phase 2 Nautilus historical
5. **NEW:** `metalabel-train` walk-forward on strategy-entry labels (TP-first = 1)

## Phase 1 ranking (with costs)

| Strategy | Best net_pnl (approx) | Notes |
|----------|----------------------|--------|
| crown_stack_long | **−37%** | Least bad; still unusable |
| trend_ride_long | −54% | Squeeze on + chop 45 helps slightly |
| ma_cross_long | −92% | Null baseline |

**Winner params (least bad, costed):**

```json
{
  "strategy": "crown_stack_long",
  "bbwp_lookback": 100,
  "bbwp_threshold": 15.0,
  "pmarp_exit_hi": 90.0,
  "exit_mode": "atr"
}
```

Metrics: trades 428 · win% ~9.8% · sharpe ~−37 · max DD ~−37%.

No-cost diagnostic still ~−1.4% → alpha ≈ fee food, not free lunch.

Legacy +$548 rows (2026-07-22) lack `research_meta` / cost honesty — **do not promote**.

## Phase 2 Nautilus

- Export used for first P2 run: `export_uptrend_245` (no-cost metrics stamp; Nautilus still lost)
- PnL ≈ **−$3,589** · orders 1607 · 129600 bars
- Aligns with costed Phase 1: **no promote**

## Walk-forward metalabel (LightGBM)

Command:

```bash
uv run python -m hypervector metalabel-train \
  --path data/exports/export_uptrend_costed_191 \
  --lookback 90 --train-days 45 --test-days 15 \
  --embargo-minutes 60 --max-hold-bars 120 --install
```

| Metric | Value |
|--------|-------|
| n_labels | 428 |
| class_balance (TP rate) | 0.30 |
| WF folds | 3 |
| OOS log_loss mean | **0.649** |
| OOS baseline log_loss | **0.582** |
| OOS AUC mean | 0.53 |
| beat_baseline | **false** |
| Purged-CV AUC (full) | 0.57 |

**Verdict:** Walk-forward OOS **does not beat** always-base-rate baseline. Do **not** treat this LGBM as a sizing edge. Bundle is installed for plumbing / further research only.

## How to re-run / use

```bash
# Research funnel
uv run python -m hypervector sweep-up --strategy crown_stack_long --lookback 90 --export
uv run python -m hypervector export --track uptrend
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-run --path data/exports/<id> --lookback 90

# Walk-forward retrain (labels = strategy entries × export TP/SL)
uv run python -m hypervector metalabel-train --path data/exports/<id> --install

# Paper (only after beat_baseline true on a future run)
export HYPERVECTOR_METALABEL_ROOT=$PWD/data/models/metalabel
uv run python -m hypervector paper-run --path data/exports/<id> --mode shadow --metalabel
```

## Next research levers (not done)

1. Regime-filter entries (only trade when EMA regime = up)
2. Higher TF or fewer trades (1m fees crush high turnover)
3. Label on trend_ride best cell instead of crown
4. 180d history + longer train folds
5. Skip floor / precision-oriented threshold on metalabel p (not just scale conviction)

## Safety

- Paper/shadow never places.
- Live remains fail-closed; **do not arm** from this research.
