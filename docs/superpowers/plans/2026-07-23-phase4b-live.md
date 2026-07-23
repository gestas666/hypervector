# Plan: Phase 4b-live

**Spec:** `docs/superpowers/specs/2026-07-23-phase4b-live-design.md`  
**Constraint:** Foundation tasks do **not** place venue orders.

## Tasks

| # | Deliverable | Status |
|---|-------------|--------|
| F1a | Design + plan | **Done** |
| F1b | Infra live/decisions + live/ledger paths | **Done** |
| F1c | `live/ledger.py` append_live_decision | **Done** |
| F1d | `live/policy.py` secrets/arm/caps | **Done** |
| F1e | CLI `live-check` | **Done** |
| F1f | Tests + HANDOFF | **Done** |
| **F2a** | `LiveExecClient` Protocol + `PlaceResult` | **Next session** |
| **F2b** | HL mainnet adapter (place market only); secrets from env | **Next** |
| **F2c** | Factory: construct only after `LivePolicy.require_start()` | **Next** |
| **F2d** | Offline tests with mock transport; paper no-submit regression | **Next** |
| **F2e** | `live-check` / readiness reflects client wired vs can_start | **Next** |
| F3 | `live-run` daemon + live ledger writes | After F2 |
| F4 | Kill switch cancel-open on stop | After F3 |

### F2 notes for implementer

- **Mainnet only** — same host family as `HL_INFO_URL`; no testnet.  
- Prefer thin REST/SDK wrapper under `src/hypervector/live/`; do **not** import into `paper/`.  
- `submit_enabled=true` only on intents that actually go through armed client (F3 may own intent stamping).  
- Default config remains `live.enabled=false`.  
- Offline suite must stay green without secrets present.
