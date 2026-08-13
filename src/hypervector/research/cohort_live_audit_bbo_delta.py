"""Compare provider-cadence executable-BBO episode evidence across prefixes."""

from __future__ import annotations

from collections.abc import Mapping
import math

Record = Mapping[str, object]
PathKey = tuple[str | None, int]

_COVERAGE_FIELDS = (
    "eligible_signals",
    "entry_matched",
    "entry_censored",
    "entry_gap",
    "resolved",
    "exit_censored",
    "exit_gap",
    "friction_contract_missing",
)
_MONOTONIC_FIELDS = (
    "eligible_signals",
    "entry_matched",
    "entry_gap",
    "resolved",
    "exit_gap",
    "friction_contract_missing",
)
_SIDE_CATEGORIES = ("long", "short")
_PRESSURE_CATEGORIES = ("aligned", "neutral", "opposed", "unavailable")


def build_executable_bbo_maturity_delta(
    before: Record, after: Record
) -> dict[str, object]:
    """Return strict report-only episode-onset BBO changes."""
    before_rows = _provider_rows(before, "before")
    after_rows = _provider_rows(after, "after")
    if before_rows is None or after_rows is None:
        return _unavailable_delta(before_rows, after_rows)
    removed = sorted(set(before_rows) - set(after_rows))
    if removed:
        raise ValueError("executable BBO provider evidence cannot disappear")
    added = sorted(set(after_rows) - set(before_rows))
    changed = [
        row
        for identity in sorted(after_rows)
        if (
            row := _provider_delta(
                identity,
                before_rows.get(identity),
                after_rows[identity],
            )
        )
    ]
    return {
        "comparable": True,
        "providers_added": added,
        "providers_removed": removed,
        "changed_providers": changed,
        "newly_matured_episode_onsets": any(
            _provider_has_maturity(row) for row in changed
        ),
        "path_identity_complete": all(
            _provider_paths_comparable(row) for row in changed
        ),
    }


def _provider_rows(audit: Record, label: str) -> dict[str, Record] | None:
    orderbook = _optional_mapping(audit.get("orderbook_opportunity"))
    if orderbook is None:
        return None
    context = _mapping(
        orderbook.get("eligible_signal_context"), f"{label} eligible signal context"
    )
    raw = _mapping(context.get("by_provider_symbol"), f"{label} BBO providers")
    result: dict[str, Record] = {}
    for identity, value in raw.items():
        provider = _mapping(value, f"{label} BBO provider")
        markouts = _optional_mapping(provider.get("executable_bbo_markouts"))
        if markouts is not None:
            result[_text(identity, f"{label} BBO provider identity")] = markouts
    return result


def _unavailable_delta(
    before: dict[str, Record] | None, after: dict[str, Record] | None
) -> dict[str, object]:
    if before is None and after is None:
        reason = "executable_bbo_context_absent_in_both_prefixes"
    elif before is None:
        reason = "executable_bbo_context_absent_in_before_prefix"
    else:
        reason = "executable_bbo_context_absent_in_after_prefix"
    return {
        "comparable": False,
        "newly_available": before is None and after is not None,
        "reason": reason,
    }


def _provider_delta(
    identity: str, before: Record | None, after: Record
) -> dict[str, object] | None:
    before_horizons = (
        {} if before is None else _mapping(before.get("horizons"), "before horizons")
    )
    after_horizons = _mapping(after.get("horizons"), "after horizons")
    missing = set(before_horizons) - set(after_horizons)
    if missing:
        raise ValueError("executable BBO horizon evidence cannot disappear")
    horizons: dict[str, object] = {}
    for horizon in sorted(after_horizons, key=_horizon_sort_key):
        row = _horizon_delta(
            identity,
            horizon,
            _optional_mapping(before_horizons.get(horizon)),
            _mapping(after_horizons[horizon], "after BBO horizon"),
        )
        if _horizon_changed(row):
            horizons[_text(horizon, "BBO horizon")] = row
    if not horizons:
        return None
    return {"provider_symbol": identity, "horizons": horizons}


