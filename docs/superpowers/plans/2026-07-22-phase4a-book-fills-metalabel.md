# Phase 4a Book Fills + Meta-label Wire Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make paper fills honest (book + staged models ending in L2 walk) without Phase 3 regressions, then optionally wire meta-label scale-only conviction into existing risk sizing — no venue orders, no live ledger, no TUI/GUI.

**Architecture:** Extend Phase 3 paper shell (Approach 1). Extract `FillModel` protocol; add `BookFeed` (public HL REST L2); select fill model by book freshness (`top_bps_v1` → prefer `l2_walk_v1`, fallback `bar_close_slippage_v1` with logged reason). After fills green, add `ConvictionProvider` (fixed | metalabel | fallback_fixed) using existing `Metalabeler` + thin point-in-time `FeatureBuilder`.

**Tech Stack:** Python 3.13, existing `hypervector.paper` / `ml.metalabel`, `requests` for HL public info, pytest, uv. No new heavy deps. No private key required for book/bars.

**Spec:** `docs/superpowers/specs/2026-07-22-phase4a-book-fills-metalabel-design.md`  
**Prior (done):** Phase 3 plan `2026-07-22-phase3-paper-live-feed.md` — do not re-execute Phase 3.

## Global Constraints

- **Process over asset:** symbol/TF/export/bundle via config/env — no BTC-only modules.
- **Paper ≠ live:** writes only `data/paper/`; refuse `data/live/`; `execution_mode=paper` forced.
- **No venue orders** in this plan.
- **Fill honesty:** preferred model after Task 4 = `l2_walk_v1` when book fresh; never silent fallback.
- **Order of work:** Tasks 1–4 (fills/book) before Task 5 (metalabel). Do not default-on metalabel until L2 path tests pass.
- **Meta-label policy:** scale only — `conviction = clip(p, 0, 1)`; **no skip floor**.
- **Sizing:** existing `risk_pct_from_conviction` / `position_size_frac` only — no second leverage model.
- **Metalabel failure:** log + `conviction_source=fallback_fixed` (fixed conviction).
- **Defaults:** metalabel **off**; `max_book_age_ms = 3000`.
- Infra I2 only; no Postgres/Redis/k8s.
- TDD: failing test → minimal code → pass → commit per task.
- Verification: offline suite. Validation: optional network book smoke after offline green.

## Traceability (SRS → tasks)

| Spec tag | Task |
|----------|------|
| SRS_HV4A_FALLBACK (extract path) | Task 1 |
| SRS_HV4A_BOOK, SRS_HV4A_STALE (age helper) | Task 2 |
| SRS_HV4A_TOP, SRS_HV4A_LOG (partial), SRS_HV4A_STALE | Task 3 |
| SRS_HV4A_L2, SRS_HV4A_PARTIAL, SRS_HV4A_LOG, SRS_HV4A_ORDER (prereq) | Task 4 |
| SRS_HV4A_ML_SCALE, SRS_HV4A_ML_SIZE, SRS_HV4A_ML_PIT, SRS_HV4A_ML_FAIL, SRS_HV4A_ORDER | Task 5 |
| SRS_HV4A_NO_VENUE, SRS_HV4A_LEDGER, SRS_HV4A_PROCESS, paper-check surface | Task 6 |

## Phase boundary

| Phase | In this plan? |
|-------|----------------|
| **4a** Book + staged fills + metalabel scale-only | **Yes** |
| **4b** Live exec / kill switch / `data/live/` | **No** |
| **4c** CLI completeness pass | **No** (only flags needed for 4a) |
| **5** TUI / GUI | **No** |

## Status at plan write

### Done (do not rebuild)

| Area | Location |
|------|----------|
| Phase 3 paper costs/fills/session/runner | `paper/costs.py`, `fills.py`, `session.py`, `runner.py`, `live_node.py` |
| Paper ledger + CLI | `paper/ledger.py`, `cli.py` paper-check/paper-run |
| Metalabeler inference process | `ml/metalabel.py` |
| Risk sizing | `sweep/sizing.py`, `nautilus/sizing.py` |
| HL candles REST | `data/hl.py` (`HL_INFO_URL`, `hl_coin`) |
| Design lock | `specs/2026-07-22-phase4a-book-fills-metalabel-design.md` |

