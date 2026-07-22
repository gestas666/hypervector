# Phase 3 Design: Paper Live-Feed Loop (hypervector)

**Date:** 2026-07-22  
**Status:** Design approved in session (Approach 1 + architecture); durable spec for implementation  
**Process:** engineering-software (Hyde) + ml-for-algo-trading realism + brainstorming  
**Depends on:**  
- Phase 1 `2026-07-21-phase1-vectorbt-design.md`  
- Phase 2/3 contract `2026-07-22-phase2-3-handoff.md`  
- Phase 2 plan complete: actor + historical runner + paper ledger scaffold  

**Scope of this design:** Phase 3 **paper** only — long-running Nautilus node on Hyperliquid **live bars**, same strategy path as Phase 2, explicit fills + hybrid costs, optional sandbox mirror.  

**Not in this implementation:** live venue orders, order-book alpha/fills, metalabel wiring, multi-strategy portfolio daemon.

---

## 1. Intent

Prove the **paper → live promotion ladder** without capital risk:

```text
Phase 1/1.5 export
  → Phase 2 historical Nautilus (done)
  → Phase 3 paper: live HL bars + same strategy + synthetic fills (this design)
  → Phase 4: order book + ML metalabel + live exec flip (separate design/plan)
```

**One-sentence lock:**  
Phase 3 paper = live HL market data + exact same Nautilus strategy/risk stack as future live, with **explicit** fills fully logged as would-be executions; **Phase 4** flips execution client + ledger root + secrets, and adds book/ML.

**Process-over-asset:** symbol / timeframe / export id / cost tier are configuration — no BTC-only modules.

---

## 2. Session decisions (locked)

| Topic | Choice |
|-------|--------|
| Host | **Full Nautilus node** (TradingNode / kernel) + `HyperliquidDataClient` |
| Market data v1 | **Bars only** (export TF); order book = **Phase 4** |
| Runtime | **Daemon** (long-running until stop) |
| Fill path | **C:** explicit model = ledger truth; **optional Nautilus Sandbox** (off by default, toggleable) |
| Costs | **Hybrid:** config fees/slippage/tier; **live signed funding** from HL public info; export costs = research provenance only |
| Warm-up | **Cache-first** research history; HL REST if cold; then live bars |
| Architecture | **Approach 1:** thin paper shell around `HypervectorStrategy` |
| ML | **Out of scope for paper v1** — fixed conviction; flag when wiring Metalabeler |
| Live | **Config flip** after paper proven; wallet + API key in secrets/config surface |

---

## 3. Non-goals (paper v1)

- Sending orders to Hyperliquid mainnet/testnet  
- Claiming paper PnL = live PnL (log fill model; expect divergence)  
- Paper-only smarter strategy branch  
- Shared paper/live ledgers  
- Order book as required input for signals  
- Metalabel / feature builder / training  
- Postgres / Redis / k8s  
- Committing secrets to git  

---

## 4. Requirements (testable)

Format: black-box *shall* / *must*. Tags for light RTM.

