# Phase 2 Strategy Actor + Optional ML Façade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a Phase 1 export through a NautilusTrader historical backtest that re-executes strategy logic from `StrategyLoadout` params (not signal replay), write Phase 2 artifacts, optionally wire a BTC 1m impulse metalabel façade for conviction, and scaffold Phase 3 paper identity without live orders.

**Architecture:** Keep VectorBT as research-only. Shared pure-Python signal builders already live in `hypervector.strategies.*` (`StrategySpec.build_signals`). Phase 2 wraps those builders inside a Nautilus `Strategy` that maintains a bar buffer, recomputes entries/exits on each bar close, and places/cancels orders with costs/risk/exits from the loadout. ML is a thin read-only façade → conviction ∈ [0,1] or skip; never greenfield training. Paper/live share the same strategy path later; this plan only scaffolds paper ledger identity.

**Tech Stack:** Python 3.13, NautilusTrader ≥1.230, existing `hypervector` package (export schema v1, `StrategyLoadout`), VectorBT only for optional parity helpers, LightGBM/joblib for optional ML façade, pytest, uv.

## Global Constraints

- BTC-PERP identity; 1m MVP bars; do not claim CEX cache bars = HL book microstructure.
- **Live alpha = strategy_name + params + costs + risk + exits** (+ optional ML conviction). Signals parquet is parity-only.
- No real venue orders; no API keys required for historical Phase 2.
- Paper and live ledgers **must never** share files (`data/paper/*` vs `data/live/*`).
- Infra stays I2: local Parquet + SQLite + filesystem under gitignored `data/`.
- Prefer reuse: Nautilus HL adapter; hyper-pi / hypertrader impulse metalabel bundles via env path — do not vendor model trees into git.
- YAGNI: one strategy family end-to-end first (`crown_stack_*` or loadout name), then generalize via registry.
- Prior plan **Tasks 1–7 are DONE** (`docs/superpowers/plans/2026-07-22-phase15-to-phase2-prep.md`).

## Status at plan write (2026-07-22)

### Done (do not re-build)

| Area | Location |
|------|----------|
| Research funnel + Phase 1.5 costs/risk/exits | `src/hypervector/{data,strategies,sweep,cli}.py` |
| Export schema v1 + `meta.exits` | `export/schema.py`, `export/phase2.py` |
| `StrategyLoadout` + offline stub | `nautilus/load_export.py`, `nautilus/config_stub.py` |
| CLI validate / phase2-check | `cli.py` |
| Infra I2 | `infra.py` |
| Spec lock Phase 2/3/paper | `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` |

### Pending (this plan)

1. Nautilus strategy actor from loadout  
2. Historical backtest runner + CLI  
3. Phase 2 result artifacts under `data/nautilus/backtest/`  
4. Optional ML impulse façade  
5. Phase 3 paper identity scaffold (no live feed loop yet)  
6. Handoff + verification

---

## File map (planned)

| Path | Responsibility |
|------|----------------|
| `src/hypervector/nautilus/signals.py` | Pure adapter: OHLCV window → last-bar entry/exit from registry |
| `src/hypervector/nautilus/sizing.py` | Risk + exit distances from loadout → order qty / SL / TP fractions |
| `src/hypervector/nautilus/actor.py` | Nautilus `Strategy` + `StrategyConfig` driven by loadout |
| `src/hypervector/nautilus/bars.py` | Convert research Parquet/DataFrame → Nautilus `Bar` list + instrument stub |
| `src/hypervector/nautilus/runner.py` | Offline `BacktestEngine` wiring; write reports under data root |
| `src/hypervector/ml/impulse_btc.py` | Optional façade: load LGBM + calibrator; `predict_conviction` |
| `src/hypervector/paper/ledger.py` | Scaffold: append-only paper decision/fill records (`execution_mode=paper`) |
| `src/hypervector/cli.py` | Add `phase2-run`; optional `--conviction-model` |
| `tests/test_nautilus_signals.py` | Offline signal adapter unit tests (no engine) |
| `tests/test_nautilus_actor_offline.py` | Actor config + buffer logic without network |
| `tests/test_nautilus_runner.py` | Short synthetic bar backtest (offline) |
| `tests/test_ml_impulse_btc.py` | Mock booster / missing-bundle graceful fail |
| `tests/test_paper_ledger.py` | Paper path separation + mode field |
| `docs/superpowers/specs/2026-07-22-phase2-3-handoff.md` | Cross-link plan status only if needed |
| `HANDOFF.md` | Point next session at this plan |

