# Phase 4b Design: Mainnet Shadow Path (hypervector)

**Date:** 2026-07-22  
**Status:** **Approved** 2026-07-22 — plan ready `plans/2026-07-22-phase4b-mainnet-shadow.md`  
**Process:** engineering-software (Hyde — requirements, RTM tags, verify vs validate) + prior Phase 3/4a locks  
**Impl skills (later):** write-clean-code; troubleshooting with think-like-a-programmer  
**Depends on:**  
- Phase 4a design `2026-07-22-phase4a-book-fills-metalabel-design.md` (shipped)  
- Phase 3 paper design `2026-07-22-phase3-paper-live-feed-design.md`  
- HANDOFF.md  

**Scope of this design:** Phase **4b only** — **mainnet shadow trading**: real Hyperliquid **mainnet** market state, live-grade compute + logs **as if** trades were real, **no venue order submit**, ledger stays under **`data/paper/`**.

**Not in this phase:** testnet, real mainnet order submit, `data/live/` writes, TUI/GUI, CLI completeness epic (4c), kill-switch for capital (no capital at risk).

---

## 1. Intent

Make the paper daemon **mainnet-honest and live-shaped** without lying via testnet and without risking capital.

**One-sentence lock:**  
Phase 4b = mainnet public market path + shadow execution mode that sizes, fills (L2 when live), fees, funding, and **logs order intents** as close as possible to a real trade — **zero HTTP order submits**.

### Why not testnet

HL testnet is **not 1:1** with mainnet (liquidity, book, fees, behavior). Validating there produces false confidence and bad promotion decisions. Shadow on **mainnet data** is the correct validation intermediate.

### Why not real submit yet

Real submit needs `data/live/`, secrets fail-closed for trading, size caps, kill switch, and ops discipline. Those are **Phase 4b-live / later** after shadow is trusted. 4b shadow proves the **path** first (Hyde: validate the right product on mainnet state without paying for requirement errors in capital).

---

## 2. Session decisions (locked)

| Topic | Choice |
|-------|--------|
| Venue universe | **Mainnet only** — **no testnet** path in 4b |
| Behavior | **Shadow**: compute + log as if real; **no venue submit** |
| Ledger | **`data/paper/`** only (Option 1) — never `data/live/` in 4b |
| Host | Extend **paper daemon shell** (Approach 1 from Phase 3/4a) |
| Fill honesty | Reuse Phase 4a: warm-up no live book; live bars prefer `l2_walk_v1` |
| Mode label | `execution_mode=shadow` on decisions (distinct from pure research paper if needed; see §6) |
| Secrets | Optional for **authenticated reads** (e.g. userFees later); **must not** unlock submit |
| Real live flip | **Out of scope** for this design’s implementation plan |

---

## 3. Phase map

```text
Phase 3   Paper: live HL bars + bar_close fills + fixed conviction     DONE
Phase 4a  Book + L2 fills + metalabel scale-only (default off)          DONE
Phase 4b  Mainnet shadow: intent log + mode + mainnet fidelity          THIS DESIGN
Phase 4b+ Real submit + data/live/ + secrets-required + kill switch     LATER DESIGN
Phase 4c  CLI completeness
Phase 5   TUI + 1-page GUI
```

---

## 4. Non-goals (4b)

- Hyperliquid **testnet** endpoints or dual-network product path  
- Placing **any** venue order (mainnet or otherwise)  
- Writing under **`data/live/`**  
- Full Nautilus `TradingNode` as a hard requirement  
- TUI / GUI  
- Making metalabel default-on  
- Training ML models  
- Committing secrets to git  
- Claiming shadow PnL = guaranteed live PnL (shadow still has model residual vs exchange match)  

---

## 5. Requirements (testable)

Format: black-box *shall* / *must*. Tags for RTM.

