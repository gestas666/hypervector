# HANDOFF — hypervector

**Saved:** 2026-07-22  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase2-actor-and-ml` (**not pushed**)  
**HEAD tip:** Phase 3 paper Tasks 1–5 complete (see task table)  
**Working tree:** untracked `audio/` ok to ignore  

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1 / 1.5 research | **Done** |
| Phase 2 actor + historical runner + metalabeler + paper ledger scaffold | **Done** (plan closed) |
| Phase 3 paper **design** | **Approved / locked** |
| Phase 3 paper **implementation plan** | **Complete — 5/5 tasks** |
| Phase 3 paper **code** | **Done** — live-feed loop + explicit fills + costs + sandbox flag |
| Phase 4 | **Next design** — order book, ML metalabel, live exec, CLI complete, GOAT TUI, 1-page GUI |

**This session (outgoing):** Phase 3 Tasks 1–5 implemented and verified offline.  
**Next session (incoming):** **Phase 4 design** (brainstorm + spec + plan). Do **not** re-do Phase 3. Do not start Phase 4 code until design is locked.

---

## Docs map (canonical)

| Role | Path |
|------|------|
| Phase 3 plan (COMPLETE) | `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` |
| Phase 3 design (approved) | `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md` |
| Pipeline / paper identity lock | `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` |
| Phase 1 design | `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` |
| Phase 2 plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md` |
| Phase 1.5 + prep plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md` |
| Infra I2 | `docs/infra-data-layout.md` |
| This handoff | `HANDOFF.md` |

Prefer **this HANDOFF** over stale agentmemory for phase status.

---

## Next session — START HERE (Phase 4 design)

**Goal:** Design Phase 4 only. Phase 3 paper is proven offline — **do not re-implement**.

```bash
cd /Users/gestas/Prototypes/hypervector
git checkout feat/phase2-actor-and-ml
uv sync --all-extras
uv run pytest tests/ -q -m "not network"

# Smoke paper surfaces (no keys required):
uv run python -m hypervector paper-check
# Optional short daemon smoke (needs export + HL public or offline inject):
# uv run python -m hypervector paper-run --path data/exports/<id> --max-live-bars 2
```

**Agent checklist on open:**

1. Confirm branch `feat/phase2-actor-and-ml`; note HEAD; do not start on `main` without asking.  
2. Baseline: offline suite green.  
3. **Do not** re-open Phase 3 plan tasks.  
4. Start **Phase 4 design** (brainstorm + spec + plan): book, ML wire, live flip, CLI complete → TUI/GUI.  
5. End session: update this HANDOFF with Phase 4 design paths when locked.

**Skills:** brainstorming → write-spec → write-plan. UX sequencing: **CLI complete → GOAT TUI + 1-page GUI**.

---

## Phase 3 plan progress (5/5)

**Plan:** `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md`  
**Design:** `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`

| Task | Deliverable | Status | Commit (approx) |
|------|-------------|--------|-----------------|
| 1 | `paper/costs.py` — HL fee tiers + signed funding | **Done** | `37eed5e` |
| 2 | `paper/fills.py` — ExplicitFillEngine + decision fields | **Done** | `740dd5c` |
| 3 | `paper/session.py` — offline bar session | **Done** | `2ff363a` |
| 4 | `paper/runner.py` + `paper-run` daemon + live bars | **Done** | `8208600` |
| 5 | Sandbox flag + full offline verify + HANDOFF update | **Done** | `25604bc` |
| fix | Signed funding applied each bar while open | **Done** | `fdab716` |

**Success criteria met:** offline suite **170 passed** (`-m "not network"`); `paper-run` warms + processes bars; decisions under `data/paper/` with `execution_mode=paper`; funding applied on open positions; no venue orders; Phase 4 scope not started.

### How to run paper-check / paper-run

```bash
# Identity + readiness (no secret values; live.enabled always false in report)
uv run python -m hypervector --data-root data paper-check
# → paper.execution_mode=paper, live_feed_loop=true, sandbox_enabled=false,
#   secrets_present bool, secret_env_names listed