| Tag | Requirement |
|-----|-------------|
| SRS_HV3P_HOST | Paper **shall** run strategy inside a Nautilus live/sandbox-capable node (not VectorBT). |
| SRS_HV3P_SAME_ALPHA | Paper **shall** recompute alpha from live/warm bars via `HypervectorStrategy` + registry params; **must not** use `signals.parquet` as live brain. |
| SRS_HV3P_BARS | Paper v1 **shall** subscribe to bars matching export timeframe (e.g. 1m). |
| SRS_HV3P_WARM | Paper **shall** warm the bar buffer from cache (HL REST backfill if cache insufficient) before acting on live signals. |
| SRS_HV3P_NO_VENUE | Paper **must not** submit real venue orders when `execution_mode=paper`. |
| SRS_HV3P_MODE | Every paper decision/fill row **shall** include `execution_mode=paper` (forced at write). |
| SRS_HV3P_LEDGER | Paper **shall** write only under `data/paper/` and **must** refuse paths under `data/live/`. |
| SRS_HV3P_FILL_EXPLICIT | Paper ledger PnL **shall** use the explicit fill/cost model as authoritative. |
| SRS_HV3P_FILL_LOG | Every paper fill **shall** log `fill_model_id`, fee rates, slippage params, funding rate used, and source timestamps. |
| SRS_HV3P_SANDBOX | Sandbox exec **shall** be optional (default off); when on, shadow only — **must not** replace explicit ledger truth. |
| SRS_HV3P_FEES | Fee rates **shall** come from config tier table aligned to HL public schedule (default Tier 0 perp base until overridden). |
| SRS_HV3P_FUNDING | While paper positions are open, system **shall** poll live HL funding and apply **signed** hourly funding (not always-drag research placeholder). |
| SRS_HV3P_COST_NONSTATIC | Cost inputs **must** be refreshable without code change (config + live poll); export `costs` snapshot is provenance only. |
| SRS_HV3P_IDENTITY | Daemon **shall** log a clear PAPER identity banner / periodic heartbeat. |
| SRS_HV3P_EXPORT | Paper **shall** load a strict Phase 1.5 export → `StrategyLoadout`. |
| SRS_HV3P_PROCESS | Symbol/TF **shall** be parameterized from export/meta/config (process-over-asset). |
| SRS_HV3P_SECRETS | Wallet address and API private key **shall** load only from env / `.env` (gitignored); **must not** appear in exports or git. |
| SRS_HV3P_LIVE_FLIP | Live mode **shall** be reachable by configuration (exec client + ledger root + secrets required) without forking strategy code — implemented **after** paper proven. |
| SRS_HV3P_ML_OFF | Paper v1 **shall** use configured conviction only; Metalabeler optional later under same path rules. |

### Design goals (not hard requirements)

- DG_HV3P_BOOK: extension point for order-book subscribe + impact fill upgrade  
- DG_HV3P_USER_FEES: optional live `userFees` when wallet configured (later)  
- DG_HV3P_HEALTH: simple health file or log for daemon supervisors  

---

## 5. Architecture

### 5.1 Context

```text
export bundle + configs ──► paper daemon (Nautilus kernel)
data/cache ───────────────► warm-up bars
HL public info/WS ────────► HyperliquidDataClient (bars)
HL public funding ────────► CostProvider (signed hourly)
optional secrets ─────────► present for live flip; unused for pure paper public path
                            │
                            ├─ HypervectorStrategy (alpha)
                            ├─ ExplicitFillEngine → data/paper/decisions + ledger
                            └─ [optional] SandboxExec → shadow logs only
```

### 5.2 Environment mapping

| Mode | Data | Execution | Ledger root |
|------|------|-----------|-------------|
| Phase 2 | Historical bars | BacktestEngine | `data/nautilus/backtest/` |
| Phase 3 paper | Live HL + warm-up | Explicit (+ optional Sandbox) | `data/paper/` |
| Phase 3 live | Live HL | HyperliquidExecClient | `data/live/` |

### 5.3 Promotion = config switch (post-paper)

When paper is proven, live is **not** a new strategy codebase:

| Knob | Paper | Live |
|------|-------|------|
| `execution_mode` | `paper` | `live` |
| Data client | HL public (keys optional) | HL (same adapter family) |
| Exec client | none / sandbox shadow | real HL exec |
| Ledger root | `data/paper/` | `data/live/` |
| Secrets | optional for public paper | **required** wallet + API key |
| Size | paper notional / risk from loadout | tiny size + kill switch (ops) |

Config and env surface should exist early so the flip is real, even if live path refuses to start until a later milestone.

---

## 6. Components & interfaces

### 6.1 `paper.runner` (daemon entry)

**Responsibility:** assemble node, load export, warm-up, run until SIGINT/SIGTERM/stop file.

**Inputs:**

- `--path` export dir (strict)
- `--data-root` (default `data`)
- config TOML + env
- `--sandbox` / config `paper.sandbox_enabled` (default false)
- `--conviction` (default from config/risk)

**Outputs:**

