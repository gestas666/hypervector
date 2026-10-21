"""Phase 2 historical backtest runner: export loadout → Nautilus engine → artifacts.

Offline-capable when ``ohlcv`` is injected (tests) or research cache is warm.
Never requires network when OHLCV is provided.

What the run models (all recorded in ``summary.json``):

* instrument: built for the export symbol from venue geometry
  (:mod:`hypervector.nautilus.venue_spec`); unknown symbols are refused before
  any history is loaded;
* costs: the export cost model (taker fee + slippage per side, post-run
  funding estimate) — :mod:`hypervector.nautilus.costs`;
* conviction: explicit argument, else the export's conviction;
* sizing: entry notional = size fraction x ``init_cash`` (``sizing_basis``),
  VectorBT's non-compounding basis, so the ``parity`` block compares like
  sizing;
* fills: a bar offers a quarter of its volume per price level, so a large
  order fills in pieces and the remainder one tick worse; those orders and
  their extra cost are reported (``volume_capped_fills``);
* brackets (``fixed_rr``/``atr``): Nautilus walks each bar open, high, low,
  close, so a long whose SL and TP both lie inside one bar takes the TP where
  VectorBT takes the SL; listed in ``event_venue_model_gaps`` and counted
  (``bracket_same_bar_tp_fills``);
* margin: ``StandardMarginModel`` with ``margin_init = 1 / sim leverage`` and
  the venue maintenance rate (Nautilus 1.230 neither denies nor liquidates
  margin-account orders in this bar sim; nothing here adds such a gate);
* bars: stamped at bar close; the actor rebuilds research bar-open labels;
* signals: precomputed once over the replay when a windowed probe confirms
  equivalence (``signal_mode="auto"``), else the windowed actor path;
* PnL: mark-to-market (realized + unrealized of open positions) minus the
  funding estimate; position cycles are reported as ``trade_count``.

Any strategy or engine error raises :class:`Phase2TechnicalFailure` and no
success summary is written (technical failure aborts; there are no gates).
"""

from __future__ import annotations