def _horizon_delta(
    identity: str,
    horizon: object,
    before: Record | None,
    after: Record,
) -> dict[str, object]:
    after_episode = _episode(after, "after")
    before_episode = None if before is None else _episode(before, "before")
    _validate_episodes(before_episode, after_episode)
    before_coverage = {} if before_episode is None else _coverage(before_episode)
    after_coverage = _coverage(after_episode)
    coverage_delta = _coverage_delta(before_coverage, after_coverage)
    prior_independent = _independent_count(before_episode)
    after_independent = _independent_count(after_episode)
    independent_delta = after_independent - prior_independent
    if independent_delta < 0:
        raise ValueError("executable BBO independent count cannot move backwards")
    paths = _path_delta(identity, horizon, before_episode, after_episode)
    economics = _economics_delta(before_episode, after_episode, independent_delta)
    return {
        "provider_cadence_minutes": _cadence(after_episode),
        "coverage_delta": coverage_delta,
        "independent_resolved_delta": independent_delta,
        "after_modeled_friction_bps": economics,
        "by_side_paths_delta": _group_path_deltas(
            before_episode, after_episode, "by_side", _SIDE_CATEGORIES
        ),
        "by_pressure_paths_delta": _group_path_deltas(
            before_episode,
            after_episode,
            "by_pressure_stance",
            _PRESSURE_CATEGORIES,
        ),
        **paths,
    }


def _episode(horizon: Record, label: str) -> Record:
    episode = _mapping(horizon.get("episode_onsets"), f"{label} BBO episode")
    if episode.get("status") != "available":
        raise ValueError(f"{label} executable BBO episode evidence is unavailable")
    return episode


def _validate_episodes(before: Record | None, after: Record) -> None:
    _validate_episode(after, "after")
    if before is None:
        return
    _validate_episode(before, "before")
    if _cadence(before) != _cadence(after):
        raise ValueError("executable BBO provider cadence cannot change")


def _validate_episode(value: Record, label: str) -> None:
    coverage = _coverage(value)
    if (
        coverage["entry_matched"] + coverage["entry_censored"] + coverage["entry_gap"]
        != coverage["eligible_signals"]
        or coverage["resolved"] + coverage["exit_censored"] + coverage["exit_gap"]
        != coverage["entry_matched"]
    ):
        raise ValueError(f"{label} executable BBO coverage does not reconcile")
    independent = _independent_count(value)
    if independent > coverage["resolved"]:
        raise ValueError(f"{label} executable BBO independent count is inflated")
    _validate_groups(value, independent, label)


def _validate_groups(value: Record, independent: int, label: str) -> None:
    all_group = _mapping(value.get("all"), f"{label} BBO all group")
    if _count(all_group.get("paths"), f"{label} BBO all paths") != independent:
        raise ValueError(f"{label} executable BBO all paths do not reconcile")
    for field, categories in (
        ("by_side", _SIDE_CATEGORIES),
        ("by_pressure_stance", _PRESSURE_CATEGORIES),
    ):
        groups = _mapping(value.get(field), f"{label} BBO {field}")
        if set(groups) != set(categories):
            raise ValueError(f"{label} executable BBO {field} is incomplete")
        total = sum(
            _count(_mapping(groups[name], name).get("paths"), f"{label} {name}")
            for name in categories
        )
        if total != independent:
            raise ValueError(f"{label} executable BBO {field} does not reconcile")


def _coverage(value: Record) -> dict[str, int]:
    raw = _mapping(value.get("coverage"), "BBO episode coverage")
    return {field: _count(raw.get(field), f"BBO {field}") for field in _COVERAGE_FIELDS}


def _coverage_delta(before: Record, after: Record) -> dict[str, int]:
    result = {
        field: _count(after.get(field), f"after {field}")
        - _count(before.get(field, 0), f"before {field}")
        for field in _COVERAGE_FIELDS
    }
    if any(result[field] < 0 for field in _MONOTONIC_FIELDS):
        raise ValueError("cumulative executable BBO coverage cannot move backwards")
    return result


def _economics_delta(
    before: Record | None, after: Record, independent_delta: int
) -> dict[str, float | None]:
    before_all = {} if before is None else _mapping(before.get("all"), "before all")
    after_all = _mapping(after.get("all"), "after all")
    fields = {
        "mean": "mean_after_modeled_friction_bps",
        "median": "median_after_modeled_friction_bps",
        "leave_largest": "mean_excluding_largest_after_modeled_friction_bps",
    }
    result: dict[str, float | None] = {}
    for label, field in fields.items():
        result[f"{label}_before"] = _optional_number(before_all.get(field))
        result[f"{label}_after"] = _optional_number(after_all.get(field))
    if independent_delta == 0 and any(
        result[f"{label}_before"] != result[f"{label}_after"] for label in fields
    ):
        raise ValueError("resolved executable BBO economics cannot change")
    return result


