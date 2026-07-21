# Phase 1 Design: VectorBT Research Funnel (hypervector)

**Date:** 2026-07-21  
**Status:** Draft for user review (design approved in session; this is the durable spec)  
**Process:** engineering-software (Hyde) + brainstorming  
**Scope:** Phase 1 only — research / parameter search / export. No live trading.

---

## 1. Intent

hypervector Phase 1 is a **fast multi-strategy research funnel** for **Hyperliquid perpetual futures**:

1. Ingest **maximum available Hyperliquid** history; **backfill/extend with Binance and/or Bybit** when HL is short or gapped.  
2. Run vectorized exploration (primarily **VectorBT**) over pluggable strategies.  
3. **Phase 1 start deliverables (three tracks):**
   - **Best uptrend strategy** (search-found, not assumed)
   - **Best downtrend strategy** (search-found)
   - **Regime detection** (tunable labels; not a forced trade gate)
4. Rank trade candidates by **net PnL / total return**; report full secondary metrics; keep **multiples**.  
5. Export versioned artifacts for **Phase 2 NautilusTrader** microstructure validation.

**Project size (Hyde):** solo / small → iterative MVP, light tag-based traceability, not full IEEE document set.

---

## 2. Non-goals (Phase 1)

- Live orders, API keys, vaults, builder fees  
- Paternalistic **risk gates** (min Sharpe walls, max-DD kill switches, forced regime vetoes) unless Albert explicitly enables a mode  
- Claiming Binance/Bybit backfill **is** Hyperliquid microstructure  
- Full Nautilus event loop inside the Phase 1 runner  
- Postgres/Redis/cluster workers  
- Entire pine library on day one  

---

## 3. Requirements (testable)

Format: black-box *shall* / *must*. Tags for light RTM.

| Tag | Requirement |
|-----|-------------|
| SRS_HV1_UNIVERSE | Phase 1 **shall** treat **Hyperliquid perps** as the universe of record (execution identity). |
| SRS_HV1_SYMBOL_MVP | MVP **shall** run on **BTC** (BTC-PERP) only. |
| SRS_HV1_SYMBOL_DESIGN | Design **shall** support a **majors basket** via config without pipeline rewrite. |
| SRS_HV1_TF_MVP | MVP primary bar interval **shall** be **1m**. |
| SRS_HV1_TF_DESIGN | Design **shall** support multi-TF order **1m → 5m → 15m**, optional later **30m / 1h**. |
| SRS_HV1_HIST_FLOOR | System **shall** run with **≥ 30 calendar days** of usable 1m bars (after HL + optional backfill). |
| SRS_HV1_HIST_DEFAULT | Default research lookback **shall** be **90 days** when available. |
| SRS_HV1_HIST_PROMO | Config **shall** support **180 days** robustness windows when available (not a candidate kill-gate). |
| SRS_HV1_DATA_HL_FIRST | History pipeline **shall** pull **maximum available Hyperliquid** candle (and book-derived) history first. |
| SRS_HV1_DATA_BACKFILL | When HL is insufficient, system **shall** support backfill/extend from **Binance and/or Bybit** with per-bar provenance. |
| SRS_HV1_DATA_PROVENANCE | Every run **shall** record data composition (HL vs backfill fractions, gaps, fee model). |
| SRS_HV1_RANK_PRIMARY | Trade-candidate ranking **shall** order primarily by **net PnL / total return**. |
| SRS_HV1_METRICS | Runs **shall** report at least: net PnL, total return %, Sharpe, trade count, W/L, win %, drawdown. |
| SRS_HV1_NO_GATES | System **must not** apply strategy/risk rejection gates unless explicitly configured by Albert. Only **technical failure** aborts a trial. |
| SRS_HV1_STRAT_MULTI | System **shall** support multiple strategies, concurrent comparison, and multi-candidate export. |
| SRS_HV1_START_THREE | Phase 1 start **shall** deliver tracks: **uptrend search**, **downtrend search**, **regime detection**. |
| SRS_HV1_UPTREND | System **shall** search/tune uptrend-oriented candidates and identify best/multiples by primary rank. |
| SRS_HV1_DOWNTREND | System **shall** search/tune downtrend-oriented candidates and identify best/multiples by primary rank. |
| SRS_HV1_REGIME | System **shall** emit regime label series (default **up / down / range**) with tunable params and detection metrics separate from trade PnL. |
| SRS_HV1_REGIME_NO_GATE | Regime labels **must not** hard-block trials or force trade vetoes unless composition mode is explicitly enabled. |
| SRS_HV1_STRAT_PINE | System **shall** support Pine-origin strategies with parameter grids (ports; no TradingView runtime required). |
| SRS_HV1_STRAT_BOOK | System **shall** support order-book-feature strategies on bars; full queue/latency fidelity is Phase 2. |
| SRS_HV1_ADAPTERS | Prefer reuse of hyper-pi, hypertrader, apex, and related HL tooling; **shall not** invent adapters that already exist. |
| SRS_HV1_CACHE | Market/book history **shall** be cached as **Parquet** under gitignored `data/cache/`; fetch is cache-first. |
| SRS_HV1_RUNS_DB | Trial/run metrics and ranks **shall** live in local **SQLite** under `data/runs/`. |
| SRS_HV1_EXPORT_FS | Phase-2 bundles **shall** be versioned directories under `data/exports/`. |