### Status (implementation)

Tasks 1–6 **pending**.

---

## File map (planned)

| Path | Responsibility |
|------|----------------|
| `src/hypervector/paper/fill_models.py` | `FillResult`, `FillModel` protocol, bar_close / top_bps / l2_walk, model selection |
| `src/hypervector/paper/book.py` | `BookSnapshot`, `BookFeed`, age/staleness, parse HL L2 payload |
| `src/hypervector/data/hl.py` | Add `fetch_hl_l2_book(symbol, …)` public REST helper |
| `src/hypervector/paper/fills.py` | `ExplicitFillEngine` uses `FillModel` + optional book; extended decision fields |
| `src/hypervector/paper/session.py` | Pass book into fills; optional conviction provider |
| `src/hypervector/paper/runner.py` | Poll book alongside bars; config max age / preferred model |
| `src/hypervector/paper/conviction.py` | `ConvictionProvider` fixed / metalabel / fallback |
| `src/hypervector/ml/features.py` | Thin `FeatureBuilder` (mapping + optional OHLCV adapter hook) |
| `src/hypervector/paper/costs.py` | Allow `fill_model_id` updates to reflect **actual** model (or stop using snapshot id as sole truth — engine logs actual) |
| `src/hypervector/cli.py` | paper-check book/fill fields; paper-run flags for book/metalabel |
| `configs/default.toml` | `[paper]` book + fill + metalabel knobs |
| `tests/test_paper_fill_models.py` | bar_close / top_bps / l2_walk / selection |
| `tests/test_paper_book.py` | parse, age, feed inject |
| `tests/test_paper_fills.py` | extend for new log fields / model injection |
| `tests/test_paper_conviction.py` | scale-only + fallback |
| `tests/test_paper_cli.py` | paper-check new keys |
| `tests/fixtures/hl_l2_sample.json` | Golden L2 payload |
| `HANDOFF.md` | 4a plan progress |

**Constants (lock in code):**

```python
FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1 = "bar_close_slippage_v1"
FILL_MODEL_TOP_BPS_V1 = "top_bps_v1"
FILL_MODEL_L2_WALK_V1 = "l2_walk_v1"
DEFAULT_MAX_BOOK_AGE_MS = 3000
```

---

### Task 1: FillModel protocol + bar_close extraction

**Files:**
- Create: `src/hypervector/paper/fill_models.py`
- Modify: `src/hypervector/paper/fills.py` (delegate price to FillModel; merge FillResult into decision)
- Modify: `src/hypervector/paper/__init__.py` (export if useful)
- Test: `tests/test_paper_fill_models.py`
- Keep green: `tests/test_paper_fills.py`, `tests/test_paper_session.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class FillResult` with:  
    `fill_px: float`, `fill_qty: float`, `fill_model_id: str`, `levels_used: int`, `shortfall_qty: float`,  
    `bbo_bid: float | None`, `bbo_ask: float | None`, `book_age_ms: float | None`,  
    `fill_fallback_reason: str | None`, `requested_qty: float`
  - `class FillModel(Protocol):`  
    `def fill(self, *, side: str, qty: float, mark_px: float, book: Any | None, slippage_bps: float) -> FillResult: ...`
  - `class BarCloseSlippageFillModel:` implements FillModel; `fill_model_id = "bar_close_slippage_v1"`  
    buy: `mark * (1 + slip)`; sell: `mark * (1 - slip)`; levels_used=0; shortfall=0; bbo null; reason null
  - `def select_fill_model(*, preferred: str, book: Any | None, max_book_age_ms: float, now_ms: float | None = None) -> tuple[FillModel, str | None]`  
    Task 1 only needs: if preferred is bar_close or book unusable → BarClose; reason `book_missing` when book is None and preferred != bar_close