# Daemon: warm-up + live HL REST bar poll + explicit fills (no venue orders)
uv run python -m hypervector --data-root data paper-run \
  --path data/exports/<export_id> \
  --conviction 0.5 \
  --fee-tier 0 \
  [--sandbox] \              # shadow flag only; no real sandbox client
  [--stop-file /tmp/hv.stop] \
  [--max-live-bars N] \      # smoke / offline cap
  [--poll-interval 5]
```

Banner on stderr: `PAPER MODE — no venue orders`.  
Decisions: `data/paper/decisions/decisions.jsonl` (I2 layout).

### Phase 3 locks (do not reopen)

| Decision | Choice |
|----------|--------|
| Host | Paper shell around `HypervectorStrategy` path (session + daemon) |
| Market data v1 | Bars only (order book = Phase 4) |
| Runtime | Long-running daemon (`paper-run`) |
| Fills | Explicit model = ledger truth; sandbox shadow default **off** |
| Sandbox v1 | Flag + `sandbox_fill_px=null` only; log `sandbox_requested_but_not_wired` |
| Costs | Hybrid: config fee tier + slippage; signed hourly funding math |
| Fee default | HL Tier 0 base **taker 0.045% / maker 0.015%** |
| Warm-up | Cache-first → HL REST if cold → live bar poll |
| Live feed v1 | HL REST poll fallback (WS preferred later) |
| ML | **Off** in Phase 3 — fixed conviction only |
| Secrets | Env names ready; paper public path works **without** keys |
| Live | Config flip later (Phase 4); paper must never place venue orders |

**Secrets env (Phase 4 live; ignored for order placement in paper):**

- `HYPERVECTOR_HL_WALLET_ADDRESS`  
- `HYPERVECTOR_HL_API_PRIVATE_KEY`  

**Live:** `configs/default.toml` → `[live] enabled = false`. Paper never writes `data/live/` or submits venue orders.

---

## Pipeline

```text
Phase 1/1.5  VectorBT research → export
Phase 2      Nautilus historical (params, not signals.parquet)
Phase 3      Paper: live HL bars + same strategy + explicit fills   ← DONE
Phase 4      Book + ML + live flip + full CLI + GOAT TUI + 1-page GUI  ← DESIGN NEXT
```

| Phase | Role | State |
|-------|------|--------|
| **1 / 1.5** | Research, costs, risk, export | **Done** |
| **2** | Event-driven historical sim | **Done** |
| **3 paper** | Live feed + synthetic fills + paper ledger | **Done** (offline verified) |
| **4** | Book, ML, live, CLI complete, GOAT TUI, 1-page GUI | **Next design** |

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
| `CostProvider` + HL fee tiers + signed funding | **Working** |
| `ExplicitFillEngine` (`bar_close_slippage_v1`) | **Working** |
| Offline `PaperSession` bar walk | **Working** |
| `paper-run` daemon (warm + REST poll + stop) | **Working** |
| `paper-check` (live_feed_loop, sandbox flag, secrets flags) | **Working** |
| Sandbox shadow flag (`sandbox_enabled`, `sandbox_fill_px=null`) | **Working** (no real client) |
| Real Phase 2 sample | export `downtrend_crown_stack_short_c4fd7067`, artifacts under `data/nautilus/backtest/` |

## What’s not built yet (Phase 4 — first-class next phase)

| Item | Phase | Notes |
|------|-------|--------|
| Order book L2 subscribe + impact fills | **4a** | `cache/book/` reserved |
| ML metalabel conviction / feature builder CLI | **4a** | Metalabeler process exists |
| Live exec + live ledger + secrets required | **4b** | Config flip; kill switch |
| Real Nautilus sandbox client mirror | **4 / harden** | Flag only in Phase 3 |
| userFees authenticated fee tier | **4a** | |
| Kill switch / supervisor production ops | **4b** | |
| CLI completeness pass | **4c** | **Gate before TUI/GUI** |
| GOAT TUI | **4d** | Epic terminal ops console |
| 1-page GUI monitoring dashboard | **4e** | Same ledger truth as TUI/CLI |
| Phase 2 runner full cost parity with VBT | backlog | Not blocking |

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
| `src/hypervector/paper/costs.py` | Fee tiers, `CostProvider`, funding math |
| `src/hypervector/paper/fills.py` | `ExplicitFillEngine` + sandbox shadow keys |
| `src/hypervector/paper/session.py` | Offline/incremental bar → fill |
| `src/hypervector/paper/runner.py` | `start_paper_daemon` |
| `src/hypervector/paper/live_node.py` | REST poll feed (WS TODO) |
| `src/hypervector/paper/ledger.py` | Paper decisions JSONL; refuse live path |
| `src/hypervector/data/hl.py` | Public HL candle REST |
| CLI | `…\|phase2-check\|phase2-run\|paper-check\|paper-run\|infra-init` |

---

## Verify / smoke (working today)

```bash
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<id> --lookback 30 --no-network
uv run python -m hypervector paper-check
uv run python -m hypervector paper-run --path data/exports/<id> --max-live-bars 2
uv run pytest tests/ -q -m "not network"
```

### Metalabeler (optional; Phase 4 CLI wire)

```python
from hypervector.ml import Metalabeler
ml = Metalabeler.from_env()  # HYPERVECTOR_METALABEL_ROOT
p = ml.predict_probability(features)  # [0, 1]
```

---

## Phase 4 epic (NEXT design session)

Implement only **after** a locked Phase 4 design + plan. Separate design session.

| Track | Deliverable | Bar |
|-------|-------------|-----|
| **4a** | Order book + impact fills; ML metalabel on shared path; userFees | Honest fills + conviction |
| **4b** | Live exec flip, secrets required, `data/live/`, kill switch | Same strategy path as paper |
| **4c** | CLI completeness — every capability consistent | Gate for UX |
| **4d** | **GOAT TUI** — best-in-class terminal ops console | Epic quality; design session |
| **4e** | **1-page GUI** monitoring dashboard | Same truth as TUI/CLI; one page |

**UX sequencing:** **4c CLI complete → then 4d TUI + 4e GUI.**  
TUI/GUI are views over ledgers/processes — not a second brain. `execution_mode` always obvious. CLI stays scriptable.

Also defer: real Nautilus sandbox client (Phase 3 only plumbs flag + null `sandbox_fill_px`).

---

## Non-goals (until Phase 4 design says otherwise)

- Live venue orders in Phase 3 (done — still forbidden until 4b)  
- VectorBT → live skip of Phase 2/paper  
- CEX bars claimed as HL book  
- Shared paper/live ledgers  
- Postgres / Redis / k8s  
- Phase 3 metalabel wiring (still off)  
- Building TUI/GUI before CLI completeness  

---

## Future: agent skill package (after phases)

After paper proven (+ live ops checklist): skill/plugin so agents follow research → phase2 → paper → live correctly. Until then: **this HANDOFF + specs/plans** are the contract.

---

## Agent notes

- Phase 2 plan **closed**. Phase 3 design + plan + code **closed**.  
- **Next:** Phase 4 **design**, not Phase 3 re-execution.  
- Branch not pushed; merge/PR when Albert wants.  
- Legacy pre-schema exports fail `export-validate` until re-exported.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator skew.  
- Paper must not submit real orders even if wallet/API key env vars are set.  
- Live feed uses **REST poll** fallback (`live_node.py`); full Nautilus WS host optional later.  

---

## Outgoing session summary (Phase 3 implementation)

Done:

- Task 1: `CostProvider` + HL fee tiers + signed funding  
- Task 2: `ExplicitFillEngine` + decision schema  
- Task 3: offline `PaperSession`  
- Task 4: `paper-run` daemon + warm-up + live bar poll  
- Task 5: sandbox shadow flag end-to-end; full offline suite; HANDOFF → Phase 4 design  

**Not done (Phase 4):** order book, ML wire, live exec, real sandbox client, TUI/GUI.
