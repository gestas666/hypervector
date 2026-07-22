"""Nautilus Strategy actor driven by Phase 1 StrategyLoadout.

Recomputes alpha from OHLCV buffer + registry (never signals.parquet).
Order placement is minimal one-position netting for Phase 2 historical sim.
"""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
from nautilus_trader.common.enums import LogColor
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.nautilus.signals import SignalIntent, last_bar_intent
from hypervector.nautilus.sizing import exit_config_from_loadout, position_size_frac
from hypervector.sweep.exits import stop_distance_frac, tp_distance_frac

DEFAULT_MAX_LOOKBACK = 2000
EXECUTION_MODE = "phase2_historical"

Action = Literal["enter_long", "enter_short", "close", "hold"]

_OHLCV_COLS = ("open", "high", "low", "close", "volume")


class HypervectorStrategyConfig(StrategyConfig, frozen=True):
    """Config for :class:`HypervectorStrategy` (msgspec / frozen StrategyConfig)."""

    bar_type: str
    strategy_name: str
    params: dict[str, Any] = {}
    loadout_summary: dict[str, Any] = {}
    instrument_id: str | None = None
    exits: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    costs: dict[str, Any] | None = None
    conviction: float = 0.5
    max_lookback: int = DEFAULT_MAX_LOOKBACK
    execution_mode: str = EXECUTION_MODE


def config_from_loadout(
    loadout: StrategyLoadout,
    *,
    bar_type: str,
    instrument_id: str | None = None,
    conviction: float = 0.5,
    max_lookback: int = DEFAULT_MAX_LOOKBACK,
) -> HypervectorStrategyConfig:
    """Build :class:`HypervectorStrategyConfig` from a validated loadout.

    ``exits`` always carries a ``mode`` key (from exits dict, exit_mode, or
    :func:`exit_config_from_loadout` defaults). Does not load signal arrays.
    """
    exits = _normalize_exits(loadout)
    resolved_id = instrument_id or _instrument_id_from_bar_type(bar_type)
    return HypervectorStrategyConfig(
        bar_type=str(bar_type),
        instrument_id=resolved_id,
        strategy_name=str(loadout.strategy_name),
        params=dict(loadout.params),
        exits=exits,
        risk=dict(loadout.risk) if loadout.risk is not None else None,
        costs=dict(loadout.costs) if loadout.costs is not None else None,
        conviction=float(conviction),
        loadout_summary=loadout.summary(),
        max_lookback=int(max_lookback),
    )


def _normalize_exits(loadout: StrategyLoadout) -> dict[str, Any]:
    """Ensure exits dict includes mode; fill remaining fields from ExitConfig."""
    raw = dict(loadout.exits or {})
    if "mode" not in raw or raw.get("mode") is None:
        if loadout.exit_mode is not None:
            raw["mode"] = loadout.exit_mode
    # Merge with ExitConfig defaults so SL/TP helpers always have keys.
    cfg = exit_config_from_loadout(
        StrategyLoadout(
            strategy_name=loadout.strategy_name,
            role=loadout.role,
            params=loadout.params,
            meta=loadout.meta,
            costs=loadout.costs,
            risk=loadout.risk,
            exit_mode=loadout.exit_mode,
            exits=raw or None,
            export_dir=loadout.export_dir,
        )
    )
    out = cfg.to_dict()
    # Preserve any extra keys from the export beyond ExitConfig fields.
    for k, v in raw.items():
        if k not in out:
            out[k] = v
    return out


def _instrument_id_from_bar_type(bar_type: str) -> str:
    """``BTC-PERP.HYPERLIQUID-1-MINUTE-LAST-EXTERNAL`` → ``BTC-PERP.HYPERLIQUID``."""
    try:
        return str(BarType.from_str(bar_type).instrument_id)
    except Exception:
        # Fallback: strip aggregation suffix after second hyphen-group of venue
        # Prefer splitting on known pattern: SYMBOL.VENUE-AGG-...
        head = bar_type.split("-", 1)[0]  # e.g. BTC-PERP.HYPERLIQUID wrong
        # Safer: InstrumentId lives before first aggregation token
        # Format: {symbol}.{venue}-{step}-{agg}-{price}-{source}
        parts = bar_type.rsplit("-", 3)
        if len(parts) == 4:
            return parts[0]
        return head


# ---------------------------------------------------------------------------
# Pure helpers (offline-testable; no engine)
# ---------------------------------------------------------------------------


