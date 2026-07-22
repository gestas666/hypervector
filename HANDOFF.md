# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase2-actor-and-ml` (not pushed)

**Status:** Phase 1 / 1.5 / Phase 2 complete. Phase 3 design + plan **locked**. **Next session starts implementation.**  
**Completed plan:** `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md`  
**Phase 3 design (approved):** `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`  
**Phase 3 plan (EXECUTE THIS):** `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md`  
**Spec (pipeline lock):** `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md`  
**Prior plan (done):** `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`  
**Infra doc:** `docs/infra-data-layout.md`

**Next session (mandatory):** **Execute** Phase 3 paper plan Tasks 1→5 end-to-end.  
Do **not** re-design. Do **not** re-execute Phase 2. Do **not** start Phase 4 (ML / book / live).

**Execution mode (recommended):** `subagent-driven-development` — one task per subagent, TDD, commit per task.  
**Fallback:** `executing-plans` inline with checkpoints.

**Phase 4 (after paper proven — first-class, not “Phase 3+”):** see full Phase 4 epic below. Separate design + plan — **not this session**.

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

| Item | Phase | Notes |
|------|-------|--------|
| **CostProvider + ExplicitFillEngine + paper session + `paper-run`** | **3** | **Execute next** — plan Tasks 1–5 |
| **CLI metalabel / feature builder** | **4** | `Metalabeler` ready; wire after paper |
| **Order book / impact fills** | **4** | `cache/book/` reserved |
| **Live exec + live ledger** | **4** | Config flip + secrets after paper proven |
| **Venue fee/slippage parity in Phase 2 runner** | backlog | Not blocking paper |

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
| **4** | Book + ML + live + full CLI + GOAT TUI + 1-page GUI dashboard | Nautilus + HL + TUI/GUI | After paper proven |

---

## Plan progress — Phase 2 (CLOSED)

| Task | Status | Commit |
|------|--------|--------|
| 1–9 actor, runner, metalabeler, paper scaffold | **Done** | through `f9c1fa9` + handoff |

Do **not** re-execute Phase 2.

## Plan progress — Phase 3 paper (EXECUTE NEXT)

**Plan:** `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md`  
**Design:** `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`

| Task | Deliverable | Status |
|------|-------------|--------|
| 1 | `paper/costs.py` — HL fee tiers + signed funding | **Pending** |
| 2 | `paper/fills.py` — ExplicitFillEngine + decision fields | **Pending** |
| 3 | `paper/session.py` — offline bar session | **Pending** |
| 4 | `paper/runner.py` + `paper-run` daemon + live bars | **Pending** |
| 5 | Sandbox flag + full offline verify + HANDOFF update | **Pending** |

Success when: offline suite green; `paper-run` can warm + process bars; decisions under `data/paper/` with `execution_mode=paper`; no venue orders; no Phase 4 scope creep.

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

## Next session — START EXECUTION HERE

**Goal:** Implement Phase 3 paper live-feed loop per plan (Tasks 1→5). Design is done — code only.

```bash
cd /Users/gestas/Prototypes/hypervector
git checkout feat/phase2-actor-and-ml
uv sync --all-extras

# 1) Baseline
uv run pytest tests/ -q -m "not network"

# 2) Read then execute (do not redesign)
#    docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md
# Skills: subagent-driven-development (preferred) OR executing-plans
#         + write-clean-code; karpathy-guidelines if loaded
# Order: Task 1 → 2 → 3 → 4 → 5; TDD; commit per task
# Out of scope: Phase 4 ML, order book, live orders
```

**Agent checklist on open:**

1. Confirm branch `feat/phase2-actor-and-ml`, working tree known.  
2. Open Phase 3 plan; mark Task 1 in progress.  
3. Execute Tasks 1–5 completely (or as far as session allows; leave checkboxes accurate).  
4. End session: update this HANDOFF task table + commits; leave Phase 4 for later.

### Research / Phase 2 (working — do not rebuild)

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

## Next session entry (copy-paste)

```bash
cd /Users/gestas/Prototypes/hypervector
git checkout feat/phase2-actor-and-ml
uv sync --all-extras
# EXECUTE Phase 3 — design/plan already locked
# Plan: docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md
# Skills: subagent-driven-development + write-clean-code
# Phase 2 CLOSED. Phase 4 (ML/book/live) NOT this session.
uv run pytest tests/ -q -m "not network"
# Then implement Task 1 (paper/costs.py) and continue 2→5
```

### Phase 3 scope (implementing)

- HL **live** bars (cache warm-up first); full Nautilus host  
- Explicit fills + hybrid costs (Tier 0 fees, live signed funding)  
- Optional sandbox shadow (default off); daemon `paper-run`  
- Secrets env names ready for Phase 4; paper needs no keys for public path  

### Phase 4 epic (do not implement until paper Tasks 1–5 done)

**Gate before UX work:** CLI must expose **all current capabilities** end-to-end (research → export → phase2 → paper → eventually live ops), clean help, exit codes, config surface — then design/build UX on that complete surface.

| Track | Deliverable | Bar |
|-------|-------------|-----|
| **4a Data / alpha** | Order book + impact fills; ML metalabel on shared path; authenticated userFees | Honest fills + conviction |
| **4b Live** | Exec config flip, secrets required, `data/live/`, tiny size + kill switch | Same strategy path as paper |
| **4c CLI complete** | Full command map: every working capability (history, regime, sweep, report, export, validate, phase2-*, paper-*, infra, future live) documented and consistent | Single source of truth for agents + humans |
| **4d GOAT TUI** | Terminal UI over the full CLI/process ladder — not a thin wrapper; **epic / best-in-class** ops console (paper/live status, decisions feed, PnL, mode banner, kill switch, run control) | Greatest-of-all-time quality bar; design session required |
| **4e 1-page GUI dashboard** | Single-page monitoring dashboard (paper/live identity, positions, recent decisions, costs/funding, health) — same truth as TUI/CLI, not a second brain | One page, high signal, monitoring-first |

**UX principles (locked for Phase 4 design):**

- TUI and GUI are **views** over the same processes/ledgers — no paper-only smarter path.  
- `execution_mode` always obvious (paper vs live).  
- CLI remains scriptable; TUI/GUI never replace batch automation.  
- Build TUI/GUI only **after** CLI completeness pass (4c).

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
- Phase 2 plan is **closed**. Phase 3 design + plan are **closed** — **execute**, do not re-brainstorm.  
- Next agent action: open `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` and run Task 1.  
- SDD ledger: `.superpowers/sdd/progress.md` (update as Phase 3 tasks complete).  
- Branch `feat/phase2-actor-and-ml` not pushed; merge/PR when ready.  
- Legacy pre-schema exports fail `export-validate` until re-exported.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator version skew.  
- Secrets for Phase 4: `HYPERVECTOR_HL_WALLET_ADDRESS`, `HYPERVECTOR_HL_API_PRIVATE_KEY` — paper path must not place live orders even if present.  
