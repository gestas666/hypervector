# Phase 1.5 Finish → Phase 2 Prep → Phase 3 Paper Design Lock

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close Phase 1.5 research realism, freeze the modular handoff contract, and scaffold Phase 2 Nautilus consumption of VectorBT exports — with Phase 3 **paper mode** specified as 1:1 live logic on the Hyperliquid feed (no real orders).

**Architecture:** VectorBT remains Phase 1 research only. Nautilus owns event-driven Phase 2 (historical) and Phase 3 (live feed paper → live). Export bundles carry params/strategy identity/costs/risk/exits; signal arrays are for **replay/parity only**, not live alpha. ML later = façade over hypertrader/hyper-pi impulse metalabel → conviction/skip (not greenfield training first).

**Tech Stack:** Python 3.13, VectorBT 1.1.0, NautilusTrader ≥1.230, Hyperliquid adapter (in Nautilus core), existing `hypervector` package, pytest, uv.

## Global Constraints

- BTC-PERP identity; 1m MVP; majors multi-TF design-ready only.
- Phase 1 start funnel is **done** (history, tracks, rank, export, live HL+backfill).
- Costs: fees + slippage + funding estimate in research; full margin/liq is Phase 2/3.
- Risk: 1%–5% equity risk by conviction; TP/SL modes: `fixed_rr` | `atr` | `trail`.
- No live orders until Phase 3 paper on HL feed is proven.
- Prefer reuse: hyper-pi / hypertrader impulse ML bundles; Nautilus HL adapter; do not invent parallel live stacks.
- Do not claim Binance/Bybit bars are HL microstructure.
- **Infra I2 locked (do not replace with Postgres/Redis/k8s in this plan):** local Parquet + SQLite + filesystem under gitignored `data/`; tracked `configs/`.

## Status at plan write (2026-07-22)

### Done

| Area | Location |
|------|----------|
| Engines installed + install tests | `tests/test_*_install.py` |
| Live history HL→Binance→Bybit + provenance + cache | `src/hypervector/data/*` |
| Regime / up / down tracks + classic + crown + trend_ride | `src/hypervector/strategies/*` |
| SQLite runs + report + export bundles | `runs/`, `report.py`, `export/phase2.py` |
| Costs + TP/SL modes + conviction risk 1–5% | `sweep/costs.py`, `exits.py`, `sizing.py`, `metrics.py` |
| CLI | `python -m hypervector history\|regime\|sweep-up\|sweep-down\|report\|export` |
| Design | `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` |
| Prior plan | `docs/superpowers/plans/2026-07-21-phase1-mvp.md` |

### Not done (this plan)

- Commit hygiene for uncommitted tree
- Documented export contract + Phase 2/3 execution modes
- **Infra layout formalize** (ensure dirs, README, paper/live ledger paths, logging)
- Nautilus Phase 2 skeleton that **loads** an export bundle
- Phase 3 paper/live mode flags (spec + stub, not full live)
- ML impulse façade (optional late task; after 1.5 verified)

---

## Infrastructure I2 (locked — do not forget)

From Phase 1 design §7; extended for Phase 2/3 paper. **Local only** for this plan.

| Concern | Path / choice | Notes |
|---------|---------------|--------|
| Market / book cache | `data/cache/**/*.parquet` | Cache-first; HL+backfill; gitignored |
| Trial / run index | `data/runs/hypervector.db` (SQLite) | Research trials + ranks |
| Phase 1 exports | `data/exports/<id>/` | Versioned bundles for Phase 2 load |
| Research logs | `data/logs/research/` | CLI / sweep logs if written |
| Phase 2 backtest catalogs | `data/nautilus/backtest/` | Catalogs / reports (create on use) |
| Phase 3 paper ledger | `data/paper/ledger/` + SQLite optional `data/paper/paper.db` | Would-be orders/fills only |
| Phase 3 paper decision log | `data/paper/decisions/` (jsonl or parquet) | Intent + fill model + feed ts |
| Phase 3 live ledger (later) | `data/live/` — **not** until live; never mix with paper | Separate root from paper |
| Tracked config | `configs/*.toml` | symbol, tf, costs, risk, exits, fee_model |
| Secrets | **none** in repo; env / local `.env` (gitignored) for live keys only | Paper should work read-only feed if possible |
| Gitignore | `/data/`, `/reference/`, `.env` | Never commit market data or keys |
| Not in I2 | Postgres, Redis, k8s, cluster workers | Explicit non-goal |

**Ensure layout helper (implement):** `hypervector.infra.ensure_data_layout(root: Path)` creates:

```text
data/
  cache/
  runs/
  exports/
  logs/research/
  logs/nautilus/
  nautilus/backtest/
  paper/ledger/
  paper/decisions/
  live/   # exists empty; write only when execution_mode=live
```

