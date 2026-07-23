# HANDOFF — hypervector

**Saved:** 2026-07-23 — **Phase 5 design + plan approved.** **Next session: execute Phase 5 TUI plan** (`hypervector-tui`).  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main` (start work on `feat/phase5-tui`)  
**HEAD:** check `git log -1` (docs for design/plan may be uncommitted)  
**Working tree:** may include uncommitted design/plan docs — commit before implementation if clean history preferred. **Local only — not pushed** unless Albert requests.

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
| Phase **5 design** (TUI) | **Approved** |
| Phase **5 plan** | **Ready to execute** |
| Phase **5 implementation** | **NEXT SESSION** |
| 1-page GUI | **Deferred** until TUI complete + holistic review/test |
| neural-trader / `@neural-trader/*` | **Rejected** — do not integrate |

**Outgoing session:** Design approved; plan written; handoff for **implementation**.  
**Incoming session:** **Execute** `docs/superpowers/plans/2026-07-23-phase5-tui.md` (Tasks 1–9).

---

## CLEAN SESSION START — Phase 5 TUI implementation

### Goal (one sentence)

Build **`hypervector-tui`**: read-only Ratatui condensed financial ops terminal (Ops Floor + Card Focus) over CLI/ledger truth — mode, gates, KPIs, decision tape, regime — with **tickrs-grade** visual craft; no second strategy brain; no GUI yet.

### Canonical docs

| Role | Path |
|------|------|
| **This handoff** | `HANDOFF.md` |
| **Approved design** | `docs/superpowers/specs/2026-07-23-phase5-tui-design.md` |
| **Execute this plan** | `docs/superpowers/plans/2026-07-23-phase5-tui.md` |
| CLI contract (4c) | `docs/superpowers/specs/2026-07-23-phase4c-cli-completeness-design.md` |
| Infra layout | `docs/infra-data-layout.md` |

### Locked decisions (do not reopen)

| Topic | Choice |
|-------|--------|
| Name | **`hypervector-tui`** (not “GOAT”) |
| Stack | **Ratatui** (Rust) + crossterm |
| Control plane v1 | **Read-only** — no start/stop/arm/kill from TUI |
| Views | **Ops floor + card focus** only (max 2) |
| Regime | Visible; metrics from CLI/export shape — **no second detector** |
| Visual bar | **tickrs** for data-display craft; btop/k9s for packing/mode |
| Data | `data/paper/`, `data/live/` + CLI JSON; no parallel truth DB |
| GUI | **Deferred** post holistic TUI+CLI acceptance |
| Live / paper safety | Paper never orders; live fail-closed; no secrets on screen |
| Network | Mainnet only |

### Bootstrap

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb
git log -6 --oneline
# recommended:
git checkout -b feat/phase5-tui
uv sync --all-extras
uv run pytest tests/ -q -m "not network"
uv run python -m hypervector status
cargo build -p hypervector-core   # existing workspace sanity
# After Task 1:
# cargo build -p hypervector-tui && cargo test -p hypervector-tui
```

### Agent checklist (implementation session)

1. Read **this HANDOFF** + **approved design** + **plan** Tasks 1–9.  
2. Use **subagent-driven-development** or **executing-plans**; work task-by-task with tests.  
3. Branch `feat/phase5-tui`; do not implement GUI.  
4. Enforce subprocess allowlist: `status`, `paper-check`, `live-check`, `paper-report`, `live-report`, `regime` only.  
5. Never place venue orders; never log secret values.  
6. Visual target: tickrs density + mode banner always obvious.  
7. End session: mark plan checkboxes; update HANDOFF (partial progress or done + acceptance gate).  
8. Do not push unless Albert asks. Do not commit `audio/`.

### Out of scope this epic

- 1-page GUI  
- TUI control plane (start/stop/arm)  
- Armed mainnet smoke (optional anytime with Albert secrets)  
- neural-trader  
- Postgres / Redis / k8s  

---

## Pipeline

```text
1/1.5 research     DONE
2 historical       DONE
3 paper feed       DONE
4a book/fills      DONE
4b shadow          DONE
4b-live F1–F4      DONE
4c CLI complete    DONE
5 design + plan    DONE (approved)
5 TUI implement    NEXT SESSION  ← execute plan
5 GUI              DEFERRED (after holistic acceptance)
```

---

## What’s working (ops today)

| Area | Command / surface |
|------|-------------------|
| Status inventory | `hypervector status` |
| Paper/shadow | `paper-check`, `paper-run`, `paper-report` |
| Live | `live-check`, `live-run`, `live-report` |
| Regime research | `hypervector regime` |
| Offline tests | `uv run pytest tests/ -q -m "not network"` |

## What’s not built yet

| Item | Notes |
|------|--------|
| **hypervector-tui** | Plan ready — implement next |
| 1-page GUI | Deferred |
| Push remote | Not done |
| Real mainnet soak | Optional; Albert secrets only |

---

## Agent notes

- **Next session title:** Execute Phase 5 — `hypervector-tui` plan Tasks 1–9.  
- Prefer HANDOFF + design + plan over agentmemory for phase status.  
- Plan stages: 5a scaffold/floor → 5b tape/KPI → 5c regime/focus → 5d polish/tests → gate.

---

## Outgoing summary

**Phase 5 design approved; implementation plan written.**  

**Next human/agent:** Checkout `feat/phase5-tui` and **execute** `docs/superpowers/plans/2026-07-23-phase5-tui.md` until Task 9 verification, then stop for Albert visual + holistic acceptance before any GUI work.
