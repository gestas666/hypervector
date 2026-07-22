"""Offline paper session: loadout → bar walk → intent → ExplicitFillEngine.

No live network, no Nautilus node, no venue orders. Alpha math matches the
actor via :func:`last_bar_intent` on an expanding OHLCV buffer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from hypervector.infra import ensure_data_layout
from hypervector.nautilus.actor import (
    DEFAULT_MAX_LOOKBACK,
    _action_from_intent,
    _append_bar_record,
    _stop_tp_fracs,
)
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.signals import last_bar_intent
from hypervector.nautilus.sizing import position_size_frac
from hypervector.paper.costs import CostProvider
from hypervector.paper.fills import ExplicitFillEngine
from hypervector.paper.ledger import DECISIONS_FILENAME, append_paper_decision
from hypervector.strategies import register_all_strategies

_OHLCV_REQUIRED = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class PaperSessionResult:
    """Outcome of an offline paper session walk."""

    run_id: str
    decisions_path: Path
    bars_processed: int
    fills_count: int
    export_dir: Path


def run_paper_session_offline(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    ohlcv: pd.DataFrame,
    conviction: float = 0.5,
    fee_tier: int = 0,
    max_bars: int | None = None,
) -> PaperSessionResult:
    """Walk injected OHLCV bars through loadout alpha into paper fills.

    Warm-up matches :class:`HypervectorStrategy`: no trade when buffer length
    is less than 2. No live funding poll, no venue orders.
    """
    register_all_strategies()
    export_path = Path(export_dir)
    if not export_path.is_dir():
        raise FileNotFoundError(f"export_dir not found: {export_path}")

    loadout = load_strategy_loadout(export_path, strict=True)
    frame = _prepare_ohlcv(ohlcv, max_bars=max_bars)
    root = Path(data_root)
    paths = ensure_data_layout(root)
    decisions_path = paths.paper_decisions / DECISIONS_FILENAME

    run_id = uuid.uuid4().hex[:12]
    export_id = loadout.run_id or export_path.name
    cost_provider = _cost_provider_from_loadout(loadout, fee_tier=fee_tier)
    engine = ExplicitFillEngine(
        root,
        cost_provider=cost_provider,
        run_id=run_id,
        export_id=str(export_id),
        strategy_name=loadout.strategy_name,
        symbol=loadout.symbol,
        timeframe=loadout.timeframe,
        conviction=float(conviction),
        sandbox_enabled=False,
    )

    equity = float(loadout.init_cash) if loadout.init_cash is not None else 10_000.0
    exits = _exits_dict(loadout)
    buffer_rows: list[dict[str, Any]] = []
    fills_count = 0
    bars_processed = 0

    for _, row in frame.iterrows():
        record = _row_to_buffer_record(row)
        _append_bar_record(
            buffer_rows, record, max_lookback=DEFAULT_MAX_LOOKBACK
        )
        bars_processed += 1
        if len(buffer_rows) < 2:
            continue

        df = _buffer_to_df(buffer_rows)
        try:
            intent = last_bar_intent(
                df, loadout.strategy_name, dict(loadout.params)
            )
        except Exception:
            # Match actor: skip bar on signal failure rather than abort session.
            continue

        pos = engine.position
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
            continue

        mark_px = float(record["close"])
        feed_ts = _feed_ts(record)
        intent_payload = {
            "direction": intent.direction,
            "enter": intent.enter,
            "exit": intent.exit,
            "bar_index": intent.bar_index,
        }

        if action == "close":
            qty = abs(float(pos.qty))
            if qty <= 0:
                continue
            side = "sell" if pos.qty > 0 else "buy"
            engine.apply_market_fill(
                feed_ts=feed_ts,
                action="close",
                side=side,
                qty=qty,
                mark_px=mark_px,
                intent=intent_payload,
            )
            fills_count += 1
            continue

        if action in ("enter_long", "enter_short"):
            qty = _entry_qty(
                df=df,
                loadout=loadout,
                exits=exits,
                equity=equity,
                conviction=float(conviction),
                mark_px=mark_px,
            )
            if qty is None or qty <= 0:
                continue
            side = "buy" if action == "enter_long" else "sell"
            engine.apply_market_fill(
                feed_ts=feed_ts,
                action=action,
                side=side,
                qty=qty,
                mark_px=mark_px,
                intent=intent_payload,
            )
            fills_count += 1

    # Ensure decisions path exists even if no fills (session identity row).
    if not decisions_path.is_file():
        append_paper_decision(
            root,
            {
                "feed_ts": "session_start",
                "run_id": run_id,
                "export_id": str(export_id),
                "strategy_name": loadout.strategy_name,
                "symbol": loadout.symbol,
                "timeframe": loadout.timeframe,
                "action": "session_start",
                "conviction": float(conviction),
                "bars_processed": bars_processed,
            },
        )

    return PaperSessionResult(
        run_id=run_id,
        decisions_path=decisions_path,
        bars_processed=bars_processed,
        fills_count=fills_count,
        export_dir=loadout.export_dir,
    )


def _prepare_ohlcv(
    ohlcv: pd.DataFrame, *, max_bars: int | None
) -> pd.DataFrame:
    if ohlcv is None or not isinstance(ohlcv, pd.DataFrame) or ohlcv.empty:
        raise ValueError("OHLCV must be a non-empty DataFrame")
    frame = ohlcv.copy()
    if "timestamp" not in frame.columns and frame.index.name == "timestamp":
        frame = frame.reset_index()
    missing = [c for c in _OHLCV_REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")
    if max_bars is not None:
        frame = frame.iloc[: int(max_bars)]
    return frame.reset_index(drop=True)


def _row_to_buffer_record(row: pd.Series) -> dict[str, Any]:
    ts = row["timestamp"] if "timestamp" in row.index else None
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        ts = pd.Timestamp.utcnow()
    else:
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    return {
        "timestamp": ts,
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }


def _buffer_to_df(buffer: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(buffer)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    return df.loc[:, list(_OHLCV_REQUIRED)].astype(float)


def _feed_ts(record: dict[str, Any]) -> str:
    ts = record.get("timestamp")
    if ts is None:
        return "unknown"
    if isinstance(ts, pd.Timestamp):
        return ts.isoformat()
    return str(ts)


def _exits_dict(loadout: StrategyLoadout) -> dict[str, Any]:
    raw = dict(loadout.exits or {})
    if "mode" not in raw or raw.get("mode") is None:
        if loadout.exit_mode is not None:
            raw["mode"] = loadout.exit_mode
    return raw


def _cost_provider_from_loadout(
    loadout: StrategyLoadout, *, fee_tier: int
) -> CostProvider:
    costs = loadout.costs or {}
    slippage_bps = float(costs.get("slippage_bps", 2.0))
    funding_hourly = 0.0
    if "funding_rate_hourly" in costs:
        funding_hourly = float(costs["funding_rate_hourly"])
    elif "funding_rate_8h" in costs:
        funding_hourly = float(costs["funding_rate_8h"]) / 8.0
    return CostProvider(
        fee_tier=int(fee_tier),
        slippage_bps=slippage_bps,
        funding_rate_hourly=funding_hourly,
    )


def _entry_qty(
    *,
    df: pd.DataFrame,
    loadout: StrategyLoadout,
    exits: dict[str, Any],
    equity: float,
    conviction: float,
    mark_px: float,
) -> float | None:
    if mark_px <= 0 or equity <= 0:
        return None
    try:
        stop_frac, _tp = _stop_tp_fracs(df, exits)
    except Exception:
        stop_frac = 0.01
    size_frac = position_size_frac(
        equity,
        stop_frac=max(float(stop_frac), 1e-6),
        loadout=loadout,
        conviction=conviction,
    )
    if size_frac <= 0:
        return None
    notional = equity * float(size_frac)
    qty = notional / mark_px
    return qty if qty > 0 else None
