"""Report-only historical funding stress for the active V58 ETH route."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
from math import isfinite
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence

_HOLD_HOURS = 12
_SOURCE = "hl_funding_history"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"

Record = Mapping[str, object]


def load_v58_eth_historical_funding_stress(
    *,
    funding_path: Path,
    manifest_path: Path,
    stress_path: Path,
    current_context_path: Path,
) -> dict[str, object]:
    """Load exact local evidence and build one durable funding diagnostic."""
    inputs = _input_evidence(funding_path, manifest_path, stress_path)
    manifest = _load_json(manifest_path, "ETH funding manifest")
    funding = pd.read_parquet(funding_path)
    _require_manifest(manifest, funding_path, funding)
    stress = _load_json(stress_path, "V58 stress artifact")
    current = _load_json(current_context_path, "V58 current funding context")
    frozen, notional = _stress_contract(stress)
    current_projection = _current_projection(current)
    report = build_v58_eth_historical_funding_stress(
        funding,
        frozen_projection_bps=frozen,
        current_projection_bps=current_projection,
        notional_usd=notional,
    )
    _require_unchanged(inputs)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["route_identity"] = {
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "notional_usd": notional,
        "hold_hours": _HOLD_HOURS,
    }
    report["source_evidence"] = {
        **inputs,
        "current_context": _path_evidence(current_context_path),
    }
    return report


def build_v58_eth_historical_funding_stress(
    funding: pd.DataFrame,
    *,
    frozen_projection_bps: float,
    current_projection_bps: float,
    notional_usd: float,
) -> dict[str, object]:
    """Compare point-in-time ETH projections with rolling historical costs."""
    rates = _validated_rates(funding)
    rolling = rates.rolling(_HOLD_HOURS, min_periods=_HOLD_HOURS).sum().dropna()
    rolling_bps = rolling * 10_000.0
    long = _distribution(rolling_bps)
    short = _distribution(-rolling_bps)
    frozen = _nonnegative(frozen_projection_bps, "frozen projection")
    current = _nonnegative(current_projection_bps, "current projection")
    notional = _positive(notional_usd, "notional_usd")
    return {
        "schema_version": 1,
        "mode": "v58_eth_historical_funding_stress_v1",
        "symbol": "ETH",
        "hold_hours": _HOLD_HOURS,
        "hourly_event_count": len(rates),
        "rolling_window_count": len(rolling_bps),
        "rolling_12h_cost_bps": {"long": long, "short": short},
        "comparisons": _comparisons(rolling_bps, frozen, current, notional, long),
        "disposition": _disposition(long["p99"], frozen),
        "limitations": _limitations(),
        "historical_distribution_claim": True,
        "sizing_input": False,
        "live_change_supported": False,
        "execution_authority": "none",
    }


def _validated_rates(funding: pd.DataFrame) -> pd.Series:
    required = {"timestamp", "funding_rate", "source", "event_ts_ms"}
    missing = sorted(required.difference(funding.columns))
    if missing:
        raise ValueError(f"ETH funding evidence is missing columns: {missing}")
    if len(funding) < _HOLD_HOURS:
        raise ValueError("ETH funding evidence has fewer than twelve hourly events")
    times = pd.to_datetime(funding["timestamp"], errors="coerce", utc=True)
    deltas = times.diff().iloc[1:]
    if times.isna().any() or not deltas.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("ETH funding evidence must be ordered contiguous UTC hours")
    events = pd.to_numeric(funding["event_ts_ms"], errors="coerce")
    opens = pd.Series(
        [int(timestamp.timestamp() * 1_000) for timestamp in times],
        index=funding.index,
    )
    valid_events = events.notna() & events.ge(opens) & events.lt(opens + 3_600_000)
    if not valid_events.all():
        raise ValueError("ETH funding event timestamps must match declared hours")
    if not funding["source"].astype(str).eq(_SOURCE).all():
        raise ValueError("ETH funding evidence source is invalid")
    rates = pd.to_numeric(funding["funding_rate"], errors="coerce")
    if rates.isna().any() or not rates.map(isfinite).all():
        raise ValueError("ETH funding rates must be finite")
    return rates.astype(float)


def _require_manifest(
    manifest: Record,
    funding_path: Path,
    funding: pd.DataFrame,
) -> None:
    expected = {
        "schema_version": 1,
        "symbol": "ETH",
        "source": _SOURCE,
        "venue": "hyperliquid",
        "complete": True,
        "missing_hour_count": 0,
    }
    if any(manifest.get(field) != value for field, value in expected.items()):
        raise ValueError("ETH funding manifest contract is invalid")
    count = len(funding)
    if manifest.get("expected_hour_count") != count:
        raise ValueError("ETH funding manifest expected count is inconsistent")
    if manifest.get("observed_hour_count") != count:
        raise ValueError("ETH funding manifest observed count is inconsistent")
    times = pd.to_datetime(funding["timestamp"], errors="coerce", utc=True)
    expected_bounds = (
        times.iloc[0],
        times.iloc[-1] + pd.Timedelta(hours=1),
        times.iloc[0],
        times.iloc[-1],
    )
    declared_bounds = tuple(
        _utc_timestamp(manifest.get(field), f"manifest {field}")
        for field in (
            "requested_start",
            "requested_end",
            "first_observed",
            "last_observed",
        )
    )
    if declared_bounds != expected_bounds:
        raise ValueError("ETH funding manifest UTC bounds are inconsistent")
    files = _mapping(manifest.get("files"), "ETH funding manifest files")
    if files.get("funding.parquet") != file_evidence(funding_path):
        raise ValueError("ETH funding manifest file evidence is inconsistent")


def _stress_contract(stress: Record) -> tuple[float, float]:
    scenarios = _records(stress.get("scenarios"), "V58 stress scenarios")
    if len(scenarios) != 1:
        raise ValueError("V58 stress artifact must contain one scenario")
    slots = _mapping(scenarios[0].get("asset_slots"), "V58 stress slots")
    eth = _mapping(slots.get("ETH"), "V58 ETH stress slot")
    routes = _records(eth.get("routes"), "V58 ETH stress routes")
    if len(routes) != 1 or routes[0].get("strategy_id") != _STRATEGY:
        raise ValueError("V58 ETH stress route identity is invalid")
    route = routes[0]
    if _number(route.get("maximum_hold_hours"), "stress hold") != _HOLD_HOURS:
        raise ValueError("V58 ETH stress hold is invalid")
    friction = _mapping(route.get("friction_components_bps"), "stress friction")
    frozen = _number(friction.get("adverse_maximum_hold_funding"), "stress funding")
    notional = _number(route.get("planned_notional_usd"), "stress notional")
    return frozen, notional


def _current_projection(document: Record) -> float:
    context = _mapping(document.get("current_funding_context"), "current context")
    if context.get("execution_authority") != "none":
        raise ValueError("current funding context has execution authority")
    if context.get("sizing_input") is not False:
        raise ValueError("current funding context must not be a sizing input")
    rows = tuple(
        row
        for row in _records(context.get("routes"), "current funding routes")
        if row.get("symbol") == "ETH" and row.get("strategy_id") == _STRATEGY
    )
    if len(rows) != 1:
        raise ValueError("current ETH funding route identity is invalid")
    if _number(rows[0].get("maximum_hold_hours"), "current hold") != _HOLD_HOURS:
        raise ValueError("current ETH funding hold is invalid")
    return _number(rows[0].get("current_worst_side_cost_bps"), "current funding")


def _distribution(values: pd.Series) -> dict[str, float]:
    return {
        "minimum": float(values.min()),
        "p50": float(values.quantile(0.50)),
        "p90": float(values.quantile(0.90)),
        "p95": float(values.quantile(0.95)),
        "p99": float(values.quantile(0.99)),
        "maximum": float(values.max()),
    }


def _comparisons(
    values: pd.Series,
    frozen: float,
    current: float,
    notional: float,
    long: dict[str, float],
) -> dict[str, object]:
    return {
        "frozen_projection": _projection_comparison(values, frozen),
        "current_projection": _projection_comparison(values, current),
        "p99_minus_frozen_bps": long["p99"] - frozen,
        "p99_minus_frozen_loss_usd": (long["p99"] - frozen) * notional / 10_000.0,
    }


def _projection_comparison(values: pd.Series, projection: float) -> dict[str, float]:
    return {
        "cost_bps": projection,
        "empirical_percentile": float((values <= projection).mean()),
        "fraction_historical_windows_above": float((values > projection).mean()),
    }


def _disposition(p99_bps: float, frozen_bps: float) -> dict[str, object]:
    return {
        "status": "report_only_stress_recalibration",
        "reason": "historical long-side p99 exceeds the frozen point-in-time projection",
        "p99_exceeds_frozen": p99_bps > frozen_bps,
        "proposed_live_change": None,
        "report_only_change": "use source-bound historical funding tails in future stress reports",
        "confidence": "high_on_historical_measurement",
        "falsifier": "a complete newer window materially lowers the side-specific tail",
    }


def _limitations() -> list[str]:
    return [
        "rolling windows overlap",
        "historical window is not a funding forecast",
        "the bundle ends before the current live lifecycle",
        "p99 is an empirical marginal quantile rather than a loss ceiling",
        "the diagnostic changes no strategy, sizing, leverage, or execution behavior",
    ]


def _nonnegative(value: float, label: str) -> float:
    if not isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return float(value)


def _positive(value: float, label: str) -> float:
    number = _nonnegative(value, label)
    if number == 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _input_evidence(
    funding_path: Path,
    manifest_path: Path,
    stress_path: Path,
) -> dict[str, dict[str, object]]:
    generator_path = Path(__file__).resolve()
    return {
        "funding": _path_evidence(funding_path),
        "manifest": _path_evidence(manifest_path),
        "stress": _path_evidence(stress_path),
        "generator": _path_evidence(generator_path),
    }


def _require_unchanged(inputs: Mapping[str, Record]) -> None:
    for label, evidence in inputs.items():
        path = Path(_text(evidence.get("path"), f"{label} evidence path"))
        observed = _path_evidence(path)
        if observed != evidence:
            raise ValueError(f"{label} evidence changed during analysis")


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_json(path: Path, label: str) -> Record:
    try:
        value: object = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}: {exc}") from exc
    return _mapping(value, label)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return tuple(_mapping(row, f"{label} row") for row in value)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return _nonnegative(float(value), label)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _utc_timestamp(value: object, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(_text(value, label))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return timestamp.tz_convert("UTC")
