# Hypervelocity Nautilus Execution Fidelity and Live Canary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve the faithful Hypervelocity strategy while using NautilusTrader and Hyperliquid venue telemetry to produce realistic shadow execution, isolated-margin accounting, a reconciled post-only live path, and a fully instrumented $120 mainnet canary.

**Architecture:** The Python backend remains the only strategy and execution authority; the TUI remains a read-only ledger projection. A shared Hypervelocity order coordinator emits typed post-only entry and reduce-only target commands to either a Nautilus-backed simulated venue or Nautilus's Hyperliquid live adapter, and both modes normalize venue events into one durable execution ledger. The existing generic market-IOC `live-run` remains available for its existing callers but must fail closed for Hypervelocity exports because it does not implement the faithful contract.

**Tech Stack:** Python 3.13, NautilusTrader 1.230.0, Hyperliquid mainnet REST/WebSocket APIs, pandas, PyArrow/Parquet, pytest, Rust/Ratatui 0.29, TOML.

---

## Systems contract and evidence status

### Fixed user-approved behavior

- BTC 1m Hypervelocity, one signed BTC position at a time.
- Canonical entry states: `TREND_UP`, `TREND_DOWN`, or direction-confirmed `BREAKOUT`.
- No entry during `RANGE`, `TRANSITION`, or `UNKNOWN`.
- An open position holds through regime changes until its single target fills.
- Margin allocation is 70% of current equity at 40x leverage.
- Target is 8% gross return on allocated margin, equivalent to a 0.2% BTC move at 40x.
- Entry and target are post-only maker orders; the target is reduce-only.
- One completed 1m bar separates a target close from a new maker attempt.
- A maker attempt expires after 300 seconds and cannot chase the same uninterrupted directional episode.
- Metalabel mode remains `observe`; it cannot gate or resize an order.
- Live canary uses isolated margin and approximately $120 of deliberately expendable build capital.
- Performance, drawdown, and trade count are reported evidence, not implicit promotion gates.

### Verified implementation gaps

- `phase2-run` feeds Nautilus OHLCV bars only and does not enable latency, event-level liquidity consumption, partial fills, or liquidation.
- Shadow maker fills are full-quantity at the exact limit after one-tick-through evidence; public queue priority, cancellations, and partial fills are unknown.
- The current Hypervelocity profile has no explicit `margin_mode`.
- The paper engine does not simulate Hyperliquid isolated maintenance margin or liquidation.
- The generic live engine emits market IOC intents and updates its local position after accepted submission, not confirmed fills.
- The generic live path does not implement Hypervelocity ALO entries, reduce-only standing targets, partial fills, or venue reconciliation.
- Nautilus's Hyperliquid adapter reports and reconciles margin/order/fill state but does not set leverage; BTC isolated 40x must be set through Hyperliquid and verified by backend preflight.

### Delivery sequence

| Phase | Outcome | Depends on |
|---|---|---|
| A | Lock the existing strategy contract and refuse incompatible live routing | Current tests |
| B | Capture event-level Hyperliquid trades and L2 data | A |
| C | Run Nautilus queue/latency/partial-fill/liquidation simulation | B |
| D | Route shared Hypervelocity commands through Nautilus live reconciliation | A-C |
| E | Mirror shadow and live during the isolated $120 canary | D |
| F | Calibrate simulation from live evidence and report discrepancies | E |
| G | Add the researched chart screen from backend candle/event telemetry | B; not required for canary |

## Execution rules

- Implement in a dedicated worktree. The current worktree contains unrelated, uncommitted TUI changes and an active shadow session.
- Do not stop, reset, or mutate the active shadow ledger while implementing Phases A-D.
- Use test-driven development and commit each task independently.
- Network calls are forbidden in tests; use recorded, sanitized fixtures.
- Never write or print wallet addresses, private keys, or signed payloads in test artifacts.
- Technical integrity failures may refuse live submission. Strategy performance must not silently refuse or resize execution.

