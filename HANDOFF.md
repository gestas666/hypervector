# HANDOFF — hypervector

**Saved:** 2026-07-22 (evening) — Phase 4a closed + warm-up book fix; paper soak next  
**Project:** `/Users/gestas/Prototypes/hypervector`  
**User:** Albert  
**Branch:** `feat/phase4a-book-fills-metalabel`  
**HEAD:** `b14b38b`+ — docs/soak notes; code tip still includes `09329f4` warm-up fix  
**Working tree:** clean except untracked `audio/` (ignore). Not pushed.  
**Soak:** running at `/tmp/hv4a-soak` (stop: `touch /tmp/hv4a-soak.stop`)

**Prefer this HANDOFF over agentmemory for phase status.**

---

## Status (read this first)

| Layer | State |
|-------|--------|
| Phase 1 / 1.5 research | **Done** |
| Phase 2 actor + historical + metalabeler process | **Done** (plan closed) |
| Phase 3 paper design + plan + code | **Done** (5/5 + funding fix) |
| Phase **4a design + plan + code** | **Done** (Tasks 1–6 + warm-up book fix) |
| Phase **4a paper soak** | **In progress** — warm honesty PASS; live L2 fill pending signal |
| Phase **4b design** | **Approved** — mainnet shadow (no testnet, no submit) |
| Phase **4b plan** | **Ready** — Tasks 1–6 pending implementation |
| Phase 4b-live / 4c CLI | **Not started** (real submit later) |
| Phase 5 TUI + 1-page GUI | **Not started** |

**Outgoing session:** 4b design approved + implementation plan written.  
**Incoming session:** **Implement 4b plan** (`docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md`) via subagent-driven or inline. Skills: write-clean-code; troubleshoot with think-like-a-programmer. No venue orders.

---

## CLEAN SESSION START — paper soak → 4b design

### Goal (one sentence)

Soak paper with real HL bars + L2 (metalabel off) until warm/live fill honesty is proven, then design Phase **4b** (live exec flip + kill switch + `data/live/`) — no venue orders until 4b is locked.

### Bootstrap commands

```bash
cd /Users/gestas/Prototypes/hypervector
git status -sb
git log -8 --oneline   # expect 09329f4 at tip
uv sync --all-extras
uv run pytest tests/ -q -m "not network"   # ~213 passed
uv run python -m hypervector paper-check
# → preferred_fill_model=l2_walk_v1, book_feed/l2_walk true, metalabel off, live.enabled false
```

### Paper soak (how to run / stop / check)

```bash
# Isolated ledger (recommended)
SOAK_ROOT=/tmp/hv4a-soak
mkdir -p "$SOAK_ROOT"
uv run python -m hypervector --data-root "$SOAK_ROOT" infra-init

# Long-running soak (no max-live-bars). Stop with stop-file.
uv run python -m hypervector --data-root "$SOAK_ROOT" paper-run \
  --path data/exports/downtrend_crown_stack_short_c4fd7067 \
  --conviction 0.5 \
  --preferred-fill-model l2_walk_v1 \
  --max-book-age-ms 3000 \
  --no-metalabel \
  --poll-interval 5 \
  --stop-file /tmp/hv4a-soak.stop \
  2>"$SOAK_ROOT/stderr.log" | tee "$SOAK_ROOT/stdout.json"

# Stop:  touch /tmp/hv4a-soak.stop

# Honesty checks on decisions:
python3 - <<'PY'
import json
from pathlib import Path
from collections import Counter
p = Path("/tmp/hv4a-soak/paper/decisions/decisions.jsonl")
rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
fills = [r for r in rows if r.get("action") not in ("funding", None) and r.get("fill_model_id")]
print("fills", len(fills), Counter(r.get("fill_model_id") for r in fills))
print("fallback", Counter(r.get("fill_fallback_reason") for r in fills))
print("execution_mode", Counter(r.get("execution_mode") for r in rows))
# Warm should be bar_close + book_missing; live may show l2_walk_v1 with BBO
for r in fills[-5:]:
    print({k: r.get(k) for k in [
        "feed_ts","action","fill_model_id","fill_fallback_reason",
        "mark_px","fill_px","bbo_bid","bbo_ask","book_age_ms"]})
PY
```

