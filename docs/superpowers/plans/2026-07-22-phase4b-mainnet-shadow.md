# Phase 4b Mainnet Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run mainnet-honest **shadow** trading on the paper shell: real HL mainnet bars/L2, live-grade fills, structured **order intents** logged as if real — **zero venue submits**, ledger stays under `data/paper/`.

**Architecture:** Extend Phase 3/4a paper daemon. Add `OrderIntent` builder + `execution_mode=shadow` + `submitted=false` on market decisions. Ledger accepts `paper|shadow` modes (still refuses `data/live/`). Structural barrier: no order-submit client on shadow path. Reuse 4a warm-up (no live book) and L2 fill selection.

**Tech Stack:** Python 3.13, existing `hypervector.paper`, pytest, uv. No new heavy deps. No private key required. No testnet.

**Spec:** `docs/superpowers/specs/2026-07-22-phase4b-mainnet-shadow-design.md` (**approved** 2026-07-22)  
**Prior (done):** Phase 4a plan `2026-07-22-phase4a-book-fills-metalabel.md` — do not re-execute 4a.  
**Impl style:** write-clean-code (SRP, YAGNI, fail early). Troubleshoot with think-like-a-programmer. Plan with engineering-software (tags, verify vs validate).

## Global Constraints

- **Mainnet only:** use existing `HL_INFO_URL = "https://api.hyperliquid.xyz/info"` — no testnet URL/config path.
- **No venue orders:** must not construct or call any order-submit client in 4b.
- **Ledger:** writes only `data/paper/`; refuse `data/live/` (existing ledger guards).
- **Mode:** daemon shadow → decisions `execution_mode=shadow`, `submitted=false`, `network=mainnet`.
- **Fills:** Phase 4a selection retained; warm-up no live L2 poll.
- **Process over asset:** symbol/TF/export via loadout — no BTC-only modules.
- **Secrets:** optional env presence for future read-only fees; must not enable submit; never log values.
- **TDD:** failing test → minimal code → pass → commit per task.
- **YAGNI:** no real submit, no `data/live/` flip, no TUI, no metalabel default-on.

## Traceability (SRS → tasks)

| Spec tag | Task |
|----------|------|
| SRS_HV4B_INTENT, DG intent schema | Task 1 |
| SRS_HV4B_MODE, SRS_HV4B_LEDGER | Task 2 |
| SRS_HV4B_SUBMITTED, SRS_HV4B_INTENT (wire), SRS_HV4B_MODE | Task 3 |
| SRS_HV4B_SAME_ALPHA, SRS_HV4B_FILLS, SRS_HV4B_WARM, SRS_HV4B_PROCESS | Task 4 |
| SRS_HV4B_CHECK, SRS_HV4B_MAINNET, SRS_HV4B_NO_TESTNET, SRS_HV4B_SECRETS | Task 5 |
| SRS_HV4B_NO_SUBMIT + full offline verify + HANDOFF | Task 6 |

## Phase boundary

| Phase | In this plan? |
|-------|----------------|
| **4b shadow** mainnet compute/log, no submit | **Yes** |
| **4b-live** real submit + `data/live/` | **No** |
| **4c** CLI completeness | **No** (only shadow flags) |
| **5** TUI/GUI | **No** |

## Status at plan write

### Done (do not rebuild)

| Area | Location |
|------|----------|
| Phase 4a fill models + book | `paper/fill_models.py`, `paper/book.py` |
| Warm-up no live book | `paper/runner.py` (`09329f4`) |
| ExplicitFillEngine + session | `paper/fills.py`, `session.py` |
| Ledger refuse live | `paper/ledger.py` |
| HL mainnet info URL | `data/hl.py` `HL_INFO_URL` |
| paper-check / paper-run | `cli.py` |

### Status (implementation)

Tasks 1–6 **Done** (2026-07-22). Commits: `46f269d` → `172e506` → `72cab62` → `a8d79f8` → `e1eea31` → Task 6 tip.

---

## File map (planned)

