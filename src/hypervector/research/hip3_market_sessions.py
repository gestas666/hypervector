"""Scheduled external-reference session labels for selected HIP-3 markets.

These labels describe published schedules. They do not prove which oracle mode
was active at a timestamp and must not be used as an execution gate.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

SCHEDULED_EXTERNAL_REFERENCE = "scheduled_external_reference"
SCHEDULED_INTERNAL_OR_CLOSED = "scheduled_internal_or_closed"

_SEOUL = ZoneInfo("Asia/Seoul")
_NEW_YORK = ZoneInfo("America/New_York")
_US_EQUITY_SYMBOLS = frozenset({"xyz:MU", "xyz:SKHY"})
_KOREA_REFERENCE_WINDOWS = (
    (time(8, 0), time(8, 50)),
    (time(9, 0), time(15, 30)),
    (time(15, 40), time(20, 0)),
)


def oracle_session_contract(symbol: str) -> dict[str, object]:
    """Return the report-only scheduled-reference contract for a symbol."""
    common: dict[str, object] = {
        "symbol": symbol,
        "execution_gate": False,
        "holiday_calendar_applied": False,
        "classification_scope": "published_schedule_not_observed_oracle_mode",
    }
    if symbol == "xyz:SKHX":
        return {
            **common,
            "status": "classified",
            "schedule_id": "korea_external_reference_v1",
            "source_url": "https://docs.trade.xyz/asset-directory/korea",
            "timezone": "Asia/Seoul",
            "weekday_windows": ["08:00-08:50", "09:00-15:30", "15:40-20:00"],
        }
    if symbol in _US_EQUITY_SYMBOLS:
        return {
            **common,
            "status": "classified",
            "schedule_id": "us_equity_24x5_reference_v1",
            "source_url": "https://docs.trade.xyz/asset-directory/stocks",
            "timezone": "America/New_York",
            "weekly_window": "Sunday 20:00-Friday 20:00",
        }
    return {**common, "status": "unclassified", "schedule_id": None}


def scheduled_oracle_session(symbol: str, timestamp: datetime) -> str:
    """Classify a timestamp under the published reference-market schedule."""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("HIP-3 session timestamp must be timezone-aware")
    if symbol == "xyz:SKHX":
        external = _inside_korea_reference_window(timestamp)
    elif symbol in _US_EQUITY_SYMBOLS:
        external = _inside_us_equity_reference_window(timestamp)
    else:
        raise ValueError(f"unsupported HIP-3 session contract: {symbol}")
    if external:
        return SCHEDULED_EXTERNAL_REFERENCE
    return SCHEDULED_INTERNAL_OR_CLOSED


def _inside_korea_reference_window(timestamp: datetime) -> bool:
    local = timestamp.astimezone(_SEOUL)
    if local.weekday() >= 5:
        return False
    local_time = local.timetz().replace(tzinfo=None)
    return any(start <= local_time < end for start, end in _KOREA_REFERENCE_WINDOWS)


def _inside_us_equity_reference_window(timestamp: datetime) -> bool:
    local = timestamp.astimezone(_NEW_YORK)
    weekday = local.weekday()
    local_time = local.timetz().replace(tzinfo=None)
    if weekday in {0, 1, 2, 3}:
        return True
    if weekday == 4:
        return local_time < time(20, 0)
    if weekday == 6:
        return local_time >= time(20, 0)
    return False
