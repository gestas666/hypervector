"""Current official-funding sensitivity for the V58 research roster."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path
from typing import Protocol

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.transient_transport import transient_read_failure_reason
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.research.v58_continuous_risk_context import load_v58_risk_context

Record = Mapping[str, object]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_LOOKBACK_HOURS = 3
_MAXIMUM_EVENT_AGE_MS = 2 * 60 * 60 * 1_000
_SERIALIZED_BPS_DECIMALS = 12


class FundingReader(Protocol):
    """Unsigned official funding-history boundary."""

    def read(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> Sequence[Mapping[str, object]]:
        """Return official bounded funding rows for one exact symbol."""


@dataclass(frozen=True)
class CurrentFundingContext:
    """Execution-incapable current funding sensitivity evidence."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_current_funding_context(
    config_path: Path,
    stress_path: Path,
    *,
    observed_at: datetime,
    reader: FundingReader,
) -> CurrentFundingContext:
    """Compare current official funding with each frozen route assumption."""
    _require_aware(observed_at)
    risk = load_v58_risk_context(config_path, stress_path)
    config = load_multi_asset_live_config(config_path, mode="observe")
    if config.profile_id != _PROFILE_ID:
        raise ValueError("V58 current-funding config identity is invalid")
    stress = _read_stress(stress_path)
    start_ms, end_ms = _bounds(observed_at)
    funding = {
        symbol: _funding_row(
            reader.read(symbol, start_ms, end_ms), symbol, start_ms, end_ms
        )
        for symbol in config.symbols
    }
    routes = _route_rows(config, stress, funding)
    _require_unchanged(risk.evidence)
    return CurrentFundingContext(
        _payload(routes, start_ms, end_ms),
        {
            **risk.evidence,
            "official_funding": {
                "source": "official_hyperliquid_fundingHistory",
                "rows_by_symbol": funding,
            },
        },
    )


def load_live_v58_current_funding_context(
    config_path: Path,
    stress_path: Path,
    *,
    observed_at: datetime,
) -> CurrentFundingContext:
    """Read current mainnet funding without constructing an exchange client."""
    return load_v58_current_funding_context(
        config_path,
        stress_path,
        observed_at=observed_at,
        reader=_official_reader(),
    )


def load_resilient_live_v58_current_funding_context(
    config_path: Path,
    stress_path: Path,
    *,
    observed_at: datetime,
    loader: Callable[
        ..., CurrentFundingContext
    ] = load_live_v58_current_funding_context,
) -> CurrentFundingContext:
    """Keep funding transport failure explicit without staling local evidence."""
    _require_aware(observed_at)
    try:
        return loader(config_path, stress_path, observed_at=observed_at)
    except (RequestException, ClientError, ServerError) as exc:
        reason = transient_read_failure_reason(exc)
        if reason is None:
            raise
        return _unavailable_funding_context(observed_at, reason, type(exc).__name__)


def current_funding_context_payload(
    context: CurrentFundingContext,
) -> dict[str, object]:
    """Serialize funding sensitivity without forecasting or sizing authority."""
    return {
        **context.payload,
        "constant_rate_projection_is_forecast": False,
        "historical_distribution_claim": False,
        "funding_cost_ceiling_claim": False,
        "sizing_input": False,
        "automatic_strategy_change": False,
        "execution_authority": context.execution_authority,
    }


def _unavailable_funding_context(
    observed_at: datetime, reason: str, exception_type: str
) -> CurrentFundingContext:
    unavailable = {
        "status": "temporarily_unavailable",
        "observed_at_utc": observed_at.astimezone(UTC).isoformat(),
        "source": "official_hyperliquid_fundingHistory",
        "failure_reason": reason,
        "exception_type": exception_type,
    }
    return CurrentFundingContext(
        {
            **unavailable,
            "routes": None,
            "routes_exceeding_frozen_adverse": None,
            "maximum_current_to_frozen_adverse_ratio": None,
            "interpretation": "current_funding_unavailable_no_projection",
        },
        {"official_funding": unavailable},
    )