| Path | Responsibility |
|------|----------------|
| `src/hypervector/paper/order_intent.py` | `build_order_intent(...)` → `hv_order_intent_v1` dict; constants |
| `src/hypervector/paper/ledger.py` | Allow `execution_mode` in `{paper, shadow}`; default paper; refuse live paths |
| `src/hypervector/paper/fills.py` | Engine `execution_mode`; stamp mode, `submitted`, `network`, `order_intent` |
| `src/hypervector/paper/session.py` | Pass execution_mode into engine; build intent on market actions |
| `src/hypervector/paper/runner.py` | Daemon `execution_mode` (default `shadow` for live REST path) |
| `src/hypervector/cli.py` | paper-check shadow surface; `paper-run --shadow` / mode flag |
| `configs/default.toml` | `[paper] mode = "shadow"` comment/default |
| `tests/test_paper_order_intent.py` | Intent schema unit tests |
| `tests/test_paper_ledger.py` | paper vs shadow mode stamps; still refuse live |
| `tests/test_paper_fills.py` | submitted + order_intent on fills |
| `tests/test_paper_cli.py` | paper-check keys; CLI flag |
| `HANDOFF.md` | 4b progress |

**Constants (lock in code):**

```python
EXECUTION_MODE_PAPER = "paper"
EXECUTION_MODE_SHADOW = "shadow"
NETWORK_MAINNET = "mainnet"
ORDER_INTENT_SCHEMA = "hv_order_intent_v1"
HL_INFO_URL  # existing mainnet only
```

---

### Task 1: OrderIntent builder

**Files:**
- Create: `src/hypervector/paper/order_intent.py`
- Create: `tests/test_paper_order_intent.py`
- Modify: `src/hypervector/paper/__init__.py` (export if useful)

**Interfaces:**
- Produces:
  - `ORDER_INTENT_SCHEMA = "hv_order_intent_v1"`
  - `NETWORK_MAINNET = "mainnet"`
  - `def build_order_intent(*, symbol: str, side: str, qty: float, order_type: str = "market", time_in_force: str = "ioc", reduce_only: bool = False, client_ts_ms: float | None = None, notes: str = "shadow-only; not sent") -> dict[str, Any]`
  - Always sets `submit_enabled=False`, `venue="hyperliquid"`, `network=NETWORK_MAINNET`, `schema=ORDER_INTENT_SCHEMA`

**Requirements:** SRS_HV4B_INTENT

- [ ] **Step 1: Write failing tests**

```python
# tests/test_paper_order_intent.py
from hypervector.paper.order_intent import (
    ORDER_INTENT_SCHEMA,
    NETWORK_MAINNET,
    build_order_intent,
)

def test_build_order_intent_market_shadow():
    d = build_order_intent(symbol="BTC-PERP", side="sell", qty=0.01)
    assert d["schema"] == ORDER_INTENT_SCHEMA
    assert d["network"] == NETWORK_MAINNET
    assert d["venue"] == "hyperliquid"
    assert d["symbol"] == "BTC-PERP"
    assert d["side"] == "sell"
    assert d["qty"] == 0.01
    assert d["order_type"] == "market"
    assert d["time_in_force"] == "ioc"
    assert d["reduce_only"] is False
    assert d["submit_enabled"] is False
    assert "client_ts_ms" in d
    assert d["notes"]

def test_build_order_intent_qty_positive():
    import pytest
    with pytest.raises(ValueError):
        build_order_intent(symbol="ETH-PERP", side="buy", qty=0.0)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_paper_order_intent.py -v
```

Expected: import / missing module.

- [ ] **Step 3: Implement `order_intent.py`**

```python
# src/hypervector/paper/order_intent.py
from __future__ import annotations
import time
from typing import Any

ORDER_INTENT_SCHEMA = "hv_order_intent_v1"
NETWORK_MAINNET = "mainnet"

def build_order_intent(
    *,
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    time_in_force: str = "ioc",
    reduce_only: bool = False,
    client_ts_ms: float | None = None,
    notes: str = "shadow-only; not sent",
) -> dict[str, Any]:
    q = float(qty)
    if q <= 0:
        raise ValueError(f"qty must be positive, got {qty!r}")
    side_n = str(side).lower().strip()
    if side_n not in ("buy", "sell"):
        raise ValueError(f"side must be buy|sell, got {side!r}")
    ts = float(client_ts_ms) if client_ts_ms is not None else time.time() * 1000.0
    return {
        "schema": ORDER_INTENT_SCHEMA,
        "network": NETWORK_MAINNET,
        "venue": "hyperliquid",
        "symbol": str(symbol),
        "side": side_n,
        "qty": q,
        "order_type": str(order_type),
        "time_in_force": str(time_in_force),
        "reduce_only": bool(reduce_only),
        "client_ts_ms": ts,
        "submit_enabled": False,  # structural: never true in 4b
        "notes": str(notes),
    }
```