**Soak pass criteria:**
1. Warm-up market fills: `bar_close_slippage_v1` + `fill_fallback_reason=book_missing` (no live BBO on old bars).  
2. Live bars after warm: when book fresh, fills may be `l2_walk_v1` with BBO; never invent depth.  
3. All rows `execution_mode=paper`; **zero** files under soak `data/live/`.  
4. No REST hammer / ConnectionReset storm during warm.  
5. Offline suite still green after any soak-driven fixes.

### Agent checklist

1. Read **this HANDOFF**.  
2. Confirm offline suite green + HEAD is `09329f4` or later.  
3. **Soak first** — do not start 4b code before design.  
4. After soak pass: open **4b design** (live flip, secrets, kill switch, live ledger).  
5. **Never** place venue orders until 4b design locks them.  
6. **Never** write `data/live/` from paper.  
7. End session: update this HANDOFF + HEAD + soak notes.

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

**Plan path:** `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md`  
**Design path:** `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md`  
**Whole-branch review:** `.superpowers/sdd/phase4a-whole-branch-review.md` (REQUEST CHANGES → fixed)

### Architecture (locked — 4a shipped)

```text
export + configs → paper daemon (Phase 3 shell)
HL bars → HypervectorStrategy (alpha unchanged)
HL L2 book → BookFeed → BookSnapshot  (LIVE phase only)
  warm-up: enable_book_poll=False → bar_close + book_missing
  after warm: one poll to arm, then poll on live bars
FillModel: bar_close_slippage_v1 | top_bps_v1 | l2_walk_v1
  selection: prefer l2 when book fresh; else fallback + fill_fallback_reason
ExplicitFillEngine → data/paper/ (execution_mode=paper)

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
| Host | Thin paper shell (not full Nautilus node in 4a) |
| Book transport v1 | Public HL **REST** L2 (`l2Book`); WS later |
| Live / TUI / GUI | **Out of scope** (4b / Phase 5) |
| Blog VBT+LGBM primary classifier | **Not** the product path |

### Success bar (4a — met)

1. Offline suite green with bar-close path (Phase 3 no regression).  
2. Golden book tests: top_bps + l2 VWAP + shortfall + stale fallback.  
3. Preferred fill `l2_walk_v1` when book fresh.  
4. Metalabel optional; default fixed conviction.  
5. `paper-check` reports book/fill/metalabel surface; `live.enabled` false.  
6. No `data/live/` writes; no venue orders.

### Out of scope remaining

- 4b live exec, kill switch, secrets-required trading  
- 4c full CLI completeness epic  
- Phase 5 GOAT TUI / 1-page GUI  
- userFees (optional DG — deferred)  
- ML training / LEXLB primary-signal notebook architecture  

---

## Docs map (canonical)

| Role | Path |
|------|------|
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

## Phase 4a progress (6/6)

| Task | Deliverable | Status | Commit |
|------|-------------|--------|--------|
| docs | Design + plan | **Done** | `171d955` |
| 1 | FillModel + bar_close extract | **Done** | `6aeba90` |
| 2 | BookSnapshot + BookFeed | **Done** | `782032e` |
| 3 | top_bps_v1 + select_fill_model | **Done** | `2f149c9` |
| 4 | l2_walk_v1 preferred | **Done** | `e788152` |
| 4 fix | pure VWAP (no extra slip) | **Done** | `ff4a417` |
| 5 | Metalabel ConvictionProvider default off | **Done** | `70f1367` |
| 6 | CLI/config/paper-check + HANDOFF | **Done** | `9a2f369` |
| fix | Warm-up without live book; live-only L2 arm | **Done** | `09329f4` |

**Success criteria met:** offline suite **213 passed** (`-m "not network"`); preferred fill `l2_walk_v1` with bar_close fallback; metalabel default off; `paper-check` surfaces book/fill/metalabel; `live.enabled` false; no venue orders. Warm-up does not apply live L2 to historical bars (`09329f4`).

### How to run paper-check / paper-run (Phase 4a)

```bash
# Identity + readiness (no secret values; live.enabled always false in report)
uv run python -m hypervector --data-root data paper-check
# → paper.execution_mode=paper, live_feed_loop=true, sandbox_enabled=false,
#   preferred_fill_model=l2_walk_v1, max_book_age_ms=3000,
#   book_feed=true, l2_walk_available=true,
#   metalabel_enabled=false, metalabel_default_off=true,
#   secrets_present bool, secret_env_names listed
# → live.enabled=false

