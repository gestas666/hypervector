# Phase 3 Paper Live-Feed Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a long-lived Phase 3 **paper** daemon: warm from cache, consume Hyperliquid **live bars** via Nautilus, re-execute `HypervectorStrategy` from export loadout, apply **explicit** fills + hybrid costs, append paper decisions — no venue orders, no Phase 4 ML/book/live.

**Architecture:** Thin paper shell (Approach 1) around existing Phase 2 actor. `CostProvider` (config fees/slippage + live signed funding) + `ExplicitFillEngine` are ledger truth; optional Nautilus Sandbox is shadow-only (default off). Secrets env names exist for Phase 4 live flip; paper public path works without keys.

**Tech Stack:** Python 3.13, NautilusTrader ≥1.230 (Hyperliquid data adapter), existing `hypervector` (export schema, loadout, actor, paper ledger scaffold), pytest, uv, public HL info API (no private key for paper data).

**Spec:** `docs/superpowers/specs/2026-07-22-phase3-paper-live-feed-design.md`  
**Prior (done):** Phase 2 actor plan `2026-07-22-phase2-actor-and-ml.md` — do not re-execute.

## Global Constraints

- **Process over asset:** symbol/TF/export id via loadout/config — no BTC-only paper modules.
- **Same alpha path:** strategy_name + params + costs/risk/exits; never `signals.parquet` as live brain.
- **Paper ≠ live storage:** writes only under `data/paper/`; refuse `data/live/`.
- **execution_mode=paper** forced on every decision row.
- **No real venue orders** in this plan; private key must not enable trading in paper mode.
- **Explicit fill = ledger truth;** sandbox optional and non-authoritative.
- **Funding:** signed hourly HL reality (not research always-drag 8h placeholder).
- **Fees:** HL official Tier 0 base default taker **0.045%** / maker **0.015%** unless config tier overrides.
- **ML / order book / live exec = Phase 4** — do not implement in this plan.
- Infra stays I2: local filesystem under gitignored `data/`; no Postgres/Redis/k8s.
- Prefer TDD: failing test → minimal code → pass → commit per task.
- Verification (build right): unit/offline tests per task. Validation (right product): short public HL smoke only after offline path works; never claim paper PnL = live.

## Traceability (SRS → tasks)

| Spec tag | Task |
|----------|------|
| SRS_HV3P_FEES, SRS_HV3P_FUNDING, SRS_HV3P_COST_NONSTATIC | Task 1 |
| SRS_HV3P_FILL_EXPLICIT, SRS_HV3P_FILL_LOG, SRS_HV3P_MODE, SRS_HV3P_LEDGER | Task 2 |
| SRS_HV3P_WARM, SRS_HV3P_EXPORT, SRS_HV3P_SAME_ALPHA, SRS_HV3P_PROCESS | Task 3 |
| SRS_HV3P_HOST, SRS_HV3P_BARS, SRS_HV3P_NO_VENUE, SRS_HV3P_IDENTITY, SRS_HV3P_SECRETS | Task 4 |
| SRS_HV3P_SANDBOX, SRS_HV3P_LIVE_FLIP (surface only), docs | Task 5 |
| SRS_HV3P_ML_OFF | all tasks — no Metalabeler wiring |

## Phase boundary

| Phase | In this plan? |
|-------|----------------|
| **3** Paper live-feed loop | **Yes** |
| **4** Order book, ML metalabel, live exec flip, userFees, ops kill switch | **No** — next design after paper proven |

## Status at plan write

### Done (do not rebuild)

| Area | Location |
|------|----------|
| Phase 2 actor + historical runner | `nautilus/actor.py`, `runner.py`, `phase2-run` |
| Paper ledger scaffold | `paper/ledger.py`, `paper-check` |
| Export loadout | `nautilus/load_export.py` |
| HL REST candles | `data/hl.py` |
| Metalabeler process (unused in Phase 3) | `ml/metalabel.py` |
| Design lock | `specs/2026-07-22-phase3-paper-live-feed-design.md` |

