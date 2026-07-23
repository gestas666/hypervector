# HANDOFF — hypervector

**Saved:** 2026-07-23 — Phase 4b shadow **verified** (soak PASS + expert review + banner honesty fix)  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase4a-book-fills-metalabel`  
**HEAD:** `55c8189` — verification tip (banner fix `07a10eb` + HANDOFF pin; base Task 6 `9579981`)  
**Working tree:** clean except untracked `audio/` (ignore). Not pushed.

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
| Phase **4b-live** (real submit + `data/live/`) | **Not started** — next design when Albert asks |
| Phase 4c CLI | **Not started** (shadow flags only in 4b) |
| Phase 5 TUI + 1-page GUI | **Not started** |

**Outgoing session:** 4b shadow **re-proven** end-to-end (offline 228, barriers, paper-check, dual smoke, mainnet soak with live L2 fill). Banner now says `SHADOW MODE` under default.  
**Incoming session:** optional longer shadow soak for ops confidence **or** **4b-live design** (real submit, kill switch, `data/live/`). **Still no venue orders until 4b-live is designed and approved.**

---

## CLEAN SESSION START — 4b-live design (or optional longer soak)

### Goal (one sentence)

Shadow path is trusted; next product step is **4b-live design** (real submit + live ledger + kill switch) when Albert asks — optional longer shadow soak only if more ops confidence is wanted first.

### Bootstrap commands

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb
git log -8 --oneline   # expect 4b Task 6 commit at tip
uv sync --all-extras
uv run pytest tests/ -q -m "not network"   # ~228 passed
uv run python -m hypervector paper-check
# → mode/execution_mode=shadow, network=mainnet, no_submit=true,
#   submitted_default=false, order_intent_schema=hv_order_intent_v1,
#   preferred_fill_model=l2_walk_v1, live.enabled=false
# Banner on paper-run: SHADOW MODE — no venue orders (default)
```

### Shadow soak (how to run / stop / check)

```bash
SOAK_ROOT=/tmp/hv4b-soak
mkdir -p "$SOAK_ROOT"
uv run python -m hypervector --data-root "$SOAK_ROOT" infra-init

# Default paper-run mode is shadow (mainnet-honest, no venue orders)
uv run python -m hypervector --data-root "$SOAK_ROOT" paper-run \
  --path data/exports/downtrend_crown_stack_short_c4fd7067 \
  --conviction 0.5 \
  --preferred-fill-model l2_walk_v1 \
  --max-book-age-ms 3000 \
  --no-metalabel \
  --poll-interval 5 \
  --stop-file /tmp/hv4b-soak.stop \
  2>"$SOAK_ROOT/stderr.log" | tee "$SOAK_ROOT/stdout.json"

# Force offline-compat paper mode: paper-run --mode paper
# Stop:  touch /tmp/hv4b-soak.stop

python3 - <<'PY'
import json
from pathlib import Path
from collections import Counter
p = Path("/tmp/hv4b-soak/paper/decisions/decisions.jsonl")
rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
fills = [r for r in rows if r.get("action") not in ("funding", None) and r.get("fill_model_id")]
print("fills", len(fills), Counter(r.get("fill_model_id") for r in fills))
print("execution_mode", Counter(r.get("execution_mode") for r in rows))
print("submitted", Counter(r.get("submitted") for r in rows))
print("fallback", Counter(r.get("fill_fallback_reason") for r in fills))
for r in fills[-5:]:
    print({k: r.get(k) for k in [
        "feed_ts","action","execution_mode","submitted","network",
        "fill_model_id","fill_fallback_reason","order_intent"]})
PY
```

