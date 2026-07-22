# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  

**Status:** Phase 1 / 1.5 / prep Tasks **1–7 DONE**. Ready for Phase 2 strategy actor.  
**Phase 1 funnel DONE** · **Phase 1.5 costs/TP-SL/risk IN CODE** · **Infra I2 DONE**  
**Export schema v1 DONE** · **Nautilus load-export stub DONE** · **CLI export-validate / phase2-check DONE**  

**Plan:** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Spec:** `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`  
**Infra doc:** `docs/infra-data-layout.md`

**Next execute:** implement Nautilus **strategy actor** that re-runs strategy from `StrategyLoadout` params (not signal replay). Task 8 ML façade optional.

---

## Goal (pipeline)

| Phase | Role | Framework |
|-------|------|-----------|
| **1** | Research / grids / rank / export | **VectorBT** |
| **1.5** | Fees, slippage, funding est., TP/SL modes, 1–5% conviction risk | VectorBT |
| **2** | Event-driven historical validation | **NautilusTrader** |
| **3 paper** | Live **HL feed**, same logic as live, **synthetic fills logged** | Nautilus |
| **3 live** | Same as paper; real execution client only | Nautilus + HL |

**Modular handoff (locked):** VectorBT exports **params + meta + metrics** (+ optional signals for **replay only**). Nautilus **re-runs strategy logic** from params — not frozen signals as live alpha.

**Phase 3 paper (locked):** 1:1 with live strategy/risk/ML path; market data from **Hyperliquid live feed**; no real orders; log would-be executions. Promote: Phase 2 sim → paper on HL feed → tiny live. Never VectorBT → live.

---

## Plan progress

| Task | Status |
|------|--------|
| 1 Spec Phase 2/3 + paper | **Done** |
| 2 Infra I2 layout + CLI | **Done** |
| 3 Export schema harden | **Done** (`export/schema.py`, `EXPORT_SCHEMA_VERSION=1`) |
| 4 Phase 1.5 verification sweep | **Done** (real 30d BTC 1m sweeps + strict validate) |
| 5 Nautilus Phase 2 load-export stub | **Done** (`nautilus/load_export.py`, `config_stub.py`) |
| 6 CLI export-validate / phase2-check | **Done** |
| 7 Commit product (not data/reference) | **Done** (this session) |
| 8 ML impulse façade (optional) | Pending |

---

## Verification evidence (2026-07-22 session)

```bash
uv run pytest tests/ -q
# 100 passed, 4 deselected (network)

uv run pytest tests/test_fetchers.py -m network -q
# 4 passed

# Real path (cached HL+Binance 30d, 43200 bars):
uv run python -m hypervector --data-root data history --lookback 30
uv run python -m hypervector --data-root data sweep-down --lookback 30 \
  --strategy crown_stack_short --cash 10000 --tp-sl-mode atr \
  --risk-min 0.01 --risk-max 0.05 --conviction 0.5 --export
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
```

Also exercised **fixed_rr** (uptrend crown), **trail** (downtrend trend_ride), negative paths (missing dir, pre-schema legacy exports correctly fail).

Example new bundle: `data/exports/downtrend_crown_stack_short_6e7347e6` with `schema_version=1`, costs/risk/tp_sl_mode.

---

## Key surfaces

| Path | Role |
|------|------|
| `src/hypervector/export/schema.py` | `validate_export_dir`, `EXPORT_SCHEMA_VERSION` |
| `src/hypervector/export/phase2.py` | Write bundle + optional validate |
| `src/hypervector/nautilus/load_export.py` | `StrategyLoadout`, `load_strategy_loadout` |
| `src/hypervector/nautilus/config_stub.py` | Offline Phase 2 stub + nautilus probe |
| `src/hypervector/infra.py` | I2 layout |
| CLI | `history\|regime\|sweep-up\|sweep-down\|report\|export\|export-validate\|phase2-check\|infra-init` |

---

## Done this arc

### Environment
- Python 3.13 / uv; `vectorbt[full,rust]==1.1.0`; `nautilus_trader>=1.230`; `backtrader[plotting]`
- Install tests: `tests/test_install.py`, `test_nautilus_install.py`, `test_backtrader_install.py`

### Phase 1 research (`src/hypervector/`)
- Live history HL → Binance → Bybit + provenance + cache
- Regime / up / down tracks; strategies: classic, crown_stack (1m), trend_ride
- SQLite runs, report, exports under `data/exports/`

### Phase 1.5
- `sweep/costs.py`, `exits.py` (`fixed_rr|atr|trail`), `sizing.py` (1–5% risk by conviction)
- CLI: `--cash`, `--tp-sl-mode`, `--risk-min/max`, `--conviction`, `--fee-model`

### Phase 2 prep
- Export schema v1; strict Phase 1.5 fields for loadout readiness
- Nautilus offline loadout + HYPERLIQUID config probe (no engine start)
- paper/live explicitly **not implemented**

### Infra
- `infra.ensure_data_layout` wired into pipeline + CLI IO commands
- Tests: `tests/test_infra.py`

---

## Next session — start here

```bash
cd /Users/gestas/Prototypes/hypervector
uv sync --all-extras
uv run pytest tests/ -q
# Implement Nautilus strategy actor from StrategyLoadout (next plan)
# Optional: Task 8 ML impulse façade
```

### Quick research commands
```bash
uv run python -m hypervector infra-init
uv run python -m hypervector --data-root data history --lookback 30
uv run python -m hypervector --data-root data sweep-down --lookback 30 \
  --strategy crown_stack_short --cash 10000 --tp-sl-mode atr \
  --risk-min 0.01 --risk-max 0.05 --conviction 0.5 --export
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
```

---

## Non-goals (still)

- Live trading / keys / vaults  
- Full Nautilus strategy actor (next)  
- Greenfield ML training  
- CEX bars claimed as HL book  
- Paper/live shared ledgers  

---

## Agent notes

- Prefer this HANDOFF + plan over stale agentmemory for phase status.
- Skills used: engineering-software, write-clean-code, verification-before-completion.
- Legacy pre-schema exports under `data/exports/*` fail validate until re-exported with current CLI.
