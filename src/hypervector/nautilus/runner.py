"""Phase 2 historical backtest runner: export loadout → Nautilus engine → artifacts.

Offline-capable when ``ohlcv`` is injected (tests) or research cache is warm.
Never requires network when OHLCV is provided.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model import TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from hypervector.config import DEFAULT_LOOKBACK
from hypervector.data.pipeline import load_research_history
from hypervector.infra import ensure_data_layout
from hypervector.nautilus.actor import (
    EXECUTION_MODE,
    HypervectorStrategy,
    config_from_loadout,
)
from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy
from hypervector.nautilus.bars import (
    bar_type_from_loadout,
    dataframe_to_bars,
    synthetic_btc_perp_instrument,
)
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.strategies import register_all_strategies

_DEFAULT_INIT_CASH = 10_000.0
_VENUE = "HYPERLIQUID"


@dataclass(frozen=True)
class Phase2Result:
    """Outcome of a Phase 2 historical backtest run."""

    export_dir: Path
    orders_count: int
    pnl: float
    report_path: Path
    loadout_summary: dict[str, Any]


def _default_leverage(loadout: StrategyLoadout) -> int:
    return 40 if is_hypervelocity_strategy(loadout.strategy_name) else 1


def run_phase2_backtest(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    ohlcv: pd.DataFrame | None = None,
    conviction: float = 0.5,
    lookback_days: int | None = None,
    max_bars: int | None = None,
    log_level: str = "ERROR",
    venue: str = _VENUE,
) -> Phase2Result:
    """Run HypervectorStrategy on research OHLCV via Nautilus BacktestEngine.

    Parameters
    ----------
    export_dir:
        Phase 1.5 strict export directory (params/meta/metrics).
    data_root:
        Data layout root; report lands under ``nautilus/backtest/<run_id>/``.
    ohlcv:
        Optional pre-loaded OHLCV. When set, no history fetch is performed
        (offline path for unit tests). When ``None``, loads via
        :func:`load_research_history` (cache-first).
    conviction:
        Position-sizing conviction passed to the strategy config.
    lookback_days:
        History window when loading from cache (defaults to loadout meta or
        :data:`DEFAULT_LOOKBACK`).
    max_bars:
        Optional bar cap after load (timeout-friendly unit tests).
    log_level:
        Nautilus console log level (default ERROR to keep tests quiet).
    venue:
        Simulated venue code (default HYPERLIQUID).

    Returns
    -------
    Phase2Result
        Orders count, total PnL, path to ``summary.json``, loadout summary.
    """
    register_all_strategies()
    export_path = Path(export_dir).resolve()
    paths = ensure_data_layout(data_root)

    loadout = load_strategy_loadout(export_path, strict=True)
    hypervelocity = is_hypervelocity_strategy(loadout.strategy_name)
    df = _resolve_ohlcv(
        ohlcv=ohlcv,
        data_root=paths.root,
        loadout=loadout,
        lookback_days=lookback_days,
    )
    if max_bars is not None and len(df) > int(max_bars):
        df = df.iloc[: int(max_bars)].copy()

    instrument = synthetic_btc_perp_instrument(venue=venue)
    bar_type = bar_type_from_loadout(loadout, venue=venue)
    bars = dataframe_to_bars(df, bar_type, instrument)

    init_cash = (
        float(loadout.init_cash)
        if loadout.init_cash is not None
        else _DEFAULT_INIT_CASH
    )
    strategy_config = config_from_loadout(
        loadout,
        bar_type=bar_type,
        instrument_id=str(instrument.id),
        conviction=float(conviction),
    )

    # Unique trader/instance IDs so sequential runs in one process don't abort
    # the Nautilus kernel (shared logging/clock singleton hazards).
    short = uuid.uuid4().hex[:8].upper()
    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TraderId(f"HV-PHASE2-{short}"),
            instance_id=UUID4(),
            logging=LoggingConfig(
                log_level=log_level,
                bypass_logging=(log_level.upper() == "ERROR"),
            ),
        )
    )
    try:
        engine.add_venue(
            venue=Venue(venue),
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(init_cash, USDT)],
            base_currency=USDT,
            default_leverage=Decimal(_default_leverage(loadout)),
        )
        engine.add_instrument(instrument)
        engine.add_data(bars)
        engine.add_strategy(HypervectorStrategy(config=strategy_config))
        engine.run()

        result = engine.get_result()
        orders_count = int(getattr(result, "total_orders", 0) or 0)
        if orders_count == 0:
            orders_count = len(engine.cache.orders())
        pnl = _extract_pnl(result, engine, Venue(venue), init_cash)
        engine_run_id = str(getattr(result, "run_id", "") or "")
    finally:
        engine.dispose()

    run_id = _make_run_id(loadout)
    report_dir = paths.nautilus_backtest / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "summary.json"

    loadout_summary = loadout.summary()
    payload: dict[str, Any] = {
        "run_id": run_id,
        "engine_run_id": engine_run_id,
        "execution_mode": EXECUTION_MODE,
        "export_dir": str(export_path),
        "data_root": str(paths.root.resolve()),
        "venue": venue,
        "instrument_id": str(instrument.id),
        "bar_type": bar_type,
        "data_fidelity": "ohlcv_bar",
        "venue_model": "phase2_bar_only",
        "event_venue_model_available": (
            "hypervelocity_event_friction_v1" if hypervelocity else None
        ),
        "event_venue_model_ready": False if hypervelocity else None,
        "event_venue_model_gaps": (
            ["native_liquidation", "proportional_target_resize"]
            if hypervelocity
            else []
        ),
        "bars": len(bars),
        "conviction": float(conviction),
        "init_cash": init_cash,
        "orders_count": orders_count,
        "pnl": pnl,
        "loadout": loadout_summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    report_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    return Phase2Result(
        export_dir=export_path,
        orders_count=orders_count,
        pnl=pnl,
        report_path=report_path.resolve(),
        loadout_summary=loadout_summary,
    )


def _resolve_ohlcv(
    *,
    ohlcv: pd.DataFrame | None,
    data_root: Path,
    loadout: StrategyLoadout,
    lookback_days: int | None,
) -> pd.DataFrame:
    if ohlcv is not None:
        if len(ohlcv) == 0:
            raise ValueError("run_phase2_backtest requires a non-empty OHLCV frame")
        return ohlcv

    days = lookback_days
    if days is None:
        meta_days = (loadout.meta or {}).get("lookback_days")
        days = int(meta_days) if meta_days is not None else DEFAULT_LOOKBACK

    df, _prov = load_research_history(
        data_root,
        symbol=loadout.symbol,
        timeframe=loadout.timeframe,
        lookback_days=int(days),
        force_refresh=False,
    )
    if df is None or len(df) == 0:
        raise ValueError(
            f"no research history for {loadout.symbol} {loadout.timeframe} "
            f"lookback={days}d under {data_root}"
        )
    return df


def _extract_pnl(
    result: Any,
    engine: BacktestEngine,
    venue: Venue,
    init_cash: float,
) -> float:
    """Total USDT PnL from engine stats, else equity delta vs init cash."""
    stats = getattr(result, "stats_pnls", None) or {}
    for _ccy, ccy_stats in stats.items():
        if isinstance(ccy_stats, dict) and "PnL (total)" in ccy_stats:
            val = ccy_stats["PnL (total)"]
            try:
                if val == val:  # not NaN
                    return float(val)
            except (TypeError, ValueError):
                pass

    try:
        equity = engine.portfolio.equity(venue)
        if equity:
            total = sum(float(m.as_double()) for m in equity.values())
            return total - float(init_cash)
    except Exception:
        pass
    return 0.0


def _make_run_id(loadout: StrategyLoadout) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    base = loadout.run_id or loadout.strategy_name or "phase2"
    # filesystem-safe
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(base))[:48]
    return f"{safe}_{stamp}_{short}"
