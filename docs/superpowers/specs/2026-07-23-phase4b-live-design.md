# Design: Phase 4b-live (real mainnet submit)

**Date:** 2026-07-23  
**Status:** **F1–F4 Done** (branch `feat/phase4b-live-f2-exec-client`). 4b-live code complete; merge + optional mainnet soak next.  
**Depends on:** Phase 4b shadow (shipped + soak PASS), paper completeness slice A  

## Intent

Flip from **shadow dry-run** to **real Hyperliquid mainnet execution** with:

- Same alpha / sizing / fill-model *intent* path as paper-shadow  
- Ledger under **`data/live/`** only (never paper root for live fills)  
- Secrets **required** and fail-closed  
- Hard size caps + kill switch  
- Explicit arm (cannot “accidentally” submit)

## Locked product decisions (do not reopen)

| Topic | Choice |
|-------|--------|
| Network | **Mainnet only** (no testnet path) |
| Alpha | Same export + strategy path as paper (process-over-asset) |
| Paper path | Unchanged; still no submit |
| Live ledger | **`data/live/`** only; refuse paper writes from live engine |
| Secrets | Wallet + API key env required to start live |
| Default | `live.enabled=false`; default CLI remains paper/shadow |

## Architecture

```text
export + configs
       │
       ▼
  live-run (explicit arm + secrets)
       │
       ├─ same warm-up + bar feed as paper (mainnet REST)
       ├─ strategy intent → size (with live max notional cap)
       ├─ OrderIntent (submit_enabled=true only when armed)
       ├─ LiveExecClient.place_market(...)  → venue
       │       └─ on ack: submitted=true + venue_order_id
       │       └─ on reject: submitted=false + error stamped
       └─ append_live_decision → data/live/decisions/
```

**Separation:** `append_paper_decision` never writes live; `append_live_decision` never writes paper.

## Staged delivery

| Stage | Deliverable | Submit? |
|-------|-------------|---------|
| **F1 foundation** | Live layout paths, live ledger, LivePolicy (secrets/caps/arm), CLI surface flags, tests | **No** |
| **F2 client** | `LiveExecClient` protocol + HL adapter (real SDK) behind flag | Yes only when armed |
| **F3 daemon** | `live-run` reuses paper daemon shell with live engine + ledger | Yes when armed |
| **F4 kill** | stop-file / signals cancel open; refuse start if unarmed | Yes cancel path |

**F1–F4 shipped.** Kill path: best-effort `cancel_all` on stop after live phase armed.

## Requirements (testable)

| Tag | Shall |
|-----|--------|
| SRS_HV4L_LEDGER | Live decisions append only under `data/live/decisions/`; refuse paper root |
| SRS_HV4L_SEPARATE | Paper path still refuses live writes (regression) |
| SRS_HV4L_SECRETS | Live start **must** fail if wallet/API env missing |
| SRS_HV4L_ARM | Live submit requires config `live.enabled` **and** explicit CLI arm flag |
| SRS_HV4L_CAPS | Live policy enforces max notional (and/or max qty) before place |
| SRS_HV4L_MAINNET | Network stamped `mainnet`; no testnet URL |
| SRS_HV4L_SUBMITTED | Decision rows stamp `submitted` from venue outcome (false until ack) |
| SRS_HV4L_PAPER_SAFE | Default paper-run / shadow path still never constructs exec client |

## Live policy (v1)

```text
env required:
  HYPERVECTOR_HL_WALLET_ADDRESS
  HYPERVECTOR_HL_API_PRIVATE_KEY

config [live]:
  enabled = false                 # must flip true for live-run
  max_notional_usd = 50.0         # hard cap v1 (tiny default)
  require_arm_flag = true

CLI:
  live-check   → readiness (no secrets values)
  live-run ... --i-accept-live-risk   # arm; without flag refuse
```

## Kill switch (v1 design; F4)

- SIGINT/SIGTERM + `--stop-file` stop the loop  
- On stop when live armed: best-effort cancel open orders via exec client  
- Foundation may only define the interface + stop hooks without network cancel  

## Non-goals (still)

- Testnet  
- TUI/GUI  
- Full Nautilus TradingNode as hard requirement  
- Shared paper/live ledgers  
- Metalabel default-on  

## Success bar (full 4b-live later)

1. Offline tests for ledger/policy/arm without network  
2. Armed live-run places **only** when secrets + arm + enabled  
3. Decisions under `data/live/` with honest `submitted`  
4. Paper/shadow suite still green; structural no-submit on paper path  

## Success bar (F1 foundation — this slice)

1. `data/live/decisions` layout + `append_live_decision`  
2. LivePolicy fail-closed secrets + arm + cap checks (pure)  
3. `live-check` CLI readiness JSON (no secret values)  
4. Offline suite green; paper path unchanged  