CLI should call ensure on `history` / `sweep-*` / future `paper` commands.

---

## Architecture lock (do not reverse)

```text
Phase 1  VectorBT research → export bundle (params, meta, metrics, optional signals)
Phase 1.5 costs + TP/SL + risk sizing (research realism)
Phase 2  Nautilus historical event sim — same strategy identity + params as export
Phase 3  paper: live HL feed + same strategy/risk as live + synthetic fills logged
Phase 3  live: flip execution client only; strategy unchanged
ML       metalabel → conviction/skip (reuse HT/hyper-pi); train only for new trade defs
```

**Export contract (canonical):**

| Artifact | Live alpha? | Role |
|----------|-------------|------|
| `meta.json` | yes (config) | run id, symbol, tf, lookback, costs, risk, exit mode, versions, provenance |
| `params.json` | yes | strategy name, role, parameters |
| `metrics.json` / CSV | no | ranking evidence |
| `signals.parquet` | **replay/parity only** | not the live brain |
| model weights (later) | with feature schema version | metalabel sizing; same feature builder as runtime |

**Phase 3 paper (locked):**

- Data: **Hyperliquid live feed** (same path as live after warm-up)
- Logic: **1:1** with live strategy/risk/ML path
- Diff: no real orders; log **would-be** order + fill model + ledger
- Promote: paper on live feed → tiny live; never VectorBT-only → live

---

## File map (planned)

| Path | Responsibility |
|------|----------------|
| `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` | Durable Phase 2/3 + paper mode + export contract + **infra** |
| `src/hypervector/infra.py` | `ensure_data_layout`, path constants (I2) |
| `data/README.md` | Documents layout (tracked); contents gitignored via `/data/*` exception if needed — or `docs/infra-data-layout.md` if README under data is awkward |
| `docs/infra-data-layout.md` | Tracked layout doc (prefer over gitignored data/README) |
| `src/hypervector/export/schema.py` | Typed export meta validation |
| `src/hypervector/nautilus/` (new) | Phase 2 load-export + stub strategy config |
| `tests/test_export_schema.py` | Schema + round-trip |
| `tests/test_infra.py` | Layout dirs created; gitignore still excludes data |
| `tests/test_nautilus_phase2_stub.py` | Offline: load bundle, construct Nautilus config without network |
| `HANDOFF.md` | Point next session here |

---

### Task 1: Durable Phase 2/3 + paper-mode spec

**Files:**
- Create: `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`

- [x] **Step 1:** Write spec covering: modular integration, export contract, promotion ladder, Phase 3 paper 1:1 on HL feed, ML reuse notes, non-goals.
- [x] **Step 2:** Cross-link from design Phase 1 §10 and this plan (HANDOFF + this plan header).
- [ ] **Step 3:** Commit with product tree when Task 6 runs: `docs: phase 2/3 handoff and paper-mode contract`

---

### Task 2: Infra I2 layout + path helpers

**Files:**
- Create: `src/hypervector/infra.py`
- Create: `docs/infra-data-layout.md`
- Modify: `src/hypervector/cli.py` (and pipeline/export entrypoints) to call `ensure_data_layout`
- Modify: `.gitignore` only if needed (keep `/data/`; never commit ledgers)
- Test: `tests/test_infra.py`

**Produces:**
- `DATA_SUBDIRS` constant list (cache, runs, exports, logs/…, paper/…, nautilus/…, live/)
- `ensure_data_layout(root: Path) -> Path` idempotent mkdir
- `paths_for(root) -> SimpleNamespace` of resolved paths
- Document paper vs live **separation** (no shared ledger file)

- [x] **Step 1:** Write failing test: after ensure, required dirs exist under tmp root
- [x] **Step 2:** Implement `infra.py` + docs
- [x] **Step 3:** Wire CLI startup / history / sweep / export to ensure layout
- [x] **Step 4:** `uv run pytest tests/test_infra.py -v`

---

### Task 3: Export schema hardening

**Files:**
- Create: `src/hypervector/export/schema.py`
- Modify: `src/hypervector/export/phase2.py` to write schema_version
- Test: `tests/test_export_schema.py`

**Produces:**
- `EXPORT_SCHEMA_VERSION = "1"`
- `validate_export_dir(path) -> dict` requiring meta/params/metrics
- meta must include: strategy, symbol, timeframe, init_cash, costs, risk, tp_sl_mode when present

- [x] **Step 1:** Failing tests for missing files / invalid meta
- [x] **Step 2:** Implement schema + validate on export write
- [x] **Step 3:** `uv run pytest tests/test_export_schema.py tests/test_export.py -v`