### Task 1: Characterize and protect the faithful runtime boundary

**Files:**
- Modify: `tests/test_live_run.py`
- Modify: `tests/test_paper_session.py`
- Modify: `src/hypervector/live/runner.py`
- Modify: `src/hypervector/cli.py`

**Step 1: Write failing characterization tests**

Add tests proving the current shadow path still produces post-only entries, target-only exits, one position, one-bar cooldown, and expired-direction re-arm. Add a live test proving a Hypervelocity export is rejected by generic `live-run` with `use hypervelocity-live-run` in the actionable error.

**Step 2: Run the tests and verify the live-routing test fails**

Run:

```bash
uv run pytest tests/test_live_run.py tests/test_paper_session.py -q
```

Expected: existing shadow characterizations pass; the new generic-live refusal test fails.

**Step 3: Add the minimum compatibility refusal**

After loading the export in `start_live_daemon`, call `is_hypervelocity_strategy(loadout.strategy_name)` and raise a `RuntimeError` explaining that market IOC execution violates the post-only Hypervelocity contract.

**Step 4: Run focused tests**

Expected: all selected tests pass; non-Hypervelocity `live-run` behavior remains unchanged.

**Step 5: Commit**

```bash
git add src/hypervector/live/runner.py src/hypervector/cli.py tests/test_live_run.py tests/test_paper_session.py
git commit -m "fix: refuse incompatible hypervelocity live routing"
```

### Task 2: Define one typed execution contract

**Files:**
- Create: `src/hypervector/execution/__init__.py`
- Create: `src/hypervector/execution/models.py`
- Create: `src/hypervector/execution/port.py`
- Create: `tests/test_execution_contract.py`

**Step 1: Write failing schema tests**

Test JSON round trips and validation for:

```python
@dataclass(frozen=True)
class OrderCommand:
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    limit_price: float
    post_only: bool
    reduce_only: bool
    submitted_at: str

@dataclass(frozen=True)
class VenueOrderEvent:
    client_order_id: str
    venue_order_id: str | None
    event_type: Literal[
        "submitted", "accepted", "rejected", "partially_filled",
        "filled", "cancel_pending", "canceled", "expired",
    ]
    event_at: str
    last_quantity: float
    cumulative_quantity: float
    fill_price: float | None
    fee_usd: float
    liquidity_side: Literal["maker", "taker"] | None
    reason: str | None
```

Add `ExecutionPort.submit`, `cancel`, `reconcile`, and `account_snapshot` protocol methods with explicit return types.

**Step 2: Verify tests fail because the package does not exist**

Run `uv run pytest tests/test_execution_contract.py -q`.

**Step 3: Implement validation and serialization**

Reject non-finite/negative quantities and prices, non-UTC timestamps, empty IDs, post-only market commands, and a target command without `reduce_only=True`.

**Step 4: Run tests and type-focused lint**

```bash
uv run pytest tests/test_execution_contract.py -q
uv run ruff check src/hypervector/execution tests/test_execution_contract.py
```

**Step 5: Commit**

```bash
git add src/hypervector/execution tests/test_execution_contract.py
git commit -m "feat: define hypervelocity execution contract"
```

### Task 3: Make isolated margin an explicit backend contract

**Files:**
- Modify: `configs/hypervelocity_faithful.toml`
- Modify: `src/hypervector/strategies/hypervelocity_profile.py`
- Modify: `src/hypervector/strategies/hypervelocity_contract.py`
- Modify: `tests/test_hypervelocity_profile.py`
- Modify: `tests/test_hypervelocity_contract.py`

**Step 1: Add failing profile tests**

Require `venue.margin_mode = "isolated"`. Reject missing, cross, or unknown values for the faithful profile. Add an explicit operator-owned `live_canary_max_notional_usd`; do not derive a hidden cap from performance.