**Soak pass criteria (4b shadow) — all PASS (2026-07-23 verification):**
1. Daemon / decisions: `execution_mode=shadow`, `submitted=false`, `network=mainnet` on market rows. **PASS**  
2. Market fills include `order_intent` with `submit_enabled=false`, schema `hv_order_intent_v1`. **PASS**  
3. Warm-up: `bar_close_slippage_v1` + `book_missing` (no live BBO on old bars). **PASS**  
4. Live bars: when book fresh, may be `l2_walk_v1`; never invent depth. **PASS** (1× live l2 close observed).  
5. **Zero** files under soak `data/live/`; ledger only under `data/paper/`. **PASS**  
6. Offline suite still green; barrier tests in `tests/test_paper_no_submit.py` green. **PASS** (228 offline).

**Soak notes:** `docs/superpowers/notes/2026-07-22-phase4b-shadow-soak.md`

### Agent checklist

1. Read **this HANDOFF**.  
2. Confirm offline suite green (~228) + verification tip at HEAD.  
3. Optional: longer mainnet shadow soak for ops confidence — **no submit path**.  
4. **Never** place venue orders until **4b-live** design locks them.  
5. **Never** write `data/live/` from paper/shadow.  
6. Next design when Albert asks: 4b-live (real submit, kill switch, live ledger).  
7. End session: update this HANDOFF + HEAD + soak notes.

### Phase 4b task board (COMPLETE)

| Task | Deliverable | Status | Commit |
|------|-------------|--------|--------|
| docs | Design + plan | **Done** | `4429b52` / `d514d39` |
| **1** | `build_order_intent` (`hv_order_intent_v1`) | **Done** | `46f269d` |
| **2** | Ledger allow `paper\|shadow`; still refuse live | **Done** | `172e506` |
| **3** | Engine stamps `submitted=false` + `order_intent` | **Done** | `72cab62` |
| **4** | Session/runner; daemon default **shadow** | **Done** | `a8d79f8` |
| **5** | paper-check surface + paper-run mode flag | **Done** | `e1eea31` |
| **6** | No-submit barriers + offline verify + HANDOFF | **Done** | Task 6 tip |

**Plan path:** `docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md`  
**Design path:** `docs/superpowers/specs/2026-07-22-phase4b-mainnet-shadow-design.md`

### Phase 4a task board (COMPLETE)

| Task | Deliverable | Status | Commit |
|------|-------------|--------|--------|
| docs | Design + plan | **Done** | `171d955` |
| **1** | `FillModel` protocol + `bar_close` extraction | **Done** | `6aeba90` |
| **2** | `BookSnapshot` + HL L2 REST `BookFeed` | **Done** | `782032e` |
| **3** | `top_bps_v1` + select stale/missing fallback | **Done** | `2f149c9` |
| **4** | `l2_walk_v1` VWAP + shortfall | **Done** | `e788152` + `ff4a417` |
| **5** | Metalabel scale-only ConvictionProvider (default off) | **Done** | `70f1367` |
| **6** | CLI/config/`paper-check` + HANDOFF | **Done** | `9a2f369` |
| fix | Warm-up **no** live book; arm L2 only for live loop | **Done** | `09329f4` |

### Architecture (locked — 4a + 4b shadow shipped)

