"""Live session: same alpha path as paper; live ledger + optional place (F3).

Warm-up history is seeded into the rolling buffer without evaluating intents
(:meth:`LiveSession.seed_history`), bars without execution authority are only
recorded (:meth:`LiveSession.observe_bar`), and arming discards any synthetic
exposure so the armed phase always starts from the venue-reconciled flat state.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector.infra import ensure_data_layout
from hypervector.live.engine import LiveFillEngine
from hypervector.live.exec_client import LiveExecClient
from hypervector.live.ledger import DECISIONS_FILENAME, append_live_decision
from hypervector.nautilus.actor import (
    DEFAULT_MAX_LOOKBACK,
    _action_from_intent,
    _append_bar_record,
)
from hypervector.nautilus.signals import last_bar_intent
from hypervector.paper.conviction import FixedConvictionProvider
from hypervector.paper.live_node import timeframe_delta
from hypervector.paper.order_intent import NETWORK_MAINNET
from hypervector.paper.session import (
    _buffer_to_df,
    _cost_provider_from_loadout,
    _entry_qty,
    _exits_dict,
    _feed_ts,
    _prepare_ohlcv,
    _row_to_buffer_record,
)
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.strategies import register_all_strategies

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveSessionResult:
    run_id: str
    decisions_path: Path
    bars_processed: int
    fills_count: int
    places_count: int
    export_dir: Path


class LiveSession:
    """Incremental live bar processor (warm-up synthetic → live place phase)."""

    def __init__(
        self,
        *,
        export_dir: Path | str,
        data_root: Path | str,
        client: LiveExecClient,
        max_notional_usd: float = 50.0,
        conviction: float = 0.5,
        fee_tier: int = 0,
        run_id: str | None = None,
        funding_rate_hourly: float | None = None,
        place_enabled: bool = False,
    ) -> None:
        register_all_strategies()
        export_path = Path(export_dir)
        if not export_path.is_dir():
            raise FileNotFoundError(f"export_dir not found: {export_path}")

        self.loadout = load_strategy_loadout(export_path, strict=True)
        # Resolve the bar duration once; an unsupported timeframe fails here,
        # before any ledger write, warm-up or arming.
        self.bar_interval = timeframe_delta(self.loadout.timeframe)
        self._bar_hours = self.bar_interval.total_seconds() / 3600.0
        self.root = Path(data_root)
        self.paths = ensure_data_layout(self.root)
        self.decisions_path = self.paths.live_decisions / DECISIONS_FILENAME
        self.conviction = float(conviction)
        self.conviction_provider = FixedConvictionProvider(self.conviction)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.export_id = self.loadout.run_id or export_path.name
        self.cost_provider = _cost_provider_from_loadout(
            self.loadout,
            fee_tier=fee_tier,
            funding_rate_hourly=funding_rate_hourly,
        )
        self.engine = LiveFillEngine(
            self.root,
            cost_provider=self.cost_provider,
            run_id=self.run_id,
            export_id=str(self.export_id),
            strategy_name=self.loadout.strategy_name,
            symbol=self.loadout.symbol,
            timeframe=self.loadout.timeframe,
            conviction=self.conviction,
            client=client,
            place_enabled=bool(place_enabled),
            max_notional_usd=float(max_notional_usd),
        )
        self.equity = (
            float(self.loadout.init_cash)
            if self.loadout.init_cash is not None
            else 10_000.0
        )
        self.exits = _exits_dict(self.loadout)
        self.buffer_rows: list[dict[str, Any]] = []
        self.fills_count = 0
        self.places_count = 0
        self.bars_processed = 0
        self._last_ts: pd.Timestamp | None = None

    def enable_live_place(self) -> None:
        """Arm venue place after warm-up (live phase only).

        Synthetic warm-up exposure never reaches the armed phase: a strategy
        exit on the first live bar would otherwise send a real order that opens
        the opposite position while the engine believes it is flat.
        """
        if not self.engine.place_enabled:
            discarded = self.engine.discard_synthetic_position()
            if discarded.qty != 0.0:
                logger.warning(
                    "live arm discarded synthetic warm-up position qty=%s avg_px=%s",
                    discarded.qty,
                    discarded.avg_px,
                )
                append_live_decision(
                    self.root,
                    {
                        "feed_ts": (
                            self._last_ts.isoformat()
                            if self._last_ts is not None
                            else "warmup_end"
                        ),
                        "run_id": self.run_id,
                        "export_id": str(self.export_id),
                        "strategy_name": self.loadout.strategy_name,
                        "symbol": self.loadout.symbol,
                        "timeframe": self.loadout.timeframe,
                        "action": "warmup_position_discarded",
                        "discarded_qty": discarded.qty,
                        "discarded_avg_px": discarded.avg_px,
                        "position_qty": 0.0,
                        "execution_mode": "live",
                        "submitted": False,
                        "place_attempted": False,
                        "live_phase": False,
                        "network": NETWORK_MAINNET,
                    },
                )
        self.engine.place_enabled = True

    @property
    def last_timestamp(self) -> pd.Timestamp | None:
        return self._last_ts

    def on_bar(self, row: pd.Series | dict[str, Any]) -> str | None:
        """Process one bar with execution authority (intent + possible order)."""
        record = self._append_record(row)
        fill_action: str | None = None
        if len(self.buffer_rows) >= 2:
            fill_action = self._process_intent(record)
        self._accrue_funding(record)
        return fill_action

    def observe_bar(self, row: pd.Series | dict[str, Any]) -> None:
        """Record one bar without execution authority (catch-up or stale bar).

        The bar extends the indicator history and accrues ledger funding on any
        open position, but no intent is evaluated and nothing is placed.
        """
        record = self._append_record(row)
        self._accrue_funding(record)

    def seed_history(self, ohlcv: pd.DataFrame) -> int:
        """Seed the rolling buffer from warm-up history in O(n); return bar count.

        Equivalent to the buffer :meth:`process_frame` leaves behind, without the
        per-bar DataFrame rebuild and strategy evaluation, and without synthetic
        fills, funding rows or position changes.
        """
        frame = _prepare_ohlcv(ohlcv, max_bars=None)
        if "timestamp" in frame.columns:
            frame = frame.sort_values("timestamp", kind="mergesort")
        tail = frame.iloc[-DEFAULT_MAX_LOOKBACK:]
        for _, row in tail.iterrows():
            _append_bar_record(
                self.buffer_rows,
                _row_to_buffer_record(row),
                max_lookback=DEFAULT_MAX_LOOKBACK,
            )
        self.bars_processed += len(frame)
        ts = self.buffer_rows[-1].get("timestamp") if self.buffer_rows else None
        if isinstance(ts, pd.Timestamp):
            self._last_ts = ts
        return len(frame)

    def _append_record(self, row: pd.Series | dict[str, Any]) -> dict[str, Any]:
        record = _row_to_buffer_record(
            row if isinstance(row, pd.Series) else pd.Series(row)
        )
        _append_bar_record(self.buffer_rows, record, max_lookback=DEFAULT_MAX_LOOKBACK)
        self.bars_processed += 1
        ts = record.get("timestamp")
        if isinstance(ts, pd.Timestamp):
            self._last_ts = ts
        return record

    def _accrue_funding(self, record: dict[str, Any]) -> None:
        if self.engine.position.qty != 0.0:
            self.engine.apply_funding(
                feed_ts=_feed_ts(record),
                oracle_px=float(record["close"]),
                hours=self._bar_hours,
            )

    def _process_intent(self, record: dict[str, Any]) -> str | None:
        df = _buffer_to_df(self.buffer_rows)
        try:
            intent = last_bar_intent(
                df, self.loadout.strategy_name, dict(self.loadout.params)
            )
        except Exception:
            return None

        pos = self.engine.position
        is_flat = pos.qty == 0.0
        if is_flat:
            position_side: str | None = None
        elif pos.qty > 0:
            position_side = "long"
        else:
            position_side = "short"

        action = _action_from_intent(
            intent, is_flat=is_flat, position_side=position_side
        )
        if action == "hold":
            return None

        mark_px = float(record["close"])
        feed_ts = _feed_ts(record)
        intent_payload = {
            "direction": intent.direction,
            "enter": intent.enter,
            "exit": intent.exit,
            "bar_index": intent.bar_index,
        }
        cv = self.conviction_provider.resolve(bars=df)

        if action == "close":
            qty = abs(float(pos.qty))
            if qty <= 0:
                return None
            side = "sell" if pos.qty > 0 else "buy"
            rec = self.engine.apply_market_fill(
                feed_ts=feed_ts,
                action="close",
                side=side,
                qty=qty,
                mark_px=mark_px,
                intent=intent_payload,
                conviction=cv.conviction,
                conviction_source=cv.source,
                reduce_only=True,
            )
            if rec.get("place_attempted"):
                self.places_count += 1
            if rec.get("submitted") or not rec.get("place_attempted"):
                # Count warm synthetic fills; live only when submitted or warm.
                if not rec.get("place_attempted") or rec.get("submitted"):
                    self.fills_count += 1
                    return action
            return None

        if action in ("enter_long", "enter_short"):
            qty = _entry_qty(
                df=df,
                loadout=self.loadout,
                exits=self.exits,
                equity=self.equity,
                conviction=cv.conviction,
                mark_px=mark_px,
            )
            if qty is None or qty <= 0:
                return None
            side = "buy" if action == "enter_long" else "sell"
            rec = self.engine.apply_market_fill(
                feed_ts=feed_ts,
                action=action,
                side=side,
                qty=qty,
                mark_px=mark_px,
                intent=intent_payload,
                conviction=cv.conviction,
                conviction_source=cv.source,
            )
            if rec.get("place_attempted"):
                self.places_count += 1
            if not rec.get("place_attempted") or rec.get("submitted"):
                self.fills_count += 1
                return action
            return None

        return None

    def process_frame(self, ohlcv: pd.DataFrame, *, max_bars: int | None = None) -> int:
        """Replay bars through :meth:`on_bar` (synthetic when unarmed).

        Kept for API compatibility; the live daemon warms up with
        :meth:`seed_history`, which is linear and leaves the engine flat.
        """
        frame = _prepare_ohlcv(ohlcv, max_bars=max_bars)
        n = 0
        for _, row in frame.iterrows():
            self.on_bar(row)
            n += 1
        return n

    def ensure_session_identity(self) -> None:
        if not self.decisions_path.is_file():
            append_live_decision(
                self.root,
                {
                    "feed_ts": "session_start",
                    "run_id": self.run_id,
                    "export_id": str(self.export_id),
                    "strategy_name": self.loadout.strategy_name,
                    "symbol": self.loadout.symbol,
                    "timeframe": self.loadout.timeframe,
                    "action": "session_start",
                    "conviction": self.conviction,
                    "bars_processed": self.bars_processed,
                    "execution_mode": "live",
                    "submitted": False,
                    "place_attempted": False,
                    "live_phase": False,
                    "network": NETWORK_MAINNET,
                },
            )

    def result(self) -> LiveSessionResult:
        self.ensure_session_identity()
        return LiveSessionResult(
            run_id=self.run_id,
            decisions_path=self.decisions_path,
            bars_processed=self.bars_processed,
            fills_count=self.fills_count,
            places_count=self.places_count,
            export_dir=self.loadout.export_dir,
        )
