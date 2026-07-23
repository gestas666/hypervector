# HANDOFF — hypervector

**Saved:** 2026-07-23 — **4b-live F1–F3 done** (ledger, policy, exec client, `live-run`). Branch `feat/phase4b-live-f2-exec-client`. **Next: F4 kill/cancel.** Neural-trader rejected. Paper/shadow still never constructs exec client.  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase4b-live-f2-exec-client`  
**HEAD tip:** see `git log -1` (F3 commit after F2 `ea855b7`)  
**Working tree:** commit F3; **not pushed** unless Albert requests.

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1–4b shadow + paper completeness A | **Done** |
| Phase **4b-live F1** foundation | **Done** |
| Phase **4b-live F2** exec client | **Done** |
| Phase **4b-live F3** live-run | **Done** |
| Phase **4b-live F4** kill/cancel | **NEXT** |
| Phase 4c / 5 | Later |
| neural-trader | **Rejected** |

**Outgoing:** F3 `live-run` fail-closed; warm-up never places; live phase places via mockable client; decisions under `data/live/`.  
**Incoming:** **F4** — stop-file/signals best-effort cancel open orders; refuse start if unarmed (already true).

---

## CLEAN SESSION START — 4b-live F4 (kill switch)

### Goal

On stop (SIGINT/SIGTERM/`--stop-file`) when live armed: best-effort cancel open orders via exec client; document interface + offline tests with mock cancel.

### Spec / plan

| Doc | Path |
|-----|------|
| Design | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |
| Plan | `docs/superpowers/plans/2026-07-23-phase4b-live.md` |

### F3 shipped — acceptance met

1. `live-run` requires `--enabled` + `--i-accept-live-risk` + secrets env.  
2. Constructs exec client only after `LivePolicy.require_start()`.  
3. Warm-up: synthetic position, `place_attempted=false`, no transport calls.  
4. Live phase: `place_market` via client; stamp `submitted` / `venue_order_id` / `submit_error`.  
5. Decisions only under `data/live/decisions/`; paper path unchanged.  
6. Offline suite with mock transport; paper no-submit regression green.  
7. Qty scaled to `max_notional_usd` (default 50).

### F4 acceptance (next)

1. `LiveExecClient` (or extension) exposes `cancel_all` / cancel open (mockable).  
2. Daemon stop path calls cancel when place was armed.  
3. Offline tests: stop triggers cancel once; unarmed path never cancels.  
4. Paper path still clean.

### Bootstrap

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb
uv run pytest tests/ -q -m "not network"   # ~269+
uv run python -m hypervector live-check
# → submit_wired=true, can_start=false default
# live-run (NEVER without Albert-approved secrets):
# uv run python -m hypervector live-run --path data/exports/<id> \
#   --enabled --i-accept-live-risk --max-live-bars 1
```

### Key F3 surfaces

| Path | Role |
|------|------|
| `src/hypervector/live/engine.py` | LiveFillEngine + live order intent |
| `src/hypervector/live/session.py` | LiveSession alpha path |
| `src/hypervector/live/runner.py` | `start_live_daemon` |
| `src/hypervector/live/exec_client.py` | F2 place client |
| `src/hypervector/cli.py` | `live-run` |
| `tests/test_live_run.py` | F3 offline suite |

### Locks (unchanged)

- Mainnet only; paper/shadow no submit  
- Default `live.enabled=false`  
- Max notional default **50** USD  
- Same path paper → live (client + ledger root flip)

### Agent checklist (F4)

1. Read HANDOFF + design/plan.  
2. Offline green ~269+.  
3. F4 only — cancel on stop.  
4. Never place from paper/shadow.  
5. Mock cancel offline; no real mainnet without Albert.

---

## Pipeline

```text
… → 4b shadow DONE → 4b-live F1–F3 DONE → F4 kill NEXT → 4c → 5
```

## Verify

```bash
uv run pytest tests/ -q -m "not network"
# Expected: 269+ passed
uv run python -m hypervector live-check
uv run pytest tests/test_live_run.py tests/test_paper_no_submit.py -q
```

## Outgoing summary

| Arc | Status |
|-----|--------|
| F2 | Protocol + HL adapter + factory gates |
| F3 | live-run + live ledger + warm/live place split |
| Offline | **269 passed** |

**Next:** F4 kill/cancel. **Not done:** merge/push, real mainnet soak with secrets, 4c/5.
