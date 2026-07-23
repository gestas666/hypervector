# HANDOFF — hypervector

**Saved:** 2026-07-23 — Shadow Ops Floor implemented (probe fix + readiness + charts + demo tape).  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `main`  
**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1–4c CLI pipeline | **Done** |
| Phase 5 thin projector TUI | **Superseded** by Shadow Ops Floor |
| Probe Python resolution | **Fixed** (`.venv` / `HYPERVECTOR_PYTHON` / `uv run`) |
| Shadow Ops Floor (readiness + charts + regime auto + tape craft) | **Implemented** — agent PTY evidence green |
| Automated QA | **Green** (TUI 33 tests; pytest offline 279) |
| Visual PASS (human) | **NEXT — Albert** |
| Holistic CLI↔TUI | **Agent assist PASS**; human on-screen confirm |
| GUI | **Deferred** until Shadow Ops visual PASS |

---

## Acceptance bar (Albert — non-negotiable)

At a glance on ≥120×32:

- MODE + **DRY-RUN READY** / **LIVE REFUSED** / live danger
- Regime mix populated (not stuck on probe errors)
- Charts: price · activity · derived equity sparklines
- Ops-grade tape (time/mode/act/side/sub/qty/mark/fill)
- Read-only; no secrets; quit restores terminal

Guide: `docs/guides/acceptance-visual-and-holistic.md`  
Launch: `./target/release/hypervector-tui --data-root data`

---

## What shipped (Shadow Ops)

- `crates/hypervector-tui/src/read/cli_probe.rs` — launcher resolution
- `model/readiness.rs`, `model/series.rs` — dry-run chip + chart series
- Banner / gates / KPI charts / tape / regime empty states upgraded
- Demo tape: `data/paper/decisions/decisions.jsonl` (48 shadow rows) + fixture `decisions_shadow_demo.jsonl`

### Verify

```bash
cargo test -p hypervector-tui
cargo build -p hypervector-tui --release
uv run pytest tests/ -q -m "not network"
./target/release/hypervector-tui --data-root data
```

Last agent PTY markers: SHADOW OPS, DRY-RUN READY, LIVE REFUSED, regime dominant RANGE, tape n=48, no module-not-found.

---

## Locked decisions

| Topic | Choice |
|-------|--------|
| TUI role | Shadow Ops Floor (dry-run cockpit), not thin JSON mirror |
| Control plane | Still read-only (no paper-run/live-run spawn) |
| Live | Fail-closed; never arm from TUI |
| GUI | Deferred post visual PASS |
| neural-trader | Rejected |

---

## NEXT

1. Albert visual walk (V* against Shadow Ops bar)
2. Sign-off note if PASS
3. Only then reopen GUI epic