- Consumes: none from Tasks 2–5

**Requirements:** SRS_HV4A_FALLBACK (scaffold)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_paper_fill_models.py
from hypervector.paper.fill_models import (
    FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
    BarCloseSlippageFillModel,
)

def test_bar_close_buy_applies_slippage():
    m = BarCloseSlippageFillModel()
    r = m.fill(side="buy", qty=1.0, mark_px=100.0, book=None, slippage_bps=10.0)
    assert r.fill_model_id == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1
    assert abs(r.fill_px - 100.0 * 1.001) < 1e-9
    assert r.fill_qty == 1.0
    assert r.levels_used == 0
    assert r.shortfall_qty == 0.0

def test_bar_close_sell_applies_slippage():
    m = BarCloseSlippageFillModel()
    r = m.fill(side="sell", qty=2.0, mark_px=100.0, book=None, slippage_bps=10.0)
    assert abs(r.fill_px - 100.0 * 0.999) < 1e-9
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

```bash
uv run pytest tests/test_paper_fill_models.py -v
```

Expected: `ModuleNotFoundError` or import error for `fill_models`.

- [ ] **Step 3: Implement `fill_models.py` + wire `ExplicitFillEngine`**

```python
# src/hypervector/paper/fill_models.py (core)
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1 = "bar_close_slippage_v1"
FILL_MODEL_TOP_BPS_V1 = "top_bps_v1"
FILL_MODEL_L2_WALK_V1 = "l2_walk_v1"
DEFAULT_MAX_BOOK_AGE_MS = 3000

@dataclass(frozen=True)
class FillResult:
    fill_px: float
    fill_qty: float
    fill_model_id: str
    levels_used: int
    shortfall_qty: float
    bbo_bid: float | None
    bbo_ask: float | None
    book_age_ms: float | None
    fill_fallback_reason: str | None
    requested_qty: float

class FillModel(Protocol):
    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult: ...

class BarCloseSlippageFillModel:
    fill_model_id = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        slip = float(slippage_bps) / 10_000.0
        side_n = side.lower().strip()
        if side_n == "buy":
            px = float(mark_px) * (1.0 + slip)
        else:
            px = float(mark_px) * (1.0 - slip)
        q = float(qty)
        return FillResult(
            fill_px=px,
            fill_qty=q,
            fill_model_id=self.fill_model_id,
            levels_used=0,
            shortfall_qty=0.0,
            bbo_bid=None,
            bbo_ask=None,
            book_age_ms=None,
            fill_fallback_reason=None,
            requested_qty=q,
        )
```

In `ExplicitFillEngine.apply_market_fill`:
- Accept optional `book=None` and `fill_model: FillModel | None = None` (default `BarCloseSlippageFillModel()`).
- Replace inline slip math with `result = fill_model.fill(...)`.
- Use `result.fill_px`, `result.fill_qty` for position update.
- Merge into decision record: all `FillResult` fields (overwrite `fill_model_id` with **actual** from result, not only CostSnapshot).

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_paper_fill_models.py tests/test_paper_fills.py tests/test_paper_session.py -q
```

Expected: PASS (no regression).

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/fill_models.py src/hypervector/paper/fills.py tests/test_paper_fill_models.py
git commit -m "feat(paper): FillModel protocol and bar_close extraction for Phase 4a"
```

---

### Task 2: BookSnapshot + HL L2 fetch + BookFeed