---

### Task 4: Phase 1.5 verification pass (evidence)

- [x] **Step 1:** `uv run pytest tests/ -q` (expect 0 failures excluding network-deselected)
- [x] **Step 2:** One live-or-cache sweep with costs:
  ```bash
  uv run python -m hypervector --data-root data history --lookback 30
  uv run python -m hypervector --data-root data sweep-down --lookback 30 \
    --strategy crown_stack_short --cash 10000 --tp-sl-mode atr \
    --risk-min 0.01 --risk-max 0.05 --conviction 0.5 --export
  ```
- [x] **Step 3:** Confirm export validates via schema; note results in HANDOFF or scratch

---

### Task 5: Nautilus Phase 2 stub — load export offline

**Files:**
- Create: `src/hypervector/nautilus/__init__.py`
- Create: `src/hypervector/nautilus/load_export.py` — parse bundle → `StrategyLoadout` dataclass
- Create: `src/hypervector/nautilus/config_stub.py` — build offline Nautilus TradingNode/BacktestEngine config **without** connecting (construct objects / dicts only)
- Test: `tests/test_nautilus_phase2_stub.py`

**Produces:**
- `StrategyLoadout(strategy_name, role, params, meta, costs, risk, exit_mode)`
- `load_strategy_loadout(export_dir: Path) -> StrategyLoadout`
- Offline test uses a minimal temp export dir (no network)
- Stub paths point at `data/nautilus/backtest/` under data root

- [x] **Step 1:** Failing test: load fixture export
- [x] **Step 2:** Implement loader + stub
- [x] **Step 3:** pytest offline; no live HL keys

---

### Task 6: CLI `export-validate` + optional `phase2-check` + `infra-init`

- [x] **Step 1:** `hypervector infra-init --data-root data` → ensure_data_layout
- [x] **Step 2:** `hypervector export-validate --path data/exports/<id>`
- [x] **Step 3:** `hypervector phase2-check --path ...` prints loadout summary + “paper/live not implemented”
- [x] **Step 4:** Tests for CLI exit codes

---

### Task 7: Commit / handoff hygiene

- [x] **Step 1:** Review `git status`; stage product + tests + docs (not `data/`, not `reference/`)
- [x] **Step 2:** Logical commits (or one coherent commit if user prefers)
- [x] **Step 3:** Update `HANDOFF.md` status → ready for Phase 2 strategy actor implementation

---

### Task 8 (optional next session+): ML façade spike

Only after Tasks 1–7 green.

- [ ] Read-only adapter stub: `src/hypervector/ml/impulse_btc.py` pointing at hyper-pi bundle paths **or** env `HYPERVECTOR_IMPULSE_BTC_ROOT`
- [ ] `predict_conviction(features) -> float` using loaded LGBM if present; else skip with clear error
- [ ] No training code in hypervector in this spike
- [ ] Unit test with mock booster / missing-bundle graceful fail

**Reuse roots (do not vendor huge trees):**
- `/Users/gestas/dev/hyper-pi/services/ml-service/external-strategies/impulse_1m_btc/`
- `/Users/gestas/Prototypes/hypertrader/backend/app/backtest/impulse_metalabel/`
- Features: hyper-pi `ml/features_impulse.py`

---

## Non-goals (this plan)

- Live order placement
- Full Nautilus strategy actor with Supertrend/crown bar logic (that is **next plan** after stub)
- Training new metalabelers
- Book/queue fidelity inside VectorBT
- Optuna / majors multi-TF runtime

---

## Verification plan

1. Spec exists and states paper = live HL feed + same logic + synthetic fills.
2. **Infra:** `ensure_data_layout` creates I2 + paper/live/nautilus dirs; `/data/` remains gitignored; `docs/infra-data-layout.md` present.
3. `pytest tests/ -q` → 0 failures (network tests deselected by default).
4. Export schema validates a real or fixture export dir.
5. Nautilus stub loads export offline without network; paths under data root.
6. HANDOFF points to this plan and lists next session entry command.

---

## Next session entry (execute)

```bash
cd /Users/gestas/Prototypes/hypervector
uv sync --all-extras
# read first:
#   HANDOFF.md
#   docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md
#   docs/superpowers/specs/2026-07-22-phase2-3-handoff.md
#   docs/infra-data-layout.md  (after Task 2)
uv run pytest tests/ -q
# then execute Tasks 2→7 in order (Task 8 ML optional)
# Task 1 spec already written
```

## Deviations

- Task 1 Step 3 commit message rolled into Task 7 product commit (single coherent tree).
- Real-world QA also exercised `fixed_rr` / `trail` exit modes and live network fetcher tests (not only atr smoke).