# Daemon: warm-up + live HL REST bar poll + book-aware fills (no venue orders)
uv run python -m hypervector --data-root data paper-run \
  --path data/exports/<export_id> \
  --conviction 0.5 \
  --fee-tier 0 \
  [--preferred-fill-model l2_walk_v1] \
  [--max-book-age-ms 3000] \
  [--metalabel | --no-metalabel] \   # default off
  [--sandbox] \              # shadow flag only; no real sandbox client
  [--stop-file /tmp/hv.stop] \
  [--max-live-bars N] \      # smoke / offline cap
  [--poll-interval 5]
```

Banner on stderr: `PAPER MODE — no venue orders`.  
Decisions: `data/paper/decisions/decisions.jsonl` (I2 layout).

### Config knobs (`configs/default.toml` `[paper]`)

```toml
preferred_fill_model = "l2_walk_v1"
max_book_age_ms = 3000
metalabel_enabled = false
```

`[live] enabled = false` — Phase 4b only.

### Phase 3 locks (do not reopen)

| Decision | Choice |
|----------|--------|
| Host | Paper shell around `HypervectorStrategy` path (session + daemon) |
| Runtime | Long-running daemon (`paper-run`) |
| Fills | Explicit model = ledger truth; sandbox shadow default **off** |
| Sandbox v1 | Flag + `sandbox_fill_px=null` only |
| Secrets | Env names ready; paper public path works **without** keys |
| Live | Config flip later (Phase 4b); paper must never place venue orders |

**Secrets env (Phase 4b live; ignored for order placement in paper):**

- `HYPERVECTOR_HL_WALLET_ADDRESS`  
- `HYPERVECTOR_HL_API_PRIVATE_KEY`  

---

## Pipeline

```text
Phase 1/1.5  VectorBT research → export
Phase 2      Nautilus historical (params, not signals.parquet)
Phase 3      Paper: live HL bars + same strategy + explicit fills   ← DONE
Phase 4a     Book + staged L2 fills + meta-label scale-only         ← DONE
Phase 4b     Live exec flip + kill switch                           ← NEXT DESIGN
Phase 4c     CLI completeness
Phase 5      GOAT TUI + 1-page GUI
```

| Phase | Role | State |
|-------|------|--------|
| **1 / 1.5** | Research, costs, risk, export | **Done** |
| **2** | Event-driven historical sim | **Done** |
| **3 paper** | Live feed + synthetic fills + paper ledger | **Done** |
| **4a** | Book, impact fills, metalabel wire | **Done** |
| **4b–4c** | Live + CLI completeness | Later design |
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
| `ExplicitFillEngine` (book-aware selection + fallback log) | **Working** |
| Offline `PaperSession` bar walk | **Working** |
| `paper-run` daemon (warm + REST poll + stop + fill/metalabel flags) | **Working** |
| `paper-check` (book/fill/metalabel surface; live false) | **Working** |
| `ConvictionProvider` scale-only metalabel (default off) | **Working** |
| Sandbox shadow flag | **Working** (no real client) |

## What’s not built yet

| Item | Phase | Notes |
|------|-------|--------|
| Live exec + live ledger + secrets required | **4b** | Config flip; kill switch |
| Real Nautilus sandbox client mirror | **4 / harden** | Flag only |
| userFees authenticated fee tier | optional | Deferred |
| Kill switch / supervisor production ops | **4b** | |
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
| `src/hypervector/paper/fills.py` | `ExplicitFillEngine` + sandbox shadow keys |
| `src/hypervector/paper/conviction.py` | Fixed / metalabel conviction providers |
| `src/hypervector/paper/session.py` | Offline/incremental bar → fill |
| `src/hypervector/paper/runner.py` | `start_paper_daemon` (fill + metalabel flags) |
| `src/hypervector/paper/live_node.py` | REST poll feed (WS TODO) |
| `src/hypervector/paper/ledger.py` | Paper decisions JSONL; refuse live path |
| `src/hypervector/data/hl.py` | Public HL candle + L2 REST |
| `src/hypervector/cli.py` | paper-check surface; paper-run 4a flags |
| `configs/default.toml` | `[paper]` preferred fill / book age / metalabel |

---

## Verify / smoke (working today)

```bash
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<id> --lookback 30 --no-network
uv run python -m hypervector paper-check
uv run python -m hypervector paper-run --path data/exports/<id> --max-live-bars 2
uv run pytest tests/ -q -m "not network"
# Expected: 210+ passed offline
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
| **4b** | Live exec flip, secrets required, `data/live/`, kill switch | **Next design** |
| **4c** | CLI completeness — every capability consistent | Later design; gate for UX |
| **5a** | **GOAT TUI** — best-in-class terminal ops console | Phase 5 |
| **5b** | **1-page GUI** monitoring dashboard | Phase 5 |