**Files:**
- Create: `src/hypervector/paper/book.py`
- Modify: `src/hypervector/data/hl.py` — add L2 fetch
- Create: `tests/fixtures/hl_l2_sample.json`
- Test: `tests/test_paper_book.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class BookLevel: price: float; size: float`
  - `@dataclass(frozen=True) class BookSnapshot:`  
    `symbol: str`, `bids: tuple[BookLevel, ...]`, `asks: tuple[BookLevel, ...]`,  
    `ts_recv_ms: float`, `ts_exchange_ms: float | None`, `source: str`  
    methods: `best_bid() -> float | None`, `best_ask() -> float | None`, `is_empty() -> bool`,  
    `age_ms(now_ms: float) -> float`  # uses ts_exchange_ms if set else ts_recv_ms
  - `def parse_hl_l2_payload(raw: Any, *, symbol: str, ts_recv_ms: float) -> BookSnapshot`  
    # HL info type l2Book: levels as [bids, asks] each list of {px, sz} or [px, sz]
  - `def fetch_hl_l2_book(symbol: str, *, session=None) -> BookSnapshot` in `data/hl.py` or `book.py`  
    POST `HL_INFO_URL` body `{"type": "l2Book", "coin": hl_coin(symbol)}`
  - `class BookFeed:`  
    - `__init__(self, symbol: str, *, max_age_ms: float = 3000)`  
    - `update(self, snap: BookSnapshot) -> None`  
    - `latest(self) -> BookSnapshot | None`  
    - `is_fresh(self, *, now_ms: float | None = None) -> bool`  
    - `poll(self, *, session=None) -> BookSnapshot | None`  # fetch + update; network
- Consumes: `hl_coin`, `HL_INFO_URL` from Task 0 / existing

**Requirements:** SRS_HV4A_BOOK, SRS_HV4A_STALE (helpers)

- [ ] **Step 1: Fixture + failing tests**

```json
// tests/fixtures/hl_l2_sample.json — simplify to match parser; example shape:
{
  "coin": "BTC",
  "time": 1700000000000,
  "levels": [
    [{"px": "100.0", "sz": "1.5"}, {"px": "99.9", "sz": "3.0"}],
    [{"px": "100.1", "sz": "2.0"}, {"px": "100.2", "sz": "1.0"}]
  ]
}
```

```python
# tests/test_paper_book.py
import json
from pathlib import Path
from hypervector.paper.book import parse_hl_l2_payload, BookFeed, BookSnapshot, BookLevel

FIX = Path(__file__).parent / "fixtures" / "hl_l2_sample.json"

def test_parse_hl_l2_orders_bids_desc_asks_asc():
    raw = json.loads(FIX.read_text())
    snap = parse_hl_l2_payload(raw, symbol="BTC-PERP", ts_recv_ms=1700000001000)
    assert not snap.is_empty()
    assert snap.best_bid() == 100.0
    assert snap.best_ask() == 100.1
    assert snap.bids[0].size == 1.5

def test_book_age_and_freshness():
    snap = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 1.0),),
        ts_recv_ms=1000.0,
        ts_exchange_ms=1000.0,
        source="fixture",
    )
    feed = BookFeed("BTC-PERP", max_age_ms=3000)
    feed.update(snap)
    assert feed.is_fresh(now_ms=2000.0) is True
    assert feed.is_fresh(now_ms=5000.0) is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_paper_book.py -v
```

- [ ] **Step 3: Implement `book.py` + `fetch_hl_l2_book`**

Parser rules:
- Accept dict with `levels` as `[bids, asks]`.
- Each level: dict with `px`/`sz` or length-2 sequence.
- Bids sorted by price **descending**; asks **ascending** (sort defensively).
- `ts_exchange_ms` from `time` field if present.
- Empty levels → `is_empty() True`.

