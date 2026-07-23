# Design: Phase 4c — CLI completeness

**Date:** 2026-07-23  
**Status:** Approved by sequencing lock (4c before Phase 5)  
**Depends on:** 4b-live F1–F4 merged to main  

## Intent

Make every ops capability **discoverable, honest, and consistent** on the CLI so TUI/GUI can be views over the same truth:

1. Symmetric **live-report** for `data/live/` (paper already has paper-report)  
2. **Honesty fix**: live submit is wired (`live-run`); paper/shadow still never submits  
3. **status** inventory: one JSON surface of commands + pipeline state (no secrets)  
4. Top-level CLI description matches the full funnel (not Phase-1-only copy)

## Non-goals

- Armed mainnet smoke (Albert + secrets)  
- TUI / GUI (Phase 5)  
- New trading strategies or ML  
- userFees / WS feed  

## Architecture

```text
paper decisions.jsonl  → paper-report
live  decisions.jsonl  → live-report
layout + policy + flags → paper-check / live-check / status
```

## Requirements (testable)

| Tag | Shall |
|-----|--------|
| SRS_HV4C_LIVE_REPORT | `live-report` reads live decisions under data-root (or --path) and prints counters for execution_mode, submitted, place_attempted, network, actions, sample last N |
| SRS_HV4C_LIVE_PATH | `live-report` refuses paper/ decisions path; `paper-report` still refuses live/ |
| SRS_HV4C_HONEST | phase2-check and paper-report surface live submit as implemented via `live-run`; paper path remains no_submit |
| SRS_HV4C_STATUS | `status` lists CLI commands + paper/live honesty flags without secret values |
| SRS_HV4C_DESC | Root CLI description names research → phase2 → paper/shadow → live |

## Success bar

1. Offline suite green  
2. `live-report` / `status` / honesty tests pass  
3. HANDOFF: 4c done; Phase 5 next  

## Verification

- Unit: live summarize on synthetic JSONL  
- CLI: live-report, status, phase2-check honesty  
- Regression: paper-report + no-submit barriers  