```text
export + configs → paper daemon (Phase 3 shell)
HL bars → HypervectorStrategy (alpha unchanged)
HL L2 book → BookFeed → BookSnapshot  (LIVE phase only)
  warm-up: enable_book_poll=False → bar_close + book_missing
  after warm: one poll to arm, then poll on live bars
FillModel: bar_close_slippage_v1 | top_bps_v1 | l2_walk_v1
  selection: prefer l2 when book fresh; else fallback + fill_fallback_reason
ExplicitFillEngine → data/paper/
  execution_mode=shadow (daemon default) | paper (offline/tests)
  submitted=false, network=mainnet, order_intent on market fills
  submit_enabled always false on intent

Metalabel (default OFF):
  Metalabeler p ∈ [0,1] → conviction = p (scale only, no skip floor)
  → existing risk_pct_from_conviction / position_size_frac
  failure → fallback_fixed
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
| **4b submit** | **Never** — order intent logged; `submit_enabled=false` |
| **4b ledger** | Still `data/paper/`; refuse `data/live/` |
| **Daemon default** | `execution_mode=shadow` |
| TUI / GUI | **Out of scope** (Phase 5) |
| Blog VBT+LGBM primary classifier | **Not** the product path |

### Success bar (4b shadow — met + re-verified 2026-07-23)

1. Offline suite green (`~228` passed, `-m "not network"`).  
2. Order intent schema + always `submit_enabled=false`.  
3. Ledger accepts `paper|shadow`; refuses live paths.  
4. Engine stamps `submitted=false`, `network=mainnet`, `order_intent` on market fills.  
5. Daemon default `shadow`; offline tests can force `paper`.  
6. `paper-check` reports shadow/mainnet/no_submit surface; `live.enabled` false.  
7. Structural barriers: no testnet in `HL_INFO_URL`; no exchange-submit imports in `paper/`.  
8. No `data/live/` writes; no venue orders.  
9. Daemon stderr banner matches mode (`SHADOW MODE` default / `PAPER MODE` when forced).

### Out of scope remaining

- **4b-live** real submit, kill switch, secrets-required trading, `data/live/`  
- 4c full CLI completeness epic  
- Phase 5 GOAT TUI / 1-page GUI  
- userFees (optional DG — deferred)  
- ML training / LEXLB primary-signal notebook architecture  

---

## Docs map (canonical)

| Role | Path |
|------|------|
| **Phase 4b design (APPROVED / SHIPPED shadow)** | `docs/superpowers/specs/2026-07-22-phase4b-mainnet-shadow-design.md` |
| **Phase 4b plan (COMPLETE Tasks 1–6)** | `docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md` |
| **Phase 4a design (APPROVED / SHIPPED)** | `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md` |
| **Phase 4a plan (COMPLETE Tasks 1–6)** | `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md` |
| Phase 3 plan (COMPLETE) | `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md` |
| Phase 3 design (approved) | `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md` |
| Pipeline / paper identity lock | `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` |
| Phase 1 design | `docs/superpowers/specs/2026-07-21-phase1-vectorbt-design.md` |
| Phase 2 plan (CLOSED) | `docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md` |
| Infra I2 | `docs/infra-data-layout.md` |
| This handoff | `HANDOFF.md` |

---

## Phase 4b progress (6/6)

| Task | Deliverable | Status | Commit |
|------|-------------|--------|--------|
| docs | Design + plan | **Done** | `4429b52` / `d514d39` |
| 1 | Order intent builder | **Done** | `46f269d` |
| 2 | Ledger paper\|shadow modes | **Done** | `172e506` |
| 3 | Engine submitted + order_intent | **Done** | `72cab62` |
| 4 | Daemon default shadow | **Done** | `a8d79f8` |
| 5 | CLI paper-check + mode flag | **Done** | `e1eea31` |
| 6 | Barriers + offline verify + HANDOFF | **Done** | Task 6 tip |

**Success criteria met:** offline suite **228 passed** (`-m "not network"`); mainnet-only HL info URL; daemon default shadow; intents never submit-enabled; ledger stays paper root; `paper-check` surfaces no_submit/mainnet/shadow; mainnet soak PASS with live `l2_walk_v1` fill; no venue orders.

### How to run paper-check / paper-run (Phase 4b shadow)

```bash
# Identity + readiness (no secret values; live.enabled always false in report)
uv run python -m hypervector --data-root data paper-check
# → paper.mode=shadow, paper.execution_mode=shadow, network=mainnet,
#   no_submit=true, submitted_default=false,
#   order_intent_schema=hv_order_intent_v1,
#   preferred_fill_model=l2_walk_v1, max_book_age_ms=3000,
#   book_feed=true, l2_walk_available=true,
#   metalabel_enabled=false, metalabel_default_off=true,
#   secrets_present bool, secret_env_names listed
# → live.enabled=false