`fetch_hl_l2_book`: use `requests.Session`, POST JSON, parse, set `ts_recv_ms = time.time()*1000`, `source="hl_rest_l2"`. On HTTP/parse failure raise or return empty — prefer raise `RuntimeError` with message; BookFeed.poll catches and returns None.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_paper_book.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/book.py src/hypervector/data/hl.py tests/test_paper_book.py tests/fixtures/hl_l2_sample.json
git commit -m "feat(paper): BookSnapshot and HL L2 REST BookFeed for Phase 4a"
```

---

### Task 3: top_bps_v1 + model selection + engine log fields

**Files:**
- Modify: `src/hypervector/paper/fill_models.py` — `TopBpsFillModel`, full `select_fill_model`
- Modify: `src/hypervector/paper/fills.py` — accept preferred model + book + max_age; record fallback reason
- Modify: `tests/test_paper_fill_models.py`
- Modify: `tests/test_paper_fills.py` if needed for new keys

**Interfaces:**
- Produces:
  - `class TopBpsFillModel:`  
    buy fill_px = best_ask * (1+slip); sell = best_bid * (1-slip);  
    if BBO missing → still return result only if caller already selected bar_close; TopBps itself may raise ValueError if book empty
  - `def select_fill_model(*, preferred: str, book: BookSnapshot | None, max_book_age_ms: float, now_ms: float | None = None) -> tuple[FillModel, str | None]:`  
    - If preferred == bar_close → (BarClose, None)  
    - If book is None or empty → (BarClose, "book_missing")  
    - If book.age_ms(now) > max → (BarClose, "book_stale")  
    - If preferred == top_bps → (TopBps, None)  
    - If preferred == l2_walk → (L2Walk if implemented else TopBps for Task 3) — **Task 3: if preferred l2_walk but class not ready, still only register top_bps; Task 4 adds L2**  
    Task 3 selection: preferred in {top_bps, l2_walk} with fresh book → TopBps until Task 4; document temporary: preferred `top_bps_v1` for integration.
  - When fallback used, `FillResult.fill_fallback_reason` set on result (BarClose path should accept optional reason override via wrapper or `BarCloseSlippageFillModel.fill` keyword — cleaner: `select_fill_model` returns reason; engine sets field on record if result.reason is None)

**Engine behavior:**
```python
model, reason = select_fill_model(preferred=self._preferred_fill_model, book=book, max_book_age_ms=self._max_book_age_ms)
result = model.fill(side=..., qty=..., mark_px=..., book=book, slippage_bps=snap.slippage_bps)
# if reason and result.fill_fallback_reason is None: use dataclasses.replace(result, fill_fallback_reason=reason)
```

**Requirements:** SRS_HV4A_TOP, SRS_HV4A_STALE, SRS_HV4A_LOG (partial)

- [ ] **Step 1: Failing tests**

```python
def test_top_bps_buy_uses_ask():
    from hypervector.paper.book import BookSnapshot, BookLevel
    from hypervector.paper.fill_models import TopBpsFillModel, FILL_MODEL_TOP_BPS_V1
    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 2.0),),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = TopBpsFillModel().fill(side="buy", qty=1.0, mark_px=100.0, book=book, slippage_bps=0.0)
    assert r.fill_model_id == FILL_MODEL_TOP_BPS_V1
    assert abs(r.fill_px - 100.1) < 1e-9
    assert r.bbo_ask == 100.1 and r.bbo_bid == 100.0

def test_select_falls_back_when_stale():
    from hypervector.paper.book import BookSnapshot, BookLevel
    from hypervector.paper.fill_models import select_fill_model, FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1, FILL_MODEL_TOP_BPS_V1
    book = BookSnapshot(
        symbol="X",
        bids=(BookLevel(1.0, 1.0),),
        asks=(BookLevel(1.1, 1.0),),
        ts_recv_ms=0.0,
        ts_exchange_ms=0.0,
        source="t",
    )
    model, reason = select_fill_model(
        preferred=FILL_MODEL_TOP_BPS_V1, book=book, max_book_age_ms=3000, now_ms=10_000
    )
    assert model.fill_model_id == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1
    assert reason == "book_stale"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_paper_fill_models.py -v