---

### Task 1: Shared bar-window signal adapter

**Files:**
- Create: `src/hypervector/nautilus/signals.py`
- Test: `tests/test_nautilus_signals.py`

**Interfaces:**
- Consumes: `hypervector.strategies.registry.get_strategy`, `register_all_strategies`, loadout `strategy_name` + `params`
- Produces:
  - `signals_from_ohlcv(df: pd.DataFrame, strategy_name: str, params: dict[str, Any]) -> tuple[pd.Series, pd.Series, str]`
  - `last_bar_intent(df: pd.DataFrame, strategy_name: str, params: dict[str, Any]) -> SignalIntent`

```python
# SignalIntent shape (in signals.py)
@dataclass(frozen=True)
class SignalIntent:
    direction: str  # "long" | "short" | "flat"
    enter: bool
    exit: bool
    bar_index: int
```

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nautilus_signals.py
from hypervector.data.sources import fixture_ohlcv
from hypervector.nautilus.signals import last_bar_intent, signals_from_ohlcv
from hypervector.strategies import register_all_strategies

def test_signals_from_ohlcv_matches_registry_builder():
    register_all_strategies()
    df = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30)
    params = {"bbwp_lookback": 100, "bbwp_threshold": 20.0, "pmarp_exit_lo": 10.0}
    entries, exits, direction = signals_from_ohlcv(df, "crown_stack_short", params)
    assert direction == "short"
    assert len(entries) == len(df)
    assert entries.dtype == bool or entries.astype(bool).dtype == bool

def test_last_bar_intent_is_boolean_on_final_index():
    register_all_strategies()
    df = fixture_ohlcv(n_bars=400, drift=20.0, wave_period=30)
    intent = last_bar_intent(df, "crown_stack_short", {"bbwp_lookback": 100})
    assert intent.direction in ("long", "short", "flat")
    assert isinstance(intent.enter, bool)
    assert isinstance(intent.exit, bool)
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

```bash
uv run pytest tests/test_nautilus_signals.py -v
```

- [ ] **Step 3: Implement minimal adapter**

```python
# src/hypervector/nautilus/signals.py (core logic)
def signals_from_ohlcv(df, strategy_name, params):
    register_all_strategies()  # idempotent if registry already filled
    spec = get_strategy(strategy_name)
    clean = {k: v for k, v in params.items() if k not in ("strategy", "role", "exit_mode")}
    return spec.build_signals(df, **clean)

def last_bar_intent(df, strategy_name, params) -> SignalIntent:
    entries, exits, direction = signals_from_ohlcv(df, strategy_name, params)
    i = len(df) - 1
    enter = bool(entries.iloc[i])
    exit_ = bool(exits.iloc[i])
    return SignalIntent(direction=direction, enter=enter, exit=exit_, bar_index=i)
```

**Note:** `build_signals` signatures differ by strategy — pass only kwargs present on the builder (filter via `inspect.signature` if needed). Do not reimplement crown/trend indicators.

- [ ] **Step 4: Tests pass**

```bash
uv run pytest tests/test_nautilus_signals.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hypervector/nautilus/signals.py tests/test_nautilus_signals.py
git commit -m "feat(nautilus): shared OHLCV signal adapter from strategy registry"
```

---

### Task 2: Loadout sizing + exit distance helpers

**Files:**
- Create: `src/hypervector/nautilus/sizing.py`
- Test: `tests/test_nautilus_sizing.py`

