"""Exact fill-cost and execution-quality validation for V79 monitoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from statistics import median

from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
)
from hypervector.research.cohort_friction_contracts import modeled_contract

Record = Mapping[str, object]
_FLOAT_TOLERANCE = 0.000_001


@dataclass(frozen=True)
class ExecutionQualityValidation:
    """V79 execution-quality rejection reasons and complete fill count."""

    reasons: tuple[str, ...]
    fills: int
    costed_fills: int


@dataclass(frozen=True)
class _FillQuality:
    fee_rate_bps: float
    slippage_bps: float
    acknowledgement_latency_ms: int


def validate_v79_execution_quality(
    audit: Record,
    config: MultiAssetLiveConfig,
) -> ExecutionQualityValidation:
    """Validate exact fee, slippage, latency, and declared entry cost bounds."""
    execution = _mapping(audit.get("execution"), "audit execution")
    fills = _record_list(execution.get("fill_details"), "fill details")
    assets = {asset.symbol: asset for asset in config.assets}
    reasons: list[str] = []
    qualities: list[_FillQuality] = []
    for fill in fills:
        quality = _fill_quality(fill)
        if quality is None:
            reasons.append("execution_quality_incomplete")
            continue
        qualities.append(quality)
        if not _slippage_reproduces(fill, quality.slippage_bps):
            reasons.append("execution_quality_metric_mismatch")
        if fill.get("operation") == "entry":
            reasons.extend(_entry_bound_reasons(fill, quality, assets))
    if not _summaries_match(execution, fills):
        reasons.append("execution_quality_summary_mismatch")
    return ExecutionQualityValidation(
        tuple(dict.fromkeys(reasons)), len(fills), len(qualities)
    )


def _fill_quality(fill: Record) -> _FillQuality | None:
    price = _positive_number(fill.get("price"))
    size = _positive_number(fill.get("size"))
    fee = _nonnegative_number(fill.get("fee_usd"))
    expected = _positive_number(fill.get("expected_price"))
    slippage = _finite_number(fill.get("slippage_bps"))
    latency = _nonnegative_integer(fill.get("acknowledgement_latency_ms"))
    side = fill.get("side")
    if None in (price, size, fee, expected, slippage, latency) or side not in {
        "A",
        "B",
    }:
        return None
    return _FillQuality(
        float(fee) / (float(price) * float(size)) * 10_000.0,
        float(slippage),
        int(latency),
    )


def _slippage_reproduces(fill: Record, reported: float) -> bool:
    price = _positive_number(fill.get("price"))
    expected = _positive_number(fill.get("expected_price"))
    side = fill.get("side")
    if price is None or expected is None or side not in {"A", "B"}:
        return False
    direction = 1.0 if side == "B" else -1.0
    calculated = direction * (price / expected - 1.0) * 10_000.0
    return math.isclose(calculated, reported, abs_tol=_FLOAT_TOLERANCE)


def _entry_bound_reasons(
    fill: Record,
    quality: _FillQuality,
    assets: Mapping[str, AssetLiveConfig],
) -> list[str]:
    symbol = fill.get("symbol")
    strategy = fill.get("strategy_id")
    oid = fill.get("oid")
    label = f"{symbol}:{oid}"
    if not isinstance(symbol, str) or not isinstance(strategy, str):
        return ["execution_quality_incomplete"]
    asset = assets.get(symbol)
    if asset is None:
        return ["execution_quality_incomplete"]
    cap_bps = asset.effective_entry_slippage_cap_fraction * 10_000.0
    expected = modeled_contract(strategy, symbol)
    reasons: list[str] = []
    if quality.slippage_bps > cap_bps + _FLOAT_TOLERANCE:
        reasons.append(f"entry_slippage_cap_exceeded:{label}")
    if expected is None:
        reasons.append(f"entry_fee_model_missing:{strategy}|{symbol}")
    elif quality.fee_rate_bps > expected.entry_fee_bps + _FLOAT_TOLERANCE:
        reasons.append(f"entry_fee_model_exceeded:{label}")
    return reasons


def _summaries_match(execution: Record, fills: Sequence[Record]) -> bool:
    fee_rates = [
        value for fill in fills if (value := _fee_rate_or_none(fill)) is not None
    ]
    slippage = [
        value
        for fill in fills
        if (value := _finite_number(fill.get("slippage_bps"))) is not None
    ]
    latency = [
        float(value)
        for fill in fills
        if (value := _nonnegative_integer(fill.get("acknowledgement_latency_ms")))
        is not None
    ]
    return all(
        _summary_matches(execution.get(key), values, len(fills))
        for key, values in (
            ("fee_rate_bps", fee_rates),
            ("slippage_bps", slippage),
            ("acknowledgement_latency_ms", latency),
        )
    )


def _fee_rate_or_none(fill: Record) -> float | None:
    price = _positive_number(fill.get("price"))
    size = _positive_number(fill.get("size"))
    fee = _nonnegative_number(fill.get("fee_usd"))
    if price is None or size is None or fee is None:
        return None
    return fee / (price * size) * 10_000.0


def _summary_matches(value: object, values: Sequence[float], fills: int) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected_status = (
        "not_applicable_no_fills"
        if fills == 0
        else "observed"
        if len(values) == fills
        else "incomplete"
    )
    expected = _summary(values)
    return value.get("status") == expected_status and all(
        _equal_optional_number(value.get(key), expected[key])
        for key in ("count", "minimum", "median", "maximum", "mean")
    )


def _summary(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "minimum": min(values) if values else None,
        "median": float(median(values)) if values else None,
        "maximum": max(values) if values else None,
        "mean": sum(values) / len(values) if values else None,
    }


def _equal_optional_number(value: object, expected: float | int | None) -> bool:
    if expected is None:
        return value is None
    parsed = _finite_number(value)
    return parsed is not None and math.isclose(
        parsed, float(expected), abs_tol=_FLOAT_TOLERANCE
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _record_list(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return tuple(value)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _positive_number(value: object) -> float | None:
    parsed = _finite_number(value)
    return parsed if parsed is not None and parsed > 0.0 else None


def _nonnegative_number(value: object) -> float | None:
    parsed = _finite_number(value)
    return parsed if parsed is not None and parsed >= 0.0 else None


def _nonnegative_integer(value: object) -> int | None:
    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if valid else None
