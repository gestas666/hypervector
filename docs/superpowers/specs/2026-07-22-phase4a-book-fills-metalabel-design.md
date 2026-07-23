# Phase 4a Design: Book Fills + Meta-label Wire (hypervector)

**Date:** 2026-07-22  
**Status:** Design approved in session (highest +EV package); durable spec for implementation plan  
**Process:** engineering-software (Hyde) + ml-for-algo-trading + superpowers brainstorming  
**Depends on:**  
- Phase 3 paper design `2026-07-22-phase3-paper-live-feed-design.md` (complete)  
- Phase 2/3 contract `2026-07-22-phase2-3-handoff.md`  
- HANDOFF.md (pipeline status)

**Scope of this design:** Phase **4a only** — L2 book feed, staged fill models ending in L2 walk, then meta-label scale-only conviction on the shared paper/strategy path; optional userFees.

**Not in this implementation:** live venue orders (4b), CLI completeness (4c), GOAT TUI / 1-page GUI (Phase 5), skip-floor policy, ML training, full Nautilus TradingNode as a hard requirement.

---

## 1. Intent

Make paper execution **honest where optimism hurts** (size × liquidity), then wire **meta-labeling** so conviction is live `p ∈ [0, 1]` mapped only into existing risk sizing — without regressions to Phase 3 and without a second leverage model.

**One-sentence lock:**  
Phase 4a = public L2 book + staged fill models (destination `l2_walk_v1`) as paper ledger truth, then optional Metalabeler scale-only conviction on the same strategy path; live flip and UX remain later phases.

**Why this package is highest +EV (session lock):**

| Goal | Choice |
|------|--------|
| Realism where wrongness is costly | L2 walk as destination (size-dependent impact) |
| No regressions | Staged C→A delivery; keep `bar_close_slippage_v1` fallback; metalabel default off |
| Avoid false paper Sharpe | Book + fills **before** metalabel (which scales size) |
| Simplicity on ML policy | Scale only — no skip floor in 4a |

---

## 2. Session decisions (locked)

| Topic | Choice |
|-------|--------|
| Phase 4 first slice | **4a** fidelity (not 4b live-first, not 4c CLI-first) |
| Phase 5 | GOAT TUI + 1-page GUI (was handoff 4d/4e) |
| Architecture host | **Approach 1:** extend Phase 3 paper shell (not full Nautilus node in 4a) |
| 4a internal order | **Book + impact first** → **meta-label second** |
| Fill destination | **L2 walk** (`l2_walk_v1`) |
| Fill delivery | **Staged hybrid C→A:** `top_bps_v1` then `l2_walk_v1` |
| Fill fallback | `bar_close_slippage_v1` when book missing/stale — **logged, never silent** |
| Meta-label policy | **Scale only:** `conviction = p`; no skip floor |
| Sizing / leverage | Existing `risk_pct_from_conviction` + `position_size_frac`; **no second ML model** |
| Metalabel default | **Off** until L2-preferred path verified |
| Metalabel failure | Log + `conviction_source=fallback_fixed` (fixed conviction) |
| Book transport v1 | Public HL **REST L2 snapshot poll** (WS later) |
| userFees | Optional in 4a when wallet present; not a blocker |
| Process-over-asset | Symbol / TF / bundle from export/config/env |

---

## 3. Phase map

```text
Phase 3 paper     Live bars + bar_close fills + fixed conviction     DONE
Phase 4a          Book + staged fills → L2; then metalabel scale     THIS DESIGN
Phase 4b          Live exec + data/live/ + secrets + kill switch
Phase 4c          CLI completeness (gate before UX)
Phase 5           GOAT TUI + 1-page GUI (views over same ledger truth)
```

---

## 4. Non-goals (4a)

- Sending orders to Hyperliquid (mainnet/testnet)  
- Shared paper/live ledgers  
- Meta-label **gate** / skip floor  
- ML-predicted leverage, TP/SL, or training pipelines  
- Claiming REST book latency = co-located WS  
- Using book as primary **alpha** (signals remain strategy/params path)  
- Postgres / Redis / k8s  
- TUI / GUI  
- Committing secrets to git  