- [ ] **Step 4: Tests PASS**

```bash
uv run pytest tests/test_paper_order_intent.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/order_intent.py tests/test_paper_order_intent.py src/hypervector/paper/__init__.py
git commit -m "feat(paper): order intent builder for mainnet shadow (v1)"
```

---

### Task 2: Ledger allows paper|shadow modes

**Files:**
- Modify: `src/hypervector/paper/ledger.py`
- Modify: `tests/test_paper_ledger.py`

**Interfaces:**
- Produces:
  - `ALLOWED_EXECUTION_MODES = frozenset({"paper", "shadow"})`
  - `append_paper_decision`: if record has `execution_mode` in allowed set, **keep it**; else default `"paper"`. Never force-overwrite a valid `shadow`. Still refuse live paths.
- Consumes: none from Task 1

**Requirements:** SRS_HV4B_MODE, SRS_HV4B_LEDGER

- [ ] **Step 1: Failing tests**

```python
def test_append_preserves_shadow_mode(tmp_path):
    from hypervector.paper.ledger import append_paper_decision
    import json
    p = append_paper_decision(
        tmp_path / "data",
        {"feed_ts": "t0", "action": "enter_long", "execution_mode": "shadow"},
    )
    line = p.read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(line)
    assert row["execution_mode"] == "shadow"

def test_append_defaults_paper_when_mode_missing(tmp_path):
    from hypervector.paper.ledger import append_paper_decision
    import json
    p = append_paper_decision(tmp_path / "data", {"feed_ts": "t0", "action": "x"})
    row = json.loads(p.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["execution_mode"] == "paper"

def test_append_still_refuses_live_root(tmp_path):
    from hypervector.paper.ledger import append_paper_decision, PaperLedgerError
    import pytest
    with pytest.raises(PaperLedgerError):
        append_paper_decision(tmp_path / "data" / "live", {"feed_ts": "t0"})
```

- [ ] **Step 2: Run — expect FAIL** (shadow currently overwritten to paper)

```bash
uv run pytest tests/test_paper_ledger.py -v -k shadow
```

- [ ] **Step 3: Implement ledger mode allow-list**

```python
# ledger.py (core change)
ALLOWED_EXECUTION_MODES = frozenset({"paper", "shadow"})
# in append_paper_decision, replace forced stamp:
mode = record.get("execution_mode")
if mode not in ALLOWED_EXECUTION_MODES:
    mode = "paper"
payload["execution_mode"] = mode
```

Update module docstring: modes paper|shadow under paper root; never live.

- [ ] **Step 4: Full ledger tests**

```bash
uv run pytest tests/test_paper_ledger.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/ledger.py tests/test_paper_ledger.py
git commit -m "feat(paper): ledger accepts execution_mode paper|shadow"
```

---

### Task 3: Engine stamps shadow fields + order_intent

**Files:**
- Modify: `src/hypervector/paper/fills.py`
- Modify: `tests/test_paper_fills.py`

**Interfaces:**
- Consumes: `build_order_intent` from Task 1; ledger from Task 2
- Produces:
  - `ExplicitFillEngine.__init__(..., execution_mode: str = "paper")`
  - Market fills (including skipped zero-qty): set  
    `execution_mode` (engine mode),  
    `submitted=False`,  
    `network="mainnet"`,  
    `order_intent=build_order_intent(...)` when side/qty known  
  - Funding rows: same `execution_mode` + `submitted=False` + `network`; **no** order_intent (or null)
  - Do **not** call any submit API

**Requirements:** SRS_HV4B_SUBMITTED, SRS_HV4B_INTENT, SRS_HV4B_MODE

- [ ] **Step 1: Failing tests**