import json
import math
import uuid
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import StandardMarginModel
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model import TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import (
    AccountType,
    OmsType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

from hypervector.config import DEFAULT_LOOKBACK
from hypervector.data.pipeline import load_research_history, strict_hl_only_from_meta
from hypervector.infra import ensure_data_layout
from hypervector.nautilus.actor import (
    EXECUTION_MODE,
    SIZING_BASIS,
    HypervectorStrategy,
    config_from_loadout,
)
from hypervector.nautilus.bars import (
    bar_interval_ns,
    bar_type_from_loadout,
    dataframe_to_bars,
)
from hypervector.nautilus.costs import (
    Phase2CostModel,
    estimate_funding,
    resolve_phase2_conviction,
    resolve_phase2_costs,
)
from hypervector.nautilus.errors import (
    Phase2IntentError,
    Phase2TechnicalFailure,
    UnknownStrategyError,
)
from hypervector.nautilus.instruments import perp_instrument_from_spec
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.precompute import (
    ohlcv_frame_from_bars,
    precompute_intents,
    probe_precomputed,
)
from hypervector.nautilus.trail import TRAIL_EXIT_MODEL
from hypervector.nautilus.venue_spec import VenueInstrumentSpec, resolve_venue_spec
from hypervector.strategies import get_strategy, register_all_strategies
from hypervector.strategies.registry import execution_profile

_DEFAULT_INIT_CASH = 10_000.0
_VENUE = "HYPERLIQUID"

SignalMode = Literal["auto", "windowed", "precomputed"]
_SIGNAL_MODES = ("auto", "windowed", "precomputed")
_SEMANTICS = {
    "precomputed": "full_frame_research_parity",
    "windowed": "rolling_window_live_parity",
}


@dataclass(frozen=True)
class Phase2Result:
    """Outcome of a Phase 2 historical backtest run."""

    export_dir: Path
    orders_count: int
    pnl: float
    report_path: Path
    loadout_summary: dict[str, Any]
    trade_count: int = 0
    pnl_realized: float = 0.0
    pnl_unrealized: float = 0.0
    funding_cost: float = 0.0
    commissions_total: float = 0.0
    open_positions_at_end: int = 0
    signal_mode: str = "windowed"
    extras: dict[str, Any] = field(default_factory=dict)


def _default_leverage(loadout: StrategyLoadout) -> Decimal:
    """The strategy's declared leverage, else 1x."""
    declared = execution_profile(loadout.strategy_name).leverage
    return Decimal(str(declared)) if declared is not None else Decimal(1)


def _sim_leverage(loadout: StrategyLoadout, spec: VenueInstrumentSpec) -> Decimal:
    """Configured sim leverage, never above the venue/charter max for the asset."""
    return min(_default_leverage(loadout), Decimal(str(spec.venue_max_leverage)))


def _require_registered_strategy(loadout: StrategyLoadout, export_path: Path) -> None:
    try:
        get_strategy(loadout.strategy_name)
    except KeyError:
        raise UnknownStrategyError(export_path, loadout.strategy_name) from None


def run_phase2_backtest(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    ohlcv: pd.DataFrame | None = None,
    conviction: float | None = None,
    lookback_days: int | None = None,
    max_bars: int | None = None,
    log_level: str = "ERROR",
    venue: str = _VENUE,
    allow_network: bool = True,
    signal_mode: SignalMode = "auto",
    strict_hl_only: bool | None = None,
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
        Position-sizing conviction. ``None`` (default) uses the export's
        ``meta.conviction``, else ``risk.default_conviction``, else 0.5.
    lookback_days:
        History window when loading from cache (defaults to loadout meta or
        :data:`DEFAULT_LOOKBACK`).
    max_bars:
        Optional bar cap after load (timeout-friendly unit tests).
    log_level:
        Nautilus console log level (default ERROR to keep tests quiet).
    venue:
        Simulated venue code (default HYPERLIQUID).
    signal_mode:
        ``"auto"`` (default): precompute signals once when the windowed probe
        finds no mismatch, else replay windowed. ``"precomputed"``: require
        precompute (probe mismatch is a technical failure). ``"windowed"``:
        rebuild signals from the trailing window on every bar.
    strict_hl_only:
        Load the strict HL-only (``_hlonly``) history window. ``None`` (default)
        follows the bundle: a bundle searched on HL-only history is replayed
        on HL-only history, never on the Binance/Bybit-backfilled entry.

    Returns
    -------
    Phase2Result
        Orders/trade counts, mark-to-market PnL, path to ``summary.json``.

    Raises
    ------
    Phase2TechnicalFailure
        Strategy error, probe mismatch in ``precomputed`` mode, or engine
        fault. No success summary is written.
    UnknownStrategyError
        The bundle names an unregistered strategy.
    UnsupportedNautilusSymbol
        No venue geometry is known for the export symbol.
    """
    if signal_mode not in _SIGNAL_MODES:
        raise ValueError(
            f"signal_mode must be one of {_SIGNAL_MODES}, got {signal_mode!r}"
        )
    register_all_strategies()
    export_path = Path(export_dir).resolve()
    paths = ensure_data_layout(data_root)

    loadout = load_strategy_loadout(export_path, strict=True)
    _require_registered_strategy(loadout, export_path)
    spec = resolve_venue_spec(loadout.symbol, loadout.meta)
    costs = resolve_phase2_costs(loadout)
    conviction_value, conviction_source = resolve_phase2_conviction(loadout, conviction)
    managed_exits = execution_profile(loadout.strategy_name).strategy_managed_exits

    df = _resolve_ohlcv(
        ohlcv=ohlcv,
        data_root=paths.root,
        loadout=loadout,
        lookback_days=lookback_days,
        allow_network=allow_network,
        strict_hl_only=strict_hl_only,
    )
    if max_bars is not None and len(df) > int(max_bars):
        df = df.iloc[: int(max_bars)].copy()

    bar_type = bar_type_from_loadout(loadout, venue=venue)
    sim_leverage = _sim_leverage(loadout, spec)
    instrument = perp_instrument_from_spec(
        spec,
        venue=venue,
        maker_fee=Decimal(str(costs.instrument_maker_fee)),
        taker_fee=Decimal(str(costs.instrument_taker_fee)),
        margin_init=Decimal(1) / sim_leverage,
        margin_maint=Decimal(str(spec.maintenance_rate)),
    )
    bar_instrument_id = str(BarType.from_str(bar_type).instrument_id)
    if str(instrument.id) != bar_instrument_id:
        raise Phase2TechnicalFailure(
            f"instrument {instrument.id} does not match bar type instrument "
            f"{bar_instrument_id}",
            strategy=loadout.strategy_name,
            export_dir=export_path,
        )
    bars = dataframe_to_bars(df, bar_type, instrument, timestamp_at="close")

    init_cash = (
        float(loadout.init_cash)
        if loadout.init_cash is not None
        else _DEFAULT_INIT_CASH
    )
    strategy_config = config_from_loadout(
        loadout,
        bar_type=bar_type,
        instrument_id=str(instrument.id),
        conviction=float(conviction_value),
    )
    strategy = HypervectorStrategy(config=strategy_config)
    # Same rule as the actor: SL/TP brackets unless the strategy owns exits.
    brackets = not managed_exits and str(
        (strategy_config.exits or {}).get("mode")
    ) in ("fixed_rr", "atr")
    signal_info = _prepare_signals(
        strategy,
        bars=bars,
        bar_type=bar_type,
        loadout=loadout,
        export_path=export_path,
        exits=dict(strategy_config.exits or {}),
        max_lookback=int(strategy_config.max_lookback),
        signal_mode=signal_mode,
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
    v = Venue(venue)
    try:
        engine.add_venue(
            venue=v,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(init_cash, USDT)],
            base_currency=USDT,
            default_leverage=sim_leverage,
            margin_model=StandardMarginModel(),
        )
        engine.add_instrument(instrument)
        engine.add_data(bars)
        engine.add_strategy(strategy)
        try:
            engine.run()
        except Phase2TechnicalFailure as exc:
            exc.export_dir = str(export_path)
            raise
        except Exception as exc:
            raise Phase2TechnicalFailure(
                f"Nautilus engine run failed for {loadout.strategy_name!r}: "
                f"{type(exc).__name__}: {exc}",
                strategy=loadout.strategy_name,
                export_dir=export_path,
                first_error=strategy.intent_error or f"{type(exc).__name__}: {exc}",
            ) from exc
        if strategy.intent_error is not None:  # defensive: never report ok
            raise Phase2IntentError(
                f"strategy {loadout.strategy_name!r} recorded an intent error",
                strategy=loadout.strategy_name,
                export_dir=export_path,
                first_error=strategy.intent_error,
            )

        result = engine.get_result()
        orders_count = int(getattr(result, "total_orders", 0) or 0)
        if orders_count == 0:
            orders_count = len(engine.cache.orders())
        outcome = _collect_outcome(
            result=result,
            engine=engine,
            strategy=strategy,
            venue=v,
            init_cash=init_cash,
            costs=costs,
            last_bar_close_ns=int(bars[-1].ts_event) if bars else 0,
        )
        orders = list(engine.cache.orders())
        volume_capped = _volume_capped_fills(orders)
        same_bar_tp = (
            _bracket_same_bar_tp_fills(orders, engine.cache, bars)
            if brackets
            else None
        )
        engine_run_id = str(getattr(result, "run_id", "") or "")
    finally:
        engine.dispose()

    run_id = _make_run_id(loadout)
    report_dir = paths.nautilus_backtest / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "summary.json"

    loadout_summary = loadout.summary()
    gaps = ["native_liquidation"]
    if brackets:
        gaps.append("bracket_same_bar_sl_tp_ohlc_order")
    payload: dict[str, Any] = {
        "run_id": run_id,
        "engine_run_id": engine_run_id,
        "execution_mode": EXECUTION_MODE,
        "export_dir": str(export_path),
        "data_root": str(paths.root.resolve()),
        "venue": venue,
        "instrument_id": str(instrument.id),
        "instrument": {
            **spec.to_dict(),
            "price_increment": str(instrument.price_increment),
            "size_increment": str(instrument.size_increment),
        },
        "bar_type": bar_type,
        "bar_timestamps": "close",
        "data_fidelity": "ohlcv_bar",
        "venue_model": "phase2_bar_only",
        "event_venue_model_gaps": gaps,
        "margin": {
            "sim_leverage": float(sim_leverage),
            "venue_max_leverage": float(spec.venue_max_leverage),
            "margin_model": "standard_init_1_over_sim_leverage",
            "margin_init": float(instrument.margin_init),
            "margin_maint": float(instrument.margin_maint),
            "margin_enforcement": "none_nautilus_1230_bar_sim_no_denial_or_liquidation",
        },
        "cost_model": costs.to_dict(),
        "exit_mode": str((strategy_config.exits or {}).get("mode")),
        "trail_exit_model": TRAIL_EXIT_MODEL if strategy._trail_enabled else None,
        "trail_exits": int(strategy.trail_exits),
        "bracket_same_bar_tp_fills": same_bar_tp,
        "volume_capped_fills": volume_capped,
        "sizing_basis": SIZING_BASIS,
        **signal_info,
        "bars": len(bars),
        "conviction": float(conviction_value),
        "conviction_source": conviction_source,
        "init_cash": init_cash,
        "orders_count": orders_count,
        "pnl": outcome["pnl"],
        "pnl_basis": "mark_to_market_net_of_fees_and_funding",
        "pnl_realized": outcome["pnl_realized"],
        "pnl_unrealized": outcome["pnl_unrealized"],
        "pnl_before_funding": outcome["pnl_before_funding"],
        "funding_cost": outcome["funding_cost"],
        "commissions_total": outcome["commissions_total"],
        "trade_count": outcome["trade_count"],
        "positions_count": outcome["trade_count"],
        "open_positions_at_end": outcome["open_positions_at_end"],
        "intent_errors": 0,
        "parity": _parity_block(loadout, outcome),
        "loadout": loadout_summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    report_path.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    return Phase2Result(
        export_dir=export_path,
        orders_count=orders_count,
        pnl=outcome["pnl"],
        report_path=report_path.resolve(),
        loadout_summary=loadout_summary,
        trade_count=outcome["trade_count"],
        pnl_realized=outcome["pnl_realized"],
        pnl_unrealized=outcome["pnl_unrealized"],
        funding_cost=outcome["funding_cost"],
        commissions_total=outcome["commissions_total"],
        open_positions_at_end=outcome["open_positions_at_end"],
        signal_mode=str(signal_info["signal_mode_used"]),
        extras={"conviction_source": conviction_source, "cost_model": costs.to_dict()},
    )


def _prepare_signals(
    strategy: HypervectorStrategy,
    *,
    bars: list[Any],
    bar_type: str,
    loadout: StrategyLoadout,
    export_path: Path,
    exits: dict[str, Any],
    max_lookback: int,
    signal_mode: str,
) -> dict[str, Any]:
    """Attach precomputed intents when allowed; return summary fields."""
    info: dict[str, Any] = {
        "signal_mode": signal_mode,
        "signal_mode_used": "windowed",
        "signal_semantics": _SEMANTICS["windowed"],
        "causal_probe": None,
    }
    if signal_mode == "windowed" or not bars:
        return info
    frame = ohlcv_frame_from_bars(bars, label_offset_ns=bar_interval_ns(bar_type))
    try:
        intents = precompute_intents(
            frame, loadout.strategy_name, dict(loadout.params), exits
        )
        probe = probe_precomputed(
            intents,
            frame,
            loadout.strategy_name,
            dict(loadout.params),
            exits,
            max_lookback=max_lookback,
        )
    except Exception as exc:
        raise Phase2IntentError(
            f"strategy {loadout.strategy_name!r} failed while computing signals: "
            f"{type(exc).__name__}: {exc}",
            strategy=loadout.strategy_name,
            export_dir=export_path,
            first_error={
                "phase": "signal_precompute",
                "error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc
    info["causal_probe"] = probe
    if probe["mismatches"]:
        if signal_mode == "precomputed":
            raise Phase2TechnicalFailure(
                f"precomputed signals for {loadout.strategy_name!r} disagree with the "
                f"windowed computation on {probe['mismatches']} of "
                f"{probe['sampled']} probed bars",
                strategy=loadout.strategy_name,
                export_dir=export_path,
                first_error=probe["first_mismatch"],
            )
        info["signal_fallback_reason"] = "causal_probe_mismatch"
        return info
    strategy.attach_precomputed(intents)
    info["signal_mode_used"] = "precomputed"
    info["signal_semantics"] = _SEMANTICS["precomputed"]
    return info


def _money_total(mapping: Any) -> float:
    if not mapping:
        return 0.0
    total = 0.0
    for money in mapping.values():
        if money is None:
            continue
        total += float(money.as_double())
    return total


def _collect_outcome(
    *,
    result: Any,
    engine: BacktestEngine,
    strategy: HypervectorStrategy,
    venue: Venue,
    init_cash: float,
    costs: Phase2CostModel,
    last_bar_close_ns: int,
) -> dict[str, Any]:
    """Mark-to-market PnL, funding, commissions and position counts (pre-dispose)."""
    pnl_realized = _realized_pnl(result, engine, venue, init_cash)
    pnl_unrealized = _money_total(engine.portfolio.unrealized_pnls(venue))
    account = engine.portfolio.account(venue)
    commissions_total = _money_total(account.commissions()) if account else 0.0

    holdings: list[tuple[float, float]] = []
    for rec in strategy.position_records:
        notional = abs(rec["avg_px_open"] * rec["peak_qty"])
        hold_min = (rec["ts_closed"] - rec["ts_opened"]) / 60e9
        if math.isfinite(notional) and math.isfinite(hold_min):
            holdings.append((notional, hold_min))
    open_positions = list(engine.cache.positions_open())
    for pos in open_positions:
        notional = abs(float(pos.avg_px_open) * float(pos.peak_qty.as_double()))
        hold_min = (last_bar_close_ns - int(pos.ts_opened)) / 60e9
        holdings.append((notional, hold_min))
    funding_cost = estimate_funding(holdings, costs)

    pnl_before_funding = pnl_realized + pnl_unrealized
    return {
        "pnl": pnl_before_funding - funding_cost,
        "pnl_realized": pnl_realized,
        "pnl_unrealized": pnl_unrealized,
        "pnl_before_funding": pnl_before_funding,
        "funding_cost": funding_cost,
        "commissions_total": commissions_total,
        "trade_count": int(strategy.positions_opened),
        "open_positions_at_end": len(open_positions),
    }


def _parity_block(loadout: StrategyLoadout, outcome: dict[str, Any]) -> dict[str, Any]:
    """Side-by-side with the export's research metrics (report only, never a gate)."""
    metrics = loadout.metrics or {}

    def _num(key: str) -> float | None:
        value = metrics.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    export_trades = _num("trade_count")
    export_pnl = _num("net_pnl")
    return {
        "export_trade_count": export_trades,
        "nautilus_trade_count": outcome["trade_count"],
        "trade_count_delta": (
            outcome["trade_count"] - export_trades
            if export_trades is not None
            else None
        ),
        "export_net_pnl": export_pnl,
        "nautilus_pnl": outcome["pnl"],
        "pnl_delta": outcome["pnl"] - export_pnl if export_pnl is not None else None,
        "sizing_basis": SIZING_BASIS,
        "note": "export metrics cover the research window; compare only like windows",
    }


def _order_fills(order: Any) -> list[Any]:
    return [event for event in order.events if isinstance(event, OrderFilled)]


def _volume_capped_fills(orders: list[Any]) -> dict[str, Any]:
    """Orders filled in more than one piece and the cost of the later pieces.

    Bar execution offers a quarter of the bar volume per price level, so an
    order larger than that fills its remainder one tick worse. ``extra_cost``
    is that remainder's cost against the first fill price (report only).
    """
    count = 0
    extra = 0.0
    for order in orders:
        fills = _order_fills(order)
        if len(fills) < 2:
            continue
        count += 1
        first = float(fills[0].last_px)
        sign = 1.0 if order.side == OrderSide.BUY else -1.0
        extra += sum(
            sign * (float(f.last_px) - first) * float(f.last_qty) for f in fills[1:]
        )
    return {
        "orders": count,
        "extra_cost": extra,
        "note": "remainder of a volume-capped bar fill, one tick worse per piece",
    }


def _bracket_same_bar_tp_fills(orders: list[Any], cache: Any, bars: list[Any]) -> int:
    """TP fills on a bar whose range also reached the bracket's SL.

    Nautilus walks a bar open, high, low, close and fills whichever level that
    path meets first; VectorBT always takes the SL. Each count is a trade
    that VectorBT would have exited at the stop (report only, never a gate).
    """
    closes = [int(bar.ts_event) for bar in bars]
    count = 0
    for order in orders:
        if order.order_type != OrderType.LIMIT or order.status != OrderStatus.FILLED:
            continue
        linked = (cache.order(cid) for cid in (order.linked_order_ids or ()))
        stop = next(
            (o for o in linked if o is not None and o.order_type == OrderType.STOP_MARKET),
            None,
        )
        if stop is None:
            continue
        i = bisect_left(closes, int(order.ts_last))
        if i >= len(bars):
            continue
        bar, trigger = bars[i], float(stop.trigger_price)
        if order.side == OrderSide.SELL:  # TP of a long; its SL sits below
            count += float(bar.low) <= trigger
        else:
            count += float(bar.high) >= trigger
    return count


def _resolve_ohlcv(
    *,
    ohlcv: pd.DataFrame | None,
    data_root: Path,
    loadout: StrategyLoadout,
    lookback_days: int | None,
    allow_network: bool = True,
    strict_hl_only: bool | None = None,
) -> pd.DataFrame:
    if ohlcv is not None:
        if len(ohlcv) == 0:
            raise ValueError("run_phase2_backtest requires a non-empty OHLCV frame")
        return ohlcv

    days = lookback_days
    if days is None:
        meta_days = (loadout.meta or {}).get("lookback_days")
        days = int(meta_days) if meta_days is not None else DEFAULT_LOOKBACK

    strict = (
        strict_hl_only_from_meta(loadout.meta)
        if strict_hl_only is None
        else bool(strict_hl_only)
    )
    df, _prov = load_research_history(
        data_root,
        symbol=loadout.symbol,
        timeframe=loadout.timeframe,
        lookback_days=int(days),
        strict_hl_only=strict,
        force_refresh=False,
        allow_network=allow_network,
    )
    if df is None or len(df) == 0:
        raise ValueError(
            f"no research history for {loadout.symbol} {loadout.timeframe} "
            f"lookback={days}d under {data_root}"
        )
    return df


def _realized_pnl(
    result: Any,
    engine: BacktestEngine,
    venue: Venue,
    init_cash: float,
) -> float:
    """Realized USDT PnL (account balance delta, net of commissions)."""
    stats = getattr(result, "stats_pnls", None) or {}
    for _ccy, ccy_stats in stats.items():
        if isinstance(ccy_stats, dict) and "PnL (total)" in ccy_stats:
            val = ccy_stats["PnL (total)"]
            try:
                if val == val:  # not NaN
                    return float(val)
            except (TypeError, ValueError):
                pass
    # No stats (e.g. no fills): realized PnL is the balance delta.
    account = engine.portfolio.account(venue)
    if account is None:
        return 0.0
    return _money_total(account.balances_total()) - float(init_cash)


def _make_run_id(loadout: StrategyLoadout) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    base = loadout.run_id or loadout.strategy_name or "phase2"
    # filesystem-safe
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(base))[:48]
    return f"{safe}_{stamp}_{short}"