**Interfaces:**
- Consumes: `StrategyLoadout`, `hypervector.sweep.exits.ExitConfig`, `hypervector.sweep.sizing.risk_pct_from_conviction`
- Produces:
  - `exit_config_from_loadout(loadout: StrategyLoadout) -> ExitConfig`
  - `position_size_frac(equity: float, stop_frac: float, loadout: StrategyLoadout, conviction: float) -> float`

- [ ] **Step 1: Failing tests for exits reconstruction and size clamp**

```python
def test_exit_config_from_loadout_preserves_cli_overrides():
    # loadout.exits = {mode: atr, sl_atr_mult: 1.75, rr: 2.5, ...}
    cfg = exit_config_from_loadout(loadout)
    assert cfg.mode == "atr"
    assert cfg.sl_atr_mult == 1.75
    assert cfg.rr == 2.5

def test_position_size_frac_uses_risk_band():
    # risk 1–5%, conviction 0.5 → 3% risk; stop 1% → size_frac ~ 3.0 capped by max_size_frac
    ...
```

- [ ] **Step 2: Implement from existing `ExitConfig` / `RiskConfig` dataclasses (import, do not duplicate formulas)**

- [ ] **Step 3: pytest green + commit**

```bash
uv run pytest tests/test_nautilus_sizing.py -v
git commit -m "feat(nautilus): size and exit helpers from StrategyLoadout"
```

---

### Task 3: Research OHLCV → Nautilus bars (offline)

**Files:**
- Create: `src/hypervector/nautilus/bars.py`
- Test: `tests/test_nautilus_bars.py`

**Interfaces:**
- Produces:
  - `dataframe_to_bars(df: pd.DataFrame, bar_type: str) -> list`  # list[Bar]
  - `synthetic_btc_perp_instrument(...)` — minimal instrument for backtest venue `HYPERLIQUID` or `SIM`
  - `bar_type_from_loadout(loadout) -> str`  # e.g. `BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL`

- [ ] **Step 1: Failing test with `fixture_ohlcv` → N bars constructed; no network**

- [ ] **Step 2: Implement using `nautilus_trader.model` Bar / BarType / CryptoPerpetual (or CurrencyPair stub if simpler for offline). Prefer patterns in `reference/nautilus_trader-develop/examples/backtest/example_05_using_portfolio/`.**

- [ ] **Step 3: pytest offline + commit**

```bash
uv run pytest tests/test_nautilus_bars.py -v
git commit -m "feat(nautilus): convert research OHLCV frames to Bar list"
```

---

### Task 4: Nautilus Strategy actor (from loadout)

**Files:**
- Create: `src/hypervector/nautilus/actor.py`
- Test: `tests/test_nautilus_actor_offline.py`
- Modify: `src/hypervector/nautilus/__init__.py` exports

**Interfaces:**
- Consumes: `StrategyLoadout`, `last_bar_intent`, sizing helpers
- Produces:
  - `HypervectorStrategyConfig(StrategyConfig)` with fields: `loadout_summary`, `bar_type`, `instrument_id`, `strategy_name`, `params`, `exits`, `risk`, `costs`, `conviction`
  - `HypervectorStrategy(Strategy)` with `on_start`, `on_bar`

**Behavior (locked):**
1. On each bar: append OHLCV to a rolling buffer (max lookback ≥ strategy needs, default 2000 bars).
2. Call `last_bar_intent` on the buffer DataFrame.
3. If flat and `enter`: submit market (or limit mid) order sized via loadout risk; attach SL/TP from exit config when mode is `fixed_rr`/`atr`.
4. If in position and `exit` or opposite signal: close.
5. **Never** read `signals.parquet` for decisions.
6. Log decisions with `execution_mode=phase2_historical`.

- [ ] **Step 1: Failing unit tests for config construction from loadout + buffer intent without `engine.run()`**

```python
def test_strategy_config_from_loadout(tmp_path):
    loadout = load_strategy_loadout(export_dir, strict=True)
    cfg = config_from_loadout(loadout, bar_type="...")
    assert cfg.strategy_name == loadout.strategy_name
    assert cfg.exits["mode"] == loadout.exit_mode
```