def _group_path_deltas(
    before: Record | None,
    after: Record,
    field: str,
    categories: tuple[str, ...],
) -> dict[str, int]:
    before_groups = {} if before is None else _mapping(before.get(field), field)
    after_groups = _mapping(after.get(field), field)
    result: dict[str, int] = {}
    for category in categories:
        before_group = _optional_mapping(before_groups.get(category)) or {}
        after_group = _mapping(after_groups.get(category), f"after {category}")
        delta = _count(after_group.get("paths"), f"after {category} paths") - _count(
            before_group.get("paths", 0), f"before {category} paths"
        )
        if delta < 0:
            raise ValueError("executable BBO group paths cannot move backwards")
        result[category] = delta
    return result


def _path_delta(
    identity: str,
    horizon: object,
    before: Record | None,
    after: Record,
) -> dict[str, object]:
    after_paths = _optional_list(after.get("independent_paths"))
    before_paths = (
        None if before is None else _optional_list(before.get("independent_paths"))
    )
    if before is not None and before_paths is not None and after_paths is None:
        raise ValueError("resolved executable BBO path schema cannot disappear")
    comparable = after_paths is not None and (
        before is None or before_paths is not None
    )
    if not comparable:
        return {"path_identity_comparable": False, "new_independent_paths": []}
    prior = _path_index(before_paths or [], identity, horizon, "before")
    current = _path_index(after_paths or [], identity, horizon, "after")
    if set(prior) - set(current):
        raise ValueError("resolved executable BBO path cannot disappear")
    if any(prior[key] != current[key] for key in prior):
        raise ValueError("resolved executable BBO path cannot change")
    added = sorted(set(current) - set(prior), key=_path_sort_key)
    return {
        "path_identity_comparable": True,
        "new_independent_paths": [dict(current[key]) for key in added],
    }


def _path_index(
    paths: list[object], identity: str, horizon: object, label: str
) -> dict[PathKey, Record]:
    expected_horizon = _positive_int(horizon, "BBO horizon")
    result: dict[PathKey, Record] = {}
    for value in paths:
        row = _mapping(value, f"{label} executable BBO path")
        if _count(row.get("horizon_minutes"), "path horizon") != expected_horizon:
            raise ValueError(f"{identity} executable BBO path horizon does not match")
        key = (
            _optional_text(row.get("source_run_id"), "path source run"),
            _count(row.get("decision_time_ms"), "path decision time"),
        )
        if key in result:
            raise ValueError(f"duplicate {label} executable BBO path identity")
        result[key] = row
    return result


def _horizon_changed(row: Record) -> bool:
    coverage = _mapping(row.get("coverage_delta"), "BBO coverage delta")
    economics = _mapping(row.get("after_modeled_friction_bps"), "BBO economics")
    return (
        any(value != 0 for value in coverage.values())
        or row.get("independent_resolved_delta") != 0
        or bool(row.get("new_independent_paths"))
        or any(
            key.endswith("_before") and economics[key] != economics[key[:-7] + "_after"]
            for key in economics
        )
    )


def _provider_has_maturity(row: Record) -> bool:
    horizons = _mapping(row.get("horizons"), "BBO provider horizons")
    return any(
        _mapping(value, "BBO horizon delta").get("independent_resolved_delta", 0) > 0
        for value in horizons.values()
    )


def _provider_paths_comparable(row: Record) -> bool:
    horizons = _mapping(row.get("horizons"), "BBO provider horizons")
    return all(
        _mapping(value, "BBO horizon delta").get("path_identity_comparable") is True
        for value in horizons.values()
    )


def _independent_count(value: Record | None) -> int:
    return (
        0
        if value is None
        else _count(value.get("independent_resolved"), "BBO independent")
    )


def _cadence(value: Record) -> int:
    return _positive_int(value.get("provider_cadence_minutes"), "provider cadence")


def _path_sort_key(key: PathKey) -> tuple[str, int]:
    return key[0] or "", key[1]


def _horizon_sort_key(value: object) -> int:
    return _positive_int(value, "BBO horizon")


def _positive_int(value: object, label: str) -> int:
    number = int(value) if isinstance(value, str) and value.isdigit() else value
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return number


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("BBO economic value must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("BBO economic value must be finite")
    return number


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_mapping(value: object) -> Record | None:
    return None if value is None else _mapping(value, "optional mapping")


def _optional_list(value: object) -> list[object] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError("executable BBO independent paths must be a list")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)