### Lookback guidance (1m BTC)

| Window | ~Bars | Role |
|--------|-------|------|
| 30d | ~43k | Floor / smoke |
| 90d | ~130k | Default research |
| 180d | ~260k | Optional robustness |

---

## 4. Architecture

**Approach A (chosen):** native `hypervector` research package + thin façades over existing HL data tooling.

```
Config (symbol, tf, lookback, fees, tracks)
  → History: HL-max → Binance/Bybit backfill → Parquet cache (+ provenance)
  → [optional] Book features join
  → Tracks:
        regime.*     → labels + detection metrics
        uptrend.*    → VectorBT param search → rank by net PnL
        downtrend.*  → VectorBT param search → rank by net PnL
  → SQLite trial index + filesystem series
  → Optional segmented analytics (regime ∩ equity) — views, not gates
  → Multi-export → Phase 2 Nautilus
```

### Components

| Component | Responsibility |
|-----------|----------------|
| `data.hl` | Max HL candles/book via reused adapters |
| `data.backfill` | Binance / Bybit with symbol maps + provenance |
| `data.cache` | Parquet cache, cache-first IO |
| `data.provenance` | Run- and bar-level source metadata |
| `regime.*` | Detectors, labels, detection metrics, optional compose helpers |
| `strategies.registry` | Name → builder + param schema + **role** (`uptrend` \| `downtrend` \| `regime` \| `other`) |
| `strategies.pine_*` / `book_*` / `classic_*` | Implementations |
| `sweep.runner` / `search` | Grid / random / optional Optuna; per-track or batch |
| `runs.db` | SQLite trial/run index |
| `report` | Per-track boards; primary net PnL for trade roles |
| `export.phase2` | Multi-candidate + regime artifacts |
| `cli` | `history`, `regime`, `sweep-up`, `sweep-down`, `report`, `export` |

Rust `hypervector-core` remains optional later acceleration — not required for Phase 1 start.

### Package layout (target)

```
src/hypervector/
  data/{hl,backfill,cache,provenance,book_features}.py
  regime/{detectors,metrics,compose}.py
  strategies/{registry,base,pine/,book/,classic/}
  sweep/{runner,search,metrics}.py
  report.py
  export/phase2.py
  cli.py
configs/                          # tracked
data/{cache,runs,exports,logs}/   # gitignored
docs/superpowers/specs/…          # this document
reference/pine-scripts/           # source for ports (gitignored tree)
```

---

## 5. Strategy surface

### 5.1 Start tracks

| Track | “Best” means | Output |
|-------|--------------|--------|
| Uptrend | Top net PnL among long/up-oriented candidates + params | Ranked table + exportable multiples |
| Downtrend | Top net PnL among short/down-oriented candidates + params | Ranked table + exportable multiples |
| Regime | Tunable `up \| down \| range` labels; detection quality metrics | Label series + param report + export |

### 5.2 Candidate sources

| Family | Role |
|--------|------|
| Pine-parameter ports | Primary pool for up/down (`reference/pine-scripts/`, hypertrader) |
| Classic trend indicators | Supertrend, MA/EMA structure, Donchian-style baselines in same search |
| Order-book features | Optional hybrid inputs when book history available |
| ML feature matrices | Later Phase-1 slice; registry hooks only at start |

Strategies are **role-tagged** so ranking is per-track (global view still available).

### 5.3 Regime rules

- Default taxonomy: **3-state** `up | down | range`.  
- Searchable detectors (e.g. ADX+DI, EMA structure, vol/return thresholds, optional book skew).  
- Metrics: duration stats, flip rate, % time in state, optional forward-return association — **reported, not gated**.  
- Optional composition (off by default): segment reports; user-enabled stack (long only in `up`, short only in `down`).

### 5.4 Search