class _OfficialFundingReader:
    def __init__(self, core: object, xyz: object) -> None:
        self._core = core
        self._xyz = xyz

    def read(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> Sequence[Mapping[str, object]]:
        client = self._xyz if symbol.startswith("xyz:") else self._core
        method = getattr(client, "funding_history", None)
        if not callable(method):
            raise RuntimeError("official Hyperliquid client lacks funding_history")
        value = method(symbol, start_ms, end_ms)
        if not isinstance(value, list):
            raise ValueError(f"official funding history is invalid for {symbol}")
        return tuple(_mapping(row, f"{symbol} funding row") for row in value)


def _official_reader() -> FundingReader:
    from hyperliquid.info import Info  # type: ignore[import-untyped]
    from hyperliquid.utils import constants  # type: ignore[import-untyped]

    endpoint = str(constants.MAINNET_API_URL)
    if "testnet" in endpoint.lower():
        raise ValueError("V58 funding context refuses a testnet endpoint")
    options = {"base_url": endpoint, "skip_ws": True, "timeout": 10.0}
    return _OfficialFundingReader(Info(**options), Info(**options, perp_dexs=["xyz"]))


def _bounds(observed_at: datetime) -> tuple[int, int]:
    end_ms = int(observed_at.astimezone(UTC).timestamp() * 1_000)
    start = observed_at.astimezone(UTC) - timedelta(hours=_LOOKBACK_HOURS)
    return int(start.timestamp() * 1_000), end_ms


def _funding_row(
    value: Sequence[Mapping[str, object]],
    symbol: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    if not value:
        raise ValueError(f"official funding history is empty for {symbol}")
    rows = [_validated_funding(row, symbol, start_ms, end_ms) for row in value]
    times = [int(row["time_ms"]) for row in rows]
    if times != sorted(times) or len(times) != len(set(times)):
        raise ValueError(
            f"official funding history is unordered or duplicated for {symbol}"
        )
    latest = rows[-1]
    age = end_ms - int(latest["time_ms"])
    if age < 0 or age > _MAXIMUM_EVENT_AGE_MS:
        raise ValueError(f"latest official funding row is stale for {symbol}")
    return {**latest, "age_ms": age, "row_count": len(rows)}


def _validated_funding(
    row: Mapping[str, object], symbol: str, start_ms: int, end_ms: int
) -> dict[str, object]:
    if row.get("coin") != symbol:
        raise ValueError(f"official funding symbol differs for {symbol}")
    timestamp = _integer(row.get("time"), f"{symbol} funding time")
    if not start_ms <= timestamp <= end_ms:
        raise ValueError(f"official funding time lies outside bounds for {symbol}")
    return {
        "symbol": symbol,
        "time_ms": timestamp,
        "funding_rate": _number(row.get("fundingRate"), f"{symbol} funding rate"),
        "premium": _number(row.get("premium"), f"{symbol} premium"),
    }


def _route_rows(
    config: MultiAssetLiveConfig,
    stress: Record,
    funding: Mapping[str, Record],
) -> list[dict[str, object]]:
    slots = _stress_slots(stress)
    output = []
    for provider in config.providers:
        for symbol in provider.execution_symbols:
            route = _stress_route(slots, symbol, provider.strategy_id)
            output.append(_route_row(provider, symbol, route, funding[symbol]))
    if len(output) != 10:
        raise ValueError("V58 current-funding route coverage is incomplete")
    return output


def _route_row(
    provider: StrategyProviderConfig,
    symbol: str,
    stress: Record,
    funding: Record,
) -> dict[str, object]:
    sides = sorted(provider.executable_sides(symbol))
    execution = provider.execution_for(symbol)
    hold_seconds = execution.hard_maximum_hold_seconds or execution.maximum_hold_seconds
    hold_hours = hold_seconds / 3_600.0
    if not _equal(stress.get("maximum_hold_hours"), hold_hours):
        raise ValueError(f"{provider.strategy_id}|{symbol} funding hold differs")
    hourly_bps = float(funding["funding_rate"]) * 10_000.0
    costs = {side: _side_cost(side, hourly_bps, hold_hours) for side in sides}
    worst = max(costs.values())
    frozen = _frozen_funding(stress)
    return {
        "route": f"{provider.strategy_id}|{symbol}",
        "strategy_id": provider.strategy_id,
        "symbol": symbol,
        "sides": sides,
        "maximum_hold_hours": hold_hours,
        "latest_event_time_ms": funding["time_ms"],
        "latest_event_age_ms": funding["age_ms"],
        "latest_hourly_funding_rate": funding["funding_rate"],
        "latest_hourly_funding_rate_bps": hourly_bps,
        "latest_premium": funding["premium"],
        "constant_rate_hold_cost_bps_by_side": costs,
        "current_worst_side_cost_bps": worst,
        "frozen_adverse_funding_bps": frozen,
        "current_to_frozen_adverse_ratio": worst / frozen,
        "current_exceeds_frozen_adverse": worst > frozen,
    }


def _stress_slots(stress: Record) -> Record:
    scenarios = stress.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 1:
        raise ValueError("V58 current-funding stress scenario is invalid")
    scenario = _mapping(scenarios[0], "V58 funding stress scenario")
    return _mapping(scenario.get("asset_slots"), "V58 funding stress slots")


def _stress_route(slots: Record, symbol: str, strategy_id: str) -> Record:
    slot = _mapping(slots.get(symbol), f"{symbol} funding stress slot")
    routes = slot.get("routes")
    if not isinstance(routes, list):
        raise ValueError(f"{symbol} funding stress routes are invalid")
    matches = [
        _mapping(row, f"{symbol} funding stress route")
        for row in routes
        if isinstance(row, Mapping) and row.get("strategy_id") == strategy_id
    ]
    if len(matches) != 1:
        raise ValueError(f"{strategy_id}|{symbol} funding stress identity is invalid")
    return matches[0]


def _frozen_funding(stress: Record) -> float:
    friction = _mapping(stress.get("friction_components_bps"), "route friction")
    value = _number(friction.get("adverse_maximum_hold_funding"), "frozen funding")
    if value <= 0.0:
        raise ValueError("frozen adverse funding must be positive")
    return value


def _side_cost(side: str, hourly_bps: float, hours: float) -> float:
    if side == "long":
        return round(hourly_bps * hours, _SERIALIZED_BPS_DECIMALS)
    if side == "short":
        return round(-hourly_bps * hours, _SERIALIZED_BPS_DECIMALS)
    raise ValueError("V58 funding route side must be long or short")


def _payload(routes: Sequence[Record], start_ms: int, end_ms: int) -> dict[str, object]:
    ratios = [float(row["current_to_frozen_adverse_ratio"]) for row in routes]
    return {
        "status": "available",
        "requested_start_ms": start_ms,
        "requested_end_ms": end_ms,
        "source": "official_hyperliquid_fundingHistory",
        "routes": [dict(row) for row in routes],
        "routes_exceeding_frozen_adverse": sum(
            row["current_exceeds_frozen_adverse"] is True for row in routes
        ),
        "maximum_current_to_frozen_adverse_ratio": max(ratios),
        "interpretation": "latest_hourly_rate_held_constant_for_configured_horizon",
    }


def _read_stress(path: Path) -> Record:
    return _mapping(json.loads(path.read_bytes()), "V58 funding stress artifact")


def _require_unchanged(evidence: Record) -> None:
    for key in ("config", "stress"):
        row = _mapping(evidence.get(key), f"V58 funding {key} evidence")
        path = Path(_text(row.get("path"), f"V58 funding {key} path"))
        current = file_evidence(path)
        expected = {"bytes": row.get("bytes"), "sha256": row.get("sha256")}
        if current != expected:
            raise ValueError(f"V58 funding {key} changed during evaluation")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("V58 current-funding observation time must be timezone-aware")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if isinstance(value, bool) or not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _equal(actual: object, expected: float) -> bool:
    return isinstance(actual, (int, float)) and math.isclose(
        float(actual), expected, rel_tol=1e-12, abs_tol=1e-12
    )