**Step 2: Verify tests fail**

Run `uv run pytest tests/test_hypervelocity_profile.py tests/test_hypervelocity_contract.py -q`.

**Step 3: Add typed fields and validation**

Extend `HypervelocityProfile` with `margin_mode: Literal["isolated"]` and `live_canary_max_notional_usd: float`. Keep the shadow portfolio at its durable $10,000 identity; the live cap applies only to explicitly armed live execution.

**Step 4: Verify profile parsing and TOML**

```bash
uv run pytest tests/test_hypervelocity_profile.py tests/test_hypervelocity_contract.py -q
uv run python -c 'import tomllib; tomllib.load(open("configs/hypervelocity_faithful.toml", "rb"))'
```

**Step 5: Commit**

```bash
git add configs/hypervelocity_faithful.toml src/hypervector/strategies/hypervelocity_profile.py src/hypervector/strategies/hypervelocity_contract.py tests/test_hypervelocity_profile.py tests/test_hypervelocity_contract.py
git commit -m "feat: specify isolated hypervelocity margin"
```

### Task 4: Archive event-level Hyperliquid market data

**Files:**
- Create: `src/hypervector/data/hl_events.py`
- Create: `src/hypervector/data/event_archive.py`
- Create: `tests/fixtures/hl_ws_l2_sample.json`
- Create: `tests/fixtures/hl_ws_trades_sample.json`
- Create: `tests/test_hl_events.py`
- Modify: `src/hypervector/infra.py`
- Modify: `docs/infra-data-layout.md`

**Step 1: Write parser and archive tests**

Cover L2 updates, public trades, exchange/receive timestamps, reconnect gaps, duplicate events, invalid prices, UTC-day file rotation, and append-only replay.

**Step 2: Verify the tests fail**

Run `uv run pytest tests/test_hl_events.py -q`.

**Step 3: Implement a backend-owned recorder**

Normalize public events into typed rows and store them below:

```text
data/cache/events/hyperliquid/BTC/YYYY-MM-DD/l2.parquet
data/cache/events/hyperliquid/BTC/YYYY-MM-DD/trades.parquet
data/cache/events/hyperliquid/BTC/YYYY-MM-DD/gaps.jsonl
```

Use bounded in-memory batches and atomic Parquet part files; do not rewrite prior parts. Record sequence/freshness uncertainty rather than filling gaps silently.

**Step 4: Run offline tests and data-layout checks**

```bash
uv run pytest tests/test_hl_events.py tests/test_infra.py -q
uv run ruff check src/hypervector/data/hl_events.py src/hypervector/data/event_archive.py tests/test_hl_events.py
```

**Step 5: Commit**

```bash
git add src/hypervector/data src/hypervector/infra.py tests/fixtures tests/test_hl_events.py docs/infra-data-layout.md
git commit -m "feat: archive hyperliquid event data"
```

### Task 5: Convert archived events into a Nautilus catalog

**Files:**
- Create: `src/hypervector/nautilus/hl_catalog.py`
- Create: `tests/test_nautilus_hl_catalog.py`
- Modify: `src/hypervector/nautilus/bars.py`

**Step 1: Write failing conversion tests**

Convert fixtures into Nautilus `OrderBookDelta`/snapshot, `QuoteTick`, and `TradeTick` objects. Assert `ts_event` is the exchange timestamp and `ts_init` is local receipt time.

**Step 2: Verify tests fail**

Run `uv run pytest tests/test_nautilus_hl_catalog.py -q`.

**Step 3: Implement catalog writes**

Use Nautilus serialization and catalog APIs rather than inventing a second replay format. Preserve Hyperliquid symbol, side, price precision, size precision, and source provenance.

**Step 4: Round-trip the fixture without network access**

Read catalog data back, compare ordered event counts and values, and assert a declared gap remains visible.

**Step 5: Commit**