---

## 5. Requirements (testable)

Format: black-box *shall* / *must*. Tags for light RTM.

| Tag | Requirement |
|-----|-------------|
| SRS_HV4A_BOOK | Paper **shall** obtain L2 snapshots for the export symbol via a public path (REST v1). |
| SRS_HV4A_STALE | If book missing or age &gt; `max_book_age_ms`, system **shall** fall back and **must** log `fill_fallback_reason`. |
| SRS_HV4A_TOP | 4a.1 **shall** implement `top_bps_v1` using BBO + slippage when book is fresh. |
| SRS_HV4A_L2 | 4a.2 **shall** implement `l2_walk_v1` (level walk VWAP); **must not** invent depth beyond the book. |
| SRS_HV4A_FALLBACK | `bar_close_slippage_v1` **shall** remain available; Phase 3 offline behavior **must** still pass. |
| SRS_HV4A_LOG | Every market fill row **shall** record actual `fill_model_id`, book age, BBO when known, levels_used, shortfall. |
| SRS_HV4A_NO_VENUE | Paper **must not** submit venue orders. |
| SRS_HV4A_ORDER | Meta-label sizing **shall not** be default-on until L2-preferred path is verified. |
| SRS_HV4A_ML_SCALE | When metalabel enabled, conviction **shall** equal clipped `p`; **must not** apply a skip floor in 4a. |
| SRS_HV4A_ML_SIZE | Size **shall** use existing risk helpers (no second leverage model). |
| SRS_HV4A_ML_PIT | Features **must** be point-in-time; inference only (no training in 4a). |
| SRS_HV4A_ML_FAIL | Metalabel failure **shall** log and fall back to fixed conviction with `conviction_source=fallback_fixed`. |
| SRS_HV4A_PROCESS | Symbol/TF/bundle **shall** be parameterized (process-over-asset). |
| SRS_HV4A_LEDGER | Paper writes **only** under `data/paper/`; `execution_mode=paper` forced. |
| SRS_HV4A_PARTIAL | On insufficient book depth, system **shall** fill available size only, set `shortfall_qty`, and **must not** synthesize deeper levels. |

### Design goals (not hard requirements)

- DG_HV4A_WS: prefer WS book when stable  
- DG_HV4A_USER_FEES: live user fee tier when wallet configured  
- DG_HV4A_STRICT_ML: optional fail-closed metalabel mode (no fixed fallback)  
- DG_HV4A_NAUTILUS_NODE: full TradingNode host deferred toward 4b  

---

## 6. Architecture

### 6.1 Context

```text
export + configs ──► paper daemon (Phase 3 shell)
data/cache (OHLCV) ─► warm-up bars
HL bars ────────────► HypervectorStrategy (alpha unchanged)
HL L2 book ─────────► BookFeed → BookSnapshot
                         │
                         ▼
              FillModel (staged selection)
                ├─ bar_close_slippage_v1   (fallback / no book)
                ├─ top_bps_v1              (4a.1)
                └─ l2_walk_v1              (4a.2 destination)
                         │
                         ▼
              ExplicitFillEngine → data/paper/decisions|ledger

After fills green (4a.3):
  FeatureBuilder + Metalabeler → conviction=p → existing position_size_frac
```

### 6.2 Host (Approach 1)

Thin paper shell around existing strategy + `ExplicitFillEngine` — same pattern as Phase 3. Do **not** require a full Nautilus live `TradingNode` for 4a success. Book feed sits beside bar feed; fills remain explicit ledger truth.

### 6.3 Components

| Unit | Responsibility |
|------|----------------|
| `BookSnapshot` | Immutable bids/asks levels, timestamps, symbol, source |
| `BookFeed` | REST poll → latest snapshot; age; optional `data/cache/book/` debug write |
| `FillModel` protocol | `fill(side, qty, mark, book\|None, costs) → FillResult` |
| `BarCloseSlippageFillModel` | Phase 3 math extracted/kept as fallback |
| `TopBpsFillModel` | Best ask/bid ± slippage_bps |
| `L2WalkFillModel` | Walk levels; size-weighted average price |
| `ExplicitFillEngine` | Position, fees, funding, ledger; **delegates** price to FillModel |
| `Metalabeler` | Existing inference process (unchanged contract) |
| `FeatureBuilder` | Point-in-time feature row matching bundle `feature_names` |
| `ConvictionProvider` | `fixed` \| `metalabel` (+ fallback_fixed on error) |