```python
def test_shadow_market_fill_has_intent_and_submitted_false(tmp_path):
    from hypervector.paper.costs import CostProvider
    from hypervector.paper.fills import ExplicitFillEngine
    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=CostProvider(fee_tier=0, slippage_bps=0.0),
        run_id="r1",
        export_id="e1",
        strategy_name="s",
        symbol="BTC-PERP",
        timeframe="1m",
        conviction=0.5,
        execution_mode="shadow",
    )
    rec = eng.apply_market_fill(
        feed_ts="t0", action="enter_long", side="buy", qty=0.01, mark_px=100.0
    )
    assert rec["execution_mode"] == "shadow"
    assert rec["submitted"] is False
    assert rec["network"] == "mainnet"
    oi = rec["order_intent"]
    assert oi["schema"] == "hv_order_intent_v1"
    assert oi["submit_enabled"] is False
    assert oi["side"] == "buy"
    assert oi["qty"] == 0.01
    # persisted
    text = (tmp_path / "data" / "paper" / "decisions" / "decisions.jsonl").read_text()
    assert "shadow" in text
    assert "order_intent" in text
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_paper_fills.py::test_shadow_market_fill_has_intent_and_submitted_false -v
```

- [ ] **Step 3: Implement engine fields**

In `ExplicitFillEngine.__init__` store `self._execution_mode` validated as paper|shadow.

In `_base_record`:
```python
"execution_mode": self._execution_mode,
"submitted": False,
"network": "mainnet",
```

In `apply_market_fill` after building record (and skipped path):
```python
from hypervector.paper.order_intent import build_order_intent
record["order_intent"] = build_order_intent(
    symbol=self._symbol, side=side_n, qty=qty_f,  # use requested qty for intent
)
```
For skipped fills use requested qty; for filled use original requested `qty_f` (intent is what we wanted to send).

- [ ] **Step 4: Keep existing fills tests green**

```bash
uv run pytest tests/test_paper_fills.py -q
```

Default `execution_mode=paper` so Phase 3 tests still see paper unless they only check via ledger overwrite — after Task 2, engine-set mode is preserved.

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/fills.py tests/test_paper_fills.py
git commit -m "feat(paper): shadow mode stamps submitted=false and order_intent"
```

---

### Task 4: Session + runner wire execution_mode

**Files:**
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/runner.py`
- Modify: `tests/test_paper_session.py` and/or `tests/test_paper_cli.py`

**Interfaces:**
- Consumes: engine Task 3
- Produces:
  - `PaperSession(..., execution_mode: str = "paper")` → pass to `ExplicitFillEngine`
  - `start_paper_daemon(..., execution_mode: str = "shadow")` — **daemon default shadow** for live REST path; offline injected tests may pass `paper` explicitly for stable assertions
  - `PaperDaemonResult.execution_mode` reflects mode used
  - No change to warm-up book arm logic (keep Task 4a fix)

**Requirements:** SRS_HV4B_SAME_ALPHA, SRS_HV4B_FILLS, SRS_HV4B_WARM, SRS_HV4B_PROCESS

- [ ] **Step 1: Failing test**

```python
def test_daemon_default_shadow_mode_on_offline_path(tmp_path):
    # Use start_paper_daemon with warm_ohlcv + poll_fn empty, execution_mode default
    # After run, decisions (if any) or result.execution_mode == "shadow"
    ...
```

Prefer assert `result.execution_mode == "shadow"` when using default kwargs; offline tests that need paper pass `execution_mode="paper"`.

Update any tests that construct session/engine and assert mode if needed.

- [ ] **Step 2: Implement session/runner kwargs**

```python
# session.py PaperSession.__init__
execution_mode: str = "paper",
# pass to ExplicitFillEngine(..., execution_mode=execution_mode)

# runner.py start_paper_daemon
execution_mode: str = "shadow",
# pass to PaperSession(..., execution_mode=execution_mode)
# PaperDaemonResult(..., execution_mode=execution_mode)
```

- [ ] **Step 3: Tests**

```bash
uv run pytest tests/test_paper_session.py tests/test_paper_cli.py tests/test_paper_fills.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/hypervector/paper/session.py src/hypervector/paper/runner.py tests/
git commit -m "feat(paper): daemon defaults to shadow execution_mode"
```

---

### Task 5: CLI paper-check surface + paper-run --shadow

**Files:**
- Modify: `src/hypervector/cli.py`
- Modify: `configs/default.toml`
- Modify: `tests/test_paper_cli.py`

**Interfaces:**
- Produces paper-check keys (booleans/strings only):

```python
"mode": "shadow",           # or paper
"network": "mainnet",
"no_submit": True,
"submitted_default": False,
"order_intent_schema": "hv_order_intent_v1",
"live.enabled": False,      # existing live block
# no secret values
```

