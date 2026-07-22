# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  

**Status:** Phase 1 / 1.5 / Phase 2 **prep** complete and verified.  
**Next plan:** `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`  
**Spec (locked):** `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`  
**Prior plan (done):** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Infra doc:** `docs/infra-data-layout.md`

**Next execute (NEXT SESSION — not started):** plan Tasks **1→6** first  
(signal adapter → actor → runner → `phase2-run`).  
Task **7 ML façade** optional. Task **8** paper ledger scaffold. Task **9** verify + handoff.

**Execution mode (user lock 2026-07-22):**
- **Subagent-driven development** (fresh subagent per task + review between tasks)
- **Required skill:** `write-clean-code` (load at session start; also `engineering-software` if process/docs)
- **Do not** inline-implement the whole plan in one agent turn unless user overrides
- Plan file: `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`

---

## What’s working (built + verified)

| Area | Status |
|------|--------|
| Phase 1 VectorBT research funnel | **Working** — history, regime, sweeps, rank, export |
| Phase 1.5 costs / TP-SL / risk | **Working** — fees, slippage, funding est., `fixed_rr\|atr\|trail`, 1–5% conviction risk |
| Infra I2 layout | **Working** — `infra-init`, paper/live separation |
| Export schema v1 | **Working** — strict needs costs, risk, tp_sl_mode, **exits** |
| Nautilus load-export **stub** | **Working** — `StrategyLoadout`, offline probe (no engine run) |
| CLI | **Working** — see commands below |
| Unit tests | **100 passed** offline; network fetchers optional green |
| Real sweeps | **Working** — 30d BTC 1m atr / fixed_rr / trail + strict validate |

## What’s not built yet

| Item | Notes |
|------|--------|
| **Nautilus strategy actor** | Next plan Tasks 1–6 — re-run logic from loadout params |
| **`phase2-run` historical engine** | BacktestEngine + artifacts under `data/nautilus/backtest/` |
| **ML impulse façade** | Task 7 optional — no `src/hypervector/ml/` yet; conviction is CLI constant |
| **Phase 3 paper live-feed loop** | Task 8 scaffold only; no HL subscribe / synthetic fill loop |
| **Phase 3 live** | Out of scope until paper proven |

**Locked rules still apply:** signals parquet = parity only; never VectorBT → live; paper ledger ≠ live ledger.

---

## Goal (pipeline)

| Phase | Role | Framework | State |
|-------|------|-----------|--------|
| **1** | Research / grids / rank / export | VectorBT | **Done** |
| **1.5** | Fees, slippage, funding, TP/SL, risk | VectorBT | **Done** |
| **2 prep** | Export contract + loadout stub | hypervector | **Done** |
| **2 actor** | Event-driven historical sim from params | NautilusTrader | **Next plan** |
| **3 paper** | HL live feed + same logic + synthetic fills | Nautilus | Scaffold then full |
| **3 live** | Same as paper; real exec client | Nautilus + HL | Later |

---

## Prior plan progress (2026-07-22-phase15-to-phase2-prep)

| Task | Status |
|------|--------|
| 1 Spec Phase 2/3 + paper | **Done** |
| 2 Infra I2 layout + CLI | **Done** |
| 3 Export schema harden | **Done** |
| 4 Phase 1.5 verification | **Done** |
| 5 Nautilus load-export stub | **Done** |
| 6 CLI export-validate / phase2-check | **Done** |
| 7 Commit product | **Done** (`e63e923`, `e73393e`) |
| 8 ML impulse façade | **Moved** → new plan Task 7 |

---

## New plan progress (2026-07-22-phase2-actor-and-ml)

| Task | Status |
|------|--------|
| 1 Shared bar-window signal adapter | **Pending** |
| 2 Loadout sizing + exit helpers | **Pending** |
| 3 OHLCV → Nautilus bars | **Pending** |
| 4 HypervectorStrategy actor | **Pending** |
| 5 Historical runner + artifacts | **Pending** |
| 6 CLI `phase2-run` | **Pending** |
| 7 ML impulse façade (optional) | **Pending** |
| 8 Paper ledger scaffold | **Pending** |
| 9 Full verify + handoff | **Pending** |

---

## Key surfaces (current)

| Path | Role |
|------|------|
| `src/hypervector/export/schema.py` | `validate_export_dir`, schema v1 + `meta.exits` |
| `src/hypervector/export/phase2.py` | Write bundle |
| `src/hypervector/nautilus/load_export.py` | `StrategyLoadout` |
| `src/hypervector/nautilus/config_stub.py` | Offline phase2-check |
| `src/hypervector/infra.py` | I2 layout |
| `src/hypervector/strategies/*` | Registry + crown / trend_ride / classic (shared by Phase 2 actor) |
| CLI | `history\|regime\|sweep-up\|sweep-down\|report\|export\|export-validate\|phase2-check\|infra-init` |

---

## Next session — start here

```bash
cd /Users/gestas/Prototypes/hypervector
uv sync --all-extras
# 1) Load skills: write-clean-code (+ engineering-software optional)
# 2) Read HANDOFF + plan 2026-07-22-phase2-actor-and-ml.md + phase2-3-handoff spec
# 3) Use superpowers:subagent-driven-development (NOT full inline)
# 4) Baseline: uv run pytest tests/ -q
# 5) Start at Task 1 (signal adapter); one subagent per task; review gate between tasks
```

### Research / validate (already working)

```bash
uv run python -m hypervector infra-init
uv run python -m hypervector --data-root data history --lookback 30
uv run python -m hypervector --data-root data sweep-down --lookback 30 \
  --strategy crown_stack_short --cash 10000 --tp-sl-mode atr \
  --risk-min 0.01 --risk-max 0.05 --conviction 0.5 --export
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
```

### After Task 6 lands

```bash
uv run python -m hypervector --data-root data phase2-run --path data/exports/<id> --lookback 30
```

---

## ML notes (for Task 7)

- **Not in tree yet** — no `src/hypervector/ml/`
- Façade only: LightGBM metalabel → conviction ∈ [0,1] or skip  
- Reuse (env `HYPERVECTOR_IMPULSE_BTC_ROOT` or defaults):
  - `~/dev/hyper-pi/services/ml-service/external-strategies/impulse_1m_btc/`
  - `~/Prototypes/hypertrader/backend/app/backtest/impulse_metalabel/`
  - features: hyper-pi `ml/features_impulse.py`
- No greenfield training in hypervector first

---

## Non-goals (still)

- Live trading / keys / vaults  
- VectorBT → live skip of Phase 2/paper  
- CEX bars claimed as HL book  
- Shared paper/live ledgers  
- Postgres / Redis / k8s  

---

## Agent notes

- Prefer this HANDOFF + **new** plan over stale agentmemory for phase status.  
- Skills: engineering-software, write-clean-code, executing-plans / subagent-driven-development.  
- Legacy pre-schema exports fail `export-validate` until re-exported with current CLI.  
- `export --track` only re-exports trials that have `research_meta` (modern sweeps).  