### Pending (this plan)

1. CostProvider + fee schedule + funding poll math  
2. ExplicitFillEngine + decision schema  
3. Offline paper session runner (injected bars)  
4. Live HL data + `paper-run` daemon CLI  
5. Optional sandbox flag + HANDOFF / config surface for Phase 4  

---

## File map (planned)

| Path | Responsibility |
|------|----------------|
| `src/hypervector/paper/costs.py` | Fee tier schedule, `CostSnapshot`, `CostProvider`, funding payment math, public funding fetch |
| `src/hypervector/paper/fills.py` | `ExplicitFillEngine`, paper portfolio state, `bar_close_slippage_v1` |
| `src/hypervector/paper/ledger.py` | Extend required decision fields; keep live-path refuse |
| `src/hypervector/paper/session.py` | Offline/online session: warm-up, on_bar → intent → fill → ledger |
| `src/hypervector/paper/runner.py` | Daemon entry: start loop, SIGTERM, run_id artifacts |
| `src/hypervector/paper/live_node.py` | Nautilus + HyperliquidDataClient wiring (Task 4); no real exec |
| `src/hypervector/paper/__init__.py` | Export public API |
| `src/hypervector/nautilus/actor.py` | Make `execution_mode` configurable (default historical; paper sets `paper`) |
| `src/hypervector/cli.py` | `paper-run`; extend `paper-check` |
| `configs/default.toml` | `[paper]`, `[live]` stubs, corrected Tier 0 fee defaults for paper schedule |
| `tests/test_paper_costs.py` | Fee tiers, funding sign, poll parse |
| `tests/test_paper_fills.py` | Fill px, fees, portfolio, funding apply |
| `tests/test_paper_ledger.py` | Extend schema tests |
| `tests/test_paper_session.py` | Offline multi-bar session without network |
| `tests/test_paper_cli.py` | paper-check / paper-run --help / offline dry flags |
| `HANDOFF.md` | Phase 3 progress; Phase 4 next after paper |
| `docs/infra-data-layout.md` | paper/runs note if needed |

---

### Task 1: CostProvider + HL fee schedule + signed funding

**Files:**
- Create: `src/hypervector/paper/costs.py`
- Test: `tests/test_paper_costs.py`
- Modify (optional defaults doc only): `configs/default.toml` — add `[paper]` fee_tier; do not break research CostModel yet without explicit dual-path note

**Interfaces:**
- Consumes: optional `requests` for public HL info; config dict / kwargs
- Produces:
  - `HL_PERP_FEE_TIERS: dict[int, tuple[float, float]]`  # tier → (taker, maker) fractions
  - `@dataclass(frozen=True) class CostSnapshot` with fields: `taker_fee`, `maker_fee`, `slippage_bps`, `funding_rate_hourly`, `fee_tier`, `fill_model_id`, `asof_ts`, `sources: dict[str, str]`
  - `def fees_for_tier(tier: int) -> tuple[float, float]`
  - `def funding_payment(*, position_qty: float, oracle_px: float, funding_rate_hourly: float, hours: float = 1.0) -> float`  
    # payment = position_qty * oracle_px * funding_rate_hourly * hours; sign follows rate × position (long +qty pays if rate > 0)
  - `class CostProvider:`  
    - `__init__(self, *, fee_tier: int = 0, slippage_bps: float = 2.0, fill_model_id: str = "bar_close_slippage_v1", assume_taker: bool = True, funding_poll_secs: float = 60.0)`  
    - `snapshot(self) -> CostSnapshot`  
    - `refresh_funding(self, coin: str, *, session=None) -> float`  # updates internal hourly rate from public API  
    - `trade_fee_rate(self) -> float`  # taker if assume_taker else maker