```bash
git add src/hypervector/nautilus/hl_catalog.py src/hypervector/nautilus/bars.py tests/test_nautilus_hl_catalog.py
git commit -m "feat: build nautilus catalog from hyperliquid events"
```

### Task 6: Configure realistic Nautilus simulated execution

**Files:**
- Create: `src/hypervector/nautilus/hypervelocity_sim.py`
- Create: `tests/test_nautilus_hypervelocity_sim.py`
- Modify: `src/hypervector/nautilus/runner.py`

**Step 1: Add failing simulation tests**

Test post-only rejection when crossing, configurable submit/cancel latency, per-level liquidity consumption, partial fills, fee assessment, cancel-before-fill, and target release proportional to partial entry fills.

**Step 2: Verify the new tests fail under the bar-only runner**

Run `uv run pytest tests/test_nautilus_hypervelocity_sim.py -q`.

**Step 3: Build a dedicated simulated venue configuration**

Set:

```text
account_type=MARGIN
oms_type=NETTING
default_leverage=40
liquidity_consumption=true
oto_trigger_mode=PARTIAL
liquidation_enabled=true
liquidation_trigger_ratio=1.0
liquidation_cancel_open_orders=true
```

Inject explicit fill, fee, latency, and margin models. Do not change generic Phase 2 defaults for unrelated strategies.

**Step 4: Run deterministic event-tape tests twice**

Assert identical commands, fills, fees, and liquidation events across both runs.

**Step 5: Commit**

```bash
git add src/hypervector/nautilus/hypervelocity_sim.py src/hypervector/nautilus/runner.py tests/test_nautilus_hypervelocity_sim.py
git commit -m "feat: simulate hypervelocity exchange friction"
```

### Task 7: Validate Hyperliquid isolated margin and liquidation math

**Files:**
- Create: `src/hypervector/nautilus/hyperliquid_margin.py`
- Create: `tests/test_hyperliquid_margin.py`
- Modify: `src/hypervector/nautilus/hypervelocity_sim.py`

**Step 1: Write formula tests from venue specifications**

For the $120 canary, assert 70% allocation produces approximately $84 isolated margin and $3,360 notional. At 40x max leverage, assert 1.25% maintenance margin on notional and test liquidation using mark price, fees, and funding.

**Step 2: Compare Nautilus's leveraged margin model**

Run the fixture against Nautilus defaults. Record exact mismatches; do not assume generic calculations equal Hyperliquid.

**Step 3: Implement only the missing venue-specific behavior**

If the default model matches, keep a thin validator. If it differs, implement a focused Hyperliquid margin model rather than duplicating all Nautilus accounting.

**Step 4: Test isolated independence**

Use BTC and a second synthetic instrument and prove one isolated liquidation does not consume the other's assigned collateral.

**Step 5: Commit**

```bash
git add src/hypervector/nautilus/hyperliquid_margin.py src/hypervector/nautilus/hypervelocity_sim.py tests/test_hyperliquid_margin.py
git commit -m "feat: model hyperliquid isolated liquidation"
```

### Task 8: Extract a shared coordinator and make enhanced friction the shadow runtime

**Files:**
- Create: `src/hypervector/strategies/hypervelocity_runtime.py`
- Create: `src/hypervector/paper/nautilus_shadow.py`
- Create: `tests/test_hypervelocity_runtime.py`
- Create: `tests/test_hypervelocity_shadow_friction.py`
- Modify: `src/hypervector/paper/session.py`
- Modify: `src/hypervector/paper/runner.py`
- Modify: `src/hypervector/strategies/hypervelocity_profile.py`
- Modify: `configs/hypervelocity_faithful.toml`
- Modify: `tests/test_paper_session.py`

**Step 1: Freeze strategy behavior and define shadow-friction expectations**

Cover flat trend-up/down, confirmed breakouts, range no-entry, open-position hold, target hit, one-bar cooldown, pending direction change, partial fill, TTL expiry, regime reset, same-direction re-entry, and opposite-direction switch after exit.

