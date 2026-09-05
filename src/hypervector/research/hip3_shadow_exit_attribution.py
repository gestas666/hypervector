"""Bias-controlled exit attribution for report-only HIP-3 shadow lifecycles."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import cast

Record = Mapping[str, object]
LifecycleKey = tuple[int, str]
PathKey = tuple[int, int, str]
_FROZEN_HORIZONS = (15, 60, 240)
_MINUTE_MS = 60_000


@dataclass(frozen=True)
class _LifecyclePair:
    key: LifecycleKey
    nominal: Record
    stress: Record

    @property
    def holding_minutes(self) -> float:
        entry = _integer(self.nominal.get("entry_time_ms"), "entry time")
        exit_time = _integer(self.nominal.get("exit_time_ms"), "exit time")
        return (exit_time - entry) / _MINUTE_MS


def build_hip3_shadow_exit_attribution(
    lifecycle_report: Record,
    markout_report: Record,
) -> dict[str, object]:
    """Attribute resolved exits to the first eligible frozen BBO horizon."""
    identity = _validated_identity(lifecycle_report, markout_report)
    pairs = _lifecycle_pairs(lifecycle_report)
    paths = _markout_paths(markout_report)
    rows = [_attribution(pair, paths) for pair in pairs]
    return {
        "schema_version": "hip3_shadow_exit_attribution_v1",
        **identity,
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "measurement_contract": _measurement_contract(),
        "summary": _summary(rows),
        "exit_attributions": rows,
        "limitations": _limitations(),
    }


def _validated_identity(
    lifecycle_report: Record, markout_report: Record
) -> dict[str, str]:
    _lifecycle_authority(lifecycle_report)
    _markout_authority(markout_report)
    names = ("symbol", "provider_id", "profile_id")
    lifecycle = {name: _text(lifecycle_report.get(name), name) for name in names}
    markout = {name: _text(markout_report.get(name), name) for name in names}
    if lifecycle != markout:
        raise ValueError("HIP-3 exit attribution route identity is inconsistent")
    if not lifecycle["symbol"].startswith("xyz:"):
        raise ValueError("HIP-3 exit attribution identity requires an xyz symbol")
    return lifecycle


def _lifecycle_authority(report: Record) -> None:
    valid = (
        report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("runtime_strategy_changed") is False
    )
    if not valid:
        raise ValueError("HIP-3 exit attribution lifecycle authority is invalid")


def _markout_authority(report: Record) -> None:
    contract = _mapping(report.get("contract"), "markout contract")
    valid = (
        report.get("execution_authority") == "none"
        and report.get("report_only") is True
        and contract.get("fills_assumed") is False
        and contract.get("pnl_claimed") is False
    )
    if not valid:
        raise ValueError("HIP-3 exit attribution markout authority is invalid")


def _lifecycle_pairs(report: Record) -> tuple[_LifecyclePair, ...]:
    nominal = _lifecycle_index(report, "nominal")
    stress = _lifecycle_index(report, "stress")
    if nominal.keys() != stress.keys():
        raise ValueError("HIP-3 nominal and stress lifecycle keys differ")
    pairs: list[_LifecyclePair] = []
    for key in sorted(nominal):
        if _lifecycle_structure(nominal[key]) != _lifecycle_structure(stress[key]):
            raise ValueError("HIP-3 nominal and stress lifecycle structure differs")
        pairs.append(_LifecyclePair(key, nominal[key], stress[key]))
    return tuple(pairs)


def _lifecycle_index(report: Record, scenario: str) -> dict[LifecycleKey, Record]:
    section = _mapping(report.get(scenario), f"{scenario} scenario")
    rows = _sequence(section.get("lifecycles"), f"{scenario} lifecycles")
    output: dict[LifecycleKey, Record] = {}
    for raw in rows:
        row = _mapping(raw, f"{scenario} lifecycle")
        key = _lifecycle_key(row)
        _validate_lifecycle(row)
        if key in output:
            raise ValueError(f"HIP-3 {scenario} lifecycle key is duplicated")
        output[key] = row
    return output


def _validate_lifecycle(row: Record) -> None:
    entry = _integer(row.get("entry_time_ms"), "entry time")
    exit_time = _integer(row.get("exit_time_ms"), "exit time")
    if exit_time < entry:
        raise ValueError("HIP-3 lifecycle exit precedes entry")
    _number(row.get("gross_return_bps"), "gross return")
    _number(row.get("net_return_bps"), "net return")
    _text(row.get("exit_reason"), "exit reason")


def _lifecycle_structure(row: Record) -> tuple[object, ...]:
    names = (
        "decision_time_ms",
        "side",
        "entry_time_ms",
        "exit_time_ms",
        "exit_reason",
        "gross_return_bps",
    )
    return tuple(row.get(name) for name in names)


def _lifecycle_key(row: Record) -> LifecycleKey:
    decision = _integer(row.get("decision_time_ms"), "decision time")
    return decision, _side(row.get("side"))


def _markout_paths(report: Record) -> dict[PathKey, Record]:
    markouts = _mapping(report.get("markouts"), "markouts")
    raw_horizons = _mapping(markouts.get("horizons"), "markout horizons")
    horizons = tuple(sorted(_positive_integer(key, "horizon") for key in raw_horizons))
    if horizons != _FROZEN_HORIZONS:
        raise ValueError("HIP-3 exit attribution requires frozen 15/60/240 horizons")
    output: dict[PathKey, Record] = {}
    for horizon in horizons:
        section = _mapping(raw_horizons[str(horizon)], f"{horizon}m horizon")
        _add_horizon_paths(output, horizon, section.get("resolved_paths"))
    return output


def _add_horizon_paths(
    output: dict[PathKey, Record], horizon: int, value: object
) -> None:
    for raw in _sequence(value, f"{horizon}m resolved paths"):
        row = _mapping(raw, f"{horizon}m path")
        if _integer(row.get("horizon_minutes"), "path horizon") != horizon:
            raise ValueError("HIP-3 exit attribution path horizon is inconsistent")
        decision, side = _lifecycle_key(row)
        key = horizon, decision, side
        if key in output:
            raise ValueError("HIP-3 exit attribution markout path is duplicated")
        _number(row.get("gross_bbo_bps"), "gross BBO return")
        _number(row.get("after_modeled_friction_bps"), "modeled return")
        output[key] = row


def _attribution(
    pair: _LifecyclePair, paths: Mapping[PathKey, Record]
) -> dict[str, object]:
    required = _required_horizon(pair.holding_minutes)
    base = _actual_fields(pair)
    if required is None:
        return {
            **base,
            "required_post_exit_horizon_minutes": None,
            "selected_post_exit_horizon_minutes": None,
            "later_frozen_horizons_not_selected": [],
            "classification": "no_post_exit_frozen_horizon",
        }
    path = paths.get((required, *pair.key))
    if path is None:
        return _unresolved_attribution(base, required)
    _require_entry_alignment(pair.nominal, path)
    gross = _number(path.get("gross_bbo_bps"), "gross BBO return")
    return {
        **base,
        "required_post_exit_horizon_minutes": required,
        "selected_post_exit_horizon_minutes": required,
        "later_frozen_horizons_not_selected": _later_horizons(required),
        "selected_horizon_gross_bbo_bps": gross,
        "selected_horizon_after_modeled_friction_bps": _number(
            path.get("after_modeled_friction_bps"), "modeled return"
        ),
        "classification": _classification(
            _number(pair.nominal.get("gross_return_bps"), "gross return"), gross
        ),
    }


def _actual_fields(pair: _LifecyclePair) -> dict[str, object]:
    nominal = pair.nominal
    return {
        "decision_time_ms": pair.key[0],
        "side": pair.key[1],
        "exit_reason": _text(nominal.get("exit_reason"), "exit reason"),
        "entry_time_ms": _integer(nominal.get("entry_time_ms"), "entry time"),
        "exit_time_ms": _integer(nominal.get("exit_time_ms"), "exit time"),
        "holding_minutes": pair.holding_minutes,
        "actual_gross_return_bps": _number(
            nominal.get("gross_return_bps"), "gross return"
        ),
        "actual_nominal_net_return_bps": _number(
            nominal.get("net_return_bps"), "nominal net return"
        ),
        "actual_stress_net_return_bps": _number(
            pair.stress.get("net_return_bps"), "stress net return"
        ),
    }


def _unresolved_attribution(base: Record, required: int) -> dict[str, object]:
    return {
        **base,
        "required_post_exit_horizon_minutes": required,
        "selected_post_exit_horizon_minutes": None,
        "later_frozen_horizons_not_selected": _later_horizons(required),
        "classification": "first_post_exit_horizon_unresolved",
    }


def _required_horizon(holding_minutes: float) -> int | None:
    return next(
        (horizon for horizon in _FROZEN_HORIZONS if horizon >= holding_minutes),
        None,
    )


def _later_horizons(required: int) -> list[int]:
    return [horizon for horizon in _FROZEN_HORIZONS if horizon > required]


def _require_entry_alignment(lifecycle: Record, path: Record) -> None:
    entry = _integer(lifecycle.get("entry_time_ms"), "lifecycle entry time")
    book = _integer(path.get("entry_book_time_ms"), "markout entry time")
    if entry != book:
        raise ValueError("HIP-3 exit attribution entry identity is inconsistent")


def _classification(actual_gross: float, horizon_gross: float) -> str:
    if actual_gross <= 0.0 < horizon_gross:
        return "directional_recovery_after_exit"
    if actual_gross <= 0.0 and horizon_gross <= 0.0:
        return "loss_persisted_after_exit"
    if actual_gross > 0.0 >= horizon_gross:
        return "profit_protected_before_later_reversal"
    if horizon_gross > actual_gross:
        return "positive_path_extended_after_exit"
    return "positive_path_reduced_after_exit"


def _summary(rows: Sequence[Record]) -> dict[str, object]:
    classifications = Counter(
        _text(row.get("classification"), "classification") for row in rows
    )
    by_side: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        by_side[_side(row.get("side"))].update(
            [_text(row.get("classification"), "classification")]
        )
    comparable = sum(
        row.get("selected_post_exit_horizon_minutes") is not None for row in rows
    )
    return {
        "completed_lifecycles": len(rows),
        "post_exit_comparable_lifecycles": comparable,
        "classifications": dict(sorted(classifications.items())),
        "classifications_by_side": {
            side: dict(sorted(counts.items()))
            for side, counts in sorted(by_side.items())
        },
    }


def _measurement_contract() -> dict[str, object]:
    return {
        "frozen_horizons_minutes": list(_FROZEN_HORIZONS),
        "selection_rule": "first_frozen_horizon_at_or_after_actual_exit",
        "classification_basis": "gross_direction_only",
        "later_horizon_selection_prohibited": True,
        "execution_equivalent_pnl_delta_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "This is a post-hoc measurement on completed prospective lifecycles, not an exit optimization or promotion test.",
        "Fixed-horizon BBO paths do not reproduce lifecycle funding, depth-sized fills, stop execution, or stress friction.",
        "The first frozen horizon may occur materially after the actual exit and cannot identify the best causal exit time.",
        "Small side and exit-reason samples can be dominated by single paths; future prospective evidence is required.",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 exit attribution {label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"HIP-3 exit attribution {label} must be a list")
    return value


def _side(value: object) -> str:
    side = _text(value, "side")
    if side not in {"long", "short"}:
        raise ValueError("HIP-3 exit attribution side is invalid")
    return side


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"HIP-3 exit attribution {label} must be text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HIP-3 exit attribution {label} must be nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    result = _integer(value, label)
    if result < 1:
        raise ValueError(f"HIP-3 exit attribution {label} must be positive")
    return result


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 exit attribution {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"HIP-3 exit attribution {label} must be finite")
    return result