**4a design:** `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md`  

**UX sequencing:** **4c CLI complete → then Phase 5 TUI + GUI.**  
TUI/GUI are views over ledgers/processes — not a second brain. `execution_mode` always obvious. CLI stays scriptable.

Also defer: real Nautilus sandbox client (Phase 3 only plumbs flag + null `sandbox_fill_px`); userFees.

---

## Non-goals (until Phase 4b design says otherwise)

- Live venue orders (still forbidden until 4b)  
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

- Phase 2 plan **closed**. Phase 3 **closed**. Phase 4a **closed** (Tasks 1–6 + `09329f4`).  
- **Next:** finish **paper soak** → then **4b design** (not live orders, not TUI).  
- Soak notes: `docs/superpowers/notes/2026-07-22-phase4a-paper-soak.md`  
- Soak runtime: `/tmp/hv4a-soak` + stop `/tmp/hv4a-soak.stop` + pid `/tmp/hv4a-soak.pid`  
- Branch `feat/phase4a-book-fills-metalabel` not pushed; merge/PR when Albert wants.  
- Legacy pre-schema exports fail `export-validate` until re-exported.  
- Upstream noise: Nautilus `Timestamp.utcnow` Pandas4Warning; sklearn calibrator version skew.  
- Paper must not submit real orders even if wallet/API key env vars are set.  
- Live feed uses **REST poll** fallback (`live_node.py`); full Nautilus WS host optional later.  
- Book: public HL L2 REST **only after warm-up** (one arm poll + live bars).  
- Do not commit `audio/`.  

---

## Outgoing session summary

Done this arc:

- Phase 4a Tasks 1–6 (`171d955`…`9a2f369`)  
- Pure L2 VWAP fix (`ff4a417`)  
- Warm-up without live book + honesty fixes (`09329f4`)  
- Offline **213** passed; whole-branch review blocker closed  
- HANDOFF updated for soak → 4b; soak process started under `/tmp/hv4a-soak`  

**Next human/agent:** monitor soak pass criteria → then 4b design.  

**Not done:** live exec, kill switch, real sandbox client, TUI/GUI, userFees.
