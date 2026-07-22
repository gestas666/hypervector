# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase2-actor-and-ml` (not pushed)

**Status:** Phase 1 / 1.5 / Phase 2 complete. Phase 3 **design + implementation plan ready** (not executed yet).  
**Completed plan:** `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`  
**Phase 3 design:** `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`  
**Phase 3 plan (execute next):** `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md`  
**Spec (pipeline lock):** `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`  
**Prior plan (done):** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Infra doc:** `docs/infra-data-layout.md`

**Next session:** **Execute** Phase 3 paper plan Tasks 1–5 (CostProvider → fills → offline session → paper-run daemon → sandbox flag + handoff). Do not go live.

**Phase 4 (after paper proven — first-class, not “Phase 3+”):** order book, **ML metalabel conviction**, live exec flip + secrets, userFees, ops kill switch. Separate design + plan.

**Later (after phases complete):** ship an **agent skill package / plugin** so agents use the full research→Phase2→paper→live ladder correctly (see below).

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
| **3 paper** | HL live feed + same logic + synthetic fills | Nautilus | Design+plan ready; **execute next** |
| **4** | Order book + ML metalabel + live exec flip | Nautilus + HL | After paper proven |

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
# Skills: subagent-driven-development or executing-plans + write-clean-code
# Plan: docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md
# Execute Tasks 1→5 only. Phase 4 (ML, book, live) is AFTER paper.
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

## Next session entry

```bash
cd /Users/gestas/Prototypes/hypervector
git checkout feat/phase2-actor-and-ml
uv sync --all-extras
# Skills: engineering-software, brainstorming, write-clean-code
# Phase 2 plan is CLOSED — do not re-execute Tasks 1–9
# 1) Read this HANDOFF + specs/2026-07-22-phase2-3-handoff.md §3–4
# 2) Brainstorm → design doc → user approve → writing-plans
# 3) Only then subagent-driven execute Phase 3 paper loop
uv run pytest tests/ -q -m "not network"
```

### Phase 3 paper loop (design + plan locked; implement next)

- HL **live** bars (cache warm-up first); full Nautilus host
- Explicit fills + hybrid costs (Tier 0 fees, live signed funding)
- Optional sandbox shadow (default off); daemon `paper-run`
- Secrets env names ready for Phase 4; paper needs no keys for public path
- **Not in Phase 3:** order book, ML metalabel, live orders

### Phase 4 (important — design after paper)

- Order book + impact fills  
- Metalabel conviction on shared path  
- Live exec config flip + `data/live/` + kill switch  
- Authenticated userFees

---

## Future: agent skill package / plugin (after phases)

**When:** after Phase 3 paper is proven (and a clear live ops checklist) — not mid-pipeline.

**Why:** agents invent VBT→live shortcuts, asset-specific forks, or wire metalabel wrong without a contract.

**Deliverable sketch** (later via create-skill or grok plugin):

| Piece | Content |
|-------|---------|
| `SKILL.md` | When to use hypervector; promotion ladder; non-goals; process principles |
| Playbooks | Research → export-validate → phase2-run → paper-check → paper loop |
| CLI map | Commands, flags, exit codes, data roots |
| Contracts | Export schema v1, StrategyLoadout, Metalabeler bundle layout, paper ledger |
| Anti-patterns | signals.parquet as alpha; VectorBT→live; shared paper/live ledgers; BTC-only modules |
| Verify | Offline pytest; real phase2-run; paper isolation |

Until then: **this HANDOFF + specs/plans** are the agent contract.

---

## Agent notes

- Prefer this HANDOFF over stale agentmemory for phase status.  
- Phase 2 plan is **closed** — next work needs a **new** design + plan.  
- SDD ledger: `.superpowers/sdd/progress.md` (Phase 2 complete).  
- Branch `feat/phase2-actor-and-ml` not pushed; merge/PR when you want Phase 2 on main.  
- Legacy pre-schema exports fail `export-validate` until re-exported.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator version skew.  
