# HANDOFF — hypervector

**Saved:** 2026-07-23 — **Phase 5 TUI merged to main + pushed to GitHub.** Awaiting Albert visual + holistic acceptance.  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main` (tracks `origin/main`)  
**Remote:** `https://github.com/gestas666/hypervector.git`  
**HEAD:** check `git log -1`  
**Working tree:** clean after merge+push.

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
| Phase **5 plan** | **Executed** (Tasks 1–9) |
| Phase **5 implementation** | **Done — in review** (visual + holistic gate) |
| 1-page GUI | **Deferred** until TUI holistic acceptance |
| neural-trader / `@neural-trader/*` | **Rejected** — do not integrate |

**Outgoing session:** Phase 5 `hypervector-tui` fully implemented and automated QA green.  
**Incoming session:** Albert visual sign-off (tickrs bar) + holistic CLI+TUI acceptance; then merge `feat/phase5-tui` → main. GUI still deferred.

---

## Phase 5 TUI — what shipped

### Binary

```bash
cargo run -p hypervector-tui -- --data-root data
# or
./target/release/hypervector-tui --data-root data
```

| Flag | Default | Notes |
|------|---------|--------|
| `--data-root` | `data` | Same layout as CLI (I2) |
| `--refresh-ms` | `1000` | Hot path tape/status refresh |
| `--tape` | `auto` | `paper` \| `live` \| `auto` (mtime) |

### Views (exactly 2)

1. **Ops Floor** — mode banner, gates, KPI (big-text + sparkline), regime, decision tape, health footer  
2. **Card Focus** — Enter on focused card; Esc → floor  

Keys: `Tab`/arrows focus · `Enter` expand · `Esc` floor · `r` refresh · `R` regime · `p`/`l`/`a` tape · `?` help · `q` quit  

### Safety

- Read-only: CLI probe allowlist only `status|paper-check|live-check|paper-report|live-report|regime`  
- Never spawns `paper-run` / `live-run`  
- No secret values rendered (presence bools only)  
- Paper/live path refuse for decision tape  
- Terminal restored via `ratatui::restore()` on quit  

### Verification (this session)

```text
cargo test -p hypervector-tui     → 28 passed (unit + integration + UI banner)
cargo build -p hypervector-tui --release → ok
uv run pytest tests/ -q -m "not network" → 279 passed, 4 deselected
uv run python -m hypervector status → ok, honesty flags intact
```

### Manual (Albert)

- [ ] Mode banner obvious for paper vs live tape  
- [ ] Cold data-root empty states (no panic)  
- [ ] Sample decisions appear on tape  
- [ ] Regime card after `R` or fixture  
- [ ] Focus Enter/Esc only two views  
- [ ] Quit restores terminal  
- [ ] No secrets on screen with env secrets set  
- [ ] Visual: tickrs density / btop-k9s packing bar  

---

## Canonical docs

| Role | Path |
|------|------|
| **This handoff** | `HANDOFF.md` |
| **Approved design** | `docs/superpowers/specs/2026-07-23-phase5-tui-design.md` |
| **Plan (executed)** | `docs/superpowers/plans/2026-07-23-phase5-tui.md` |
| CLI contract (4c) | `docs/superpowers/specs/2026-07-23-phase4c-cli-completeness-design.md` |
| Infra layout | `docs/infra-data-layout.md` |

### Locked decisions (do not reopen)

| Topic | Choice |
|-------|--------|
| Name | **`hypervector-tui`** |
| Stack | **Ratatui** + crossterm |
| Control plane v1 | **Read-only** |
| Views | **Ops floor + card focus** only |
| Regime | Display only — no second detector |
| GUI | **Deferred** post holistic acceptance |
| Network | Mainnet only |

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
5 design + plan    DONE
5 TUI implement    DONE (in review / visual gate)  ← you are here
5 GUI              DEFERRED
```

---

## What’s working (ops today)

| Area | Command / surface |
|------|-------------------|
| Status inventory | `hypervector status` |
| Paper/shadow | `paper-check`, `paper-run`, `paper-report` |
| Live | `live-check`, `live-run`, `live-report` |
| Regime research | `hypervector regime` |
| **TUI monitor** | **`hypervector-tui`** (read-only) |
| Offline tests | `uv run pytest tests/ -q -m "not network"` + `cargo test -p hypervector-tui` |

## What’s not done yet

| Item | Notes |
|------|--------|
| Albert visual sign-off | Required before merge claim of “holistic complete” |
| Merge `feat/phase5-tui` | After visual OK |
| 1-page GUI | Deferred |
| Push remote | **Done** — `origin` → `gestas666/hypervector` |
| Real mainnet soak | Optional; Albert secrets only |

---

## Agent notes

- **Next session title:** Phase 5 visual acceptance + merge; then optional GUI design only if Albert reopens.  
- Prefer HANDOFF + design + plan over agentmemory for phase status.  
- Do not implement GUI until holistic TUI+CLI acceptance.  
- Do not commit `audio/`; do not push unless asked.

---

## Outgoing summary

**Phase 5 `hypervector-tui` implemented (Tasks 1–9). Automated QA green.**  

**Next human:** Run the binary, visual-check against tickrs bar, tick the manual checklist above, then merge branch when satisfied. GUI remains deferred.