- [ ] **Step 2: Implement actor; keep order placement minimal (one position netting)**

- [ ] **Step 3: pytest + commit**

```bash
uv run pytest tests/test_nautilus_actor_offline.py -v
git commit -m "feat(nautilus): HypervectorStrategy actor driven by StrategyLoadout"
```

---

### Task 5: Historical backtest runner + artifacts

**Files:**
- Create: `src/hypervector/nautilus/runner.py`
- Test: `tests/test_nautilus_runner.py`

**Interfaces:**
- Produces:
  - `run_phase2_backtest(*, export_dir: Path, data_root: Path, ohlcv: pd.DataFrame | None = None, conviction: float = 0.5) -> Phase2Result`
  - `Phase2Result` dataclass: `export_dir`, `orders_count`, `pnl`, `report_path`, `loadout_summary`

**Runner steps:**
1. `ensure_data_layout(data_root)`
2. `load_strategy_loadout(export_dir, strict=True)`
3. Load OHLCV: argument, or `load_research_history` from cache using loadout symbol/tf/lookback (no force network in tests)
4. Build engine + venue + instrument + bars
5. Add `HypervectorStrategy`
6. `engine.run()` / `dispose()`
7. Write JSON report to `data/nautilus/backtest/<run_id>/summary.json`

- [ ] **Step 1: Failing test with fixture OHLCV + temp export (strict meta with exits)**

- [ ] **Step 2: Implement runner; timeout-friendly (≤500 bars in unit test)**

- [ ] **Step 3: pytest offline**

```bash
uv run pytest tests/test_nautilus_runner.py -v
```

- [ ] **Step 4: Real-world check (manual / optional in CI)**

```bash
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<strict_export_id> --lookback 30
# expect summary.json under data/nautilus/backtest/
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(nautilus): Phase 2 historical backtest runner + artifacts"
```

---

### Task 6: CLI `phase2-run`

**Files:**
- Modify: `src/hypervector/cli.py`
- Modify: `tests/test_cli.py`

**CLI contract:**

```bash
uv run python -m hypervector --data-root data phase2-run \
  --path data/exports/<id> \
  [--lookback 30] [--conviction 0.5] [--no-network]
```

- Exit `0` on completed backtest; print JSON summary to stdout  
- Exit `1` on schema/loadout errors (reuse `ExportSchemaError`)  
- stderr may note `paper/live not implemented` only if flags requested (do not claim paper ran)

- [ ] **Step 1: CLI test with tmp export + injected OHLCV (monkeypatch history)**

- [ ] **Step 2: Wire `cmd_phase2_run` → `run_phase2_backtest`**

- [ ] **Step 3: pytest + commit**

```bash
uv run pytest tests/test_cli.py -k phase2 -v
git commit -m "feat(cli): phase2-run historical backtest from export"
```

---

### Task 7 (optional but planned): ML impulse façade

**Files:**
- Create: `src/hypervector/ml/__init__.py`
- Create: `src/hypervector/ml/impulse_btc.py`
- Test: `tests/test_ml_impulse_btc.py`

**Interfaces:**
- Produces:
  - `ImpulseBtcFacade.from_env() -> ImpulseBtcFacade`  # reads `HYPERVECTOR_IMPULSE_BTC_ROOT` or default hyper-pi path
  - `predict_conviction(features: pd.DataFrame | dict) -> float`  # clipped [0, 1]
  - raises `ImpulseBundleError` with clear message if models missing

**Reuse roots (do not copy into repo):**
- `/Users/gestas/dev/hyper-pi/services/ml-service/external-strategies/impulse_1m_btc/`
- `/Users/gestas/Prototypes/hypertrader/backend/app/backtest/impulse_metalabel/models/`
- Features reference: hyper-pi `services/ml-service/ml/features_impulse.py`

**Rules:**
- No training code in hypervector  
- Unit tests use mock booster / missing path → graceful fail  
- Wire optional CLI: `--conviction-model impulse_btc` on `phase2-run` / sweeps later; default remains fixed `--conviction`

- [ ] **Step 1: Tests for missing root and mock predict**

