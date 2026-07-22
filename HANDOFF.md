# HANDOFF — hypervector

**Saved:** 2026-07-22 (evening)  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main`  
**HEAD (last commit):** `b83b791` — Phase 3 paper complete (funding fix + offline pass notes)  
**Working tree at handoff write:**

| Path | State |
|------|--------|
| `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md` | **Untracked** — design approved |
| `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md` | **Untracked** — plan ready |
| `HANDOFF.md` | **Modified** — this file |
| `audio/` | Untracked — ignore |

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1 / 1.5 research | **Done** |
| Phase 2 actor + historical + metalabeler process | **Done** (plan closed) |
| Phase 3 paper design + plan + code | **Done** (5/5 + funding fix) |
| Phase **4a design** | **Approved / locked** |
| Phase **4a plan** | **Ready — Tasks 1–6 all pending code** |
| Phase 4b live / 4c CLI | **Not started** (separate designs later) |
| Phase 5 TUI + 1-page GUI | **Not started** (was old 4d/4e) |

**Outgoing session:** Design + plan only. **No Phase 4a code yet.**  
**Incoming session:** **Subagent-driven implementation** of Phase 4a plan Tasks 1→6.

---

## CLEAN SESSION START — Phase 4a implement (subagent-driven)

### Goal (one sentence)

Execute `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md` task-by-task with **subagent-driven-development**: honest paper fills (book + staged L2 walk) then optional meta-label **scale-only** conviction — no live orders, no Phase 3 rewrite, no TUI/GUI.

### Skills to load (in order)

1. **using-superpowers** (skill-first)  
2. **subagent-driven-development** (REQUIRED execution mode — Albert chose this; clean session)  
3. **engineering-software** (testable requirements, verification vs validation)  
4. **ml-for-algo-trading** (point-in-time features, fill realism, meta-label ≠ primary signal)  
5. Optional: **test-driven-development** per plan step  

Do **not** re-run brainstorming or rewrite the design unless Albert asks. Do **not** use the blog “LightGBM is the primary buy/sell brain” architecture — product path is meta-label **scale only**.

### Bootstrap commands

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb
git log -3 --oneline
uv sync --all-extras
uv run pytest tests/ -q -m "not network"
# Baseline: Phase 3 offline suite green (was ~170 passed). If red, fix before Task 1.
```

### First commits (recommended before Task 1 code)

Design + plan + HANDOFF are uncommitted. Either:

```bash
# Option A — docs-only commit first (clean history)
git add docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md \
        docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md \
        HANDOFF.md
git commit -m "docs: Phase 4a design + plan for book fills and meta-label wire"
```

…or include them with Task 1 if Albert prefers fewer commits. **Do not commit `audio/`.**

### Agent checklist (strict)

1. Read **this HANDOFF** + Phase 4a **design** + Phase 4a **plan** (sections: Global Constraints, File map, Task N).  
2. Confirm offline baseline green.  
3. Invoke **subagent-driven-development**: one subagent per plan task; two-stage review between tasks.  
4. Start at **Task 1** only (FillModel extract). Mark plan checkboxes as done.  
5. After each task: tests for that task green + commit as plan specifies.  
6. **Never** implement Task 5 (metalabel) before Tasks 1–4 fill path is green.  
7. **Never** place venue orders; **never** write `data/live/`.  
8. End session: update this HANDOFF task table + HEAD; leave clear next task id.

### Phase 4a task board (implement these)

| Task | Deliverable | Status |
|------|-------------|--------|
| **1** | `FillModel` protocol + `bar_close` extraction; engine delegates; no regression | **Pending** |
| **2** | `BookSnapshot` + HL L2 REST `BookFeed` + fixture/tests | **Pending** |
| **3** | `top_bps_v1` + `select_fill_model` stale/missing → logged fallback | **Pending** |
| **4** | `l2_walk_v1` VWAP + shortfall; preferred when book fresh | **Pending** |
| **5** | `ConvictionProvider` meta-label scale-only (default **off**) + FeatureBuilder | **Pending** |
| **6** | CLI/config/`paper-check` surface + full offline verify + HANDOFF | **Pending** |

**Plan path (source of truth for steps/code):**  
`docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md`

**Design path (locks + SRS tags):**  
`docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md`

### Architecture (do not reopen)

```text
export + configs → paper daemon (Phase 3 shell — Approach 1)
HL bars → HypervectorStrategy (alpha unchanged)
HL L2 book → BookFeed → BookSnapshot
FillModel: bar_close_slippage_v1 | top_bps_v1 | l2_walk_v1
  selection: prefer l2 when book fresh; else fallback + fill_fallback_reason
ExplicitFillEngine → data/paper/ (execution_mode=paper)

After fills green (Task 5):
  Metalabeler p ∈ [0,1] → conviction = p (scale only, no skip floor)
  → existing risk_pct_from_conviction / position_size_frac
  default metalabel OFF; failure → fallback_fixed
```

### Locks (Albert approved — do not reopen without him)

