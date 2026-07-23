# HANDOFF — hypervector

**Saved:** 2026-07-23 — **4b-live F2 done** (exec client + mock transport tests). Branch `feat/phase4b-live-f2-exec-client` (not merged). **Next session: 4b-live F3** (`live-run`). Neural-trader rejected. **No venue submit from paper/shadow; live-run not wired yet.**  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase4b-live-f2-exec-client` (base: `main` @ `db09dd2`)  
**Working tree:** F2 code + docs; commit when ready. **Not pushed** unless Albert requests.

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1 / 1.5 research | **Done** |
| Phase 2 actor + historical + metalabeler process | **Done** (plan closed) |
| Phase 3 paper design + plan + code | **Done** (5/5 + funding fix) |
| Phase **4a design + plan + code** | **Done** (Tasks 1–6 + warm-up book fix) |
| Phase **4a paper soak** | Warm honesty PASS (earlier); superseded by 4b shadow soak |
| Phase **4b design** | **Approved** — mainnet shadow (no testnet, no submit) |
| Phase **4b plan + code** | **Done** (Tasks 1–6) |
| Phase **4b shadow verification / soak** | **PASS** — dual smoke + bounded mainnet soak + 1× live `l2_walk_v1` |
| Phase **paper completeness (slice A)** | **Done** — `paper-report`, CLI honesty, acceptance matrix |
| Phase **4b-live F1 foundation** | **Done** — live ledger, LivePolicy, `live-check` |
| Phase **4b-live F2** (exec client) | **Done** — protocol + HL adapter + factory gates; offline mock transport |
| Phase **4b-live F3–F4** (live-run + kill/cancel) | **NEXT** (F3 daemon) |
| Phase 4c CLI | **Partial** (paper-report + live-check); full epic later |
| Phase 5 TUI + 1-page GUI | **Not started** |
| neural-trader / `@neural-trader/*` | **Rejected** — do not integrate |

**Outgoing session:** F2 exec client behind policy gates; `submit_wired=true`; start still refused by default.  
**Incoming session:** **Implement 4b-live F3** (`live-run` reuses paper shell + live engine + ledger). Still fail-closed without secrets+arm+enabled.

---

## CLEAN SESSION START — 4b-live F3 (live-run daemon)

### Goal (one sentence)

Implement **F3**: `live-run` CLI that reuses the paper daemon shell with **live ledger** + armed `LiveExecClient.place_market` only when `LivePolicy.require_start()` passes.

### Spec / plan

| Doc | Path |
|-----|------|
| Design | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |
| Plan | `docs/superpowers/plans/2026-07-23-phase4b-live.md` |

### F2 shipped (this session) — acceptance met

1. `LiveExecClient` Protocol + `PlaceResult` (`submitted`, `venue_order_id | None`, `error | None`).  
2. `HyperliquidLiveExecClient` + injectable `PlaceTransport`; secrets from env via factory.  
3. Offline tests: mock transport — armed+secrets → place called; unarmed/no secrets → never constructs; over notional → no transport call.  
4. Paper path regression: `tests/test_paper_no_submit.py` green; no exchange imports in `paper/`.  
5. `live-check`: `submit_wired=true`, `can_start=false` by default, `venue_submit=false`.  
6. **No** `live-run` daemon (F3). **No** cancel-all (F4).  
7. Default max notional still `50` USD.

### F3 acceptance (next session)

1. `live-run` CLI requires `--i-accept-live-risk` + config/enabled path.  
2. Constructs exec client only after `LivePolicy.require_start()`.  
3. Decisions under `data/live/decisions/` with honest `submitted` from place result.  
4. Paper/shadow path still never constructs client.  
5. Offline tests mock transport; no accidental real place.  
6. Default still `live.enabled=false`; paper-run default still shadow.

### Bootstrap commands

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb   # expect feat/phase4b-live-f2-exec-client or main after merge
git log -8 --oneline
uv sync --all-extras
uv run pytest tests/ -q -m "not network"   # ~261+ passed
uv run python -m hypervector paper-check
# → mode/execution_mode=shadow, network=mainnet, no_submit=true,
#   submitted_default=false, order_intent_schema=hv_order_intent_v1,
#   preferred_fill_model=l2_walk_v1, live.enabled=false
# Banner on paper-run: SHADOW MODE — no venue orders (default)
uv run python -m hypervector paper-report --last 5
uv run python -m hypervector live-check
# → start_gate=refused by default; submit_wired=true (F2); can_start=false
```

### Key F2 surfaces

| Path | Role |
|------|------|
| `src/hypervector/live/exec_client.py` | Protocol, PlaceResult, HyperliquidLiveExecClient, factories |
| `src/hypervector/live/policy.py` | readiness `submit_wired` via `is_submit_wired()` |
| `src/hypervector/live/ledger.py` | live decisions JSONL (F1) |
| `tests/test_live_exec_client.py` | offline mock transport + gate tests |

**Factory:** `create_live_exec_client(policy, wallet=…, key=…, transport=…)` and `create_live_exec_client_from_env(policy, transport=…)` both call `policy.require_start()` first.

**Production transport:** optional `hyperliquid-python-sdk` + `eth_account` (`_SdkPlaceTransport`); offline suite never needs them (inject `PlaceTransport`).

**Mainnet only:** `HL_EXCHANGE_URL = https://api.hyperliquid.xyz/exchange` (no testnet).

### Agent checklist (next session = F3)

1. Read **this HANDOFF** + 4b-live design/plan.  
2. Confirm offline suite green (~261+) on F2 branch or merged main.  
3. Implement **F3 only** (`live-run` + live ledger wiring); do not skip kill/cancel (F4) unless trivial stub.  
4. **Never** place venue orders from paper/shadow path.  
5. **Never** construct exec client without `LivePolicy.require_start()`.  
6. Real HL place in tests must be mocked offline; any network live smoke only with Albert-approved secrets + arm.  
7. End session: update HANDOFF + plan F3 checkboxes + offline suite green.

### Phase 4b-live task board

| Task | Deliverable | Status |
|------|-------------|--------|
| F1 | ledger + policy + live-check | **Done** |
| **F2** | LiveExecClient + HL adapter + gates | **Done** (this session) |
| **F3** | live-run + live ledger writes | **Next** |
| F4 | kill switch cancel-open | After F3 |

### Phase 4b shadow task board (COMPLETE)

| Task | Deliverable | Status |
|------|-------------|--------|
| 1–6 | intents, shadow default, barriers, soak | **Done** |

### Architecture (locked — 4a + 4b shadow + F1/F2)

```text
export + configs → paper daemon (Phase 3 shell) — still no exec client
HL bars → HypervectorStrategy (alpha unchanged)
HL L2 book → BookFeed → BookSnapshot  (LIVE phase only)
FillModel: bar_close_slippage_v1 | top_bps_v1 | l2_walk_v1
ExplicitFillEngine → data/paper/
  execution_mode=shadow (daemon default) | paper
  submitted=false, network=mainnet, order_intent on market fills

Live (F2 present; F3 will use):
  LivePolicy.require_start() → create_live_exec_client*
  HyperliquidLiveExecClient.place_market → PlaceTransport
  append_live_decision → data/live/decisions/  (F3 writes)
```

### Locks (Albert approved — do not reopen without him)

| Topic | Choice |
|-------|--------|
| +EV package | Book + honest fills **before** metalabel; L2 walk destination |
| Fill delivery | Staged: extract bar_close → top_bps → **l2_walk_v1** preferred |
| Fallback | `bar_close_slippage_v1` if book missing/stale; **log reason, never silent** |
| `max_book_age_ms` | **3000** default |
| Meta-label policy | **Scale only** (`conviction = p`); **no skip floor** |
| Meta-label default | **Off** until explicitly enabled (`--metalabel`) |
| Meta-label fail | `conviction_source=fallback_fixed` |
| Leverage | **Not** a second model — existing risk band only |
| Host | Thin paper shell (not full Nautilus node in 4a/4b) |
| Book transport v1 | Public HL **REST** L2 (`l2Book`); WS later |
| **4b network** | **Mainnet only** — no testnet URL/config path |
| **4b submit (shadow)** | **Never** — order intent logged; `submit_enabled=false` |
| **4b ledger (shadow)** | Still `data/paper/`; refuse `data/live/` |
| **Daemon default** | `execution_mode=shadow` |
| **4b-live** | secrets+arm+enabled; max notional default **50** USD |
| TUI / GUI | **Out of scope** (Phase 5) |
| Blog VBT+LGBM primary classifier | **Not** the product path |

### Success bar (F2 — met 2026-07-23)

1. Offline suite green (**261** passed, `-m "not network"`).  
2. Protocol + PlaceResult + HyperliquidLiveExecClient.  
3. Factory refuses without require_start gates.  
4. Mock transport place on armed path; no place when over notional.  
5. `live-check`: `submit_wired=true`, `can_start=false` default.  
6. Paper no-submit barriers still green.  
7. No live-run / no cancel-all / no paper imports of exec client.

### Out of scope remaining

- **F3** live-run daemon + live decision writes with real place path  
- **F4** kill switch / cancel open  
- 4c full CLI completeness epic  
- Phase 5 GOAT TUI / 1-page GUI  
- userFees (optional DG — deferred)  
- ML training / LEXLB primary-signal notebook architecture  

---

## Docs map (canonical)

| Role | Path |
|------|------|
| **Phase 4b-live design** | `docs/superpowers/specs/2026-07-23-phase4b-live-design.md` |
| **Phase 4b-live plan** | `docs/superpowers/plans/2026-07-23-phase4b-live.md` |
| **Phase 4b shadow design (SHIPPED)** | `docs/superpowers/specs/2026-07-22-phase4b-mainnet-shadow-design.md` |
| **Phase 4b shadow plan (COMPLETE)** | `docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md` |
| **Phase 4a design (SHIPPED)** | `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md` |
| Phase 3 plan (COMPLETE) | `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` |
| Infra I2 | `docs/infra-data-layout.md` |
| This handoff | `HANDOFF.md` |

---

## Pipeline

```text
Phase 1/1.5  VectorBT research → export
Phase 2      Nautilus historical (params, not signals.parquet)
Phase 3      Paper: live HL bars + same strategy + explicit fills   ← DONE
Phase 4a     Book + staged L2 fills + meta-label scale-only         ← DONE
Phase 4b     Mainnet shadow: intents, submitted=false, no submit    ← DONE
Phase 4b-live F1 ledger/policy  ← DONE
Phase 4b-live F2 exec client    ← DONE (this session)
Phase 4b-live F3 live-run       ← NEXT
Phase 4b-live F4 kill           ← after F3
Phase 4c     CLI completeness
Phase 5      GOAT TUI + 1-page GUI
```

---

## Process principles (locked)

| Principle | Meaning |
|-----------|---------|
| **Process over asset** | Parameterize by symbol / TF / bundle id — no `BtcOnly` modules |
| **Version via config/bundle** | New market/model = new export or metalabel dir, not forked code |
| **Improve, don’t ship suboptimal** | No ML conviction until features + labels match the gate |
| **Same path paper → live** | Only execution client + ledger root flip; no paper-only smarter branch |

---

## What’s working (built + verified)

| Area | Status |
|------|--------|
| Phase 1–4b shadow stack | **Working** |
| Live ledger + LivePolicy (F1) | **Working** |
| `live-check` readiness | **Working** (`submit_wired=true`) |
| **LiveExecClient + HL adapter (F2)** | **Working** (offline mock; SDK optional for real place) |
| Paper/shadow no-submit barriers | **Working** |

## What’s not built yet

| Item | Phase | Notes |
|------|-------|--------|
| `live-run` daemon + live engine wiring | **F3** | Reuse paper shell |
| Kill switch / cancel open | **F4** | |
| CLI completeness pass | **4c** | Partial |
| GOAT TUI / 1-page GUI | **5** | |

**Rules:** signals.parquet = parity only; never VectorBT → live; paper ledger ≠ live ledger.

---

## Key surfaces (current code)

| Path | Role |
|------|------|
| `src/hypervector/live/exec_client.py` | **F2** Protocol + HL place adapter + factories |
| `src/hypervector/live/policy.py` | Secrets / arm / max notional fail-closed |
| `src/hypervector/live/ledger.py` | Live decisions under `data/live/decisions/` |
| `src/hypervector/paper/*` | Shadow/paper path — **must not** import exec client |
| `src/hypervector/cli.py` | paper-* + live-check |
| `tests/test_live_exec_client.py` | F2 offline suite |
| `tests/test_paper_no_submit.py` | Structural no-testnet / no-submit barriers |
| `configs/default.toml` | `[live] enabled = false`, `max_notional_usd = 50` |

---

## Verify / smoke (working today)

```bash
uv run pytest tests/ -q -m "not network"
# Expected: 261+ passed offline
uv run python -m hypervector live-check
# → submit_wired=true, can_start=false, start_gate=refused, venue_submit=false
uv run python -m hypervector paper-check
uv run pytest tests/test_live_exec_client.py tests/test_paper_no_submit.py -q
```

---

## Non-goals (until F3/F4 design says otherwise)

- Accidental venue orders (still forbidden without arm+secrets+enabled)  
- Testnet as validation path  
- VectorBT → live skip of Phase 2/paper  
- Shared paper/live ledgers  
- Building TUI/GUI before CLI completeness  

---

## Agent notes

- Phase 2–4b shadow **closed**. Paper completeness **A done**. **4b-live F1+F2 done**.  
- **Next:** **F3** `live-run` + live ledger decision writes using F2 client.  
- Daemon default remains **shadow** dry-run; paper never constructs exec client.  
- Production place needs optional `hyperliquid-python-sdk` + `eth_account` (not hard dep).  
- Specs: `docs/superpowers/specs/2026-07-23-phase4b-live-design.md`.  
- Branch not pushed. Do not commit `audio/`.  

---

## Outgoing session summary

**4b-live F2 implemented on `feat/phase4b-live-f2-exec-client` (2026-07-23).**

| Arc | Highlights |
|-----|------------|
| F2a–e | Protocol, HL adapter, factory gates, mock tests, live-check wired |
| Verify | offline **261 passed**; live-check submit_wired=true / start refused |
| Decision | **neural-trader rejected** (unchanged) |

**Next human/agent:** **4b-live F3** — `live-run` daemon + live ledger (see CLEAN SESSION START).  

**Not done:** live-run, kill cancel, full 4c, TUI/GUI, merge/push of F2 branch.