# Daemon: default --mode shadow (no venue orders)
uv run python -m hypervector --data-root data paper-run \
  --path data/exports/<export_id> \
  --conviction 0.5 \
  --fee-tier 0 \
  [--mode shadow|paper] \    # default shadow
  [--preferred-fill-model l2_walk_v1] \
  [--max-book-age-ms 3000] \
  [--metalabel | --no-metalabel] \   # default off
  [--sandbox] \              # shadow flag only; no real sandbox client
  [--stop-file /tmp/hv.stop] \
  [--max-live-bars N] \      # smoke / offline cap
  [--poll-interval 5]
```

Banner on stderr: `SHADOW MODE — no venue orders` (default) or `PAPER MODE — no venue orders` (`--mode paper`).  
Decisions: `data/paper/decisions/decisions.jsonl` (I2 layout).

### Config knobs (`configs/default.toml` `[paper]`)

```toml
mode = "shadow"                 # paper|shadow; daemon default shadow
preferred_fill_model = "l2_walk_v1"
max_book_age_ms = 3000
metalabel_enabled = false
```

`[live] enabled = false` — 4b-live only.

### Phase 3 locks (do not reopen)

| Decision | Choice |
|----------|--------|
| Host | Paper shell around `HypervectorStrategy` path (session + daemon) |
| Runtime | Long-running daemon (`paper-run`) |
| Fills | Explicit model = ledger truth; sandbox shadow default **off** |
| Sandbox v1 | Flag + `sandbox_fill_px=null` only |
| Secrets | Env names ready; paper public path works **without** keys |
| Live submit | Later **4b-live**; paper/shadow must never place venue orders |

**Secrets env (4b-live later; ignored for order placement in paper/shadow):**

- `HYPERVECTOR_HL_WALLET_ADDRESS`  
- `HYPERVECTOR_HL_API_PRIVATE_KEY`  

---

## Pipeline

```text
Phase 1/1.5  VectorBT research → export
Phase 2      Nautilus historical (params, not signals.parquet)
Phase 3      Paper: live HL bars + same strategy + explicit fills   ← DONE
Phase 4a     Book + staged L2 fills + meta-label scale-only         ← DONE
Phase 4b     Mainnet shadow: intents, submitted=false, no submit    ← DONE
Phase 4b-live Real submit + data/live/ + kill switch                ← NEXT DESIGN
Phase 4c     CLI completeness
Phase 5      GOAT TUI + 1-page GUI
```

| Phase | Role | State |
|-------|------|--------|
| **1 / 1.5** | Research, costs, risk, export | **Done** |
| **2** | Event-driven historical sim | **Done** |
| **3 paper** | Live feed + synthetic fills + paper ledger | **Done** |
| **4a** | Book, impact fills, metalabel wire | **Done** |
| **4b shadow** | Mainnet-honest intents, no venue submit | **Done** |
| **4b-live / 4c** | Real submit + CLI completeness | Later design |
| **5** | TUI + GUI | Later design |

---

## Process principles (locked)

| Principle | Meaning |
|-----------|---------|
| **Process over asset** | Parameterize by symbol / TF / bundle id — no `BtcOnly` modules |
| **Version via config/bundle** | New market/model = new export or metalabel dir, not forked code |
| **Improve, don’t ship suboptimal** | No ML conviction until features + labels match the gate |
| **Same path paper → live** | Only execution client + ledger root flip; no paper-only smarter branch |

Metalabel process (wired, default off):

```text
features (metadata schema)
  → LightGBM + optional calibrator
  → p ∈ [0, 1]
  → conviction = p (scale only) → existing risk band
  failure → fallback_fixed
