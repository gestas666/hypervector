"""Report-only decision for the frozen ETH side/relation mechanism set."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]

_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_SYMBOL = "ETH"
_MODE = "eth_pullback_side_breakout_relation_attribution_v1"
_PARTITIONS = ("development", "opened_final_60d")
_SIDES = ("long", "short")
_RELATION_ARMS = (
    "long|aligned",
    "long|opposed",
    "short|aligned",
    "short|opposed",
)
_ECONOMIC_FIELDS = (
    "trades",
    "wins",
    "losses",
    "net_return_bps",
    "profit_factor",
    "net_excluding_largest_winner_bps",
)
_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "model_authority": "none",
    "automatic_promotion": False,
    "automatic_retuning": False,
    "runtime_strategy_changed": False,
}


def build_eth_side_mechanism_decision(
    attribution: Record,
    duration: Record,
) -> dict[str, object]:
    """Resolve the tested ETH side/relation set without execution authority."""
    _validate_source(attribution, "ETH attribution")
    _validate_source(duration, "ETH duration")
    _validate_matching_identity(attribution, duration)
    segments = _mapping(attribution.get("segments"), "ETH segments")
    _validate_duration_economics(segments, duration)
    side_arms = _arms(segments, "by_side", _SIDES)
    relation_arms = _arms(segments, "by_side_relation", _RELATION_ARMS)
    stable_sides = _stable_keys(side_arms)
    stable_relations = _stable_keys(relation_arms)
    return {
        "schema_version": "eth_side_mechanism_decision_v1",
        "mode": "eth_side_breakout_relation_decision",
        "contract": dict(_CONTRACT),
        "route": {"strategy_id": _STRATEGY, "symbol": _SYMBOL},
        "split": dict(_mapping(attribution.get("split"), "ETH split")),
        "coverage": dict(_mapping(attribution.get("coverage"), "ETH coverage")),
        "side_arms": side_arms,
        "side_relation_arms": relation_arms,
        "assessment": {
            "tested_side_arms": len(side_arms),
            "stable_side_arms": stable_sides,
            "tested_side_relation_arms": len(relation_arms),
            "stable_side_relation_arms": stable_relations,
            "retained_maximum_hold_minutes": 720,
            "holdout_claimed": False,
        },
        "decision": _decision(stable_sides, stable_relations),
        "limitations": _limitations(),
    }


def _validate_source(source: Record, label: str) -> None:
    if source.get("schema_version") != 1 or source.get("mode") != _MODE:
        raise ValueError(f"{label} identity is unsupported")
    if source.get("strategy_id") != _STRATEGY or source.get("symbol") != _SYMBOL:
        raise ValueError(f"{label} route identity mismatch")
    contract = _mapping(source.get("contract"), f"{label} contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "entry_gate": False,
        "portfolio_pnl_claimed": False,
    }
    mismatches = [key for key, value in expected.items() if contract.get(key) != value]
    if mismatches:
        raise ValueError(f"{label} violates report-only contract: {mismatches}")


def _validate_matching_identity(attribution: Record, duration: Record) -> None:
    for field in ("strategy_id", "symbol", "split", "coverage"):
        if attribution.get(field) != duration.get(field):
            raise ValueError(f"ETH attribution and duration disagree on {field}")


def _validate_duration_economics(segments: Record, duration: Record) -> None:
    comparisons = _mapping(duration.get("duration_comparison"), "duration comparison")
    for partition in _PARTITIONS:
        segment = _mapping(segments.get(partition), f"{partition} segment")
        expected_sides = _mapping(segment.get("by_side"), f"{partition} sides")
        partition_comparison = _mapping(
            comparisons.get(partition), f"{partition} duration comparison"
        )
        fixed = _mapping(partition_comparison.get("fixed_720m"), "720-minute control")
        actual_sides = _mapping(fixed.get("by_side"), "720-minute sides")
        for side in _SIDES:
            expected = _mapping(expected_sides.get(side), f"{partition} {side}")
            actual = _mapping(actual_sides.get(side), f"720-minute {partition} {side}")
            if not _economics_match(expected, actual):
                raise ValueError("720-minute side economics mismatch")


def _economics_match(expected: Record, actual: Record) -> bool:
    for field in _ECONOMIC_FIELDS:
        left = expected.get(field)
        right = actual.get(field)
        if left is None or right is None:
            if left is not right:
                return False
        elif field in {"trades", "wins", "losses"}:
            if _integer(left, field) != _integer(right, field):
                return False
        elif abs(_number(left, field) - _number(right, field)) > 1e-9:
            return False
    return True


def _arms(
    segments: Record,
    section: str,
    keys: tuple[str, ...],
) -> dict[str, object]:
    return {key: _arm_record(segments, section, key) for key in keys}


def _arm_record(segments: Record, section: str, key: str) -> dict[str, object]:
    cells = {
        partition: _economic_cell(
            _mapping(
                _mapping(segments.get(partition), f"{partition} segment").get(section),
                f"{partition} {section}",
            ).get(key),
            f"{partition} {key}",
        )
        for partition in _PARTITIONS
    }
    failed = [partition for partition, cell in cells.items() if not _repeatable(cell)]
    return {
        "stable": not failed,
        "failed_partitions": failed,
        "partitions": cells,
        "criteria": (
            "nonempty_net_positive_pf_above_one_and_positive_without_largest_winner"
        ),
    }


def _economic_cell(value: object, label: str) -> dict[str, object]:
    source = _mapping(value, label)
    trades = _integer(source.get("trades"), f"{label} trades")
    wins = _integer(source.get("wins"), f"{label} wins")
    losses = _integer(source.get("losses"), f"{label} losses")
    if wins + losses > trades:
        raise ValueError(f"{label} outcome counts exceed trades")
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "net_return_bps": _number(source.get("net_return_bps"), f"{label} net"),
        "profit_factor": _optional_number(source.get("profit_factor"), f"{label} PF"),
        "net_excluding_largest_winner_bps": _number(
            source.get("net_excluding_largest_winner_bps"), f"{label} repeatability"
        ),
    }


def _repeatable(cell: Record) -> bool:
    profit_factor = cell.get("profit_factor")
    return (
        _integer(cell.get("trades"), "cell trades") > 0
        and _number(cell.get("net_return_bps"), "cell net") > 0.0
        and profit_factor is not None
        and _number(profit_factor, "cell PF") > 1.0
        and _number(cell.get("net_excluding_largest_winner_bps"), "cell repeatability")
        > 0.0
    )


def _stable_keys(arms: Record) -> list[str]:
    return [
        key for key, value in arms.items() if _mapping(value, key).get("stable") is True
    ]


def _decision(stable_sides: list[str], stable_relations: list[str]) -> str:
    if stable_sides or stable_relations:
        return "stable_eth_side_arm_requires_preregistered_forward_test"
    return "tested_side_relation_set_falsified_requires_new_mechanism_identity"


def _limitations() -> list[str]:
    return [
        "The opened final 60-day block was previously inspected and is descriptive.",
        "The exact entry and 60-bps stop/12-hour hold shape followed prior trials.",
        "One-minute bars cannot reproduce private IOC latency or intrabar stop ordering.",
        "The test exhausts side and breakout relation, not all causal ETH mechanisms.",
        "No result grants execution, sizing, gating, retuning, or promotion authority.",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not result == result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return result


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)
