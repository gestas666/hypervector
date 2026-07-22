# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase2-actor-and-ml` (not pushed)

**Status:** Phase 1 / 1.5 / Phase 2 **actor + runner + ML façade + paper scaffold** complete and verified.  
**Completed plan:** `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`  
**Spec (locked):** `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`  
**Prior plan (done):** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Infra doc:** `docs/infra-data-layout.md`

**Next session:** Phase 3 **paper live-feed loop** (HL subscribe + same strategy path + synthetic fills logged via paper ledger). Not started. Do not go live.

---

## What’s working (built + verified)

| Area | Status |
|------|--------|
| Phase 1 VectorBT research funnel | **Working** — history, regime, sweeps, rank, export |
| Phase 1.5 costs / TP-SL / risk | **Working** — fees, slippage, funding est., `fixed_rr\|atr\|trail`, 1–5% conviction risk |
| Infra I2 layout | **Working** — `infra-init`, paper/live separation |
| Export schema v1 | **Working** — strict needs costs, risk, tp_sl_mode, **exits** |
| Nautilus signal adapter | **Working** — `nautilus/signals.py` registry → `last_bar_intent` |
| Loadout sizing / exits | **Working** — `nautilus/sizing.py` → `ExitConfig` / size frac |
| OHLCV → Nautilus bars | **Working** — `nautilus/bars.py` + synthetic BTC-PERP |
| HypervectorStrategy actor | **Working** — params-driven; never signals.parquet; `execution_mode=phase2_historical` |
| Historical runner + artifacts | **Working** — `run_phase2_backtest` → `data/nautilus/backtest/<run_id>/summary.json` |
| CLI `phase2-run` | **Working** — strict export + cache history |
| ML impulse façade | **Working** — `ml/impulse_btc.py` load LGBM+calibrator → conviction [0,1]; no training |
| Paper ledger scaffold | **Working** — `paper/ledger.py` forces `execution_mode=paper`; refuses live paths; `paper-check` CLI |
| Unit tests | **143 passed** offline (`-m "not network"`, ignore fetchers) |
| Real Phase 2 path | **Working** — strict export `downtrend_crown_stack_short_c4fd7067`, 43200 bars, 690 orders, summary under `data/nautilus/backtest/` |

## What’s not built yet

| Item | Notes |
|------|--------|
| **CLI `--conviction-model impulse_btc`** | Façade ready; needs feature vector builder wired to phase2-run (defer) |
| **Venue fee/slippage from loadout.costs** | Runner uses loadout for sizing; fill model not fully cost-parity with VectorBT |
| **Phase 3 paper live-feed loop** | HL subscribe + synthetic fills + append_paper_decision — **next** |
| **Phase 3 live** | Out of scope until paper proven |

**Locked rules still apply:** signals parquet = parity only; never VectorBT → live; paper ledger ≠ live ledger.

---

## Goal (pipeline)

| Phase | Role | Framework | State |
|-------|------|-----------|--------|
| **1** | Research / grids / rank / export | VectorBT | **Done** |
| **1.5** | Fees, slippage, funding, TP/SL, risk | VectorBT | **Done** |
| **2 prep** | Export contract + loadout stub | hypervector | **Done** |
| **2 actor** | Event-driven historical sim from params | NautilusTrader | **Done** |
| **3 paper** | HL live feed + same logic + synthetic fills | Nautilus | Scaffold done; **loop next** |
| **3 live** | Same as paper; real exec client | Nautilus + HL | Later |

---

## Plan progress (2026-07-22-phase2-actor-and-ml)

| Task | Status | Commit |
|------|--------|--------|
| 1 Shared bar-window signal adapter | **Done** | `35d3219` |
| 2 Loadout sizing + exit helpers | **Done** | `e804ec2` |
| 3 OHLCV → Nautilus bars | **Done** | `243268a` |
| 4 HypervectorStrategy actor | **Done** | `55210ed` |
| 5 Historical runner + artifacts | **Done** | `b1680cf` |
| 6 CLI `phase2-run` | **Done** | `406bbef` |
| 7 ML impulse façade (optional) | **Done** | `c9490e1` |
| 8 Paper ledger scaffold | **Done** | `f9c1fa9` |
| 9 Full verify + handoff | **Done** | (this commit) |

---

## Key surfaces (current)

| Path | Role |
|------|------|
| `src/hypervector/export/schema.py` | `validate_export_dir`, schema v1 + `meta.exits` |
| `src/hypervector/nautilus/signals.py` | OHLCV window → registry signals / `SignalIntent` |
| `src/hypervector/nautilus/sizing.py` | Loadout → ExitConfig + position_size_frac |
| `src/hypervector/nautilus/bars.py` | Research frame → Bar list + synthetic instrument |
| `src/hypervector/nautilus/actor.py` | `HypervectorStrategy` from loadout |
| `src/hypervector/nautilus/runner.py` | `run_phase2_backtest` + summary.json |
| `src/hypervector/ml/impulse_btc.py` | Optional metalabel conviction façade |
| `src/hypervector/paper/ledger.py` | Paper decisions JSONL scaffold |
| CLI | `history\|regime\|sweep-*\|report\|export\|export-validate\|phase2-check\|phase2-run\|paper-check\|infra-init` |

---

## Next session — start here

```bash
cd /Users/gestas/Prototypes/hypervector
git checkout feat/phase2-actor-and-ml
uv sync --all-extras
# Load write-clean-code (+ engineering-software / brainstorming for design)
# NEXT: design + plan Phase 3 paper live-feed loop (HL feed + synthetic fills)
#   - reuse HypervectorStrategy + paper ledger
#   - still no live orders
uv run pytest tests/ -q -m "not network"
```

### Research / Phase 2 (working)

```bash
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<id> --lookback 30 --no-network
ls data/nautilus/backtest/
uv run python -m hypervector paper-check
```

### ML façade (optional conviction)

```python
from hypervector.ml.impulse_btc import ImpulseBtcFacade
# HYPERVECTOR_IMPULSE_BTC_ROOT or hypertrader/hyper-pi defaults
facade = ImpulseBtcFacade.from_env()
p = facade.predict_conviction({"rsi_1m": 40.0, ...})  # feature dict; clipped [0,1]
```

CLI still uses fixed `--conviction` until a feature builder is wired.

---

## ML notes (shipped Task 7)

- **In tree:** `src/hypervector/ml/impulse_btc.py` (inference only)
- LightGBM `metalabel_lgbm.txt` + optional `metalabel_calibrator.joblib`
- Env: `HYPERVECTOR_IMPULSE_BTC_ROOT`; defaults hyper-pi then hypertrader models
- Optional extra: `uv sync --extra ml` (lightgbm)
- **Not shipped:** training, feature engine in hypervector, CLI `--conviction-model`

---

## Non-goals (still)

- Live trading / keys / vaults  
- VectorBT → live skip of Phase 2/paper  
- CEX bars claimed as HL book  
- Shared paper/live ledgers  
- Postgres / Redis / k8s  

---

## Agent notes

- Prefer this HANDOFF over stale agentmemory for phase status.  
- SDD ledger: `.superpowers/sdd/progress.md`  
- Skills used this session: engineering-software, brainstorming (design already locked), write-clean-code, subagent-driven-development.  
- Legacy pre-schema exports fail `export-validate` until re-exported with current CLI.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator version skew.  
- Ray adapter test can flake on raylet startup — not Phase 2 scope.  
