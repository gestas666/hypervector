"""Read backend-authoritative BTC equity for shared shadow accounting."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import Mapping, cast

from hypervector.research.sol_range_onset_shadow_models import SharedCapitalSnapshot


class BtcShadowCapitalReader:
    """Incrementally project BTC backend equity and reserved isolated margin."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._offset = 0
        self._run_id: str | None = None
        self._margin_fraction: float | None = None
        self._leverage: float | None = None
        self._observed_time_ms: int | None = None
        self._equity_usd: float | None = None
        self._position_qty = 0.0
        self._position_avg_px = 0.0
        self._maker_pending = False

    def read_latest(self) -> SharedCapitalSnapshot | None:
        """Consume appended backend rows and return the newest capital view."""
        if not self._path.exists():
            return None
        if self._path.stat().st_size < self._offset:
            self._reset()
        with self._path.open("rb") as handle:
            handle.seek(self._offset)
            for line_number, raw in enumerate(handle, start=1):
                self._ingest(_json_row(raw, line_number))
            self._offset = handle.tell()
        return self._snapshot()

    def _ingest(self, row: Mapping[str, object]) -> None:
        action = row.get("action")
        if action == "session_start":
            self._start_session(row)
            return
        if row.get("run_id") != self._run_id:
            return
        if row.get("execution_mode") != "shadow":
            raise ValueError("BTC shared-capital rows must remain shadow-only")
        if action == "regime_observation":
            self._ingest_regime(row)
        elif action == "entry_execution_observation":
            self._maker_pending = row.get("maker_entry_state") == "pending"

    def _start_session(self, row: Mapping[str, object]) -> None:
        if row.get("execution_mode") != "shadow":
            raise ValueError("BTC shared-capital session must be shadow-only")
        run_id = row.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("BTC session_start requires a run_id")
        risk = _mapping(row.get("risk"), "risk")
        strategy = _mapping(row.get("strategy_params"), "strategy_params")
        self._run_id = run_id
        self._margin_fraction = _positive_number(risk, "margin_fraction")
        self._leverage = _positive_number(strategy, "leverage")
        self._observed_time_ms = None
        self._equity_usd = None
        self._position_qty = 0.0
        self._position_avg_px = 0.0
        self._maker_pending = False

    def _ingest_regime(self, row: Mapping[str, object]) -> None:
        self._observed_time_ms = _timestamp_ms(row.get("feed_ts"))
        self._equity_usd = _positive_number(row, "equity")
        self._position_qty = _finite_number(row, "position_qty")
        self._position_avg_px = _nonnegative_number(row, "position_avg_px")
        if self._position_qty != 0.0 and self._position_avg_px <= 0.0:
            raise ValueError("open BTC position requires a positive average price")

    def _snapshot(self) -> SharedCapitalSnapshot | None:
        values = (
            self._run_id,
            self._margin_fraction,
            self._leverage,
            self._observed_time_ms,
            self._equity_usd,
        )
        if any(value is None for value in values):
            return None
        run_id, margin_fraction, leverage, observed, equity = values
        if not isinstance(run_id, str):
            raise RuntimeError("validated BTC run_id changed type")
        reserved = self._reserved_margin(
            float(equity), float(margin_fraction), float(leverage)
        )
        return SharedCapitalSnapshot(int(observed), float(equity), reserved, run_id)

    def _reserved_margin(
        self,
        equity: float,
        margin_fraction: float,
        leverage: float,
    ) -> float:
        if self._position_qty != 0.0:
            return abs(self._position_qty) * self._position_avg_px / leverage
        return equity * margin_fraction if self._maker_pending else 0.0

    def _reset(self) -> None:
        self._offset = 0
        self._run_id = None
        self._margin_fraction = None
        self._leverage = None
        self._observed_time_ms = None
        self._equity_usd = None
        self._position_qty = 0.0
        self._position_avg_px = 0.0
        self._maker_pending = False


def _json_row(raw: bytes, line_number: int) -> Mapping[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"invalid BTC shadow JSON at appended line {line_number}"
        ) from exc
    return _mapping(value, f"line {line_number}")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"BTC shared-capital {label} must be an object")
    return cast(dict[str, object], value)


def _timestamp_ms(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("BTC feed_ts must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("BTC feed_ts must be timezone-aware")
    return int(parsed.astimezone(UTC).timestamp() * 1_000)


def _finite_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"BTC {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"BTC {key} must be finite")
    return number


def _positive_number(values: Mapping[str, object], key: str) -> float:
    number = _finite_number(values, key)
    if number <= 0.0:
        raise ValueError(f"BTC {key} must be positive")
    return number


def _nonnegative_number(values: Mapping[str, object], key: str) -> float:
    number = _finite_number(values, key)
    if number < 0.0:
        raise ValueError(f"BTC {key} must be non-negative")
    return number
