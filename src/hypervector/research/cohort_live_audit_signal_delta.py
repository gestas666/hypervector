"""Attribute causal provider-signal maturity across live-audit prefixes."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]
ProviderKey = tuple[str, str]
AttributionKey = tuple[str | None, str, str, tuple[ProviderKey, ...]]
PathKey = tuple[str | None, int]

_HORIZON_FIELDS = (
    "resolved",
    "non_overlapping_resolved",
    "censored",
    "cost_clearing_close_count",
    "cost_clearing_mfe_count",
    "failed_to_clear_cost_count",
    "reversed_after_cost_clear_count",
    "robust_mfe_count",
)
_CAPTURE_FIELDS = _HORIZON_FIELDS[3:]
_PORTFOLIO_FIELDS = (
    "provider_observations",
    "unique_directional_paths",
    "duplicate_provider_observations_removed",
    "cross_provider_path_groups",
    "direction_competition_groups",
    "reference_price_conflict_groups",
)


def build_signal_maturity_delta(before: Record, after: Record) -> dict[str, object]:
    """Build provider and one-blocker causal-outcome maturity changes."""
    before_outcomes = _mapping(before.get("signal_outcomes"), "before signal outcomes")
    after_outcomes = _mapping(after.get("signal_outcomes"), "after signal outcomes")
    before_providers = _mapping(
        before_outcomes.get("by_provider_symbol"), "before provider outcomes"
    )
    after_providers = _mapping(
        after_outcomes.get("by_provider_symbol"), "after provider outcomes"
    )
    before_ids = {_text(key, "before provider identity") for key in before_providers}
    after_ids = {_text(key, "after provider identity") for key in after_providers}
    changed = [
        row
        for key in sorted(before_ids & after_ids)
        if (row := _provider_delta(key, before_providers, after_providers))
    ]
    return {
        "evaluations_delta": _cumulative_delta(
            before_outcomes, after_outcomes, "evaluations"
        ),
        "eligible_evaluations_delta": _cumulative_delta(
            before_outcomes, after_outcomes, "eligible_evaluations"
        ),
        "directional_evaluations_delta": _cumulative_delta(
            before_outcomes, after_outcomes, "directional_evaluations"
        ),
        "providers_added": sorted(after_ids - before_ids),
        "providers_removed": sorted(before_ids - after_ids),
        "changed_providers": changed,
        "newly_matured_paths": any(_has_new_maturity(row) for row in changed),
        "portfolio_opportunity_maturity": _portfolio_opportunity_delta(
            before_outcomes, after_outcomes
        ),
    }


def _portfolio_opportunity_delta(before: Record, after: Record) -> dict[str, object]:
    before_value = _optional_mapping(before.get("portfolio_opportunity_dedup"))
    after_value = _optional_mapping(after.get("portfolio_opportunity_dedup"))
    if before_value is None or after_value is None:
        return {
            "comparable": False,
            "newly_available": before_value is None and after_value is not None,
            "reason": _portfolio_unavailable_reason(before_value, after_value),
        }
    horizons = _horizon_deltas(
        _mapping(before_value.get("horizons"), "before portfolio horizons"),
        _mapping(after_value.get("horizons"), "after portfolio horizons"),
    )
    result: dict[str, object] = {
        "comparable": True,
        "horizons": horizons,
        "episode_attribution_maturity": _episode_attribution_delta(
            before_value, after_value
        ),
        "newly_matured_unique_paths": any(
            _mapping(value, "portfolio horizon delta").get("resolved_delta", 0) > 0
            for value in horizons.values()
        ),
    }
    result.update(
        {
            f"{field}_delta": _cumulative_delta(before_value, after_value, field)
            for field in _PORTFOLIO_FIELDS
        }
    )
    return result


def _episode_attribution_delta(before: Record, after: Record) -> dict[str, object]:
    before_rows = _optional_list(before.get("by_attribution"), "before attribution")
    after_rows = _optional_list(after.get("by_attribution"), "after attribution")
    before_available = _episode_schema_available(before_rows)
    after_available = _episode_schema_available(after_rows)
    if not before_available or not after_available:
        return {
            "comparable": False,
            "newly_available": not before_available and after_available,
            "reason": _episode_unavailable_reason(before_available, after_available),
        }
    before_index = _attribution_index(before_rows or [], "before")
    after_index = _attribution_index(after_rows or [], "after")
    added = sorted(set(after_index) - set(before_index), key=_attribution_sort_key)
    removed = sorted(set(before_index) - set(after_index), key=_attribution_sort_key)
    changed = _changed_attributions(before_index, after_index)
    return {
        "comparable": True,
        "attributions_added": [_attribution_identity(key) for key in added],
        "attributions_removed": [_attribution_identity(key) for key in removed],
        "changed_attributions": changed,
        "newly_matured_episode_onsets": any(
            _attribution_has_new_path(row) for row in changed
        ),
    }


def _episode_schema_available(rows: list[object] | None) -> bool:
    if rows is None:
        return False
    for value in rows:
        row = _mapping(value, "attribution row")
        cadence = _mapping(row.get("decision_cadence"), "attribution cadence")
        if "episode_count" not in cadence:
            return False
        horizons = _mapping(row.get("horizons"), "attribution horizons")
        if any(
            "episode_onsets" not in _mapping(item, "attribution horizon")
            for item in horizons.values()
        ):
            return False
    return True


def _episode_unavailable_reason(before: bool, after: bool) -> str:
    if not before and not after:
        return "episode_attribution_absent_in_both_prefixes"
    if not before:
        return "episode_attribution_absent_in_before_prefix"
    return "episode_attribution_absent_in_after_prefix"


def _attribution_index(rows: list[object], label: str) -> dict[AttributionKey, Record]:
    result: dict[AttributionKey, Record] = {}
    for value in rows:
        row = _mapping(value, f"{label} attribution row")
        key = _attribution_key(row, label)
        if key in result:
            raise ValueError(f"duplicate {label} attribution identity")
        result[key] = row
    return result


def _attribution_key(row: Record, label: str) -> AttributionKey:
    source_run_id = _optional_text(row.get("source_run_id"), f"{label} source run")
    providers = _list(row.get("providers"), f"{label} providers")
    members = tuple(
        sorted(
            (
                _text(_mapping(value, "provider").get("strategy_id"), "strategy id"),
                _text(_mapping(value, "provider").get("blocker"), "blocker"),
            )
            for value in providers
        )
    )
    return (
        source_run_id,
        _text(row.get("symbol"), f"{label} symbol"),
        _text(row.get("side"), f"{label} side"),
        members,
    )


def _changed_attributions(
    before: Mapping[AttributionKey, Record], after: Mapping[AttributionKey, Record]
) -> list[dict[str, object]]:
    changed: list[dict[str, object]] = []
    for key in sorted(after, key=_attribution_sort_key):
        row = _attribution_delta(key, before.get(key), after[key])
        if _record_changed(row):
            changed.append(row)
    return changed


def _attribution_delta(
    key: AttributionKey, before: Record | None, after: Record
) -> dict[str, object]:
    prior = before or {}
    before_cadence = _optional_mapping(prior.get("decision_cadence")) or {}
    after_cadence = _mapping(after.get("decision_cadence"), "after cadence")
    return {
        "identity": _attribution_identity(key),
        "path_groups_delta": _cumulative_delta(
            prior, after, "path_groups", default_zero=before is None
        ),
        "decision_minutes_delta": _cumulative_delta(
            before_cadence,
            after_cadence,
            "decision_minutes",
            default_zero=before is None,
        ),
        "episode_count_delta": _cumulative_delta(
            before_cadence,
            after_cadence,
            "episode_count",
            default_zero=before is None,
        ),
        "horizons": _episode_horizon_deltas(key, prior, after),
    }


def _episode_horizon_deltas(
    key: AttributionKey, before: Record, after: Record
) -> dict[str, object]:
    before_horizons = _optional_mapping(before.get("horizons")) or {}
    after_horizons = _mapping(after.get("horizons"), "after attribution horizons")
    result: dict[str, object] = {}
    for horizon in sorted(set(before_horizons) | set(after_horizons), key=int):
        before_row = _optional_mapping(before_horizons.get(horizon)) or {}
        after_row = _mapping(after_horizons.get(horizon), "after attribution horizon")
        before_episode = _optional_mapping(before_row.get("episode_onsets")) or {}
        after_episode = _mapping(
            after_row.get("episode_onsets"), "after episode onsets"
        )
        counts = _horizon_deltas({horizon: before_episode}, {horizon: after_episode})
        row = dict(_optional_mapping(counts.get(horizon)) or {})
        new_paths = _new_independent_paths(key, before_episode, after_episode)
        if new_paths:
            row["new_independent_paths"] = new_paths
        if row:
            result[_text(horizon, "episode horizon")] = row
    return result


def _new_independent_paths(
    key: AttributionKey, before: Record, after: Record
) -> list[dict[str, object]]:
    before_index = _path_index(before.get("independent_paths", []), key, "before")
    after_index = _path_index(after.get("independent_paths", []), key, "after")
    if set(before_index) - set(after_index):
        raise ValueError("resolved episode path cannot disappear")
    if any(before_index[path] != after_index[path] for path in before_index):
        raise ValueError("resolved episode path cannot change")
    added = sorted(set(after_index) - set(before_index), key=_path_sort_key)
    return [dict(after_index[path_key]) for path_key in added]


def _path_index(
    value: object, attribution: AttributionKey, label: str
) -> dict[PathKey, Record]:
    result: dict[PathKey, Record] = {}
    for item in _list(value, f"{label} independent paths"):
        row = _mapping(item, f"{label} independent path")
        source_run_id = _optional_text(row.get("source_run_id"), "path source run")
        if source_run_id != attribution[0]:
            raise ValueError("episode path source run must match attribution")
        path_key = (
            source_run_id,
            _nonnegative_int(row.get("decision_time_ms"), "path decision time"),
        )
        if path_key in result:
            raise ValueError(f"duplicate {label} episode path identity")
        result[path_key] = row
    return result


def _attribution_identity(key: AttributionKey) -> dict[str, object]:
    source_run_id, symbol, side, providers = key
    return {
        "source_run_id": source_run_id,
        "symbol": symbol,
        "side": side,
        "providers": [
            {"strategy_id": strategy_id, "blocker": blocker}
            for strategy_id, blocker in providers
        ],
    }


def _attribution_has_new_path(row: Record) -> bool:
    horizons = _mapping(row.get("horizons"), "attribution horizon changes")
    return any(
        bool(_mapping(value, "attribution horizon delta").get("new_independent_paths"))
        for value in horizons.values()
    )


def _attribution_sort_key(key: AttributionKey) -> tuple[object, ...]:
    return key[0] or "", key[1], key[2], key[3]


def _path_sort_key(key: PathKey) -> tuple[str, int]:
    return key[0] or "", key[1]


def _portfolio_unavailable_reason(before: Record | None, after: Record | None) -> str:
    if before is None and after is None:
        return "portfolio_dedup_absent_in_both_prefixes"
    if before is None:
        return "portfolio_dedup_absent_in_before_prefix"
    return "portfolio_dedup_absent_in_after_prefix"


def _provider_delta(
    identity: str, before: Record, after: Record
) -> dict[str, object] | None:
    before_provider = _mapping(before.get(identity), f"before provider {identity}")
    after_provider = _mapping(after.get(identity), f"after provider {identity}")
    result: dict[str, object] = {"provider_symbol": identity}
    for field in ("evaluations", "eligible_evaluations", "readiness_annotations"):
        result[f"{field}_delta"] = _cumulative_delta(
            before_provider, after_provider, field
        )
    result["horizons"] = _horizon_deltas(
        _mapping(before_provider.get("horizons"), "before provider horizons"),
        _mapping(after_provider.get("horizons"), "after provider horizons"),
    )
    result["one_blocker_changes"] = _one_blocker_deltas(before_provider, after_provider)
    return result if _record_changed(result) else None


def _one_blocker_deltas(before: Record, after: Record) -> list[dict[str, object]]:
    before_section = _mapping(
        before.get("one_blocker_near_misses"), "before one-blocker section"
    )
    after_section = _mapping(
        after.get("one_blocker_near_misses"), "after one-blocker section"
    )
    before_rows = _mapping(before_section.get("by_blocker"), "before blockers")
    after_rows = _mapping(after_section.get("by_blocker"), "after blockers")
    changes: list[dict[str, object]] = []
    for blocker in sorted(set(before_rows) | set(after_rows)):
        before_row = _optional_mapping(before_rows.get(blocker)) or {}
        after_row = _optional_mapping(after_rows.get(blocker)) or {}
        row = {
            "blocker": _text(blocker, "blocker"),
            "evaluations_delta": _cumulative_delta(
                before_row, after_row, "evaluations", default_zero=True
            ),
            "horizons": _horizon_deltas(
                _optional_mapping(before_row.get("horizons")) or {},
                _optional_mapping(after_row.get("horizons")) or {},
            ),
        }
        if _record_changed(row):
            changes.append(row)
    return changes


def _horizon_deltas(before: Record, after: Record) -> dict[str, object]:
    result: dict[str, object] = {}
    direct_fields = {"resolved", "non_overlapping_resolved", "censored"}
    for horizon in sorted(set(before) | set(after), key=int):
        before_row = _optional_mapping(before.get(horizon)) or {}
        after_row = _optional_mapping(after.get(horizon)) or {}
        before_capture = _optional_mapping(before_row.get("opportunity_capture")) or {}
        after_capture = _optional_mapping(after_row.get("opportunity_capture")) or {}
        before_independent = (
            _optional_mapping(before_row.get("independent_opportunity_capture")) or {}
        )
        after_independent = (
            _optional_mapping(after_row.get("independent_opportunity_capture")) or {}
        )
        row = {
            f"{field}_delta": _count_delta(
                before_row if field in direct_fields else before_capture,
                after_row if field in direct_fields else after_capture,
                field,
            )
            for field in _HORIZON_FIELDS
        }
        row.update(
            {
                f"independent_{field}_delta": _count_delta(
                    before_independent, after_independent, field
                )
                for field in _CAPTURE_FIELDS
            }
        )
        if any(_nonzero(value) for value in row.values()):
            result[_text(horizon, "horizon")] = row
    return result


def _has_new_maturity(provider: Record) -> bool:
    groups = [_mapping(provider.get("horizons"), "provider horizons")]
    blockers = provider.get("one_blocker_changes")
    if not isinstance(blockers, list):
        raise TypeError("one-blocker changes must be a list")
    groups.extend(
        _mapping(_mapping(row, "blocker change").get("horizons"), "blocker horizons")
        for row in blockers
    )
    return any(
        _mapping(value, "horizon delta").get("resolved_delta", 0) > 0
        for group in groups
        for value in group.values()
    )


def _record_changed(row: Record) -> bool:
    return any(
        (_nonzero(value) if key.endswith("_delta") else bool(value))
        for key, value in row.items()
        if key not in {"provider_symbol", "blocker", "identity"}
    )


def _integer_delta(before: Record, after: Record, field: str) -> int:
    return _nonnegative_int(after.get(field), f"after {field}") - _nonnegative_int(
        before.get(field), f"before {field}"
    )


def _cumulative_delta(
    before: Record, after: Record, field: str, *, default_zero: bool = False
) -> int:
    delta = (
        _count_delta(before, after, field)
        if default_zero
        else _integer_delta(before, after, field)
    )
    if delta < 0:
        raise ValueError(f"{field} cannot move backwards")
    return delta


def _count_delta(before: Record, after: Record, field: str) -> int:
    return _nonnegative_int(after.get(field, 0), f"after {field}") - _nonnegative_int(
        before.get(field, 0), f"before {field}"
    )


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _nonzero(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_mapping(value: object) -> Record | None:
    return None if value is None else _mapping(value, "optional mapping")


def _optional_list(value: object, label: str) -> list[object] | None:
    return None if value is None else _list(value, label)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value