- [ ] **Step 2: Implement façade (load `metalabel_lgbm.txt` + calibrator if present)**

- [ ] **Step 3: pytest + commit**

```bash
uv run pytest tests/test_ml_impulse_btc.py -v
git commit -m "feat(ml): optional BTC 1m impulse metalabel conviction façade"
```

---

### Task 8: Phase 3 paper identity scaffold (no live loop)

**Files:**
- Create: `src/hypervector/paper/__init__.py`
- Create: `src/hypervector/paper/ledger.py`
- Test: `tests/test_paper_ledger.py`

**Produces:**
- `append_paper_decision(data_root, record: dict) -> Path` under `data/paper/decisions/`
- Every record **must** include `"execution_mode": "paper"` and a feed timestamp field
- Refuse writes if path resolves under `data/live/`
- CLI: `paper-check` prints layout + “live feed loop not implemented”

**Out of scope this task:** Hyperliquid live subscribe, order gateway, real synthetic fill loop.

- [ ] **Step 1–4: TDD ledger helper + CLI smoke + commit**

```bash
git commit -m "feat(paper): decision ledger scaffold with execution_mode=paper"
```

---

### Task 9: Full verification + handoff close

**Files:**
- Modify: `HANDOFF.md`
- Modify: this plan checkboxes as done

- [ ] **Step 1: Full offline suite**

```bash
uv run pytest tests/ -q
# expect 0 failures (network deselected)
```

- [ ] **Step 2: Real-world Phase 2 path**

```bash
uv run python -m hypervector --data-root data history --lookback 30
# use a strict export (or re-sweep --export)
uv run python -m hypervector export-validate --path data/exports/<id> --strict
uv run python -m hypervector phase2-check --path data/exports/<id>
uv run python -m hypervector --data-root data phase2-run --path data/exports/<id> --lookback 30
ls data/nautilus/backtest/
```

- [ ] **Step 3: Update HANDOFF status → Phase 2 actor done; paper live-loop next**

- [ ] **Step 4: Commit docs**

```bash
git commit -m "docs: handoff after Phase 2 actor plan execution"
```

---

## Non-goals (this plan)

- Live order placement / API keys / vaults  
- Full paper live-feed event loop (scaffold only)  
- Greenfield metalabel training  
- Multi-symbol / multi-TF runtime  
- Signal parquet as live brain  
- Postgres / Redis / k8s  

---

## Verification plan

1. `pytest tests/ -q` → 0 failures (network deselected).  
2. Signal adapter matches registry builder on fixture OHLCV.  
3. `phase2-run` on strict export + cached history completes offline-capable path; writes `data/nautilus/backtest/*/summary.json`.  
4. Actor never opens `signals.parquet` for decisions (code review / grep).  
5. ML façade tests pass without real models; real bundle optional smoke if path exists.  
6. Paper ledger rejects live path mixing; stamps `execution_mode=paper`.  
7. HANDOFF points at remaining live-loop / promotion work.

---

## Next session entry (execute)

```bash
cd /Users/gestas/Prototypes/hypervector
uv sync --all-extras
# read:
#   HANDOFF.md
#   docs/superpowers/plans/2026-07-22-phase2-actor-and-ml.md
#   docs/superpowers/specs/2026-07-22-phase2-3-handoff.md
uv run pytest tests/ -q
# execute Tasks 1→6 first; Task 7 ML optional; Task 8 paper scaffold; Task 9 verify
```

## Deviations

- (none yet)

## Spec coverage (self-check)

| Spec concern | Task |
|--------------|------|
| Load export → StrategyLoadout | exists (prior); used in 4–6 |
| Re-run strategy from params, not signals | 1, 4 |
| Phase 2 historical sim | 5–6 |
| Costs/risk/exits on loadout | 2, 4 |
| Paper 1:1 identity later; synthetic logging | 8 scaffold |
| ML façade reuse, no training | 7 |
| I2 paths / paper-live separation | 5, 8 |
| Promotion ladder (no VBT→live) | HANDOFF + non-goals |