```

- [ ] **Step 3: Implement TopBps + select + engine kwargs**

`ExplicitFillEngine.__init__` add:
- `preferred_fill_model: str = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1` (Task 3 default remains bar_close for safety; Task 4/6 can default preferred to l2_walk)
- `max_book_age_ms: float = 3000`

`apply_market_fill(..., book: BookSnapshot | None = None)`.

- [ ] **Step 4: Full paper offline**

```bash
uv run pytest tests/test_paper_fill_models.py tests/test_paper_fills.py tests/test_paper_session.py tests/test_paper_book.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/fill_models.py src/hypervector/paper/fills.py tests/test_paper_fill_models.py
git commit -m "feat(paper): top_bps_v1 fill model and book-aware selection"
```

---

### Task 4: l2_walk_v1 destination + prefer when fresh

**Files:**
- Modify: `src/hypervector/paper/fill_models.py` — `L2WalkFillModel`, select prefers L2
- Test: `tests/test_paper_fill_models.py` golden walk + shortfall
- Modify: session/runner to pass book when available (inject for offline)

**Interfaces:**
- Produces:
  - `class L2WalkFillModel:`  
    - buy: walk `book.asks` ascending, accumulate notional/size until qty filled  
    - sell: walk `book.bids` descending  
    - `fill_px = total_notional / filled_qty` if filled_qty > 0 else raise or mark fallback  
    - `fill_qty = min(requested, available)`; `shortfall_qty = requested - fill_qty`  
    - `levels_used` = number of levels with size consumed > 0  
    - **must not** invent depth  
    - bbo from best bid/ask  
  - `select_fill_model`: fresh book + preferred `l2_walk_v1` → L2WalkFillModel

**Requirements:** SRS_HV4A_L2, SRS_HV4A_PARTIAL, SRS_HV4A_LOG, SRS_HV4A_ORDER (prereq for ML)

- [ ] **Step 1: Golden failing tests**

```python
def test_l2_walk_buy_vwap_two_levels():
    from hypervector.paper.book import BookSnapshot, BookLevel
    from hypervector.paper.fill_models import L2WalkFillModel, FILL_MODEL_L2_WALK_V1
    # ask 100.1 x 2.0, 100.2 x 1.0; buy qty 3 → full
    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 5.0),),
        asks=(BookLevel(100.1, 2.0), BookLevel(100.2, 1.0)),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = L2WalkFillModel().fill(side="buy", qty=3.0, mark_px=100.0, book=book, slippage_bps=0.0)
    assert r.fill_model_id == FILL_MODEL_L2_WALK_V1
    # VWAP = (2*100.1 + 1*100.2) / 3 = 100.1333...
    assert abs(r.fill_px - (2 * 100.1 + 1 * 100.2) / 3.0) < 1e-9
    assert r.fill_qty == 3.0
    assert r.shortfall_qty == 0.0
    assert r.levels_used == 2

def test_l2_walk_shortfall_no_invented_depth():
    from hypervector.paper.book import BookSnapshot, BookLevel
    from hypervector.paper.fill_models import L2WalkFillModel
    book = BookSnapshot(
        symbol="BTC-PERP",
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(100.1, 1.0),),
        ts_recv_ms=1.0,
        ts_exchange_ms=1.0,
        source="t",
    )
    r = L2WalkFillModel().fill(side="buy", qty=5.0, mark_px=100.0, book=book, slippage_bps=0.0)
    assert r.fill_qty == 1.0
    assert r.shortfall_qty == 4.0
    assert r.levels_used == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_paper_fill_models.py::test_l2_walk_buy_vwap_two_levels tests/test_paper_fill_models.py::test_l2_walk_shortfall_no_invented_depth -v
```

- [ ] **Step 3: Implement L2WalkFillModel + selection**

If `fill_qty == 0` (empty side): treat as unusable book → caller should fallback; L2Walk can return fill_qty=0 and engine skips or falls back — **spec: do not invent**. Prefer: `select` already ensures non-empty; if walk yields 0, engine logs and skips fill.

Wire `PaperSession` / daemon: hold `BookFeed`; on bar, `book = feed.latest()`; pass into fill engine. Offline tests inject `BookSnapshot` without network.

- [ ] **Step 4: Regression + new tests**

```bash
uv run pytest tests/test_paper_fill_models.py tests/test_paper_fills.py tests/test_paper_session.py tests/test_paper_book.py -q
uv run pytest tests/ -q -m "not network"
```

Expected: all offline PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/fill_models.py src/hypervector/paper/fills.py src/hypervector/paper/session.py src/hypervector/paper/runner.py tests/
git commit -m "feat(paper): l2_walk_v1 fill model as preferred when book fresh"
```

