# Design: Paper Completeness (pre-live slice A)

**Date:** 2026-07-23  
**Status:** Approved by scope choice (Albert: option A)  
**Phase:** Pre-4b-live hardening — **no venue submit**

## Intent

Make dry-run paper/shadow **ops-complete and honest** before any live wiring:

1. Summarize real decision ledgers via CLI (`paper-report`)
2. Fix stale CLI copy that claims paper is “not implemented”
3. Encode an **acceptance matrix** as offline tests driving real paper entry points

## Non-goals

- Live submit, `data/live/` trading, kill switch for capital  
- userFees, real Nautilus sandbox client, WS feed  
- Full 4c CLI epic beyond paper ops honesty  
- TUI/GUI  

## Architecture

```text
decisions.jsonl (paper root only)
        │
        ▼
  summarize_paper_decisions()   # pure
        │
        ▼
  paper-report CLI  → JSON summary
```

`paper-run` / `paper-check` unchanged in semantics; report is read-only.

## Requirements

| Tag | Shall |
|-----|--------|
| SRS_HVPC_REPORT | `paper-report` reads `data/paper/decisions/decisions.jsonl` under `--data-root` (or `--path`) and prints counts for execution_mode, submitted, network, fill models, fallbacks, actions, order_intent submit flags, last N market rows |
| SRS_HVPC_NO_LIVE | Report path must refuse reading under `live/` as the paper decisions source; live dir file count may be reported as 0/expected |
| SRS_HVPC_CLI_HONEST | phase2-check/run must not claim paper dry-run is missing; point to `paper-run`; live submit still not implemented |
| SRS_HVPC_MATRIX | Offline tests prove: shadow default stamps, forced paper mode, order_intent always submit_enabled=false, no live writes, stop-file / max-live-bars / metalabel flags wire into daemon |

## Success bar

1. Offline suite green  
2. `paper-report` on fixture ledger matches hand-counted counters  
3. phase2 CLI no longer prints blanket “paper/live not implemented” without distinguishing dry-run  
4. HANDOFF documents paper-complete slice A done; 4b-live still next for real capital  

## Verification

- Unit: `summarize_paper_decisions` on synthetic JSONL  
- CLI: `main(["paper-report", ...])`  
- Matrix: daemon offline with fixture OHLCV for mode/intent/live barriers  