| Tag | Requirement |
|-----|-------------|
| SRS_HV4B_MAINNET | Shadow path **shall** use Hyperliquid **mainnet** public market endpoints for bars and L2 (same hosts as Phase 3/4a paper). |
| SRS_HV4B_NO_TESTNET | System **must not** require or default to testnet for 4b validation. |
| SRS_HV4B_NO_SUBMIT | Paper/shadow path **must not** submit create/cancel/order requests to the venue. |
| SRS_HV4B_LEDGER | Shadow decisions **shall** write only under `data/paper/`; **must** refuse `data/live/`. |
| SRS_HV4B_MODE | Every market decision row **shall** set `execution_mode` to `shadow` when running in 4b shadow mode (or document alias; see §6.2). |
| SRS_HV4B_SAME_ALPHA | Shadow **shall** recompute alpha via existing strategy/export loadout — no `signals.parquet` live brain. |
| SRS_HV4B_FILLS | Shadow **shall** use Phase 4a fill selection (prefer `l2_walk_v1` when book fresh on **live** bars; warm-up bar_close + logged fallback). |
| SRS_HV4B_INTENT | On each market action, system **shall** append a structured **order intent** payload describing what a live client would have sent (symbol, side, qty, order type, reduce_only/flags as known, ts) **without** submitting. |
| SRS_HV4B_SUBMITTED | Decision rows **shall** include `submitted=false` (or equivalent) for shadow fills. |
| SRS_HV4B_SECRETS | Presence of wallet/API env vars **must not** enable order submit in shadow mode. Secrets **must never** appear in logs or decisions. |
| SRS_HV4B_CHECK | `paper-check` (or shadow-check) **shall** report shadow/mainnet surface: mode, no_submit=true, live.enabled=false, ledger paper. |
| SRS_HV4B_PROCESS | Symbol/TF/export parameterized (process-over-asset). |
| SRS_HV4B_WARM | Historical warm-up **must not** poll live L2 (Phase 4a fix retained). |

### Design goals (not hard requirements)

- DG_HV4B_USER_FEES: optional authenticated mainnet fee tier when secrets present (read-only)  
- DG_HV4B_INTENT_SCHEMA_V1: versioned intent JSON under `intent` key for forward compatibility  
- DG_HV4B_CLI_ALIAS: `shadow-run` as alias of paper-run with mode forced  

---

## 6. Architecture

### 6.1 Context

```text
export + configs ──► paper/shadow daemon (Phase 3/4a shell)
mainnet HL bars ──► HypervectorStrategy (alpha unchanged)
mainnet HL L2  ──► BookFeed (live phase only)
                         │
                         ▼
              FillModel (4a selection)
                         │
                         ▼
              ExplicitFillEngine
                - position, fees, funding
                - order intent object (logged)
                - submitted=false
                - execution_mode=shadow
                         │
                         ▼
              data/paper/decisions|ledger
              (NO data/live/, NO venue submit)
```

### 6.2 Mode naming

| Field | Shadow 4b value | Notes |
|-------|-----------------|-------|
| `execution_mode` | `shadow` | Distinguishes from pure offline research walks if any remain `paper` |
| `submitted` | `false` | Always for 4b |
| `venue` | `hyperliquid` | Optional string |
| `network` | `mainnet` | Explicit; no testnet enum value used |

**CLI default:** `paper-run --shadow` (or config `[paper] mode = "shadow"`) forces the above. Existing offline tests may keep `execution_mode=paper` for Phase 3 compatibility **or** migrate to shadow — plan chooses one migration strategy without breaking offline suite.

**Recommendation for plan:** daemon live path defaults to `shadow`; unit tests that assert `paper` updated to accept `shadow` **or** set mode explicitly to `paper` only for pure offline fixtures.

### 6.3 Components

| Unit | Responsibility |
|------|----------------|
| `ShadowPolicy` / config | mode=shadow, network=mainnet, submit_enabled=false (hard) |
| `OrderIntent` builder | From strategy action + sized qty + symbol/TF → serializable intent dict |
| `ExplicitFillEngine` | Existing fills + merge intent + submitted flag + execution_mode |
| `BookFeed` / fill models | Unchanged from 4a |
| Ledger | Unchanged refuse-live path |
| CLI `paper-check` | Surface shadow flags |
| CLI `paper-run --shadow` | Start daemon in shadow mode |

### 6.4 Order intent (minimum schema)

Logged on each market fill decision under key `order_intent` (versioned):

```json
{
  "schema": "hv_order_intent_v1",
  "network": "mainnet",
  "venue": "hyperliquid",
  "symbol": "BTC-PERP",
  "side": "sell",
  "qty": 0.01,
  "order_type": "market",
  "time_in_force": "ioc",
  "reduce_only": false,
  "client_ts_ms": 0,
  "submit_enabled": false,
  "notes": "shadow-only; not sent"
}
```

Fields may expand later for limit/TP-SL; v1 covers market aggressive path used by paper fills today.