```

---

## What’s working (built + verified)

| Area | Status |
|------|--------|
| Phase 1 VectorBT research funnel | **Working** |
| Phase 1.5 costs / TP-SL / risk | **Working** |
| Infra I2 (`infra-init`, paper/live roots) | **Working** |
| Export schema v1 (strict: costs, risk, exits) | **Working** |
| Nautilus signals / sizing / bars / actor / runner | **Working** |
| CLI `phase2-run` / `phase2-check` / `export-validate` | **Working** |
| Metalabeler process (`ml/metalabel.py`) | **Working** |
| `CostProvider` + HL fee tiers + signed funding | **Working** |
| `FillModel` + `bar_close` / `top_bps` / `l2_walk` | **Working** |
| `BookSnapshot` + REST `BookFeed` | **Working** |
| `ExplicitFillEngine` (book-aware + shadow stamps) | **Working** |
| `build_order_intent` (`hv_order_intent_v1`) | **Working** |
| Ledger paper\|shadow modes (refuse live) | **Working** |
| Offline `PaperSession` bar walk | **Working** |
| `paper-run` daemon default **shadow** | **Working** |
| `paper-check` shadow/mainnet/no_submit surface | **Working** |
| Structural no-submit / no-testnet barriers | **Working** |
| `ConvictionProvider` scale-only metalabel (default off) | **Working** |
| Sandbox shadow flag | **Working** (no real client) |

## What’s not built yet

| Item | Phase | Notes |
|------|-------|--------|
| Live exec + live ledger + secrets required | **4b-live** | Config flip; kill switch |
| Real Nautilus sandbox client mirror | **harden** | Flag only |
| userFees authenticated fee tier | optional | Deferred |
| Kill switch / supervisor production ops | **4b-live** | |
| CLI completeness pass | **4c** | **Gate before TUI/GUI** |
| GOAT TUI | **5** | Epic terminal ops console |
| 1-page GUI monitoring dashboard | **5** | Same ledger truth as TUI/CLI |
| Phase 2 runner full cost parity with VBT | backlog | Not blocking |

**Rules:** signals.parquet = parity only; never VectorBT → live; paper ledger ≠ live ledger.

---

## Key surfaces (current code)

| Path | Role |
|------|------|
| `src/hypervector/export/schema.py` | Export validate schema v1 |
| `src/hypervector/nautilus/signals.py` | OHLCV → `SignalIntent` |
| `src/hypervector/nautilus/sizing.py` | Loadout → exits / size |
| `src/hypervector/nautilus/bars.py` | Research frame → Nautilus bars |
| `src/hypervector/nautilus/actor.py` | `HypervectorStrategy` |
| `src/hypervector/nautilus/runner.py` | Phase 2 historical backtest |
| `src/hypervector/ml/metalabel.py` | Reusable Metalabeler |
| `src/hypervector/ml/features.py` | Point-in-time FeatureBuilder |
| `src/hypervector/paper/costs.py` | Fee tiers, `CostProvider`, funding math |
| `src/hypervector/paper/fill_models.py` | FillModel protocol + bar_close/top_bps/l2_walk |
| `src/hypervector/paper/book.py` | BookSnapshot + BookFeed |
| `src/hypervector/paper/order_intent.py` | `build_order_intent` shadow intents |
| `src/hypervector/paper/fills.py` | `ExplicitFillEngine` + shadow stamps |
| `src/hypervector/paper/conviction.py` | Fixed / metalabel conviction providers |
| `src/hypervector/paper/session.py` | Offline/incremental bar → fill |
| `src/hypervector/paper/runner.py` | `start_paper_daemon` (default shadow) |
| `src/hypervector/paper/live_node.py` | REST poll feed (WS TODO) |
| `src/hypervector/paper/ledger.py` | Paper decisions JSONL; paper\|shadow; refuse live |
| `src/hypervector/data/hl.py` | Public HL candle + L2 REST (**mainnet only**) |
| `src/hypervector/cli.py` | paper-check shadow surface; paper-run `--mode` |
| `configs/default.toml` | `[paper] mode = "shadow"` + fill/metalabel knobs |
| `tests/test_paper_no_submit.py` | Structural no-testnet / no-submit barriers |

---

## Verify / smoke (working today)

```bash
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<id> --lookback 30 --no-network
uv run python -m hypervector paper-check
uv run python -m hypervector paper-run --path data/exports/<id> --max-live-bars 2
uv run pytest tests/test_paper_no_submit.py -q
uv run pytest tests/ -q -m "not network"
# Expected: 228+ passed offline
```

### Metalabeler (optional; enable with `--metalabel`)

```python
from hypervector.ml import Metalabeler
ml = Metalabeler.from_env()  # HYPERVECTOR_METALABEL_ROOT
p = ml.predict_probability(features)  # [0, 1]
```

---

## Phase 4 / 5 epic

| Track | Deliverable | State |
|-------|-------------|--------|
| **4a** | Order book + staged L2 fills; meta-label scale-only | **Done** |
| **4b shadow** | Mainnet-honest intents; no venue submit | **Done** |
| **4b-live** | Real submit, secrets required, `data/live/`, kill switch | **Next design** |
| **4c** | CLI completeness — every capability consistent | Later design; gate for UX |
| **5a** | **GOAT TUI** — best-in-class terminal ops console | Phase 5 |
| **5b** | **1-page GUI** monitoring dashboard | Phase 5 |

**4b design:** `docs/superpowers/specs/2026-07-22-phase4b-mainnet-shadow-design.md`  

**UX sequencing:** **4c CLI complete → then Phase 5 TUI + GUI.**  
TUI/GUI are views over ledgers/processes — not a second brain. `execution_mode` always obvious. CLI stays scriptable.

Also defer: real Nautilus sandbox client (Phase 3 only plumbs flag + null `sandbox_fill_px`); userFees.

---

## Non-goals (until 4b-live design says otherwise)

- Live venue orders (still forbidden)  
- Testnet as validation path  
- VectorBT → live skip of Phase 2/paper  
- CEX bars claimed as HL book  
- Shared paper/live ledgers  
- Postgres / Redis / k8s  
- Building TUI/GUI before CLI completeness  

---

## Future: agent skill package (after phases)

After paper proven (+ live ops checklist): skill/plugin so agents follow research → phase2 → paper → live correctly. Until then: **this HANDOFF + specs/plans** are the contract.

---

## Agent notes

- Phase 2 plan **closed**. Phase 3 **closed**. Phase 4a **closed**. Phase **4b shadow closed + verified** (Tasks 1–6 + soak PASS).  
- **Next:** **4b-live design** (real submit, kill switch, `data/live/`) when Albert asks — not TUI yet. Optional longer shadow soak only for ops confidence.  
- Daemon default: `execution_mode=shadow`; force paper with `--mode paper`.  
- Soak notes (4b): `docs/superpowers/notes/2026-07-22-phase4b-shadow-soak.md`  
- Soak notes (4a): `docs/superpowers/notes/2026-07-22-phase4a-paper-soak.md`  
- Branch `feat/phase4a-book-fills-metalabel` not pushed; merge/PR when Albert wants.  
- Legacy pre-schema exports fail `export-validate` until re-exported.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator version skew.  
- Paper/shadow must not submit real orders even if wallet/API key env vars are set.  
- Live feed uses **REST poll** fallback (`live_node.py`); full Nautilus WS host optional later.  
- Book: public HL L2 REST **only after warm-up** (one arm poll + live bars).  
- Do not commit `audio/`.  

---

## Outgoing session summary

Done this verification arc (2026-07-23):

- Re-proved offline suite (**228** passed after banner test) and barrier honesty  
- Real `paper-check` surface matches locked 4b fields  
- Dual isolated `paper-run` smokes: all shadow / submitted=false / mainnet / no live writes  
- Bounded mainnet shadow soak: **PASS** all 6 criteria; **1× live `l2_walk_v1` fill** observed  
- Honesty fix: stderr banner matches `execution_mode` (SHADOW vs PAPER)  
- Soak notes + this HANDOFF updated  

**Next human/agent:** optional longer soak **or** **4b-live design** when Albert asks.  

**Not done:** real submit, kill switch, `data/live/`, real sandbox client, TUI/GUI, userFees.
