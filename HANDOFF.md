# HANDOFF — hypervector

**Saved:** 2026-07-23 — **4c CLI completeness done** on `feat/phase4c-cli-completeness`. 4b-live already on main. **Next: merge 4c → main; then Phase 5 design (or Albert mainnet smoke).**  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase4c-cli-completeness`  
**Not pushed** unless Albert requests.

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status

| Layer | State |
|-------|--------|
| Phase 1–4b shadow + paper A | **Done** (on main) |
| Phase **4b-live F1–F4** | **Done** (merged main `3b94008`) |
| Phase **4c** CLI completeness | **Done** (this branch) |
| Phase **5** TUI + GUI | **Next design** |
| neural-trader | **Rejected** |

---

## CLEAN SESSION START — Phase 5 or merge 4c

### Goal options

1. **Merge** `feat/phase4c-cli-completeness` → `main`  
2. **Phase 5 design** — GOAT TUI + 1-page GUI (views over ledgers; no second brain)  
3. **Armed mainnet smoke** (Albert + secrets only)

### 4c shipped

| Item | Detail |
|------|--------|
| `status` | Pipeline + command inventory + honesty (no secrets) |
| `live-report` | Symmetric to paper-report for `data/live/` |
| Honesty | phase2-check / paper-report: live submit via `live-run` |
| CLI desc | Full funnel: research → phase2 → paper → live |
| Offline | **279 passed** |

### Bootstrap

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb
uv run pytest tests/ -q -m "not network"   # ~279
uv run python -m hypervector status
uv run python -m hypervector live-check
uv run python -m hypervector paper-check
uv run python -m hypervector live-report --last 5
uv run python -m hypervector paper-report --last 5
```

### Docs

| Role | Path |
|------|------|
| 4c design | `docs/superpowers/specs/2026-07-23-phase4c-cli-completeness-design.md` |
| 4c plan | `docs/superpowers/plans/2026-07-23-phase4c-cli-completeness.md` |
| 4b-live design | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |

### Locks

- Paper/shadow never place; never import exec client into `paper/`  
- live-run requires --enabled + --i-accept-live-risk + secrets  
- max notional default 50 USD  
- TUI/GUI after CLI complete (now ready for Phase 5 design)

### Outgoing

4c complete offline. Merge then Phase 5 design is the product path; mainnet smoke is ops with Albert secrets.