| Topic | Choice |
|-------|--------|
| +EV package | Book + honest fills **before** metalabel; L2 walk destination |
| Fill delivery | Staged: extract bar_close → top_bps → **l2_walk_v1** preferred |
| Fallback | `bar_close_slippage_v1` if book missing/stale; **log reason, never silent** |
| `max_book_age_ms` | **3000** default |
| Meta-label policy | **Scale only** (`conviction = p`); **no skip floor** |
| Meta-label default | **Off** until L2 path verified |
| Meta-label fail | `conviction_source=fallback_fixed` |
| Leverage | **Not** a second model — existing risk band only |
| Host | Thin paper shell (not full Nautilus node in 4a) |
| Book transport v1 | Public HL **REST** L2 (`l2Book`); WS later |
| Live / TUI / GUI | **Out of scope** (4b / Phase 5) |
| Blog VBT+LGBM primary classifier | **Not** the product path |

### Naming (for commits/docs)

- Pattern name: **meta-labeling** (secondary model scores strength; primary signal stays strategy/params).  
- Not: “LightGBM predicts long/short as the live brain.”

### Success bar (4a done)

1. Offline suite green with bar-close path (Phase 3 no regression).  
2. Golden book tests: top_bps + l2 VWAP + shortfall + stale fallback.  
3. Preferred fill `l2_walk_v1` when book fresh.  
4. Metalabel optional; default fixed conviction.  
5. `paper-check` reports book/fill/metalabel surface; `live.enabled` false.  
6. No `data/live/` writes; no venue orders.

### Out of scope this implementation pass

- 4b live exec, kill switch, secrets-required trading  
- 4c full CLI completeness epic  
- Phase 5 GOAT TUI / 1-page GUI  
- userFees (optional DG — only if free during Task 6)  
- ML training / LEXLB primary-signal notebook architecture  
- Reopening Phase 3 plan tasks  

### Key code surfaces (today, before 4a)

| Path | Role |
|------|------|
| `src/hypervector/paper/fills.py` | `ExplicitFillEngine` — **Task 1** extracts fill model from here |
| `src/hypervector/paper/session.py` / `runner.py` | Bar session + daemon — later pass book + conviction |
| `src/hypervector/paper/costs.py` | Fees/funding; `fill_model_id` on snapshot |
| `src/hypervector/data/hl.py` | Candles REST — **Task 2** adds L2 helper |
| `src/hypervector/ml/metalabel.py` | Inference process — wire in **Task 5** only |
| `src/hypervector/sweep/sizing.py` | `risk_pct_from_conviction` — reuse, don’t fork |
| `src/hypervector/cli.py` | paper-check / paper-run — **Task 6** surface |

### Prompt seed for clean session (paste-friendly)

```text
Read HANDOFF.md. Load using-superpowers + subagent-driven-development +
engineering-software + ml-for-algo-trading. Execute Phase 4a plan
docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md
subagent-driven, Task 1 first. Do not redesign. Do not touch live/TUI.
Commit design/plan/HANDOFF if still untracked, then implement.
```

---

## Docs map (canonical)

| Role | Path |
|------|------|
| **Phase 4a design (APPROVED)** | `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md` |
| **Phase 4a plan (READY — execute)** | `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md` |
| Phase 3 plan (COMPLETE) | `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` |
| Phase 3 design (approved) | `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md` |
| Pipeline / paper identity lock | `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` |
| Phase 1 design | `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` |
| Phase 2 plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md` |
| Phase 1.5 + prep plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md` |
| Infra I2 | `docs/infra-data-layout.md` |
| This handoff | `HANDOFF.md` |

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
Phase 4a     Book + staged L2 fills + meta-label scale-only         ← DESIGN LOCKED; plan next
Phase 4b     Live exec flip + kill switch
Phase 4c     CLI completeness
Phase 5      GOAT TUI + 1-page GUI
```

| Phase | Role | State |
|-------|------|--------|
| **1 / 1.5** | Research, costs, risk, export | **Done** |
| **2** | Event-driven historical sim | **Done** |
| **3 paper** | Live feed + synthetic fills + paper ledger | **Done** (offline verified) |
| **4a** | Book, impact fills, metalabel wire | **Design locked** |
| **4b–4c** | Live + CLI | Later design |
| **5** | TUI + GUI | Later design |

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

## Phase 4 / 5 epic

| Track | Deliverable | State |
|-------|-------------|--------|
| **4a** | Order book + staged L2 fills; meta-label scale-only; optional userFees | **Design locked** — plan/implement next |
| **4b** | Live exec flip, secrets required, `data/live/`, kill switch | Later design |
| **4c** | CLI completeness — every capability consistent | Later design; gate for UX |
| **5a** | **GOAT TUI** — best-in-class terminal ops console | Phase 5 |
| **5b** | **1-page GUI** monitoring dashboard | Phase 5 |

**4a design:** `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md`  

**UX sequencing:** **4c CLI complete → then Phase 5 TUI + GUI.**  
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
