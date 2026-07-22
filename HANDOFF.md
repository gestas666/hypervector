# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase2-actor-and-ml` (**not pushed**)  
**HEAD (docs tip):** `5f62f35` — handoff/docs only; Phase 3 **code not started**  
**Working tree:** clean for product code; untracked `audio/` ok to ignore  

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1 / 1.5 research | **Done** |
| Phase 2 actor + historical runner + metalabeler + paper ledger scaffold | **Done** (plan closed) |
| Phase 3 paper **design** | **Approved / locked** |
| Phase 3 paper **implementation plan** | **Locked — 0/5 tasks coded** |
| Phase 3 paper **code** | **Not started** — next session implements |
| Phase 4 | **Deferred** — design after Phase 3 paper proven |

**This session (outgoing):** design + plan + Phase 4 epic notes only. **No Phase 3 product code.**

**Next session (incoming):** **EXECUTE Phase 3 plan Tasks 1→5.** Do not re-design. Do not re-execute Phase 2. Do not start Phase 4.

---

## Docs map (canonical)

| Role | Path |
|------|------|
| **EXECUTE THIS** | `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` |
| Phase 3 design (approved) | `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md` |
| Pipeline / paper identity lock | `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` |
| Phase 1 design | `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` |
| Phase 2 plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md` |
| Phase 1.5 + prep plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md` |
| Infra I2 | `docs/infra-data-layout.md` |
| This handoff | `HANDOFF.md` |

Prefer **this HANDOFF** over stale agentmemory for phase status.

---

## Next session — START EXECUTION HERE

**Goal:** Implement Phase 3 paper live-feed loop. Design is done — **code only**.

```bash
cd /Users/gestas/Prototypes/hypervector
git checkout feat/phase2-actor-and-ml
uv sync --all-extras
uv run pytest tests/ -q -m "not network"

# Then open and execute:
#   docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md
# Skills: subagent-driven-development (preferred) OR executing-plans
#         + write-clean-code
# Order: Task 1 → 2 → 3 → 4 → 5 · TDD · commit per task
# Out of scope: Phase 4 (ML, book, live, TUI, GUI)
```

**Agent checklist on open:**

1. Confirm branch `feat/phase2-actor-and-ml`; note HEAD; do not start on `main` without asking.  
2. Baseline: `uv run pytest tests/ -q -m "not network"` (expect green).  
3. Open Phase 3 plan; begin **Task 1** (`paper/costs.py`).  
4. Execute Tasks 1–5 completely (or as far as session allows; keep task table accurate).  
5. End session: update this HANDOFF (task status + commits); leave Phase 4 alone.  
6. Optional: `.superpowers/sdd/progress.md` ledger line per completed task.

**Execution mode:** `subagent-driven-development` recommended (one implementer + review per task). Fallback: inline `executing-plans`.

---

## Phase 3 plan progress (0/5)

**Plan:** `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md`  
**Design:** `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`

| Task | Deliverable | Status | Commit |
|------|-------------|--------|--------|
| 1 | `paper/costs.py` — HL fee tiers + signed funding | **Pending** | — |
| 2 | `paper/fills.py` — ExplicitFillEngine + decision fields | **Pending** | — |
| 3 | `paper/session.py` — offline bar session | **Pending** | — |
| 4 | `paper/runner.py` + `paper-run` daemon + live bars | **Pending** | — |
| 5 | Sandbox flag + full offline verify + HANDOFF update | **Pending** | — |

**Success when:** offline suite green; `paper-run` warms + processes bars; decisions under `data/paper/` with `execution_mode=paper`; no venue orders; no Phase 4 scope creep.

### Phase 3 locks (do not reopen)

