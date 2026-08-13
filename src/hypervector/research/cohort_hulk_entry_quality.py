"""Report-only Hulk entry quality attribution from point-in-time live evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

Record = Mapping[str, object]
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_VOLUME_BASELINE = 1.0
_QUALITIES = ("flow_and_volume", "one_of_two", "neither", "unavailable")


@dataclass(frozen=True)
class _EntryQuality:
    side: str
    flow_direction: int | None
    volume_ratio: float | None
    quality: str


def build_hulk_entry_quality_mechanism(
    closed_trades: Sequence[Record],
    open_trades: Sequence[Record] = (),
) -> dict[str, object]:
    """Stratify Hulk outcomes without gating, sizing, or execution authority."""
    closed = tuple(row for row in closed_trades if row.get("strategy_id") == _HULK)
    opened = tuple(row for row in open_trades if row.get("strategy_id") == _HULK)
    by_quality = _quality_summaries(closed)
    return {
        "schema_version": 1,
        "mode": "cohort_hulk_entry_quality_mechanism_v1",
        "scope": "all_live_history_mixed_profiles",
        "strategy_id": _HULK,
        "current_stage": "annotation_only",
        "contract": _contract(),
        "feature_contract": _feature_contract(),
        "closed_trades": len(closed),
        "attributable_closed_trades": sum(
            int(by_quality[name]["trades"]) for name in _QUALITIES[:-1]
        ),
        "open_trades": len(opened),
        "closed_by_quality": by_quality,
        "by_side": {side: _side_summary(closed, side) for side in ("long", "short")},
        "open_observations": [_open_observation(row) for row in opened],
        "predeclared_variants": _predeclared_variants(),
        "limitations": _limitations(),
    }


def _quality_summaries(trades: Sequence[Record]) -> dict[str, dict[str, object]]:
    grouped = {
        name: [row for row in trades if _entry_quality(row).quality == name]
        for name in _QUALITIES
    }
    return {name: _outcome_summary(rows) for name, rows in grouped.items()}


def _side_summary(trades: Sequence[Record], side: str) -> dict[str, object]:
    selected = [row for row in trades if _side(row) == side]
    return {
        "closed_trades": len(selected),
        "closed_by_quality": _quality_summaries(selected),
    }


def _outcome_summary(trades: Sequence[Record]) -> dict[str, object]:
    pnl = [_number(row.get("net_pnl_usd"), "net pnl") for row in trades]
    returns = [
        _number(row.get("net_return_on_margin_pct"), "return on margin")
        for row in trades
    ]
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    return {
        "trades": len(trades),
        "wins": sum(value > 0.0 for value in returns),
        "losses": sum(value < 0.0 for value in returns),
        "breakeven": sum(value == 0.0 for value in returns),
        "net_pnl_usd": sum(pnl),
        "mean_net_return_on_margin_pct": (
            sum(returns) / len(returns) if returns else None
        ),
        "normalized_profit_factor": gains / losses if losses > 0.0 else None,
    }


def _open_observation(trade: Record) -> dict[str, object]:
    quality = _entry_quality(trade)
    economics = _optional_mapping(trade.get("marked_economics"), "marked economics")
    marked = _optional_number(
        economics.get("active_lifecycle_marked_net_pnl_usd"), "marked net pnl"
    )
    return {
        "symbol": _text(trade.get("symbol"), "symbol"),
        "side": quality.side,
        "flow_direction": quality.flow_direction,
        "volume_ratio": quality.volume_ratio,
        "quality": quality.quality,
        "marked_net_pnl_usd": marked,
        "status": "unresolved",
    }


def _entry_quality(trade: Record) -> _EntryQuality:
    side = _side(trade)
    metrics = _entry_metrics(trade)
    flow = _optional_direction(metrics.get("money_flow_direction"))
    volume = _optional_nonnegative(metrics.get("volume_ratio"), "volume ratio")
    if flow is None or volume is None:
        return _EntryQuality(side, flow, volume, "unavailable")
    aligned = flow == (1 if side == "long" else -1)
    supported = volume >= _VOLUME_BASELINE
    if aligned and supported:
        quality = "flow_and_volume"
    elif aligned or supported:
        quality = "one_of_two"
    else:
        quality = "neither"
    return _EntryQuality(side, flow, volume, quality)


def _entry_metrics(trade: Record) -> Record:
    context = _optional_mapping(trade.get("entry_context"), "entry context")
    provider = _optional_mapping(context.get("signal_provider"), "signal provider")
    readiness = _optional_mapping(provider.get("readiness"), "readiness")
    return _optional_mapping(readiness.get("metrics"), "readiness metrics")


def _side(trade: Record) -> str:
    side = _text(trade.get("side"), "side")
    if side not in {"long", "short"}:
        raise ValueError(f"unsupported Hulk side: {side}")
    return side


def _optional_direction(value: object) -> int | None:
    if value is None:
        return None
    number = _number(value, "money flow direction")
    if number not in {-1.0, 0.0, 1.0}:
        raise ValueError("money flow direction must be -1, 0, or 1")
    return int(number)


def _optional_nonnegative(value: object, label: str) -> float | None:
    if value is None:
        return None
    number = _number(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _optional_mapping(value: object, label: str) -> Record:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _feature_contract() -> dict[str, object]:
    return {
        "source": "entry_decision_readiness_metrics",
        "money_flow_alignment": "direction_sign_equals_position_side",
        "volume_support_minimum_ratio": _VOLUME_BASELINE,
        "volume_threshold_origin": "untuned_relative_volume_baseline",
        "symmetric_long_short": True,
    }


def _predeclared_variants() -> dict[str, object]:
    return {
        "control": {"entry": "unchanged", "size_multiplier": 1.0},
        "hard_gate": {"requires": "flow_and_volume", "execution": "disabled"},
        "scaled": {
            "flow_and_volume": 1.0,
            "one_of_two": 0.5,
            "neither": 0.25,
            "execution": "disabled",
        },
        "annotation": {"entry": "unchanged", "execution": "active_stage"},
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "execution_gate": False,
        "position_sizing_authority": False,
    }


def _limitations() -> list[str]:
    return [
        "open observations are unresolved and excluded from realized outcomes",
        "legacy entries without point-in-time readiness remain unavailable",
        "one untuned 1.0x relative-volume baseline avoids threshold fishing",
        "small live categories do not establish a durable sizing or gating edge",
        "mixed profile sizes make net USD descriptive rather than portfolio additive",
    ]