**Requirements covered:** SRS_HV3P_FEES, SRS_HV3P_FUNDING, SRS_HV3P_COST_NONSTATIC

- [ ] **Step 1: Write failing tests**

```python
# tests/test_paper_costs.py
from hypervector.paper.costs import (
    HL_PERP_FEE_TIERS,
    CostProvider,
    fees_for_tier,
    funding_payment,
)

def test_tier0_matches_official_base():
    taker, maker = fees_for_tier(0)
    assert taker == 0.00045
    assert maker == 0.00015
    assert HL_PERP_FEE_TIERS[0] == (0.00045, 0.00015)

def test_funding_payment_long_pays_when_rate_positive():
    # qty > 0 long, rate > 0 → positive payment means paid by long (cash drag)
    pay = funding_payment(position_qty=1.0, oracle_px=100_000.0, funding_rate_hourly=0.0001, hours=1.0)
    assert pay == 10.0  # 1 * 100000 * 0.0001

def test_funding_payment_short_receives_when_rate_positive():
    pay = funding_payment(position_qty=-1.0, oracle_px=100_000.0, funding_rate_hourly=0.0001, hours=1.0)
    assert pay == -10.0  # short receives

def test_cost_provider_snapshot_fields():
    cp = CostProvider(fee_tier=0, slippage_bps=2.0)
    snap = cp.snapshot()
    assert snap.taker_fee == 0.00045
    assert snap.maker_fee == 0.00015
    assert snap.slippage_bps == 2.0
    assert snap.fill_model_id == "bar_close_slippage_v1"
    assert isinstance(snap.sources, dict)
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

```bash
uv run pytest tests/test_paper_costs.py -v
```

Expected: `ModuleNotFoundError` or import error for `hypervector.paper.costs`.

- [ ] **Step 3: Implement `paper/costs.py`**

```python
# src/hypervector/paper/costs.py
"""Hybrid paper costs: HL fee tiers (config) + live signed hourly funding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from hypervector.data.hl import HL_INFO_URL, hl_coin

# Official Hyperliquid perp base schedule (Tier 0) and volume tiers (fractions).
# Source: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
HL_PERP_FEE_TIERS: dict[int, tuple[float, float]] = {
    0: (0.00045, 0.00015),
    1: (0.00040, 0.00012),  # >5M 14d weighted
    2: (0.00035, 0.00008),  # >25M
    3: (0.00030, 0.00004),  # >100M
    4: (0.00028, 0.00000),  # >500M
    5: (0.00026, 0.00000),  # >2B
    6: (0.00024, 0.00000),  # >7B
}

FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1 = "bar_close_slippage_v1"


def fees_for_tier(tier: int) -> tuple[float, float]:
    if tier not in HL_PERP_FEE_TIERS:
        raise ValueError(f"unknown fee_tier={tier}; known={sorted(HL_PERP_FEE_TIERS)}")
    return HL_PERP_FEE_TIERS[tier]


def funding_payment(
    *,
    position_qty: float,
    oracle_px: float,
    funding_rate_hourly: float,
    hours: float = 1.0,
) -> float:
    """Signed funding cashflow for the position holder.

    Positive return = cash paid by the position (drag for that side).
    HL: payment ≈ position_size * oracle_price * funding_rate (hourly).
    """
    return float(position_qty) * float(oracle_px) * float(funding_rate_hourly) * float(hours)


@dataclass(frozen=True)
class CostSnapshot:
    taker_fee: float
    maker_fee: float
    slippage_bps: float
    funding_rate_hourly: float
    fee_tier: int
    fill_model_id: str
    asof_ts: str
    sources: dict[str, str] = field(default_factory=dict)

    def trade_fee_rate(self, *, assume_taker: bool = True) -> float:
        return self.taker_fee if assume_taker else self.maker_fee


class CostProvider:
    def __init__(
        self,
        *,
        fee_tier: int = 0,
        slippage_bps: float = 2.0,
        fill_model_id: str = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
        assume_taker: bool = True,
        funding_poll_secs: float = 60.0,
        funding_rate_hourly: float = 0.0,
    ) -> None:
        self.fee_tier = int(fee_tier)
        self.slippage_bps = float(slippage_bps)
        self.fill_model_id = str(fill_model_id)
        self.assume_taker = bool(assume_taker)
        self.funding_poll_secs = float(funding_poll_secs)
        self._funding_rate_hourly = float(funding_rate_hourly)
        self._taker, self._maker = fees_for_tier(self.fee_tier)

    def trade_fee_rate(self) -> float:
        return self._taker if self.assume_taker else self._maker

    def snapshot(self) -> CostSnapshot:
        now = datetime.now(timezone.utc).isoformat()
        return CostSnapshot(
            taker_fee=self._taker,
            maker_fee=self._maker,
            slippage_bps=self.slippage_bps,
            funding_rate_hourly=self._funding_rate_hourly,
            fee_tier=self.fee_tier,
            fill_model_id=self.fill_model_id,
            asof_ts=now,
            sources={
                "fees": "config_tier",
                "slippage": "config",
                "funding": "live_or_last" if self._funding_rate_hourly else "unset",
            },
        )

    def refresh_funding(
        self,
        coin: str,
        *,
        session: requests.Session | None = None,
    ) -> float:
        """Pull hourly funding for coin from public metaAndAssetCtxs."""
        sess = session or requests.Session()
        resp = sess.post(
            HL_INFO_URL,
            json={"type": "metaAndAssetCtxs"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        meta, ctxs = payload[0], payload[1]
        universe = meta.get("universe") or []
        name = hl_coin(coin)
        idx = next(i for i, u in enumerate(universe) if u.get("name") == name)
        rate = float(ctxs[idx]["funding"])
        self._funding_rate_hourly = rate
        return rate
```


- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_paper_costs.py -v
```

Expected: all PASS (network tests for `refresh_funding` optional, mark network if added).

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/costs.py tests/test_paper_costs.py
git commit -m "feat(paper): CostProvider with HL fee tiers and signed funding math"
```

---

### Task 2: ExplicitFillEngine + decision schema

**Files:**
- Create: `src/hypervector/paper/fills.py`
- Modify: `src/hypervector/paper/ledger.py`
- Modify: `src/hypervector/paper/__init__.py`
- Test: `tests/test_paper_fills.py`
- Modify: `tests/test_paper_ledger.py` (required fields optional vs required policy)

**Interfaces:**
- Consumes: `CostProvider` / `CostSnapshot`, `append_paper_decision`
- Produces:
  - `@dataclass class PaperPosition` — `qty: float`, `avg_px: float`, `realized_pnl: float`
  - `class ExplicitFillEngine:`  
    - `__init__(self, data_root, *, cost_provider: CostProvider, run_id: str, export_id: str, strategy_name: str, symbol: str, timeframe: str, conviction: float, sandbox_enabled: bool = False)`  
    - `apply_market_fill(self, *, feed_ts, action: str, side: str, qty: float, mark_px: float, intent: dict | None = None) -> dict`  
    - `apply_funding(self, *, feed_ts, oracle_px: float) -> dict | None`  
    - `position` property  
  - Fill rule v1: `fill_px = mark_px * (1 + slip)` for buy, `mark_px * (1 - slip)` for sell; `slip = slippage_bps/10_000`; fee = abs(qty)*fill_px*trade_fee_rate  
  - Decision dict **must** include keys from design §6.5 (at least):  
    `execution_mode`, `feed_ts`, `run_id`, `export_id`, `strategy_name`, `symbol`, `timeframe`, `action`, `side`, `qty`, `mark_px`, `fill_px`, `fill_model_id`, `slippage_bps`, `taker_fee`, `maker_fee`, `fee_usd`, `funding_rate_hourly`, `costs_source`, `sandbox_enabled`, `conviction`

**Requirements covered:** SRS_HV3P_FILL_EXPLICIT, SRS_HV3P_FILL_LOG, SRS_HV3P_MODE, SRS_HV3P_LEDGER

- [ ] **Step 1: Write failing tests**

```python
# tests/test_paper_fills.py
from pathlib import Path
from hypervector.paper.costs import CostProvider
from hypervector.paper.fills import ExplicitFillEngine

def test_buy_fill_pays_slippage_and_fee(tmp_path: Path):
    cp = CostProvider(fee_tier=0, slippage_bps=10.0)  # 10 bps
    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=cp,
        run_id="r1",
        export_id="e1",
        strategy_name="crown_stack_short",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
    )
    rec = eng.apply_market_fill(
        feed_ts="2026-07-22T00:00:00Z",
        action="enter_long",
        side="buy",
        qty=0.01,
        mark_px=100_000.0,
    )
    assert rec["execution_mode"] == "paper"
    assert rec["fill_model_id"] == "bar_close_slippage_v1"
    assert rec["fill_px"] == 100_000.0 * (1 + 10 / 10_000)
    assert rec["fee_usd"] > 0
    assert eng.position.qty == 0.01

def test_funding_on_open_long_drag(tmp_path: Path):
    cp = CostProvider(fee_tier=0, funding_rate_hourly=0.0001)
    eng = ExplicitFillEngine(
        tmp_path / "data",
        cost_provider=cp,
        run_id="r1",
        export_id="e1",
        strategy_name="s",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
    )
    eng.apply_market_fill(
        feed_ts="t0", action="enter_long", side="buy", qty=1.0, mark_px=50_000.0
    )
    fre = eng.apply_funding(feed_ts="t1", oracle_px=50_000.0)
    assert fre is not None
    assert fre["action"] == "funding"
    assert fre["funding_payment_usd"] == 5.0  # 1 * 50000 * 0.0001
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_paper_fills.py -v
```

- [ ] **Step 3: Implement `fills.py`; wire `append_paper_decision`**

Core fill logic (implementer expands full decision dict):

```python
slip = cost_provider.slippage_bps / 10_000.0
if side == "buy":
    fill_px = mark_px * (1.0 + slip)
else:
    fill_px = mark_px * (1.0 - slip)
fee_usd = abs(qty) * fill_px * cost_provider.trade_fee_rate()
# update position qty/avg; append_paper_decision(data_root, record)
```

Keep ledger path refuse behavior. Do not require all new keys in ledger module validation if that breaks old tests — either update old tests to pass full records **or** keep ledger minimal (feed_ts + mode) and let fill engine always pass full records. Prefer: ledger still only **requires** feed_ts + forces mode; fill engine always supplies full schema.

- [ ] **Step 4: Run tests — PASS**

```bash
uv run pytest tests/test_paper_fills.py tests/test_paper_ledger.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/fills.py src/hypervector/paper/__init__.py tests/test_paper_fills.py tests/test_paper_ledger.py
git commit -m "feat(paper): ExplicitFillEngine bar_close_slippage_v1 and funding rows"
```

---

### Task 3: Offline paper session (warm-up + bar loop, no live network)

**Files:**
- Create: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/nautilus/actor.py` — configurable `execution_mode` on strategy (config field + instance)
- Test: `tests/test_paper_session.py`

**Interfaces:**
- Consumes: `load_strategy_loadout`, `last_bar_intent` / actor buffer helpers, `ExplicitFillEngine`, `load_research_history` or injected `pd.DataFrame`
- Produces:
  - `@dataclass class PaperSessionResult` — `run_id`, `decisions_path`, `bars_processed`, `fills_count`, `export_dir`
  - `def run_paper_session_offline(*, export_dir, data_root, ohlcv: pd.DataFrame, conviction: float = 0.5, fee_tier: int = 0, max_bars: int | None = None) -> PaperSessionResult`  
  - Behavior: register strategies; load loadout; create CostProvider + ExplicitFillEngine; walk OHLCV rows; on each bar recompute intent via `last_bar_intent` on expanding window (same as actor); map enter/exit to fill engine; no Nautilus network

**Warm-up rule:** first `max_lookback` bars only build buffer (no trades) **or** trade only when buffer length ≥ 2 (match actor). Prefer match actor: no trade if `len(buffer) < 2`.

**Requirements covered:** SRS_HV3P_WARM (offline inject = warm data), SRS_HV3P_EXPORT, SRS_HV3P_SAME_ALPHA, SRS_HV3P_PROCESS, SRS_HV3P_ML_OFF

- [ ] **Step 1: Write failing test**

```python
# tests/test_paper_session.py
from pathlib import Path
from hypervector.data.sources import fixture_ohlcv
from hypervector.paper.session import run_paper_session_offline

def test_offline_session_writes_paper_decisions(tmp_path: Path, monkeypatch):
    # Use a real strict export if present under data/exports; else skip or build minimal
    export = Path("data/exports/downtrend_crown_stack_short_c4fd7067")
    if not export.is_dir():
        import pytest
        pytest.skip("strict export not available")
    ohlcv = fixture_ohlcv(n_bars=300, drift=-5.0, wave_period=40)
    result = run_paper_session_offline(
        export_dir=export,
        data_root=tmp_path / "data",
        ohlcv=ohlcv,
        conviction=0.5,
        max_bars=300,
    )
    assert result.bars_processed > 0
    assert result.decisions_path.is_file()
    text = result.decisions_path.read_text(encoding="utf-8")
    assert "execution_mode" in text
    assert "paper" in text
```

If fixture path is fragile, construct minimal export in tmp_path matching schema v1 strict (meta/params/metrics with costs/risk/exits) — prefer self-contained fixture in test for CI.

**Preferred self-contained approach:** write helper in test that writes minimal strict export under `tmp_path` using same keys as `validate_export_dir` strict mode. Implementer reads `export/schema.py` for required fields.

- [ ] **Step 2: Run — FAIL (session missing)**

```bash
uv run pytest tests/test_paper_session.py -v
```

- [ ] **Step 3: Implement session + actor mode field**

In `HypervectorStrategyConfig` add:

```python
execution_mode: str = "phase2_historical"
```

In `HypervectorStrategy.__init__`:

```python
self.execution_mode = str(getattr(config, "execution_mode", None) or "phase2_historical")
```

Session offline path may call `last_bar_intent` directly without full Nautilus Strategy lifecycle (simpler, still same alpha). That satisfies “same alpha math”; full Strategy class reuse is Task 4 when node exists.

```python
# session sketch
register_all_strategies()
loadout = load_strategy_loadout(export_dir, strict=True)
run_id = uuid.uuid4().hex[:12]
engine = ExplicitFillEngine(...)
buffer_rows = []
for i, row in ohlcv.iterrows():
    buffer_rows.append({...ohlcv...})
    if len(buffer_rows) < 2:
        continue
    df = pd.DataFrame(buffer_rows)
    intent = last_bar_intent(df, loadout.strategy_name, dict(loadout.params))
    # map intent → fill actions using flat/side state from engine.position
```

- [ ] **Step 4: Tests PASS**

```bash
uv run pytest tests/test_paper_session.py tests/test_nautilus_actor_offline.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/session.py src/hypervector/nautilus/actor.py tests/test_paper_session.py
git commit -m "feat(paper): offline session walks bars into ExplicitFillEngine"
```

---

### Task 4: Live HL bars + paper-run daemon CLI

**Files:**
- Create: `src/hypervector/paper/runner.py`
- Create: `src/hypervector/paper/live_node.py` (or fold into runner if small)
- Modify: `src/hypervector/cli.py` — `paper-run` subcommand; extend `paper-check`
- Modify: `configs/default.toml` — `[paper]`, `[live]` stubs + secret env names in comments
- Test: `tests/test_paper_cli.py` (offline: help, check flags; live node may be mocked)

**Interfaces:**
- Produces:
  - `def start_paper_daemon(*, export_dir, data_root, conviction=0.5, sandbox_enabled=False, fee_tier=0, stop_file: Path | None = None) -> None`  
  - Warm-up: `load_research_history` (cache-first) for loadout symbol/TF lookback → seed session buffer  
  - Live: wire `HyperliquidDataClient` / TradingNode per installed Nautilus version  
  - On each live bar: same intent→fill path as offline session  
  - Log banner: `PAPER MODE — no venue orders`  
  - SIGINT/SIGTERM or stop_file → graceful summary  
  - **Must not** construct live order client that sends to venue  
  - Secrets: document `HYPERVECTOR_HL_WALLET_ADDRESS`, `HYPERVECTOR_HL_API_PRIVATE_KEY`; paper-check reports `secrets_present: bool` without printing values  

**CLI:**

```bash
uv run python -m hypervector paper-run --path data/exports/<id> --data-root data
uv run python -m hypervector paper-check --data-root data
```

**Requirements covered:** SRS_HV3P_HOST, SRS_HV3P_BARS, SRS_HV3P_NO_VENUE, SRS_HV3P_IDENTITY, SRS_HV3P_SECRETS, SRS_HV3P_WARM

**Implementation note:** Nautilus live API varies by version. Order of work:

1. Implement warm-up + polling fallback: if full TradingNode wiring is blocked, **poll HL REST candles** on interval as interim live feed behind the same session callbacks — still public, still daemon — and file a code comment `TODO Phase3: prefer HyperliquidDataClient WS when stable`.  
2. Prefer real adapter when `try_import` succeeds.

Do not leave the task incomplete: daemon must process new bars somehow offline-testable via injected clock/poll mock.

- [ ] **Step 1: Failing CLI test**

```python
# tests/test_paper_cli.py
from hypervector.cli import main

def test_paper_check_reports_mode(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["hypervector", "--data-root", str(tmp_path / "data"), "paper-check"])
    # or call main with list if supported
```

Inspect how CLI tests are written in `tests/test_cli.py` and match that pattern.

```python
def test_paper_run_requires_export_path():
    # assert non-zero exit without --path
```

- [ ] **Step 2: Run — FAIL until command exists**

```bash
uv run pytest tests/test_paper_cli.py -v
uv run python -m hypervector paper-run --help
```

- [ ] **Step 3: Implement runner + CLI**

```toml
# configs/default.toml additions
[paper]
sandbox_enabled = false
funding_poll_secs = 60
fill_model_id = "bar_close_slippage_v1"
fee_tier = 0
assume_taker = true

[live]
enabled = false
# Phase 4: set execution_mode=live + secrets
# HYPERVECTOR_HL_WALLET_ADDRESS=
# HYPERVECTOR_HL_API_PRIVATE_KEY=
```

- [ ] **Step 4: Offline tests PASS; optional network smoke manual**

```bash
uv run pytest tests/test_paper_cli.py tests/test_paper_session.py -v
# Manual (optional):
# uv run python -m hypervector paper-run --path data/exports/<strict> --data-root data
# Ctrl-C after decisions appear
```

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/paper/runner.py src/hypervector/paper/live_node.py src/hypervector/cli.py configs/default.toml tests/test_paper_cli.py
git commit -m "feat(paper): paper-run daemon with warm-up and live bar feed"
```

---

### Task 5: Optional sandbox flag + verification + HANDOFF (Phase 4 pointer)

**Files:**
- Modify: `src/hypervector/paper/fills.py` / runner — `sandbox_enabled` shadow fields only  
- Modify: `src/hypervector/cli.py` — `paper-check` shows `live_feed_loop: true` when implemented; sandbox flag; secrets present  
- Modify: `HANDOFF.md`  
- Modify: design/plan status if needed  
- Test: unit that sandbox flag lands on decision records without changing fill_px

**Requirements covered:** SRS_HV3P_SANDBOX, SRS_HV3P_LIVE_FLIP (config surface only), success criteria §15

- [ ] **Step 1: Test sandbox shadow fields**

```python
def test_sandbox_flag_on_record_does_not_change_fill(tmp_path):
    # two engines identical costs; sandbox True only sets sandbox_enabled True
    ...
    assert rec["sandbox_enabled"] is True
    assert rec["fill_px"] == expected_explicit_px
```

If full Nautilus sandbox client is too heavy, Phase 3 v1 may only plumb the **flag + shadow keys** (`sandbox_fill_px=null`) and document real Sandbox client as Phase 4/hardening — **but** design preferred optional mirror. Minimum for this task: flag wired end-to-end; real Sandbox client if import works within 1–2 hours spike, else stub with log `sandbox_requested_but_not_wired`.

- [ ] **Step 2: Full offline suite**

```bash
uv run pytest tests/ -q -m "not network"
```

Expected: all green (or only pre-existing known skips).

- [ ] **Step 3: Update HANDOFF.md**

Must state:

- Phase 3 paper plan path and task completion status  
- How to run `paper-run` / `paper-check`  
- **Next design: Phase 4** — order book, ML metalabel, live exec flip (not “Phase 3+”)  
- Secrets env names; live disabled  

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md src/hypervector/paper tests docs/superpowers
git commit -m "docs: Phase 3 paper verify + handoff; Phase 4 deferred items named"
```

---

## Verification checklist (plan complete when)

| Check | Command / evidence |
|-------|-------------------|
| Offline tests | `uv run pytest tests/ -q -m "not network"` green |
| Cost tiers | Tier 0 = 4.5 / 1.5 bps |
| Funding signed | long + positive rate → positive payment |
| Ledger isolation | refuses live path |
| paper-check | `execution_mode=paper`, secrets flags without secrets dump |
| paper-run offline path | session test writes decisions |
| No live orders | no HyperliquidExecClient private submit in paper path |
| Phase 4 not started | no metalabel wire, no book, live.enabled=false |

---

## Out of scope (Phase 4 — first-class next phase)

Do **not** implement in Tasks 1–5:

1. **Order book** L2 subscribe + impact fills  
2. **ML metalabel** conviction / feature builder  
3. **Live execution** real orders + `data/live/` ledger  
4. **userFees** authenticated fee tier  
5. **Kill switch / supervisor** production ops  

After Phase 3 success criteria met → **new Phase 4 design** (brainstorm + spec + plan).

---

## Spec coverage self-review

| Spec section | Plan task |
|--------------|-----------|
| §6.3 CostProvider | Task 1 |
| §6.4 ExplicitFillEngine | Task 2 |
| §6.5 Decision schema | Task 2 |
| §6.1 Runner daemon | Task 4 |
| §6.6 Secrets / live surface | Task 4–5 |
| §6.7 CLI | Task 4 |
| §7 Data flow warm-up | Task 3–4 |
| §8–9 Phase 4 book/ML | Explicitly excluded |
| §10 Testing | each task + final suite |
| §14 PR1–5 | Tasks 1–5 |
| §15 Success criteria | Task 5 verification |

Placeholder scan: no TBD steps; Nautilus WS has documented REST poll fallback.

Type consistency: `CostProvider`, `CostSnapshot`, `ExplicitFillEngine`, `run_paper_session_offline`, `start_paper_daemon`, `fill_model_id` (field name), `funding_rate_hourly`.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-22-phase3-paper-live-feed.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session, executing-plans with checkpoints  

**Which approach?**
