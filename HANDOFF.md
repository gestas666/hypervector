# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase2-actor-and-ml` (not pushed)

**Status:** Phase 1 / 1.5 / Phase 2 **actor + runner + metalabeler + paper scaffold** complete and verified.  
**Completed plan:** `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`  
**Spec (locked):** `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`  
**Prior plan (done):** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Infra doc:** `docs/infra-data-layout.md`

**Next session:** Phase 3 **paper live-feed loop** (HL subscribe + same strategy path + synthetic fills logged via paper ledger). Not started. Do not go live.

---

## Process principles (locked)

Build **reusable processes**, not one-off asset/interval products. Defaults may be BTC 1m for MVP; the design must reapply without a rewrite.

| Principle | Meaning |
|-----------|---------|
| **Process over asset** | Strategy registry, export loadout, Phase 2 actor, metalabeler, paper ledger — parameterized by symbol / TF / bundle id, not `BtcOnly` types. |
| **Version via config/bundle** | New market or model = new export / strategy params / metalabel **bundle directory**, not a forked module. Spin off a code version only when the *process* changes. |
| **Improve, don’t ship suboptimal** | No wiring ML conviction until features + labels match the gate; no dual leverage vs risk semantics; measure before promote. |
| **Same path paper → live** | Only execution client differs later; no paper-only smarter branch. |

Metalabel process (any asset/interval once bundle is valid):

```text
features (metadata schema)
  → LightGBM + optional calibrator
  → p ∈ [0, 1]
  → policy (optional floor skip) → conviction → existing risk band
```

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
| Metalabeler (reusable) | **Working** — `ml/metalabel.py` load any LGBM+calibrator bundle → p∈[0,1]; no training |
| Paper ledger scaffold | **Working** — `paper/ledger.py` forces `execution_mode=paper`; refuses live paths; `paper-check` CLI |
| Unit tests | offline suite green (see latest pytest) |
| Real Phase 2 path | **Working** — strict export `downtrend_crown_stack_short_c4fd7067`, 43200 bars, 690 orders, summary under `data/nautilus/backtest/` |

## What’s not built yet

| Item | Notes |
|------|--------|
| **CLI metalabel / feature builder** | `Metalabeler` ready; needs bar→feature builder + bundle id; defer until process is correct |
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
| 7 Metalabeler (optional; was impulse façade) | **Done** | `c9490e1` + rename |
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
| `src/hypervector/ml/metalabel.py` | Reusable `Metalabeler` (bundle-parameterized) |
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

### Metalabeler (optional conviction / probability)

```python
from hypervector.ml import Metalabeler
# HYPERVECTOR_METALABEL_ROOT → any bundle dir (legacy: HYPERVECTOR_IMPULSE_BTC_ROOT)
ml = Metalabeler.from_env()           # or Metalabeler.from_root(path)
p = ml.predict_probability(features)  # clipped [0, 1]; alias: predict_conviction
```

CLI still uses fixed `--conviction` until a feature builder is wired to a bundle whose **labels match the strategy gate**.

---

## ML notes

- **Process:** `Metalabeler` — not BTC-specific; version via new bundle directory
- **Bundle contract:** `metalabel_lgbm.txt`, optional calibrator, `metalabel_metadata.json` (`feature_names`)
- **Env:** `HYPERVECTOR_METALABEL_ROOT` (preferred); legacy `HYPERVECTOR_IMPULSE_BTC_ROOT` still works
- **Compat:** `ml/impulse_btc.py` re-exports deprecated aliases for one cycle
- Optional extra: `uv sync --extra ml` (lightgbm)
- **Not shipped:** training, feature engine, policy (floor_p), multi-bundle registry, CLI flag

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