---

### Task 5: ConvictionProvider + FeatureBuilder + metalabel scale-only

**Files:**
- Create: `src/hypervector/paper/conviction.py`
- Create: `src/hypervector/ml/features.py`
- Modify: `src/hypervector/paper/session.py` — conviction per entry from provider
- Modify: `src/hypervector/paper/fills.py` — allow per-fill conviction override on record
- Test: `tests/test_paper_conviction.py`
- Keep: `tests/test_ml_metalabel.py` green

**Interfaces:**
- Produces:
  - `class ConvictionResult(frozen): conviction: float; source: str; metalabel_p: float | None; metalabel_bundle_id: str | None`
  - `class ConvictionProvider(Protocol):`  
    `def resolve(self, *, features: Mapping[str, float] | None = None, bars: pd.DataFrame | None = None) -> ConvictionResult`
  - `class FixedConvictionProvider:` always returns fixed c, source=`fixed`
  - `class MetalabelConvictionProvider:`  
    - `__init__(self, metalabeler: Metalabeler, feature_builder: FeatureBuilder, *, fixed_fallback: float)`  
    - On success: conviction=p, source=`metalabel`, metalabel_p=p  
    - On any error: conviction=fixed_fallback, source=`fallback_fixed`, log exception  
    - **No skip floor**
  - `class FeatureBuilder:`  
    - `build(self, *, feature_names: list[str], bars: pd.DataFrame | None, features: Mapping | None) -> dict[str, float]`  
    - If `features` mapping provided and complete → use it (test path)  
    - Else if bars provided: only fill names that exist as columns on last row; if any missing → raise `FeatureBuildError`  
    - No training; point-in-time = last closed bar only
- Session: if metalabel disabled → FixedConvictionProvider(cli conviction). If enabled → MetalabelConvictionProvider.  
- Decision fields: `conviction`, `conviction_source`, `metalabel_p`, `metalabel_bundle_id`

**Requirements:** SRS_HV4A_ML_*, SRS_HV4A_ORDER

- [ ] **Step 1: Failing tests**

```python
# tests/test_paper_conviction.py
from hypervector.paper.conviction import FixedConvictionProvider, MetalabelConvictionProvider, FeatureBuilder

def test_fixed_provider():
    r = FixedConvictionProvider(0.4).resolve()
    assert r.conviction == 0.4
    assert r.source == "fixed"

def test_metalabel_scales_with_p(monkeypatch):
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a"]
        def predict_probability(self, features):
            return float(features["a"])
    fb = FeatureBuilder()
    prov = MetalabelConvictionProvider(FakeML(), fb, fixed_fallback=0.5)
    r = prov.resolve(features={"a": 0.8})
    assert r.conviction == 0.8
    assert r.source == "metalabel"

def test_metalabel_fallback_on_missing_features():
    class FakeML:
        root = type("R", (), {"name": "bundle"})()
        feature_names = ["a", "b"]
        def predict_probability(self, features):
            raise AssertionError("should not call")
    prov = MetalabelConvictionProvider(FakeML(), FeatureBuilder(), fixed_fallback=0.5)
    r = prov.resolve(features={"a": 0.1})  # missing b
    assert r.conviction == 0.5
    assert r.source == "fallback_fixed"

def test_higher_p_higher_risk_size():
    from hypervector.sweep.sizing import RiskConfig, risk_pct_from_conviction
    cfg = RiskConfig(risk_pct_min=0.01, risk_pct_max=0.05)
    assert risk_pct_from_conviction(0.2, cfg) < risk_pct_from_conviction(0.8, cfg)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_paper_conviction.py -v
```

- [ ] **Step 3: Implement conviction + features; wire session**

Default: metalabel **disabled**. Enable only via config/CLI flag after L2 tests exist (Task 4 done).