| Decision | Choice |
|----------|--------|
| Host | Full Nautilus node + HL data client |
| Market data v1 | Bars only (order book = Phase 4) |
| Runtime | Long-running daemon |
| Fills | Explicit model = ledger truth; optional sandbox shadow (default **off**) |
| Costs | Hybrid: config fee tier + slippage; **live signed hourly funding** |
| Fee default | HL Tier 0 base **taker 0.045% / maker 0.015%** |
| Warm-up | Cache-first → HL REST if cold → live bars |
| Architecture | Approach 1: thin shell around `HypervectorStrategy` |
| ML | **Off** in Phase 3 — fixed conviction only |
| Secrets | Env names ready; paper public path works **without** keys |
| Live | Config flip later (Phase 4); paper must never place venue orders |

**Secrets env (Phase 4 live; ignore for order placement in paper):**

- `HYPERVECTOR_HL_WALLET_ADDRESS`  
- `HYPERVECTOR_HL_API_PRIVATE_KEY`  

---

## Pipeline

```text
Phase 1/1.5  VectorBT research → export
Phase 2      Nautilus historical (params, not signals.parquet)
Phase 3      Paper: live HL bars + same strategy + explicit fills   ← IMPLEMENT NEXT
Phase 4      Book + ML + live flip + full CLI + GOAT TUI + 1-page GUI
```

| Phase | Role | State |
|-------|------|--------|
| **1 / 1.5** | Research, costs, risk, export | **Done** |
| **2** | Event-driven historical sim | **Done** |
| **3 paper** | Live feed + synthetic fills + paper ledger | **Design+plan locked; code pending** |
| **4** | Book, ML, live, CLI complete, GOAT TUI, 1-page GUI | **After paper proven** |

---

## Process principles (locked)

| Principle | Meaning |
|-----------|---------|
| **Process over asset** | Parameterize by symbol / TF / bundle id — no `BtcOnly` modules |
| **Version via config/bundle** | New market/model = new export or metalabel dir, not forked code |
| **Improve, don’t ship suboptimal** | No ML conviction until features + labels match the gate |
| **Same path paper → live** | Only execution client + ledger root flip; no paper-only smarter branch |

Metalabel process (Phase 4 wire-up; process already exists):

```text
features (metadata schema)
  → LightGBM + optional calibrator
  → p ∈ [0, 1]
  → policy (optional floor) → conviction → existing risk band
```

---

## What’s working (built + verified)

| Area | Status |
|------|--------|
| Phase 1 VectorBT research funnel | **Working** |
| Phase 1.5 costs / TP-SL / risk | **Working** |
| Infra I2 (`infra-init`, paper/live roots) | **Working** |
| Export schema v1 (strict: costs, risk, exits) | **Working** |
| Nautilus signals / sizing / bars / actor / runner | **Working** |
| CLI `phase2-run` / `phase2-check` / `export-validate` | **Working** |
| Metalabeler process (`ml/metalabel.py`) | **Working** (not wired to CLI) |
| Paper ledger scaffold + `paper-check` | **Working** (no live-feed loop yet) |
| Real Phase 2 sample | export `downtrend_crown_stack_short_c4fd7067`, artifacts under `data/nautilus/backtest/` |

## What’s not built yet

| Item | Phase | Notes |
|------|-------|--------|
| CostProvider + ExplicitFillEngine + session + `paper-run` | **3** | **Next session Tasks 1–5** |
| CLI metalabel / feature builder | **4a** | After paper |
| Order book / impact fills | **4a** | `cache/book/` reserved |
| Live exec + live ledger | **4b** | Config flip + secrets |
| CLI completeness pass | **4c** | **Gate before TUI/GUI** |
| GOAT TUI | **4d** | Epic terminal ops console |
| 1-page GUI monitoring dashboard | **4e** | Same ledger truth as TUI/CLI |
| Phase 2 runner full cost parity with VBT | backlog | Not blocking paper |

**Rules:** signals.parquet = parity only; never VectorBT → live; paper ledger ≠ live ledger.

---

## Key surfaces (current code)