- continuous decisions JSONL under `paper/decisions/`
- optional position/fill ledger under `paper/ledger/`
- session meta under `paper/runs/<run_id>/` (or equivalent): start time, export id, git hash if available, config hash, fill_model_id

**Lifecycle:**

1. `ensure_data_layout`  
2. Load loadout; refuse non-strict export  
3. Resolve instrument/bar type from loadout symbol + TF + venue HYPERLIQUID  
4. Warm-up bars into strategy/buffer (cache → HL REST)  
5. Start data client (live bars)  
6. Run event loop; on stop: flush, write session summary, exit  

### 6.2 `HypervectorStrategy` (reuse + mode)

- Reuse Phase 2 actor for intent/sizing/exit distances.  
- `execution_mode` **must** be configurable (`phase2_historical` | `paper` | later `live`), not a hard-coded constant only.  
- Paper path: order submit goes to **paper execution adapter** (explicit fill), not venue.  
- Prefer minimal actor changes: inject mode + hooks rather than forking strategy classes.

### 6.3 `CostProvider` (hybrid, non-static)

| Input | Source | Refresh |
|-------|--------|---------|
| `taker_fee` / `maker_fee` | Config fee schedule + `fee_tier` (default Tier 0 base: **0.045% / 0.015%** perps per official HL docs) | File/env reload optional; default process start |
| `slippage_bps` | Config model (size-aware buckets later) | Config |
| `funding_rate` (signed, hourly) | HL public `metaAndAssetCtxs` (or equivalent) for coin | Poll on interval (e.g. 60s) and at funding hour |
| Export `costs` | Loadout meta | Provenance only; log if diverges from live/config |

**Corrections vs research placeholders:**

- HL funding is **hourly** (8h formula / 8), not a single 8h research drag.  
- Funding is **signed** (long pays short if rate &gt; 0).  
- Default research `taker_fee=0.00035` is **not** Tier 0 base; paper defaults must document official Tier 0 unless operator sets volume tier.

**Paper fee assumption v1:** market / aggressive entries = **taker** rates (matches current actor market-order style). Maker path is design-future if limit entries appear.

### 6.4 `ExplicitFillEngine`

On strategy intent that would trade:

1. Mark price = bar close (v1); optional mid when quotes available later  
2. Slippage: buy pays +bps, sell pays −bps (fraction of price)  
3. Fee = notional × taker_fee (config)  
4. Update paper portfolio state (position, avg entry, realized/unrealized)  
5. Apply funding on open positions when poll delivers rate × hold fraction  
6. `append_paper_decision` + ledger fill row with full cost snapshot  

**Sandbox (optional):** if enabled, also submit/sim via Nautilus sandbox client; log sandbox fill events under paper shadow fields (`sandbox_*`). Never overwrite explicit ledger fields with sandbox-only numbers.

### 6.5 Ledger / decision schema (v1 minimum)

Extend free-form JSONL with required keys (additive to existing `append_paper_decision`):

```text
execution_mode          # forced "paper"
feed_ts                 # bar/event time (exchange)
run_id
export_id / export_path
strategy_name
symbol, timeframe
intent / action         # enter_long|enter_short|close|hold|funding
side, qty, mark_px, fill_px
fill_model_id           # e.g. "bar_close_slippage_v1"
slippage_bps
taker_fee, maker_fee    # rates applied
fee_usd
funding_rate_hourly     # if funding event or open pos snapshot
funding_payment_usd     # if applied
costs_source            # config|live_funding|export_provenance
sandbox_enabled
sandbox_fill_px         # optional
conviction
```

### 6.6 Secrets & config surface (early, live-ready)

**Tracked config** (`configs/*.toml`) — no secrets:

```toml
[paper]
sandbox_enabled = false
funding_poll_secs = 60
fill_model_id = "bar_close_slippage_v1"
fee_tier = 0                    # HL perp volume tier index
assume_taker = true

[costs]
# Prefer schedule resolution from fee_tier; explicit overrides optional
taker_fee = 0.00045             # Tier 0 base official
maker_fee = 0.00015
slippage_bps = 2.0
# funding_rate_8h deprecated for paper; live poll is source of truth

[live]                            # present for flip; paper ignores start if mode=paper
enabled = false
# require_secrets = true when enabled
```