---

## 7. Fill staged path

| Stage | `fill_model_id` | When | Behavior |
|-------|-----------------|------|----------|
| 0 (today) | `bar_close_slippage_v1` | No usable book | Close ± slippage_bps |
| 4a.1 | `top_bps_v1` | Book fresh | Buy @ ask×(1+slip); sell @ bid×(1−slip) |
| 4a.2 | `l2_walk_v1` | Book fresh | Walk asks/bids for qty; VWAP; log levels |
| Always | fallback | Missing or stale book | Stage 0; log `fill_fallback_reason` |

**After 4a.2 ships:** preferred model = `l2_walk_v1` when book is fresh. Never silently use bar-close when book was expected.

### 7.1 L2 walk rules

- Buy walks **asks** ascending; sell walks **bids** descending.  
- Fill price = size-weighted average of consumed levels.  
- Depth &lt; qty → fill available only; `shortfall_qty` set; **no invented liquidity**.  
- Fees from `CostProvider` (taker default for aggressive walk).  

### 7.2 Staleness

```text
on fill decision:
  book = BookFeed.latest(symbol)
  if book is None or empty → fallback, reason=book_missing
  elif book_age_ms > max_book_age_ms → fallback, reason=book_stale
  else → preferred model (top_bps_v1 or l2_walk_v1)
```

| Parameter | Default (design) |
|-----------|------------------|
| `max_book_age_ms` | 2000–5000 (config) |

Prefer exchange timestamp when available; log receive time when useful.

### 7.3 FillResult

| Field | Purpose |
|-------|---------|
| `fill_px` | Ledger price |
| `fill_qty` | May be &lt; requested |
| `fill_model_id` | Actual model used |
| `levels_used` | 0 for bar-close |
| `shortfall_qty` | Unfilled remainder |
| `bbo_bid` / `bbo_ask` | Top of book or null |
| `book_age_ms` | Freshness |
| `fill_fallback_reason` | null or reason |

Optional audit: `fill_model_preferred` vs actual.

---

## 8. BookFeed

| Choice | Spec |
|--------|------|
| Transport v1 | Public HL REST L2 snapshot poll (no API key) |
| Later | WS / Nautilus data client (DG) |
| Cadence | Configurable (e.g. 1–2s or aligned with bar poll) |
| Cache | Optional under `data/cache/book/` for debug/replay — **not** live brain |
| Warm | One fresh snapshot before preferring book fills (no multi-day warm-up) |

Process-over-asset: symbol from export/meta/config.

---

## 9. Decision log extensions

Keep Phase 3 fields. Add (null-ok for funding / legacy rows):

- `book_age_ms`  
- `bbo_bid`, `bbo_ask`  
- `levels_used`  
- `shortfall_qty`  
- `requested_qty`  
- `fill_fallback_reason`  
- `conviction_source`: `fixed` \| `metalabel` \| `fallback_fixed`  
- `metalabel_p`  
- `metalabel_bundle_id` (or root basename)  
- `feature_schema_version` when available  

`fill_model_id` = **actual** model after fallback selection.

---

## 10. Meta-label wire (4a.3)

### 10.1 Prerequisite

4a.1 + 4a.2 green (book, top_bps, l2_walk, fallback, offline + golden book tests). Do not default-enable metalabel on bar-close-only paper.

### 10.2 Process (named: meta-labeling)

```text
primary signal → side / enter|hold|close
features (metadata schema) → Metalabeler → p ∈ [0, 1]
conviction = p                    # scale only; no skip floor
risk_pct_from_conviction → size_frac → notional
FillModel (L2 preferred) → paper ledger
```

**Meta-labeling** = primary signal for side/timing; secondary model for take-strength; risk rules for size. Leverage remains a **capped side effect** of notional vs equity, not an ML output.

