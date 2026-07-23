# HANDOFF — hypervector

**Saved:** 2026-07-23 — **Phases 1–4c done on `main`.** **Next session: Phase 5 design only** (GOAT TUI + 1-page GUI). No product code until design approved.  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main`  
**HEAD:** `77f11af` (docs pin after 4c merge `5f483aa`; 4b-live merge `3b94008`)  
**Working tree:** clean expected. **Local only — not pushed** unless Albert requests.

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1 / 1.5 research | **Done** |
| Phase 2 historical Nautilus | **Done** |
| Phase 3 paper live-feed | **Done** |
| Phase 4a book + fills + metalabel | **Done** |
| Phase 4b mainnet shadow | **Done** + soak PASS |
| Paper completeness A | **Done** |
| Phase **4b-live F1–F4** | **Done** (merged main) |
| Phase **4c** CLI completeness | **Done** (merged main) |
| Phase **5** GOAT TUI + 1-page GUI | **NEXT — design session** |
| neural-trader / `@neural-trader/*` | **Rejected** — do not integrate |

**Outgoing session:** 4c merged; CLI gate for UX closed.  
**Incoming session:** **Phase 5 design** (spec + plan; no implementation until Albert approves).

---

## CLEAN SESSION START — Phase 5 design

### Goal (one sentence)

Produce an approved **Phase 5 design** for a **GOAT TUI** (terminal ops console) and a **1-page GUI** monitoring dashboard that are **views over the same ledger/CLI truth** — never a second strategy or execution brain.

### Process (required)

Use **superpowers** process skills in order:

1. **brainstorming** — explore Albert’s intent (TUI-first vs GUI-first, stack prefs, must-have panels).  
2. **writing-plans** / project design loop — write:
   - `docs/superpowers/specs/YYYY-MM-DD-phase5-tui-gui-design.md`
   - `docs/superpowers/plans/YYYY-MM-DD-phase5-tui-gui.md`  
3. Present design for **Albert approval** before any implementation.  
4. Optional: engineering-software (requirements shalls, verification vs validation, traceability tags).

Do **not** start coding TUI/GUI widgets in the design session unless Albert explicitly says implement.

### Locked product decisions (do not reopen without Albert)

| Topic | Choice |
|-------|--------|
| UX sequencing | **CLI complete first** (4c **done**) → then TUI + GUI |
| Data model | **Same ledgers** as CLI: `data/paper/`, `data/live/`; no parallel DB of truth |
| Brain | **No second strategy** — UI does not re-run alpha; shows decisions/status |
| Mode visibility | `execution_mode` (**shadow / paper / live**) always obvious |
| Paper/shadow | **Never** place venue orders |
| Live | Fail-closed: enabled + arm + secrets; max notional default **50** USD |
| Network | **Mainnet only** — no testnet path |
| CLI | Remains **scriptable**; TUI/GUI do not replace CLI |
| neural-trader | **Rejected** |

### Prior UX notes (from Phase 3 design — expand in Phase 5)

From `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`:

| Surface | Intent |
|---------|--------|
| **GOAT TUI** | Best-in-class terminal console — status, decisions, PnL, mode banner, run control, kill switch — not a thin CLI wrapper |
| **1-page GUI** | Single-page monitor: paper/live identity, positions, decisions, costs/funding, health; same ledger truth as TUI/CLI |

### CLI / data truth the UI must consume (do not invent new sources)

| Source | Path / command |
|--------|----------------|
| Ops inventory | `hypervector status` |
| Paper identity | `paper-check` → `data/paper/` |
| Paper decisions | `paper-report` → `data/paper/decisions/decisions.jsonl` |
| Live readiness | `live-check` (no secret values) |
| Live decisions | `live-report` → `data/live/decisions/decisions.jsonl` |
| Paper/shadow daemon | `paper-run` (default **shadow**) |
| Live daemon | `live-run` (enabled + arm + secrets) |
| Layout | `infra-init` / I2 under `--data-root` |

### Design questions to resolve with Albert (session start)

1. **TUI stack:** Textual / rich / ratatui / other?  
2. **GUI stack:** single HTML page + local server, FastAPI+htmx, Streamlit, Tauri, other?  
3. **Ship order:** TUI-first, GUI-first, or both in one epic with staged PRs?  
4. **Control plane:** read-only monitor first vs start/stop daemons + kill from UI?  
5. **Live safety:** any UI live controls still require arm flag + confirm? (recommend **yes**)  
6. **Deploy:** local-only v1 vs remote dashboard?

### Suggested design deliverables

| Artifact | Contents |
|----------|----------|
| Spec | Goals, non-goals, actors, requirements (shall/must), architecture (view-only), screens/panels, data bindings to CLI/JSONL, safety model, success bar |
| Plan | Staged tasks: e.g. 5a TUI read-only → 5b TUI control → 5c GUI monitor → 5d polish |
| RTM-lite | Map SRS tags → panels → tests |

### Bootstrap (next agent)

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb          # expect main, clean
git log -6 --oneline
uv sync --all-extras
uv run pytest tests/ -q -m "not network"   # ~279 passed
uv run python -m hypervector status
uv run python -m hypervector paper-check
uv run python -m hypervector live-check
# → submit_wired=true, can_start=false by default
```

### Agent checklist (Phase 5 design session)

1. Read **this HANDOFF** + 4c design (CLI is the contract).  
2. Confirm offline suite green on `main`.  
3. Invoke brainstorming / design skills before writing code.  
4. Write Phase 5 **spec + plan** under `docs/superpowers/`.  
5. **Stop for Albert approval** before implementation.  
6. Never place venue orders from paper path; never log secret values.  
7. End design session: update HANDOFF (design approved / awaiting approval / plan path).

### Out of scope for Phase 5 design session

- Implementing widgets / app shell (unless Albert says implement now)  
- Armed mainnet smoke (Albert secrets; optional anytime)  
- Reopening 4b-live / fill models / metalabel defaults  
- neural-trader integration  
- Postgres / Redis / k8s  

---

## Pipeline (complete → next)

```text
1/1.5 research     DONE
2 historical       DONE
3 paper feed       DONE
4a book/fills      DONE
4b shadow          DONE
4b-live F1–F4      DONE
4c CLI complete    DONE  ← UX gate closed
5 TUI + GUI        NEXT DESIGN
```

---

## Docs map (canonical)

| Role | Path |
|------|------|
| **This handoff** | `HANDOFF.md` |
| **4c design (CLI contract for UI)** | `docs/superpowers/specs/2026-07-23-phase4c-cli-completeness-design.md` |
| **4b-live design** | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |
| **4b shadow design** | `docs/superpowers/specs/2026-07-22-phase4b-mainnet-shadow-design.md` |
| **Phase 3 design (UX sequencing note)** | `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md` |
| Infra I2 | `docs/infra-data-layout.md` |

---

## What’s working (ops today)

| Area | Command / surface |
|------|-------------------|
| Status inventory | `hypervector status` |
| Paper/shadow | `paper-check`, `paper-run`, `paper-report` |
| Live | `live-check`, `live-run`, `live-report` |
| Research ladder | `history`, `regime`, `sweep-*`, `export`, `phase2-*` |
| Offline tests | `uv run pytest tests/ -q -m "not network"` (~279) |

## What’s not built

| Item | Notes |
|------|--------|
| GOAT TUI | Phase 5 |
| 1-page GUI | Phase 5 |
| Push remote | Not done |
| Real mainnet soak | Optional; Albert secrets only |

---

## Agent notes

- **Next session title:** Phase 5 design — TUI + 1-page GUI.  
- Prefer HANDOFF + 4c/3 specs over agentmemory for phase status.  
- Do not commit `audio/`. Do not push unless asked.  
- Feature branches for implementation later: e.g. `feat/phase5-tui`, `feat/phase5-gui`.  

---

## Outgoing summary

**Phases 1–4c closed on main.** CLI is the honest ops surface.  

**Next human/agent:** Start Phase 5 **design** (brainstorm → spec → plan → Albert approve) before any TUI/GUI code.