**Secrets (env / `.env` only):**

| Env | Purpose |
|-----|---------|
| `HYPERVECTOR_HL_WALLET_ADDRESS` | Account / user address (fees, positions later) |
| `HYPERVECTOR_HL_API_PRIVATE_KEY` | API wallet key for **live** (and any authenticated endpoints) |
| optional vault/testnet flags later | |

Rules:

- Paper **public** path: data + funding work **without** keys.  
- If keys present in paper mode: may enable optional authenticated reads later; **must not** place live orders.  
- Live mode start **shall** fail closed if secrets missing when `execution_mode=live`.  
- Never write secrets into decision logs or exports.

### 6.7 CLI

| Command | Behavior |
|---------|----------|
| `paper-check` | existing: layout + identity (extend: config/secrets present flags, no key material) |
| `paper-run` / `paper-daemon` | start long-running paper loop |
| stop | SIGINT/SIGTERM or `--stop-file` |

---

## 7. Data flow

```text
1. load_strategy_loadout(export, strict=True)
2. warm_bars = cache OHLCV for symbol/TF lookback
   if insufficient → fetch_hl_ohlcv → merge/cache
3. convert to Nautilus bars; seed strategy buffer / catalog
4. connect HyperliquidDataClient; subscribe bar type
5. on each live bar:
     strategy.on_bar → intent/action
     if trade action → ExplicitFillEngine.apply → append_paper_decision
     if sandbox on → mirror submit (shadow log)
6. on funding poll tick:
     rate = live funding for coin
     if open paper position → funding payment → ledger + decision row
7. on shutdown → session summary (counts, paper PnL, paths)
```

**Point-in-time discipline (ML4T):** decisions only use bars with `feed_ts` ≤ decision time; no future cache rows after live switch. Log `data_source=cache|hl_rest|hl_live` during warm-up vs live.

---

## 8. Phase 4 (important — deferred from this plan)

**Phase 3** = paper live-feed loop only (this design + plan).  
**Phase 4** is a first-class next phase, not a vague “nice later” list. It owns the deferred items that matter for production-quality promotion:

| Phase 4 item | Why it matters |
|--------------|----------------|
| **Order book** | Honest impact/slippage; L2 subscribe; optional impact fill model; `cache/book/` already reserved |
| **ML metalabel conviction** | Real sizing signal via `Metalabeler` + feature builder; same path paper/live; labels must match gate |
| **Live execution flip** | Config switch: real `HyperliquidExecClient`, secrets required, `data/live/` ledger, tiny size + kill switch |
| **Authenticated fee tier** | Optional `userFees` from wallet when secrets present |
| **Ops hardening** | Supervisor recipes, kill switch, live risk banners |

### 8.1 Order book (Phase 4)

Design hooks only in Phase 3:

- `cache/book/` already exists in I2 layout  
- Future: subscribe L2 via HL adapter; optional `ImpactFillModel` replacing flat slippage  
- Alpha remains bar-driven until a strategy explicitly consumes book features  

Phase 3 **must not** block on book.

### 8.2 ML (Phase 4 — explicit flag)

**Phase 3 paper:** `conviction` from CLI/config only.

When Phase 4 opens ML:

- Same decision path as paper/live (no paper-only smarter branch)  
- `Metalabeler` + feature builder + label/gate alignment required first  
- Decision rows carry `metalabel_bundle_id`, `p`, `feature_schema_version`  
- Still subject to existing risk band  

Out of scope for the Phase 3 paper-loop implementation plan.

---

## 10. Testing strategy

| Layer | What |
|-------|------|
| Unit | CostProvider fee tier table; signed funding payment math; fill px = mark ± slip; ledger refuses live paths; mode stamp |
| Offline integration | Inject synthetic bar stream (no network) into paper loop → decisions JSONL schema |
| Optional network | Short-lived paper-run against public HL (marked `@pytest.mark.network`) |
| Regression | Phase 2 historical tests remain green; paper does not break actor offline tests |
| Non-test | Never assert paper PnL equals future live |