Add shadow-friction cases for submit/ack latency, queue-ahead quantity, partial entry and target fills, cancel latency, ALO rejection, displayed-liquidity consumption, account-specific fees, hourly funding, isolated maintenance margin, liquidation, and a declared event-stream gap.

**Step 2: Verify characterization tests pass before refactoring**

Run:

```bash
uv run pytest tests/test_paper_session.py tests/test_hypervelocity_runtime.py tests/test_hypervelocity_shadow_friction.py -q
```

Expected: existing characterizations pass; the new runtime and enhanced-friction tests fail because the shared coordinator and shadow port do not exist.

**Step 3: Implement a pure coordinator**

The coordinator accepts backend market state plus normalized venue events and returns zero or more `OrderCommand` objects. It performs no network or ledger I/O and does not calculate regime state.

**Step 4: Wire the coordinator to the Nautilus simulated shadow port**

Add `runtime.shadow_execution_model = "nautilus_event_v1"` to the faithful profile and validate it as the authoritative shadow execution model. `hypervelocity-shadow-run` must send coordinator commands to `NautilusShadowExecutionPort`, consume the archived/live Hyperliquid event tape, and write partial fills and order-state transitions back through the normalized ledger.

Keep the existing one-tick-through implementation available only as the explicitly selected `legacy_bar_through_v1` research comparator. Do not silently fall back to it. When the event stream has a declared gap or stale book, preserve the pending command, append `execution_evidence_uncertain`, and refrain from claiming a fill; this changes execution evidence, not strategy eligibility.

Stamp every shadow session and fill with execution model, data source, event freshness, configured latency, queue-ahead estimate, requested quantity, cumulative filled quantity, remaining quantity, maker/taker classification, and margin model.

**Step 5: Verify runtime parity and enhanced friction, then commit**

Run:

```bash
uv run pytest tests/test_paper_session.py tests/test_hypervelocity_runtime.py tests/test_hypervelocity_shadow_friction.py -q
```

Expected: strategy commands match the characterization tape; enhanced shadow produces deterministic partial fills/liquidations; uncertain evidence never becomes a success-shaped full fill.

```bash
git add configs/hypervelocity_faithful.toml src/hypervector/strategies/hypervelocity_runtime.py src/hypervector/strategies/hypervelocity_profile.py src/hypervector/paper/nautilus_shadow.py src/hypervector/paper/session.py src/hypervector/paper/runner.py tests/test_hypervelocity_runtime.py tests/test_hypervelocity_shadow_friction.py tests/test_paper_session.py
git commit -m "feat: run hypervelocity shadow with nautilus friction"
```

## Foundation completion criteria

- Generic market-IOC live execution cannot accept a Hypervelocity export.
- One typed order/event contract is shared by shadow, simulation, and future live execution.
- The faithful profile explicitly requires isolated margin.
- Event-level Hyperliquid trades and L2 updates round-trip through a Nautilus catalog with gap provenance.
- Nautilus simulation demonstrates deterministic latency, liquidity consumption, partial fills, fees, funding, and isolated liquidation.
- The extracted coordinator reproduces every current Hypervelocity state transition without adding a strategy gate.
- The unified `hypervelocity-shadow-run` uses `nautilus_event_v1`, exposes partial/uncertain execution honestly, and never silently falls back to candle-through full fills.

Continue with [Hypervelocity Live Canary Operations](2026-07-26-hypervelocity-live-canary-operations.md) only after these criteria are verified.

## Foundation rollback

- Each task is independently revertible without deleting append-only market or shadow evidence.
- If Nautilus simulation cannot express required venue behavior, preserve the typed execution contract and event archive, document the mismatch, and implement only the missing model behind the same interfaces.
- Do not re-enable the generic market-IOC route for Hypervelocity.
