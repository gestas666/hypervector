# HANDOFF — hypervector

**Saved:** 2026-07-23 — **4c merged to main** (`5f483aa`). 4b-live already on main. **Next: Phase 5 design (TUI + 1-page GUI).** Optional: Albert mainnet smoke / push.  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main`  
**HEAD:** `5f483aa` Merge branch 'feat/phase4c-cli-completeness'  
**Local only — not pushed** unless Albert requests.

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status

| Layer | State |
|-------|--------|
| Phase 1–4b shadow + paper A | **Done** |
| Phase **4b-live F1–F4** | **Done** (main) |
| Phase **4c** CLI completeness | **Done** (merged `5f483aa`) |
| Phase **5** TUI + GUI | **NEXT** |
| neural-trader | **Rejected** |

---

## CLEAN SESSION START — Phase 5

### Goal

Design (then implement) **GOAT TUI + 1-page GUI** as views over the same ledgers/CLI truth — not a second brain. `execution_mode` always obvious.

### Why not mainnet smoke first?

Smoke needs Albert secrets + capital risk. 4c completed the locked gate **before UX**. Phase 5 is the product path; smoke is an ops exercise anytime.

### Bootstrap

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb   # main
uv run pytest tests/ -q -m "not network"   # ~279
uv run python -m hypervector status
uv run python -m hypervector live-check
uv run python -m hypervector paper-report --last 5
uv run python -m hypervector live-report --last 5
```

### 4c surfaces (shipped)

| Command | Role |
|---------|------|
| `status` | Pipeline + command inventory + honesty |
| `live-report` | Live decisions summary (read-only) |
| `paper-report` | Paper/shadow summary (read-only) |
| `live-check` / `live-run` | Readiness / fail-closed place |
| `paper-check` / `paper-run` | Shadow default dry-run |

### Specs

| Role | Path |
|------|------|
| 4c design | `docs/superpowers/specs/2026-07-23-phase4c-cli-completeness-design.md` |
| 4b-live design | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |
| This handoff | `HANDOFF.md` |

### Locks

- Paper/shadow never place  
- live-run: enabled + arm + secrets; max notional 50 default  
- TUI/GUI are views only; CLI stays scriptable  

### Outgoing

CLI complete for ops. **Next: Phase 5 design** (brainstorm + superpowers design skill).