Integrity: medium — wrong fills mislead promotion; explicit model + schema tests required.

---

## 11. Key decisions

| Decision | Rationale |
|----------|-----------|
| Full Nautilus node for paper | Same path paper→live; reuse HL adapter |
| Explicit fill is ledger truth | Honest costs; sandbox opacity on bars |
| Optional sandbox off by default | Try Nautilus path without polluting PnL |
| Hybrid costs | Fees/slippage controllable; funding non-static and signed |
| Official Tier 0 fee defaults | Research 3.5 bps understates HL base 4.5 bps taker |
| Cache-first warm-up | Fast restart; HL REST when cold |
| Secrets in env early | Live flip is config; no secret scrape into git |
| ML deferred | Avoid wrong conviction before gate/feature alignment |
| Book deferred | Bars match Phase 2 actor; book is fill/ops upgrade |

---

## 12. Open questions (resolved or deferred)

| Item | Status |
|------|--------|
| Host / bars / daemon / fill C / costs A / warm A / Approach 1 | **Resolved** |
| Exact Nautilus API for sandbox + HL data in pinned package version | **Implementation discovery** — spike in first PR if needed |
| Daemon supervisor (launchd/systemd) | **Ops later**; SIGTERM + stop file enough for v1 |
| userFees live tier from wallet | **Deferred** (DG); config tier for now |
| Metalabel in paper | **Deferred** |

---

## 13. Traceability

| Concern | Spec | Plan (next) |
|---------|------|-------------|
| Phase 3 paper loop | this file | `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` |
| Phase 2 actor | handoff + phase2 plan | done |
| Infra I2 | `docs/infra-data-layout.md` | done |

---

## 14. PR Plan (implementation order)

### PR1 — CostProvider + fee schedule + funding math
- HL perp tier table (config-driven); Tier 0 defaults 4.5/1.5 bps  
- Signed hourly funding helpers; live poll client (public info)  
- Unit tests; no node yet  
- **Deps:** none  

### PR2 — ExplicitFillEngine + decision schema
- Fill model `bar_close_slippage_v1`  
- Paper portfolio state; funding application hooks  
- Extend `append_paper_decision` required fields / validators  
- **Deps:** PR1  

### PR3 — Paper runner skeleton (offline)
- Warm-up from cache/injected OHLCV  
- Drive strategy buffer + explicit fills without live network  
- Session run_id artifacts under `data/paper/`  
- **Deps:** PR2; reuses `HypervectorStrategy`  

### PR4 — Nautilus live data + daemon CLI
- HyperliquidDataClient wiring; `paper-run` daemon  
- Cache→live transition; PAPER banner; SIGTERM  
- Config surface: `[paper]`, `[live]`, secrets env names (documented)  
- **Deps:** PR3  

### PR5 — Optional sandbox mirror + docs/handoff
- `sandbox_enabled` flag; shadow fields  
- Update HANDOFF, paper-check, infra notes  
- Network-marked smoke optional  
- **Deps:** PR4  

### Later — **Phase 4** (separate design + plan; high priority after paper proven)
- Order book subscribe + impact fills  
- Metalabel conviction on shared path  
- Live exec flip + kill switch + live ledger  
- Authenticated `userFees` tier  
- Ops hardening (supervisor, kill switch UX) 

---

## 15. Success criteria (paper v1 done)

1. `paper-run` stays up on public HL bars for an export without private key.  
2. Decisions JSONL shows `execution_mode=paper`, fill_model_id, fees, live funding fields.  
3. No writes under `data/live/`; no real orders.  
4. Sandbox off by default; on = shadow only.  
5. Offline tests cover cost/fill/ledger; Phase 2 suite still green.  
6. Config documents live flip + secret env names without enabling live.  

---

## 16. Implementation note (for next session)

Do **not** re-execute Phase 2 plan.  
Next: execute `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` (PR/tasks 1→5).  
After paper proven: **Phase 4** design (ML, order book, live flip) — not “Phase 3+”.  
Live keys may be **present in env** for Phase 4; Phase 3 paper path must ignore them for order placement.