Sizing path: `conviction = provider.resolve(...).conviction` then existing `position_size_frac(..., conviction=conviction)`.

- [ ] **Step 4: Tests**

```bash
uv run pytest tests/test_paper_conviction.py tests/test_ml_metalabel.py tests/test_paper_session.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/conviction.py src/hypervector/ml/features.py src/hypervector/paper/session.py src/hypervector/paper/fills.py tests/test_paper_conviction.py
git commit -m "feat(paper): meta-label scale-only ConvictionProvider (default off)"
```

---

### Task 6: CLI, config, paper-check surface, HANDOFF, full verify

**Files:**
- Modify: `src/hypervector/cli.py` — paper-check keys; paper-run `--preferred-fill-model`, `--max-book-age-ms`, `--metalabel` / `--no-metalabel`
- Modify: `configs/default.toml` — `[paper]` section knobs
- Modify: `tests/test_paper_cli.py`
- Modify: `HANDOFF.md`
- Optional: wire `BookFeed.poll` in `runner.py` on interval (already partial in Task 4)

**paper-check payload additions (booleans/strings only; no secrets):**

```python
"preferred_fill_model": "...",
"max_book_age_ms": 3000,
"book_feed": True,  # module/path available
"l2_walk_available": True,
"metalabel_enabled": False,
"metalabel_default_off": True,
"live.enabled": False,  # still false
```

**Requirements:** SRS_HV4A_NO_VENUE, SRS_HV4A_LEDGER, SRS_HV4A_PROCESS

- [ ] **Step 1: Failing CLI test for new keys**

```python
def test_paper_check_reports_fill_and_book_surface(tmp_path):
    # invoke paper-check with data-root tmp; assert keys in JSON/stdout parse
    ...
```

- [ ] **Step 2: Implement CLI + config defaults**

```toml
# configs/default.toml — under [paper] or new keys
# preferred_fill_model = "l2_walk_v1"
# max_book_age_ms = 3000
# metalabel_enabled = false
```

Default preferred after Task 4 complete: `l2_walk_v1` (falls back cleanly without book).

- [ ] **Step 3: Full offline suite**

```bash
uv run pytest tests/ -q -m "not network"
uv run python -m hypervector paper-check
```

Expected: all offline PASS; paper-check shows book/fill/metalabel surface; live still false.

- [ ] **Step 4: Update HANDOFF**

Mark Tasks 1–6 done; next = 4b design or soak paper with book. Note commit SHAs.

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/cli.py configs/default.toml tests/test_paper_cli.py HANDOFF.md
git commit -m "feat(paper): Phase 4a CLI/config surface and handoff"
```

---

## Spec coverage self-review

| Spec requirement | Task |
|------------------|------|
| Book REST L2 | 2, 6 |
| Stale/missing fallback logged | 3, 4 |
| top_bps_v1 | 3 |
| l2_walk_v1 no invented depth | 4 |
| bar_close remains / Phase 3 green | 1, 4, 6 |
| Decision log fields | 1, 3, 4, 5 |
| No venue orders | 6 / all |
| Metalabel after fills; scale only; fallback fixed | 5 |
| Existing risk sizing | 5 |
| Process-over-asset | 2, 5, 6 |
| userFees optional | **Deferred** (non-blocking DG; skip unless free while in Task 6) |

## Placeholder scan

No TBD steps. `userFees` explicitly deferred as optional non-blocker. FeatureBuilder external hyper-pi adapter is optional enhancement inside Task 5 mapping path — OHLCV column passthrough + mapping is enough for 4a tests; full impulse feature parity can follow without blocking L2.

## Type consistency

- `FillResult` fields used in engine decision records in Tasks 1/3/4.  
- `BookSnapshot` consumed by TopBps/L2Walk and `select_fill_model`.  
- `ConvictionResult.source` ∈ {`fixed`, `metalabel`, `fallback_fixed`}.  
- Constants: `FILL_MODEL_*` string ids match design.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-phase4a-book-fills-metalabel.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, executing-plans style with checkpoints  

**Which approach?**