### 10.3 Config / CLI

| Surface | Behavior |
|---------|----------|
| Default | Fixed conviction (Phase 3) |
| Enable | Config / flag e.g. `metalabel.enabled` + `HYPERVECTOR_METALABEL_ROOT` |
| Bundle | Env or path; any compatible bundle (process-over-asset) |
| Failure | Log + fixed fallback + `conviction_source=fallback_fixed` |

### 10.4 Feature builder

- Point-in-time only.  
- Inference only — no training in 4a.  
- Must match bundle `feature_names`; if unbuildable from current inputs, keep metalabel **off**.  
- Prefer adapter to existing hyper-pi / hypertrader feature pipelines over asset-specific forks.

### 10.5 Naming (for humans / docs)

| Piece | Name |
|-------|------|
| Whole pattern | Meta-labeling architecture |
| LightGBM `p` | Meta-label / secondary model |
| `p → risk → size` | Conviction / risk-based position sizing |
| Caps | Risk overlay |

---

## 11. Optional userFees

If wallet env present: optional refresh of fee tier into `CostProvider`. Else HL Tier 0 table. Non-blocking for 4a.1–4a.3.

Secrets env (still no order placement in paper):

- `HYPERVECTOR_HL_WALLET_ADDRESS`  
- `HYPERVECTOR_HL_API_PRIVATE_KEY`  

---

## 12. Testing & success criteria

### 12.1 Offline (required)

| Test | Assert |
|------|--------|
| Phase 3 suite | Pass with bar-close path |
| Golden book buy across levels | L2 VWAP + `levels_used` |
| Thin book | `shortfall_qty > 0`, no invented depth |
| Stale / missing book | Fallback + reason logged |
| Metalabel mock `p` | Monotonic size in risk band when enabled |
| Metalabel disabled | Fixed conviction behavior |
| Missing features | Fallback or clear error per policy |

### 12.2 Smoke (optional network)

- `paper-check` reports book feed + preferred fill model.  
- Short `paper-run` with book when HL public available.  

### 12.3 Success bar for 4a complete

1. Offline suite green (no Phase 3 regression).  
2. Golden book tests for top_bps + l2_walk + fallback.  
3. Preferred fill = `l2_walk_v1` when book fresh.  
4. Metalabel optional path verified; default fixed conviction.  
5. No `data/live/` writes; no venue orders.  

---

## 13. Implementation order (for writing-plans)

| Step | Deliverable |
|------|-------------|
| 4a.0 | Extract `FillModel` protocol; keep bar-close as default |
| 4a.1 | `BookFeed` REST + `top_bps_v1` + log fields + staleness |
| 4a.2 | `l2_walk_v1` preferred when fresh; golden tests |
| 4a.3 | `ConvictionProvider` + FeatureBuilder adapter + CLI/config enable |
| 4a.x | Optional userFees if cheap |

Do **not** start 4b until 4a success bar met (or explicitly waived by user).

---

## 14. Traceability

| Concern | Spec | Plan (next) |
|---------|------|-------------|
| Phase 3 paper | `2026-07-22-phase3-paper-live-feed-design.md` | complete |
| Phase 4a book/fills/ML | **this file** | `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md` (to write) |
| Phase 4b live | separate design | — |
| Phase 4c CLI | separate design | — |
| Phase 5 TUI/GUI | separate design | — |

---

## 15. Spec self-review (session)

| Check | Result |
|-------|--------|
| Placeholders | None intentional; plan path named for next skill |
| Consistency | Book-first then ML; C→A fills; scale-only; Approach 1 |
| Scope | Single implementation plan suitable (4a only); 4b/4c/5 split out |
| Ambiguity | Partial fill = default; metalabel fail = fixed fallback; max_book_age configurable range |

---

## 16. Open items for plan (not design blockers)

- Exact HL REST endpoint helper and rate limits  
- Default numeric `max_book_age_ms` (pick one value in plan, e.g. 3000)  
- FeatureBuilder: which external module to adapter first  
- CLI flag names for metalabel / fill model preference  