### 6.5 Kill switch / stop (daemon only)

Shadow has no capital risk; still support:

- SIGINT / SIGTERM  
- `--stop-file`  

No venue cancel-all required (nothing submitted).

### 6.6 Secrets

| Env | Shadow 4b |
|-----|-----------|
| `HYPERVECTOR_HL_WALLET_ADDRESS` | Optional; may enable read-only fee tier later |
| `HYPERVECTOR_HL_API_PRIVATE_KEY` | Optional; **must not** call order APIs |

Rule: **structural barrier** (Spraul) — no order-client constructor on the shadow code path; not merely a boolean around submit.

---

## 7. Data flow

```text
1. load_strategy_loadout(export, strict=True)
2. warm-up OHLCV (mainnet cache/HL) with enable_book_poll=False
   fills → bar_close + book_missing (logged)
3. arm BookFeed once; enable_book_poll for live loop
4. on each live bar:
     strategy intent → size
     build OrderIntent (submit_enabled=false)
     select FillModel (l2 if fresh else fallback)
     ExplicitFillEngine.apply → decision with mode=shadow, submitted=false, order_intent
5. funding while open (mainnet rate when refresh enabled)
6. stop → summary (counts, paper paths, mode=shadow)
```

---

## 8. CLI / config

```toml
[paper]
# 4b
mode = "shadow"                 # paper | shadow  (daemon default shadow after 4b)
preferred_fill_model = "l2_walk_v1"
max_book_age_ms = 3000
metalabel_enabled = false
# submit_enabled is NOT a user knob in 4b — always false in code

[live]
enabled = false                 # remains false; real submit later design
```

| Command | Behavior |
|---------|----------|
| `paper-check` | Report mode, network=mainnet, no_submit, ledger paper, live.enabled false |
| `paper-run --shadow` | Daemon shadow mode (default once 4b ships) |
| stop-file / signals | Unchanged |

---

## 9. Verification vs validation

| Kind | What |
|------|------|
| **Verification** | Offline tests: mode fields, intent schema present, no live path writes, warm-up no book poll, submit client absent |
| **Validation** | Mainnet soak: live bars + L2 fills when trading; intents look like real orders; no connection spam; compare shadow fills to BBO sanity |

---

## 10. Success bar (4b done)

1. Offline suite green (no Phase 3/4a regression).  
2. Daemon shadow mode: decisions under `data/paper/` with `execution_mode=shadow`, `submitted=false`, `order_intent` present on market actions.  
3. Warm-up still no live L2 on historical bars.  
4. Live phase can produce `l2_walk_v1` when book fresh (soak).  
5. `paper-check` shows shadow/mainnet/no_submit; `live.enabled` false.  
6. Grep/static guarantee: no order-submit client wired on shadow path.  
7. No testnet URLs required.

---

## 11. Out of scope → later design (“4b-live” or Phase 4b.2)

- Real mainnet order submit  
- `data/live/` ledger root  
- Secrets **required** to start  
- Size caps / kill switch that cancel open venue orders  
- Full Nautilus exec client production hardening  
- Testnet (permanently out of product path unless Albert reopens)  

---

## 12. Traceability seed (plan will expand)

| Spec tag | Likely tasks |
|----------|----------------|
| SRS_HV4B_MODE, SUBMITTED, INTENT | Engine + decision fields + tests |
| SRS_HV4B_NO_SUBMIT, NO_TESTNET, MAINNET | Config/CLI/check + structural barrier |
| SRS_HV4B_FILLS, WARM | Reuse 4a; regression tests only |
| SRS_HV4B_LEDGER, CHECK | CLI + ledger refuse live |
| SRS_HV4B_SAME_ALPHA, PROCESS | Session unchanged |

---

## 13. Spec self-review

| Check | Result |
|-------|--------|
| Placeholders | None intentional; 4b-live deferred explicitly |
| Contradictions | Shadow stays on paper ledger; live.enabled false |
| Scope | Single MVP: shadow mainnet, no submit |
| Ambiguity | `execution_mode=shadow` vs `paper` migration left to plan with offline compatibility note |

---

## 14. Approval gate

Session locks in §2 + mode split approved by Albert (2026-07-22).  

**Please review this file.** After approval, next skill is **writing-plans** → `docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md` (implement with write-clean-code; troubleshoot with think-like-a-programmer).