- Coarse **grid or random**, then optional **Optuna/Bayesian refine** per track.  
- Agent/manual loops supported via CLI + full artifact dumps.  
- Technical failures mark trial `error`; other trials continue. **No risk stonewalls.**

---

## 6. Data

| Rule | Detail |
|------|--------|
| Identity | Instrument of record = HL BTC-PERP (majors later). Backfill is price-path assistance only. |
| Order | HL maximum first; Binance then Bybit for gaps/extension (default priority). |
| Provenance | Per-bar `source` (+ mapped symbol, original timestamp as needed). |
| Cache | Parquet under `data/cache/`; book features under `data/cache/book/`. |
| Adapters | hyper-pi, hypertrader, apex, `reference/orderbook/` first. |
| Strict HL-only | Optional config flag; default **off** (backfill allowed). |

---

## 7. Infrastructure (I2 locked)

| Concern | Choice |
|---------|--------|
| Market/book cache | **Parquet** files |
| Trial/run index | **SQLite** (`data/runs/hypervector.db` or equivalent) |
| Exports | Versioned dirs under `data/exports/<id>/` |
| Config | YAML/TOML under `configs/` (tracked) |
| Secrets | None required for public candles Phase 1 |
| Parallelism | Local multi-process for trials |
| Network tests | Offline fixtures only in CI |
| Not in Phase 1 | Postgres, Redis, k8s, live order DB |

### Export bundle (minimum)

- `meta.json` — run id, git hash, config hash, symbol, tf, lookback, fee model, data provenance summary, package versions  
- `params.json` — strategy name, role, parameters  
- `metrics.csv` / row in SQLite — full metric set  
- `signals.parquet` (optional) — positions/signals for Phase 2  
- `regime_labels.parquet` when applicable  

---

## 8. Use cases

1. **UC_LoadHistory** — Unified HL-max + backfill + provenance.  
2. **UC_LoadBookFeatures** — Optional book metrics on bars.  
3. **UC_RunRegime** — Sweep detectors; labels + detection metrics.  
4. **UC_SearchUptrend** — Sweep uptrend role; rank by net PnL.  
5. **UC_SearchDowntrend** — Sweep downtrend role; rank by net PnL.  
6. **UC_ReportTracks** — Per-track boards; optional segmented views.  
7. **UC_ExportMany** — Best and/or multiples per track + regime artifact.  
8. **UC_ExtendUniverseTF** — Majors + multi-TF via config (design-ready).

---

## 9. Verification vs validation (Hyde)

| Kind | How |
|------|-----|
| **Verification** (built right) | Offline unit/integration tests: cache merge + provenance; per-track smoke (≥1 up, ≥1 down, ≥1 regime); metrics columns present; rank order by net PnL; export schema; install tests already present for VectorBT/Nautilus/Backtrader |
| **Validation** (right product) | Albert promotes candidates to Phase 2; human judgment on metrics dumps — **not** automated risk veto |

---

## 10. Implementation sequence (after this spec is approved + writing-plans)

1. This spec committed and user-reviewed.  
2. Implementation plan via **writing-plans** only.  
3. History pipeline: HL-max + Binance/Bybit backfill + Parquet cache + provenance.  
4. SQLite run schema + report stubs.  
5. Regime detector v1 + param sweep + label export.  
6. Uptrend candidate set + search → best/multiples.  
7. Downtrend candidate set + search → best/multiples.  
8. Multi-export + optional segmented analytics.  
9. Expand pines / book hybrids / majors / multi-TF / Optuna.

---

## 11. Defaults (unless overridden)

| Topic | Default |
|-------|---------|
| Symbol | BTC |
| TF | 1m |
| Lookback | 90d (floor 30d) |
| Backfill priority | Binance → Bybit |
| Regime states | up / down / range |
| Rank | net PnL / total return |
| Gates | none (technical fail only) |
| Infra | I2 Parquet + SQLite + FS exports |
| First classic baselines | Supertrend / MA structure style until specific pines named |

---

## 12. Traceability (light)

| Requirements | Design | Tests (later) |
|--------------|--------|---------------|
| SRS_HV1_* | §§4–8 components & flows | STC_HV1_* offline tests |

---

## 13. Open (non-blocking)

- Named first pine ports from `reference/pine-scripts/`  
- Exact HL fee defaults in config  
- Optuna as hard dependency vs optional extra  

---

## 14. Approval

Session design decisions are reflected above.  

**Please review this file** and request changes if needed. After your OK, the next step is **writing-plans** (implementation plan only — no product code until that plan is executed under its own process).
