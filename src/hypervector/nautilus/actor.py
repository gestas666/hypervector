"""Nautilus Strategy actor driven by Phase 1 StrategyLoadout.

Recomputes alpha from OHLCV buffer + registry (never signals.parquet).
Order placement is minimal one-position netting for Phase 2 historical sim.

Two intent sources share one decision path:

* windowed (default for a bare actor): rebuild signals from the trailing
  ``max_lookback`` bars on every bar (live-parity semantics);
* precomputed: the runner attaches :class:`PrecomputedIntents` built once over
  the replay and probed against the windowed computation; ``on_bar`` then
  reads the intent by bar label instead of rebuilding indicators.

A strategy error is a technical failure: it is recorded on
``intent_error`` and raised (:class:`Phase2IntentError`) out of
``engine.run()`` instead of being logged and skipped.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
from nautilus_trader.common.enums import LogColor
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from hypervector.nautilus.errors import Phase2IntentError
from hypervector.nautilus.load_export import StrategyLoadout
from hypervector.nautilus.signals import SignalIntent, last_bar_intent
from hypervector.nautilus.sizing import (
    exit_config_from_dict,
    exit_config_from_loadout,
    position_size_frac,
)
from hypervector.nautilus.trail import (
    TrailState,
    grid_stop_price,
    trail_ratchet,
    trail_start,
)
from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy
from hypervector.sweep.exits import stop_distance_frac, tp_distance_frac

if TYPE_CHECKING:
    from hypervector.nautilus.precompute import PrecomputedIntents

DEFAULT_MAX_LOOKBACK = 2000
EXECUTION_MODE = "phase2_historical"

Action = Literal["enter_long", "enter_short", "close", "hold"]

_OHLCV_COLS = ("open", "high", "low", "close", "volume")


def _uses_strategy_exits_only(strategy_name: str) -> bool:
    return is_hypervelocity_strategy(strategy_name)


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
    # "close": Bar.ts_event is the bar close (dataframe_to_bars default);
    # research frames are labelled by bar open, so the actor subtracts one
    # bar interval to rebuild the research label.
    bar_timestamps: str = "close"


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


def _bar_ohlcv_record(bar: Bar, *, label_offset_ns: int = 0) -> dict[str, Any]:
    """Extract one OHLCV row dict from a Nautilus ``Bar``.

    ``label_offset_ns`` converts a close-stamped ``ts_event`` back to the
    research bar-open label (pass the bar interval for close-stamped bars).
    """
    return {
        "timestamp": pd.Timestamp(
            int(bar.ts_event) - int(label_offset_ns), unit="ns", tz="UTC"
        ),
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
    """Convert buffer records to a research-style OHLCV DataFrame.

    Column-wise construction (same frame as ``pd.DataFrame(buffer)
    .set_index("timestamp")[cols].astype(float)``, without the per-row dict
    parsing that dominated the windowed replay).
    """
    if not buffer:
        return pd.DataFrame(columns=list(_OHLCV_COLS))
    n = len(buffer)
    data = {
        c: np.fromiter((r[c] for r in buffer), dtype=np.float64, count=n)
        for c in _OHLCV_COLS
    }
    if "timestamp" in buffer[0]:
        index = pd.DatetimeIndex([r["timestamp"] for r in buffer], name="timestamp")
        return pd.DataFrame(data, index=index)
    return pd.DataFrame(data)


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
    cfg = exit_config_from_dict(exits)
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
        self._bars_seen = 0
        self._label_offset_ns = _label_offset_ns(config)
        self._precomputed: PrecomputedIntents | None = None
        mode = str((config.exits or {}).get("mode", "atr"))
        self._trail_enabled = mode == "trail" and not _uses_strategy_exits_only(
            config.strategy_name
        )
        # Trail mode: one trailing stop per position (see hypervector.nautilus.trail).
        self._trail: TrailState | None = None
        self._trail_order: Any = None  # resting reduce-only STOP_MARKET
        self._trail_open_exit_ns: int | None = None  # scheduled next-open exit
        self._trail_stopped = False  # the trail closed the position since last bar
        self._last_close: Any = None  # close Price of the latest bar
        # Run telemetry read by the runner after engine.run().
        self.intent_error: dict[str, Any] | None = None
        self.positions_opened = 0
        self.position_records: list[dict[str, Any]] = []
        self.trail_exits = 0

    def attach_precomputed(self, intents: PrecomputedIntents) -> None:
        """Read intents/exit distances by bar label instead of rebuilding windows."""
        self._precomputed = intents

    @property
    def signal_source(self) -> str:
        return "precomputed" if self._precomputed is not None else "windowed"

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
            f"instrument_id={self._instrument_id} conviction={self.config.conviction} "
            f"signals={self.signal_source}",
            color=LogColor.BLUE,
        )

    def on_bar(self, bar: Bar) -> None:
        """Append bar, read/recompute intent, enter/exit with one netting position."""
        self._bars_seen += 1
        self._last_close = bar.close
        if self._precomputed is None:
            self._append_bar(bar)
        # A trail stop that filled since the previous bar makes this VectorBT's
        # stop bar: its signals are not acted on.
        trail_stopped = self._trail_stopped
        self._trail_stopped = False
        if self._bars_seen < 2:
            return

        instrument_id = self._instrument_id or bar.bar_type.instrument_id
        is_flat = self._is_flat(instrument_id)
        position_side = None if is_flat else self._position_side(instrument_id)

        row: int | None = None
        frame: pd.DataFrame | None = None
        try:
            if self._precomputed is not None:
                row = self._precomputed.row(self._bar_label_ns(bar))
                intent = self._precomputed.intent(row)
            else:
                frame = _bars_to_ohlcv_df(self._bar_buffer)
                intent = last_bar_intent(
                    frame, self.config.strategy_name, dict(self.config.params)
                )
        except Exception as exc:
            self._fail_intent(bar, exc)

        action = _action_from_intent(
            intent, is_flat=is_flat, position_side=position_side
        )
        if trail_stopped:
            action = "hold"
        elif self._trail is not None:
            if is_flat and not self._pending_entry:
                self._clear_trail()
            elif not is_flat and action == "hold":
                self._ratchet_trail(bar, instrument_id)
        self.log.info(
            f"execution_mode={self.execution_mode} bar={self._bars_seen} "
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
            self._enter(bar, instrument_id, direction, row=row, frame=frame)

    # -- buffer / intent (public-ish for offline tests) --------------------

    def _append_bar(self, bar: Bar) -> None:
        _append_bar_record(
            self._bar_buffer,
            _bar_ohlcv_record(bar, label_offset_ns=self._label_offset_ns),
            max_lookback=self.max_lookback,
        )

    def _bar_label_ns(self, bar: Bar) -> int:
        return int(bar.ts_event) - self._label_offset_ns

    def _intent_from_buffer(self) -> SignalIntent:
        df = _bars_to_ohlcv_df(self._bar_buffer)
        return last_bar_intent(df, self.config.strategy_name, dict(self.config.params))

    def _fail_intent(self, bar: Bar, exc: Exception) -> None:
        """Record the first strategy error and abort the run (technical failure)."""
        label = pd.Timestamp(self._bar_label_ns(bar), unit="ns", tz="UTC")
        self.intent_error = {
            "bar": int(self._bars_seen),
            "bar_open": label.isoformat(),
            "signal_source": self.signal_source,
            "error": f"{type(exc).__name__}: {exc}",
        }
        self.log.error(
            f"execution_mode={self.execution_mode} intent failed "
            f"bar={self._bars_seen}: {type(exc).__name__}: {exc}"
        )
        raise Phase2IntentError(
            f"strategy {self.config.strategy_name!r} failed at bar "
            f"{self._bars_seen} ({label.isoformat()}): {type(exc).__name__}: {exc}",
            strategy=str(self.config.strategy_name),
            first_error=self.intent_error,
        ) from exc

    # -- trailing stop -------------------------------------------------------

    def _ratchet_trail(self, bar: Bar, instrument_id: InstrumentId) -> None:
        """Take this bar's extreme into the anchor, then move the resting stop."""
        assert self._trail is not None
        self._trail = trail_ratchet(
            self._trail,
            high=float(bar.high.as_double()),
            low=float(bar.low.as_double()),
        )
        self._sync_trail_order(instrument_id)

    def _sync_trail_order(self, instrument_id: InstrumentId) -> None:
        """Rest (or move) the reduce-only stop at the grid price of the level.

        A level already at/through the last close cannot rest (the venue
        rejects a stop in the market); the exit is scheduled for the next bar's
        open instead, where VectorBT fills it.
        """
        trail = self._trail
        if trail is None or self._trail_open_exit_ns is not None:
            return
        instrument = self.cache.instrument(instrument_id)
        if instrument is None or self._last_close is None:
            raise RuntimeError(
                f"trail stop needs instrument {instrument_id} and a last bar close"
            )
        value = grid_stop_price(
            trail.stop_level,
            increment=float(instrument.price_increment.as_double()),
            precision=int(instrument.price_precision),
            direction=trail.direction,
        )
        if value is None:
            return  # level below one tick: unreachable, VectorBT never fills it
        trigger = instrument.make_price(value)
        long = trail.direction == "long"
        if (trigger >= self._last_close) if long else (trigger <= self._last_close):
            self._schedule_trail_open_exit(trigger)
            return
        order = self._trail_order
        if order is None or order.is_closed:
            qty = self._open_quantity(instrument_id)
            if qty is None:
                return
            order = self.order_factory.stop_market(
                instrument_id=instrument_id,
                order_side=OrderSide.SELL if long else OrderSide.BUY,
                quantity=qty,
                trigger_price=trigger,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
                tags=["TRAIL"],
            )
            self._trail_order = order
            self.submit_order(order)
            self.log.info(
                f"execution_mode={self.execution_mode} trail stop placed "
                f"{trail.direction} trigger={trigger} level={trail.stop_level:.8g}",
                color=LogColor.GREEN,
            )
        elif order.trigger_price != trigger and not order.is_pending_cancel:
            self.modify_order(order, trigger_price=trigger)

    def _schedule_trail_open_exit(self, trigger: Any) -> None:
        now = int(self.clock.timestamp_ns())
        self._trail_open_exit_ns = now + 1
        self.clock.set_time_alert_ns(
            name=f"{self.id}-trail-open-exit-{now}",
            alert_time_ns=now + 1,
            callback=self._on_trail_open_exit,
        )
        self.log.info(
            f"execution_mode={self.execution_mode} trail level {trigger} is through "
            f"the close {self._last_close}: exit at the next bar open",
            color=LogColor.YELLOW,
        )

    def _on_trail_open_exit(self, event: Any) -> None:
        """Next-bar-open exit for a level that ratcheted through the close."""
        if self._trail is None or self._trail_open_exit_ns != int(event.ts_event):
            return  # position already closed by something else
        self._trail_open_exit_ns = None
        instrument_id = self._instrument_id
        if instrument_id is None or self._is_flat(instrument_id):
            self._clear_trail()
            return
        self.trail_exits += 1
        self._trail_stopped = True
        self.log.info(
            f"execution_mode={self.execution_mode} trail stop hit at the open",
            color=LogColor.YELLOW,
        )
        self._close_position(instrument_id)

    def _clear_trail(self) -> None:
        """Forget the trail and cancel its resting stop (never left behind)."""
        order = self._trail_order
        self._trail = None
        self._trail_order = None
        self._trail_open_exit_ns = None
        if order is not None and not order.is_closed and not order.is_pending_cancel:
            self.cancel_order(order)

    def _is_trail_order(self, event: Any) -> bool:
        order = self._trail_order
        return order is not None and event.client_order_id == order.client_order_id

    def _open_quantity(self, instrument_id: InstrumentId) -> Quantity | None:
        try:
            net = self.portfolio.net_position(instrument_id)
        except Exception:
            return None
        if net is None or float(net) == 0.0:
            return None
        return self._make_qty(instrument_id, abs(float(net)))

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
        *,
        row: int | None = None,
        frame: pd.DataFrame | None = None,
    ) -> None:
        if self._precomputed is not None and row is not None:
            stop_frac, tp_frac = self._precomputed.stop_tp(row)
        else:
            df = frame if frame is not None else _bars_to_ohlcv_df(self._bar_buffer)
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

        uses_bracket = not _uses_strategy_exits_only(self.config.strategy_name)
        uses_bracket &= mode in ("fixed_rr", "atr")
        uses_bracket &= tp_frac is not None and stop_frac > 0
        if uses_bracket:
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
        if self._trail_enabled:
            # Trail mode has no bracket: the trailing stop is anchored at this
            # bar's close with the entry-bar distance; its order rests once the
            # position exists (on_position_opened).
            self._clear_trail()
            self._trail = trail_start(
                direction, entry_close=price, sl_frac=float(stop_frac)
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
        self._clear_trail()
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

    def _make_qty(self, instrument_id: InstrumentId, qty_raw: float) -> Quantity | None:
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
        self._on_trail_order_refused(event)

    def on_order_rejected(self, event: Any) -> None:
        self._pending_entry = False
        self._on_trail_order_refused(event)

    def on_order_modify_rejected(self, event: Any) -> None:
        self._on_trail_order_refused(event)

    def _on_trail_order_refused(self, event: Any) -> None:
        """A refused trail stop/modify leaves the level in the market: exit at the open."""
        if self._trail is None or not self._is_trail_order(event):
            return
        self.log.warning(
            f"execution_mode={self.execution_mode} trail stop refused: "
            f"{getattr(event, 'reason', event)}"
        )
        if self._trail_order is not None and self._trail_order.is_closed:
            self._trail_order = None
        if self._trail_open_exit_ns is None:
            self._schedule_trail_open_exit(None)

    def on_order_filled(self, event: Any) -> None:
        if not self._is_trail_order(event) or not self._trail_order.is_closed:
            return
        self.trail_exits += 1
        self._trail_stopped = True
        self._trail_order = None
        self._trail = None
        self.log.info(
            f"execution_mode={self.execution_mode} trail stop filled "
            f"px={event.last_px}",
            color=LogColor.YELLOW,
        )

    def on_position_opened(self, event: Any) -> None:
        self._pending_entry = False
        self.positions_opened += 1
        if self._trail is not None:
            self._sync_trail_order(event.instrument_id)

    def on_position_closed(self, event: Any) -> None:
        self._pending_entry = False
        self._clear_trail()
        self.position_records.append(_position_record(event))

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


def _label_offset_ns(config: HypervectorStrategyConfig) -> int:
    """Bar interval (ns) when bars are close-stamped, else 0."""
    if str(getattr(config, "bar_timestamps", "close")) != "close":
        return 0
    try:
        return int(pd.Timedelta(BarType.from_str(config.bar_type).spec.timedelta).value)
    except Exception:
        return 0


def _position_record(event: Any) -> dict[str, Any]:
    """Serializable record of one closed position cycle (NETTING)."""

    def _f(value: Any) -> float:
        try:
            return (
                float(value.as_double())
                if hasattr(value, "as_double")
                else float(value)
            )
        except (TypeError, ValueError):
            return math.nan

    return {
        "side": str(getattr(event, "side", "")).split(".")[-1],
        "ts_opened": int(getattr(event, "ts_opened", 0) or 0),
        "ts_closed": int(getattr(event, "ts_closed", 0) or 0),
        "peak_qty": _f(getattr(event, "peak_qty", math.nan)),
        "avg_px_open": _f(getattr(event, "avg_px_open", math.nan)),
        "avg_px_close": _f(getattr(event, "avg_px_close", math.nan)),
        "realized_pnl": _f(getattr(event, "realized_pnl", math.nan)),
    }


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
