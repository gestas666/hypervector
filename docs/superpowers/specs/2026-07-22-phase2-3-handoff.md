# Phase 2/3 Handoff Contract + Paper Mode (hypervector)

**Date:** 2026-07-22  
**Status:** Approved in session (design lock for next implementation)  
**Depends on:** Phase 1 design `2026-07-21-phase1-vectorbt-design.md` (complete for start funnel)  
**Execute via (prep, done):** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Execute via (actor + ML next):** `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`

---

## 1. Pipeline (locked)

```text
Phase 1   VectorBT research (features, grids, rank, export)
Phase 1.5 Costs + TP/SL modes + conviction risk sizing (research realism)
Phase 2   NautilusTrader event-driven **historical** sim — same strategy identity/params
Phase 3   paper | live on **Hyperliquid live feed** — same strategy code; only execution client differs
```

Modular integration (recommended, locked): research stays isolated; Nautilus owns execution fidelity.

---

## 2. Export contract (Phase 1 → Phase 2/3)

Minimum bundle under `data/exports/<id>/`:

| File | Required | Live alpha? |
|------|----------|-------------|
| `meta.json` | yes | config / provenance |
| `params.json` | yes | strategy + parameters |
| `metrics.json` (+ CSV optional) | yes | evidence only |
| `signals.parquet` | optional | **replay / parity only** — not live brain |
| `regime_labels.parquet` | optional | analytics |

**Canonical live inputs:** `strategy_name` + `params` + cost/risk/exit config + optional `model_id` + feature schema version.  
**Not canonical live inputs:** frozen signal arrays (stale by definition on a live feed).

`meta.json` should carry when available:

- `schema_version`, `package_version`, `run_id`
- `symbol`, `timeframe`, `lookback_days`, `init_cash`
- `costs` (fees, slippage_bps, funding_rate_8h)
- `risk` (risk_pct_min/max, conviction)
- `tp_sl_mode` / exit config
- `data_provenance` summary
- `git_hash` / config hash when available

---

## 3. Phase 2 — Nautilus historical sim

**Function:** Re-run exported strategy configuration in an event-driven engine for microstructure-oriented validation (fills, timing model as Nautilus provides).

**Rules:**

- Load export → `StrategyLoadout`
- Implement Nautilus strategy **from params**, not by replaying signal parquet as primary alpha
- Signal parquet may be used for **parity tests** (VectorBT vs Nautilus decisions on same bars)
- No API keys required for pure historical backtest configs

---

## 4. Phase 3 — Paper (dry-run) then Live

### 4.1 Paper mode (required before live)

| Dimension | Requirement |
|-----------|-------------|
| Market data | **Hyperliquid live feed** (same adapter path as live after history warm-up) |
| Strategy / risk / TP-SL / ML | **1:1 identical** to live code path |
| Orders | **Not sent** to venue (or paper execution client only) |
| Logging | Every decision: intent, size, TP/SL, modelled fill, fees, would-be PnL |
| Identity | Hard banner / field `execution_mode=paper` on all logs and DB rows |

**One-sentence lock:**  
Phase 3 paper = live HL market data + exact same Nautilus strategy/risk stack as live, with synthetic fills fully logged as would-be executions; live only flips the execution client.

### 4.2 Live mode

- Same strategy binary path as paper
- Real Hyperliquid execution client
- Start with tiny size / hard kill switch (ops, not research veto gates)

### 4.3 Promotion ladder

```text
VectorBT (1 / 1.5) export
  → Nautilus Phase 2 historical sim
  → Phase 3 paper on live HL feed
  → Phase 3 live (tiny → scale)
```

Never: VectorBT green → live.

### 4.4 Fill model honesty

Paper fills use an explicit model (e.g. mid ± slippage_bps). Log the model on every paper fill. Divergence from live is expected; shadow compare later is optional.

---

## 5. ML (when, not Phase 2 blocker)

- **First:** façade over hypertrader / hyper-pi **BTC 1m impulse metalabel** (LightGBM + calibrator) → conviction in [0,1] or skip
- **Not first:** greenfield training inside hypervector
- **Train later** only for hypervector-specific trade definitions (labels must match TP/SL + costs)
- Reuse roots:
  - `~/dev/hyper-pi/services/ml-service/external-strategies/impulse_1m_btc/`
  - `~/Prototypes/hypertrader/backend/app/backtest/impulse_metalabel/`
  - features: hyper-pi `ml/features_impulse.py`

---

## 6. Infrastructure I2 (locked)

Local solo-project infra — **do not** introduce Postgres/Redis/k8s in Phase 1–2 prep.

| Concern | Location |
|---------|----------|
| Market cache | `data/cache/` Parquet (cache-first HL + backfill) |
| Research trials | `data/runs/hypervector.db` SQLite |
| Export bundles | `data/exports/<id>/` |
| Research / Nautilus logs | `data/logs/research/`, `data/logs/nautilus/` |
| Phase 2 backtest artifacts | `data/nautilus/backtest/` |
| Phase 3 paper ledger + decisions | `data/paper/ledger/`, `data/paper/decisions/` (optional `data/paper/paper.db`) |
| Phase 3 live (later only) | `data/live/` — **never** share ledger files with paper |
| Tracked config | `configs/*.toml` |
| Secrets | env / `.env` (gitignored); paper prefers public feed only |
| Gitignore | `/data/`, `/reference/`, `.env*` |

**Rules:**

1. Call `ensure_data_layout(data_root)` before research or paper writes.
2. Paper and live **must not** append to the same ledger DB/files.
3. Every paper log row includes `execution_mode=paper` and feed timestamp.
4. No secrets in export bundles or git.

Layout doc: `docs/infra-data-layout.md` (created when plan Task 2 runs).

---

## 7. Non-goals (still)

- Live keys / vaults / builder fees in Phase 1–2
- Claiming CEX backfill = HL book
- Separate “paper-only smarter” strategy branch
- Postgres/Redis/cluster for MVP
- Mixing paper and live ledgers

---

## 8. Traceability

| Concern | Spec | Implementation plan |
|---------|------|---------------------|
| Phase 1 research | `2026-07-21-phase1-vectorbt-design.md` | `plans/2026-07-21-phase1-mvp.md` |
| Phase 1.5 + Phase 2 stub + paper lock + **infra** | this file | `plans/2026-07-22-phase15-to-phase2-prep.md` |