def _bar_ohlcv_record(bar: Bar) -> dict[str, Any]:
    """Extract one OHLCV row dict from a Nautilus ``Bar``."""
    return {
        "timestamp": pd.Timestamp(int(bar.ts_event), unit="ns", tz="UTC"),
        "open": float(bar.open.as_double()),
        "high": float(bar.high.as_double()),
        "low": float(bar.low.as_double()),
        "close": float(bar.close.as_double()),
        "volume": float(bar.volume.as_double()),
    }


def _append_bar_record(
    buffer: list[dict[str, Any]],
    record: dict[str, Any],
    *,
    max_lookback: int = DEFAULT_MAX_LOOKBACK,
) -> list[dict[str, Any]]:
    """Append and trim rolling buffer in-place; return the same list."""
    buffer.append(record)
    overflow = len(buffer) - int(max_lookback)
    if overflow > 0:
        del buffer[:overflow]
    return buffer


def _bars_to_ohlcv_df(buffer: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert buffer records to a research-style OHLCV DataFrame."""
    if not buffer:
        return pd.DataFrame(columns=list(_OHLCV_COLS))
    df = pd.DataFrame(buffer)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    return df.loc[:, list(_OHLCV_COLS)].astype(float)


def _action_from_intent(
    intent: SignalIntent,
    *,
    is_flat: bool,
    position_side: str | None,
) -> Action:
    """Map last-bar intent + portfolio flatness → single netting action."""
    if is_flat:
        if intent.enter and intent.direction in ("long", "short"):
            return "enter_long" if intent.direction == "long" else "enter_short"
        return "hold"

    # In a position
    if intent.exit:
        return "close"
    if (
        intent.enter
        and intent.direction in ("long", "short")
        and position_side is not None
        and intent.direction != position_side
    ):
        return "close"
    return "hold"


def _stop_tp_fracs(
    df: pd.DataFrame,
    exits: dict[str, Any] | None,
) -> tuple[float, float | None]:
    """Last-bar stop / TP distances as fractions of price from exit dict."""
    from hypervector.sweep.exits import ExitConfig

    raw = dict(exits or {})
    defaults = ExitConfig()
    cfg = ExitConfig(
        mode=str(raw.get("mode", defaults.mode)),  # type: ignore[arg-type]
        sl_pct=float(raw.get("sl_pct", defaults.sl_pct)),
        rr=float(raw.get("rr", defaults.rr)),
        atr_length=int(raw.get("atr_length", defaults.atr_length)),
        sl_atr_mult=float(raw.get("sl_atr_mult", defaults.sl_atr_mult)),
        trail_atr_mult=float(raw.get("trail_atr_mult", defaults.trail_atr_mult)),
    )
    stop = stop_distance_frac(df, cfg)
    tp = tp_distance_frac(stop, cfg)
    stop_frac = float(stop.iloc[-1])
    tp_last = float(tp.iloc[-1]) if len(tp) else float("nan")
    if cfg.mode == "trail" or tp_last != tp_last:  # NaN
        return stop_frac, None
    return stop_frac, tp_last


# ---------------------------------------------------------------------------
# Strategy actor
# ---------------------------------------------------------------------------


class HypervectorStrategy(Strategy):
    """One-position netting strategy: loadout params → live signals → market.

    Lifecycle owns bar buffer + order submission. Signal math stays in
    ``signals`` / ``sizing`` modules.
    """

    def __init__(self, config: HypervectorStrategyConfig) -> None:
        super().__init__(config)
        self.execution_mode = str(
            getattr(config, "execution_mode", None) or EXECUTION_MODE
        )
        self.max_lookback = int(config.max_lookback or DEFAULT_MAX_LOOKBACK)
        self._bar_buffer: list[dict[str, Any]] = []
        self._bar_type: BarType | None = None
        self._instrument_id: InstrumentId | None = None
        self._pending_entry = False

    def on_start(self) -> None:
        """Subscribe to bars and log Phase 2 historical mode."""
        self._bar_type = BarType.from_str(self.config.bar_type)
        if self.config.instrument_id:
            self._instrument_id = InstrumentId.from_str(self.config.instrument_id)
        else:
            self._instrument_id = self._bar_type.instrument_id

        self.subscribe_bars(self._bar_type)
        self.log.info(
            f"HypervectorStrategy start execution_mode={self.execution_mode} "
            f"strategy={self.config.strategy_name} bar_type={self.config.bar_type} "
            f"instrument_id={self._instrument_id} conviction={self.config.conviction}",
            color=LogColor.BLUE,
        )

    def on_bar(self, bar: Bar) -> None:
        """Append bar, recompute intent, enter/exit with one netting position."""
        self._append_bar(bar)
        if len(self._bar_buffer) < 2:
            return

        instrument_id = self._instrument_id or bar.bar_type.instrument_id
        is_flat = self._is_flat(instrument_id)
        position_side = None if is_flat else self._position_side(instrument_id)

        try:
            intent = self._intent_from_buffer()
        except Exception as exc:
            self.log.warning(
                f"execution_mode={self.execution_mode} intent failed: {exc}"
            )
            return

        action = _action_from_intent(
            intent, is_flat=is_flat, position_side=position_side
        )
        self.log.info(
            f"execution_mode={self.execution_mode} bar={len(self._bar_buffer)} "
            f"flat={is_flat} side={position_side} "
            f"intent(enter={intent.enter},exit={intent.exit},dir={intent.direction}) "
            f"action={action}",
            color=LogColor.CYAN,
        )

        if action == "hold":
            return
        if action == "close":
            self._close_position(instrument_id)
            return
        if action in ("enter_long", "enter_short") and not self._pending_entry:
            direction = "long" if action == "enter_long" else "short"
            self._enter(bar, instrument_id, direction)

    # -- buffer / intent (public-ish for offline tests) --------------------

    def _append_bar(self, bar: Bar) -> None:
        _append_bar_record(
            self._bar_buffer,
            _bar_ohlcv_record(bar),
            max_lookback=self.max_lookback,
        )

    def _intent_from_buffer(self) -> SignalIntent:
        df = _bars_to_ohlcv_df(self._bar_buffer)
        return last_bar_intent(df, self.config.strategy_name, dict(self.config.params))

    # -- portfolio helpers -------------------------------------------------

    def _is_flat(self, instrument_id: InstrumentId) -> bool:
        try:
            return bool(self.portfolio.is_flat(instrument_id))
        except Exception:
            return True

    def _position_side(self, instrument_id: InstrumentId) -> str | None:
        try:
            net = self.portfolio.net_position(instrument_id)
            if net is None:
                return None
            qty = float(net)
            if qty > 0:
                return "long"
            if qty < 0:
                return "short"
            return None
        except Exception:
            return None

    def _equity_estimate(self) -> float:
        """Prefer portfolio mark equity when the engine is attached; else init_cash."""
        try:
            venue = None
            if self._instrument_id is not None:
                venue = self._instrument_id.venue
            equity_map = self.portfolio.equity(venue)
            if equity_map:
                total = sum(float(m.as_double()) for m in equity_map.values())
                if total > 0:
                    return total
        except Exception:
            pass
        summary = self.config.loadout_summary or {}
        init = summary.get("init_cash")
        if init is not None:
            try:
                return float(init)
            except (TypeError, ValueError):
                pass
        return 10_000.0

    # -- orders ------------------------------------------------------------

    def _enter(
        self,
        bar: Bar,
        instrument_id: InstrumentId,
        direction: str,
    ) -> None:
        df = _bars_to_ohlcv_df(self._bar_buffer)
        stop_frac, tp_frac = _stop_tp_fracs(df, self.config.exits)
        equity = self._equity_estimate()

        # Build a minimal loadout-shaped object for sizing (fields only).
        loadout = _sizing_loadout_view(self.config)
        size_frac = position_size_frac(
            equity,
            stop_frac=max(stop_frac, 1e-6),
            loadout=loadout,
            conviction=float(self.config.conviction),
        )
        price = float(bar.close.as_double())
        if price <= 0 or size_frac <= 0:
            self.log.warning(
                f"execution_mode={self.execution_mode} skip enter: "
                f"price={price} size_frac={size_frac}"
            )
            return

        notional = equity * float(size_frac)
        qty_raw = notional / price
        qty = self._make_qty(instrument_id, qty_raw)
        if qty is None:
            return

        side = OrderSide.BUY if direction == "long" else OrderSide.SELL
        mode = (self.config.exits or {}).get("mode", "atr")

        if mode in ("fixed_rr", "atr") and tp_frac is not None and stop_frac > 0:
            self._submit_bracket(
                instrument_id=instrument_id,
                side=side,
                qty=qty,
                price=price,
                direction=direction,
                stop_frac=stop_frac,
                tp_frac=tp_frac,
            )
        else:
            order = self.order_factory.market(
                instrument_id=instrument_id,
                order_side=side,
                quantity=qty,
                time_in_force=TimeInForce.GTC,
            )
            self.submit_order(order)
            self.log.info(
                f"execution_mode={self.execution_mode} market {direction} qty={qty} "
                f"size_frac={size_frac:.4f} stop_frac={stop_frac:.4f}",
                color=LogColor.GREEN,
            )
        self._pending_entry = True

    def _submit_bracket(
        self,
        *,
        instrument_id: InstrumentId,
        side: OrderSide,
        qty: Quantity,
        price: float,
        direction: str,
        stop_frac: float,
        tp_frac: float,
    ) -> None:
        if direction == "long":
            sl = price * (1.0 - stop_frac)
            tp = price * (1.0 + tp_frac)
        else:
            sl = price * (1.0 + stop_frac)
            tp = price * (1.0 - tp_frac)

        instrument = None
        try:
            instrument = self.cache.instrument(instrument_id)
        except Exception:
            instrument = None

        if instrument is not None:
            sl_price = instrument.make_price(sl)
            tp_price = instrument.make_price(tp)
        else:
            # Fallback string prices (runner will supply real instrument)
            from nautilus_trader.model.objects import Price

            sl_price = Price.from_str(f"{sl:.1f}")
            tp_price = Price.from_str(f"{tp:.1f}")

        bracket = self.order_factory.bracket(
            instrument_id=instrument_id,
            order_side=side,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
            tp_price=tp_price,
            sl_trigger_price=sl_price,
        )
        self.submit_order_list(bracket)
        self.log.info(
            f"execution_mode={self.execution_mode} bracket {direction} qty={qty} "
            f"sl={sl_price} tp={tp_price}",
            color=LogColor.GREEN,
        )

    def _close_position(self, instrument_id: InstrumentId) -> None:
        try:
            self.close_all_positions(instrument_id)
            self.log.info(
                f"execution_mode={self.execution_mode} close_all_positions "
                f"{instrument_id}",
                color=LogColor.YELLOW,
            )
        except Exception as exc:
            # Fallback: market flatten via net position
            self.log.warning(
                f"execution_mode={self.execution_mode} close_all_positions failed: {exc}"
            )
            try:
                net = self.portfolio.net_position(instrument_id)
                qty_f = abs(float(net)) if net is not None else 0.0
                if qty_f <= 0:
                    return
                side = OrderSide.SELL if float(net) > 0 else OrderSide.BUY
                qty = self._make_qty(instrument_id, qty_f)
                if qty is None:
                    return
                order = self.order_factory.market(
                    instrument_id=instrument_id,
                    order_side=side,
                    quantity=qty,
                    time_in_force=TimeInForce.GTC,
                    reduce_only=True,
                )
                self.submit_order(order)
            except Exception as exc2:
                self.log.error(
                    f"execution_mode={self.execution_mode} flatten failed: {exc2}"
                )
        self._pending_entry = False

    def _make_qty(
        self, instrument_id: InstrumentId, qty_raw: float
    ) -> Quantity | None:
        if qty_raw <= 0:
            return None
        try:
            instrument = self.cache.instrument(instrument_id)
            if instrument is not None:
                return instrument.make_qty(qty_raw)
        except Exception:
            pass
        # Offline / no instrument in cache: 3-decimal crypto stub
        return Quantity.from_str(f"{qty_raw:.3f}")

    def on_order_denied(self, event: Any) -> None:
        """Clear pending-entry so a deny cannot wedge the strategy forever."""
        self._pending_entry = False

    def on_order_rejected(self, event: Any) -> None:
        self._pending_entry = False

    def on_position_opened(self, event: Any) -> None:
        self._pending_entry = False

    def on_position_closed(self, event: Any) -> None:
        self._pending_entry = False

    def on_event(self, event: Any) -> None:
        """Fallback clear for terminal order/position events (typed hooks preferred)."""
        name = type(event).__name__
        if name in (
            "PositionOpened",
            "PositionClosed",
            "OrderRejected",
            "OrderDenied",
            "OrderCanceled",
        ):
            self._pending_entry = False


def _sizing_loadout_view(config: HypervectorStrategyConfig) -> StrategyLoadout:
    """Minimal StrategyLoadout for :func:`position_size_frac` / exit helpers."""
    from pathlib import Path

    return StrategyLoadout(
        strategy_name=config.strategy_name,
        role=None,
        params=dict(config.params or {}),
        meta={},
        costs=dict(config.costs) if config.costs else None,
        risk=dict(config.risk) if config.risk else None,
        exit_mode=(config.exits or {}).get("mode"),
        exits=dict(config.exits) if config.exits else None,
        export_dir=Path("."),
        init_cash=(config.loadout_summary or {}).get("init_cash"),
    )