- `paper-run --shadow` / `--mode shadow|paper` (pick one; recommended: `--shadow` flag default True for daemon, `--paper-mode` to force paper for offline-compat — or `--mode` with default shadow)
- Wire `execution_mode` into `start_paper_daemon`
- Config comment: `[paper] mode = "shadow"`

**Requirements:** SRS_HV4B_CHECK, SRS_HV4B_MAINNET, SRS_HV4B_NO_TESTNET, SRS_HV4B_SECRETS

- [ ] **Step 1: Failing test for paper-check keys**

```python
def test_paper_check_reports_shadow_surface(tmp_path):
    # invoke paper-check; parse JSON stdout
    assert paper["mode"] in ("shadow", "paper")  # after 4b default shadow
    assert paper["network"] == "mainnet"
    assert paper["no_submit"] is True
    assert report["live"]["enabled"] is False
```

- [ ] **Step 2: Implement CLI + config docs**

Ensure help text: **no venue orders; mainnet shadow**.

- [ ] **Step 3: Tests**

```bash
uv run pytest tests/test_paper_cli.py -q
```

- [ ] **Step 4: Commit**

```bash
git add src/hypervector/cli.py configs/default.toml tests/test_paper_cli.py
git commit -m "feat(cli): paper-check shadow surface and paper-run mode flag"
```

---

### Task 6: Structural no-submit barrier + full verify + HANDOFF

**Files:**
- Create: `tests/test_paper_no_submit.py` (lightweight)
- Modify: `HANDOFF.md`
- Optional: mark plan checkboxes done as tasks complete

**Interfaces:**
- Produces:
  - Test that shadows: `src/hypervector` has no imports of order-submit clients used for trading (grep-style or import-guard). Practical approach:

```python
def test_no_testnet_url_in_hl_module():
    from hypervector.data import hl
    assert "hyperliquid.xyz" in hl.HL_INFO_URL
    assert "testnet" not in hl.HL_INFO_URL.lower()

def test_order_intent_never_submit_enabled():
    from hypervector.paper.order_intent import build_order_intent
    d = build_order_intent(symbol="X", side="buy", qty=1.0)
    assert d["submit_enabled"] is False
```

  - Full offline: `uv run pytest tests/ -q -m "not network"`
  - HANDOFF: Phase 4b tasks done; next = soak shadow / 4b-live design later; HEAD SHAs

**Requirements:** SRS_HV4B_NO_SUBMIT, SRS_HV4B_NO_TESTNET + success bar

- [ ] **Step 1: Write barrier tests + run full offline suite**

```bash
uv run pytest tests/test_paper_no_submit.py tests/test_paper_order_intent.py -q
uv run pytest tests/ -q -m "not network"
```

Expected: all offline PASS.

- [ ] **Step 2: Update HANDOFF.md**

- Phase 4b shadow **Done** (task table + commits)  
- Default daemon mode shadow  
- Still no venue orders; no `data/live/`  
- Next: longer mainnet soak under shadow; real submit design later  

- [ ] **Step 3: Commit**

```bash
git add tests/test_paper_no_submit.py HANDOFF.md docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md
git commit -m "docs: Phase 4b shadow verify + handoff; no-submit barriers"
```

- [ ] **Step 4: Spec status**

Update design file status line to **Approved + plan ready** (optional docs commit).

---

## Spec coverage self-review

| Spec requirement | Task |
|------------------|------|
| Mainnet HL endpoints | 5, 6 (existing hl.py) |
| No testnet | 6 |
| No submit | 1 (flag), 3, 6 |
| Paper ledger only | 2 |
| execution_mode=shadow | 2, 3, 4 |
| Same alpha / process | 4 |
| Fills 4a + warm | 4 (reuse) |
| Order intent | 1, 3 |
| submitted=false | 3 |
| Secrets no submit | 5, 6 |
| paper-check surface | 5 |
| userFees | **Deferred** (DG) |

## Placeholder scan

No TBD steps. userFees and real submit explicitly out of plan.

## Type consistency

- `execution_mode`: `"paper" | "shadow"`
- `build_order_intent` → dict with `submit_enabled: False`
- Engine default offline/tests: `"paper"`; daemon default: `"shadow"`
- Ledger allow-list matches engine modes

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-phase4b-mainnet-shadow.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans checkpoints  

**Which approach?**