| Path | Role |
|------|------|
| `src/hypervector/export/schema.py` | Export validate schema v1 |
| `src/hypervector/nautilus/signals.py` | OHLCV → `SignalIntent` |
| `src/hypervector/nautilus/sizing.py` | Loadout → exits / size |
| `src/hypervector/nautilus/bars.py` | Research frame → Nautilus bars |
| `src/hypervector/nautilus/actor.py` | `HypervectorStrategy` |
| `src/hypervector/nautilus/runner.py` | Phase 2 historical backtest |
| `src/hypervector/ml/metalabel.py` | Reusable Metalabeler |
| `src/hypervector/paper/ledger.py` | Paper decisions JSONL scaffold only |
| `src/hypervector/data/hl.py` | Public HL candle REST |
| CLI | `history\|regime\|sweep-*\|report\|export\|export-validate\|phase2-check\|phase2-run\|paper-check\|infra-init` |

**Planned Phase 3 paths (create in Tasks 1–5):**  
`paper/costs.py`, `paper/fills.py`, `paper/session.py`, `paper/runner.py`, `paper/live_node.py`, `paper-run` CLI.

---

## Verify / smoke (working today)

```bash
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<id> --lookback 30 --no-network
uv run python -m hypervector paper-check
uv run pytest tests/ -q -m "not network"
```

### Metalabeler (optional; Phase 4 CLI wire)

```python
from hypervector.ml import Metalabeler
ml = Metalabeler.from_env()  # HYPERVECTOR_METALABEL_ROOT
p = ml.predict_probability(features)  # [0, 1]
```

---

## Phase 4 epic (NOT next session)

Implement only **after** Phase 3 Tasks 1–5 succeed. Separate design + plan.

| Track | Deliverable | Bar |
|-------|-------------|-----|
| **4a** | Order book + impact fills; ML metalabel on shared path; userFees | Honest fills + conviction |
| **4b** | Live exec flip, secrets required, `data/live/`, kill switch | Same strategy path as paper |
| **4c** | CLI completeness — every capability consistent | Gate for UX |
| **4d** | **GOAT TUI** — best-in-class terminal ops console | Epic quality; design session |
| **4e** | **1-page GUI** monitoring dashboard | Same truth as TUI/CLI; one page |

**UX sequencing:** **4c CLI complete → then 4d TUI + 4e GUI.**  
TUI/GUI are views over ledgers/processes — not a second brain. `execution_mode` always obvious. CLI stays scriptable.

---

## Non-goals (until Phase 4 design says otherwise)

- Live venue orders in Phase 3  
- VectorBT → live skip of Phase 2/paper  
- CEX bars claimed as HL book  
- Shared paper/live ledgers  
- Postgres / Redis / k8s  
- Phase 3 metalabel wiring  
- Building TUI/GUI before CLI completeness  

---

## Future: agent skill package (after phases)

After paper proven (+ live ops checklist): skill/plugin so agents follow research → phase2 → paper → live correctly. Until then: **this HANDOFF + specs/plans** are the contract.

---

## Agent notes

- Phase 2 plan **closed**. Phase 3 design + plan **closed** → **execute only**.  
- First code file: `src/hypervector/paper/costs.py` + `tests/test_paper_costs.py` (Task 1).  
- Branch not pushed; merge/PR when Albert wants.  
- Legacy pre-schema exports fail `export-validate` until re-exported.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator skew.  
- Paper must not submit real orders even if wallet/API key env vars are set.  

---

## Outgoing session summary (2026-07-22 design session)

Done this session (docs only):

- Skills: engineering-software, ml-for-algo-trading, brainstorming  
- Phase 3 design Approach 1 locked (Nautilus host, bars, daemon, fill C, hybrid costs, warm-up A)  
- Spec: `2026-07-22-phase3-paper-live-feed-design.md`  
- Plan: `2026-07-22-phase3-paper-live-feed.md` (Tasks 1–5)  
- Deferred work renamed **Phase 4** (not “Phase 3+”), including ML importance  
- Phase 4 UX: CLI complete → GOAT TUI + 1-page GUI  
- HANDOFF pointed at **execute next**  

**Not done:** any Phase 3 implementation code.
