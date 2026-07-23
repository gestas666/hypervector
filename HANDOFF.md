# HANDOFF — hypervector

**Saved:** 2026-07-23 — **4b-live F1–F4 merged to `main`** (`3b94008`). **Next: optional armed mainnet smoke (Albert); then 4c / 5.** Neural-trader rejected.  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main`  
**HEAD:** `3b94008` Merge branch 'feat/phase4b-live-f2-exec-client' (4b-live F2–F4); docs tip may be later  

**Local only — not pushed** unless Albert requests.

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1–4b shadow + paper completeness A | **Done** |
| Phase **4b-live F1** foundation | **Done** |
| Phase **4b-live F2** exec client | **Done** |
| Phase **4b-live F3** live-run | **Done** |
| Phase **4b-live F4** kill/cancel | **Done** |
| Phase **4c** CLI completeness | **Partial** (paper-report + live-check + live-run); full epic later |
| Phase **5** TUI + GUI | **Not started** |
| neural-trader | **Rejected** |

**Outgoing:** 4b-live merged to main; offline 272 passed; live-check refuse-by-default.  
**Incoming:** Optional Albert-approved mainnet smoke; then 4c CLI completeness or Phase 5 design.

---

## CLEAN SESSION START — after 4b-live merge

### Goal options (pick one)

1. ~~**Merge** to main~~ **Done** (`3b94008`).  
2. **Armed mainnet smoke** (Albert only): tiny notional, secrets + arm + enabled, short `--max-live-bars`.  
3. **4c CLI completeness** epic.  
4. **Phase 5** TUI/GUI design (after 4c preferred).

### Spec / plan (4b-live closed)

| Doc | Path |
|-----|------|
| Design | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |
| Plan | `docs/superpowers/plans/2026-07-23-phase4b-live.md` (F1–F4 **Done**) |

### 4b-live shipped summary

| Stage | Deliverable |
|-------|-------------|
| F1 | Live ledger + LivePolicy + `live-check` |
| F2 | `LiveExecClient` + HL adapter + factory gates; `submit_wired=true` |
| F3 | `live-run`: warm no-place → live place; `data/live/` decisions; honest `submitted` |
| F4 | Stop path `cancel_all` best-effort; `cancel_attempted` / `cancel_ok` on result |

### Bootstrap

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb   # expect main @ 3b94008 (or later handoff tip)
uv run pytest tests/ -q -m "not network"   # ~272+
uv run python -m hypervector live-check
# → submit_wired=true, can_start=false, start_gate=refused
uv run python -m hypervector paper-check
# live-run only with Albert approval + secrets:
# uv run python -m hypervector live-run --path data/exports/<id> \
#   --enabled --i-accept-live-risk --max-live-bars 1 --max-notional-usd 50
```

### Key surfaces

| Path | Role |
|------|------|
| `src/hypervector/live/policy.py` | Fail-closed secrets/arm/caps |
| `src/hypervector/live/ledger.py` | `data/live/decisions` only |
| `src/hypervector/live/exec_client.py` | place_market + cancel_all |
| `src/hypervector/live/engine.py` | LiveFillEngine (warm vs live phase) |
| `src/hypervector/live/session.py` | LiveSession alpha |
| `src/hypervector/live/runner.py` | start_live_daemon + kill cancel |
| `src/hypervector/cli.py` | live-check / live-run |
| `tests/test_live_*.py` | Offline suite |

### Locks

- Mainnet only; default `live.enabled=false`  
- Paper/shadow never place; never import exec client into `paper/`  
- Max notional default **50** USD  
- Production place/cancel needs optional `hyperliquid-python-sdk` + `eth_account`  
- Offline tests always inject mock transport  

### Agent checklist

1. Do not re-open 4b-live F1–F4 unless bugs.  
2. Prefer merge/verify before 4c/5.  
3. Never real mainnet without Albert secrets + explicit arm.  
4. Update HANDOFF after any merge or soak.

---

## Pipeline

```text
1/1.5 research → 2 historical → 3 paper → 4a book → 4b shadow → 4b-live F1–F4 DONE
→ 4c CLI complete → 5 TUI/GUI
```

## Verify

```bash
uv run pytest tests/ -q -m "not network"
uv run pytest tests/test_live_run.py tests/test_live_exec_client.py tests/test_paper_no_submit.py -q
uv run python -m hypervector live-check
```

## Outgoing summary

| Arc | Status |
|-----|--------|
| 4b-live F1–F4 | **Complete + merged to main** |
| Offline | **272 passed** |
| Push remote | Not done |
| Real mainnet soak | Not done (needs Albert) |

**Next human decision:** mainnet smoke? 4c? push?
