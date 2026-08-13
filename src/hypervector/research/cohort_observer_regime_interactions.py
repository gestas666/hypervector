"""Route-specific regime interactions from authority-none observer replays."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from math import isfinite
from statistics import median

_FEATURE_FIELDS = (
    "primary_regime",
    "state_1m",
    "state_5m",
    "context_15m",
    "structural_direction",
)
_DIRECTIONAL_STATES = {"TREND_UP": 1, "TREND_DOWN": -1}


def build_observer_regime_interactions(
    reports: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Aggregate exact entry states without creating execution authority."""
    if not reports:
        raise ValueError("at least one observer report is required")
    identities = [_report_identity(report) for report in reports]
    if len(set(identities)) != 1:
        raise ValueError("all reports must use the same observer run and profile")
    routes = [_route_interactions(report) for report in reports]
    run_id, fingerprint = identities[0]
    return {
        "schema_version": 1,
        "mode": "observer_regime_interaction_diagnostic",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_change": False,
        "source_run_id": run_id,
        "effective_profile_fingerprint": fingerprint,
        "routes": routes,
        "limitations": [
            "groups are descriptive and may contain very small samples",
            "fixed-horizon counterfactual returns are not live fills or PnL",
            "the diagnostic does not create an entry, exit, sizing, or leverage gate",
        ],
    }


def _report_identity(report: Mapping[str, object]) -> tuple[str, str]:
    _require_authority_none(report)
    source = _mapping(report.get("source"), "source")
    run_id = _text(source.get("selected_run_id"), "selected run id")
    fingerprint = _text(
        source.get("effective_profile_fingerprint"),
        "effective profile fingerprint",
    )
    return run_id, fingerprint


def _require_authority_none(report: Mapping[str, object]) -> None:
    valid = (
        report.get("report_only") is True
        and report.get("execution_authority") == "none"
        and report.get("runtime_strategy_changed") is False
    )
    if not valid:
        raise ValueError("observer interaction input must be authority-none")


def _route_interactions(report: Mapping[str, object]) -> dict[str, object]:
    contract = _mapping(report.get("contract"), "contract")
    rows = _resolved_rows(report)
    return {
        "strategy_id": _text(contract.get("strategy_id"), "strategy id"),
        "symbol": _text(contract.get("symbol"), "symbol"),
        "blocker": _text(contract.get("blocker"), "blocker"),
        "horizon_minutes": _positive_int(
            contract.get("horizon_minutes"), "horizon minutes"
        ),
        "resolved": len(rows),
        "by_context_15m_relation": _relation_groups(rows, "context_15m"),
        "by_state_5m_relation": _relation_groups(rows, "state_5m"),
        "by_state_1m_relation": _relation_groups(rows, "state_1m"),
        "by_exact_entry_state": _exact_state_groups(rows),
    }


def _resolved_rows(report: Mapping[str, object]) -> list[dict[str, object]]:
    raw = report.get("executions")
    if not isinstance(raw, list):
        raise ValueError("executions must be a list")
    rows: list[dict[str, object]] = []
    for item in raw:
        row = _mapping(item, "execution")
        if row.get("status") != "resolved":
            continue
        side = _text(row.get("side"), "execution side")
        if side not in {"long", "short"}:
            raise ValueError("execution side must be long or short")
        features = _entry_features(row)
        rows.append(
            {
                "side": side,
                "net_return_bps": _finite_number(
                    row.get("net_return_bps"), "net return bps"
                ),
                **features,
            }
        )
    return rows


def _entry_features(row: Mapping[str, object]) -> dict[str, str]:
    source = _mapping(row.get("entry_features"), "entry features")
    return {field: _text(source.get(field), field) for field in _FEATURE_FIELDS}


def _relation_groups(
    rows: Sequence[Mapping[str, object]], field: str
) -> dict[str, dict[str, int | float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        relation = _direction_relation(
            _text(row[field], field), _text(row["side"], "side")
        )
        grouped[relation].append(
            _finite_number(row["net_return_bps"], "net return bps")
        )
    return {key: _metrics(values) for key, values in sorted(grouped.items())}


def _exact_state_groups(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in rows:
        key = tuple(_text(row[field], field) for field in _FEATURE_FIELDS)
        grouped[key].append(_finite_number(row["net_return_bps"], "net return bps"))
    return [_state_payload(key, values) for key, values in sorted(grouped.items())]


def _state_payload(key: tuple[str, ...], values: Sequence[float]) -> dict[str, object]:
    payload: dict[str, object] = dict(zip(_FEATURE_FIELDS, key, strict=True))
    payload["metrics"] = _metrics(values)
    return payload


def _direction_relation(state: str, side: str) -> str:
    state_sign = _DIRECTIONAL_STATES.get(state)
    if state_sign is None:
        return "non_directional"
    side_sign = 1 if side == "long" else -1
    return "aligned" if state_sign == side_sign else "opposed"


def _metrics(values: Sequence[float]) -> dict[str, int | float]:
    total = sum(values)
    largest_winner = max((value for value in values if value > 0.0), default=0.0)
    return {
        "resolved": len(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value < 0.0 for value in values),
        "total_net_return_bps": total,
        "mean_net_return_bps": total / len(values),
        "median_net_return_bps": median(values),
        "net_excluding_largest_winner_bps": total - largest_winner,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value
