"""Canonical V58 context for exact active-route lifecycle collectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_active_route_lifecycle_status import (
    load_active_route_lifecycle_statuses,
)
from hypervector.research.v58_future_only_experiment_context import (
    V58FutureOnlyExperimentContext,
    attach_v58_future_only_experiment_context,
    load_v58_future_only_experiment_context,
)

Record = Mapping[str, object]

_ROUTES = frozenset(
    {
        "hulk_expansion_short_robust_v3|BTC",
        "hulk_expansion_short_tuned_v2|BTC",
        "hulk_expansion_bidirectional_tuned_v2|SOL",
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK",
    }
)


@dataclass(frozen=True)
class V58RouteLifecycleItem:
    """Normalized evidence for one exact configured V58 route collector."""

    route: str
    symbol: str
    state: str
    pending: int
    resolved: int
    unresolved: int
    source_age_seconds: float
    evidence: dict[str, object]

    @property
    def technical_complete(self) -> bool:
        """Return whether every observed closed lifecycle is resolved."""
        return self.unresolved == 0


@dataclass(frozen=True)
class V58ActiveRouteContext:
    """Validated exact-route statuses and their frozen source evidence."""

    items: tuple[V58RouteLifecycleItem, ...]
    statuses: tuple[dict[str, object], ...]
    evidence: dict[str, object]
    execution_authority: str
    experiments: V58FutureOnlyExperimentContext | None = None


def load_v58_active_route_lifecycle_context(
    overrides_path: Path,
    checkpoint_path: Path,
    *,
    project_root: Path,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> V58ActiveRouteContext:
    """Load every remaining V58 collector through the shared exact validator."""
    overrides = _json_mapping(overrides_path, "V58 route collector overrides")
    _require_overrides(overrides)
    checkpoint = _json_mapping(checkpoint_path, "V58 live checkpoint")
    audit = _mapping(checkpoint.get("audit"), "V58 checkpoint audit")
    collection = load_active_route_lifecycle_statuses(
        overrides,
        audit,
        overrides_path=overrides_path,
        project_root=project_root,
        observed_at=observed_at,
        maximum_age_seconds=maximum_age_seconds,
    )
    items = tuple(_item(status, collection.evidence) for status in collection.statuses)
    _require_route_set(item.route for item in items)
    evidence = {
        "overrides": _path_evidence(overrides_path),
        "checkpoint": _path_evidence(checkpoint_path),
        "statuses": dict(collection.evidence),
    }
    experiments = load_v58_future_only_experiment_context(
        overrides,
        audit,
        overrides_path=overrides_path,
        project_root=project_root,
        observed_at=observed_at,
        maximum_age_seconds=maximum_age_seconds,
    )
    return V58ActiveRouteContext(
        items, tuple(collection.statuses), evidence, "none", experiments
    )


def attach_v58_active_route_lifecycle_context(
    report: dict[str, object], context: V58ActiveRouteContext
) -> None:
    """Attach exact route collectors without changing strategy authority."""
    _require_report(report, context)
    ledger = _mutable_rows(report.get("hypothesis_ledger"), "hypothesis ledger")
    coverage = _mapping(report.get("lifecycle_capture_coverage"), "coverage")
    captures = _mutable_rows(coverage.get("routes"), "capture routes")
    lifecycles = _mapping(
        _mapping(report.get("evidence"), "evidence").get("lifecycles"),
        "lifecycle evidence",
    )
    for item in context.items:
        _attach_item(item, ledger, captures, lifecycles)
    coverage["watcher_count"] = sum(
        row.get("watcher_attached") is True for row in captures
    )
    coverage["eligible_without_exact_capture"] = sum(
        row.get("status") == "eligible_without_exact_lifecycle_capture"
        for row in captures
    )
    report["active_route_lifecycle_context"] = {
        "statuses": [dict(row) for row in context.statuses],
        "execution_authority": "none",
        "automatic_live_change": False,
    }
    _mapping(report.get("evidence"), "evidence")["active_route_lifecycle_context"] = (
        dict(context.evidence)
    )
    if context.experiments is not None:
        attach_v58_future_only_experiment_context(report, context.experiments)


def _item(status: Record, evidence: Record) -> V58RouteLifecycleItem:
    route = _text(status.get("route"), "route")
    source = _mapping(
        evidence.get(_text(status.get("hypothesis_id"), "hypothesis id")),
        "route evidence",
    )
    return V58RouteLifecycleItem(
        route=route,
        symbol=_text(status.get("symbol"), "symbol"),
        state=_text(status.get("state"), "state"),
        pending=_count(status.get("open_lifecycles"), "open lifecycles"),
        resolved=_count(status.get("resolved_lifecycles"), "resolved lifecycles"),
        unresolved=_count(status.get("unresolved_lifecycles"), "unresolved lifecycles"),
        source_age_seconds=_number(status.get("age_seconds"), "source age"),
        evidence=dict(source),
    )


def _attach_item(
    item: V58RouteLifecycleItem,
    ledger: list[dict[str, object]],
    captures: list[dict[str, object]],
    evidence: dict[str, object],
) -> None:
    row = _one_route(ledger, item.route, "hypothesis ledger")
    row.update(
        {
            "status": _status(item),
            "watch_state": item.state,
            "pending_lifecycles": item.pending,
            "resolved_lifecycles": item.resolved,
            "technical_complete": item.technical_complete,
            "source_age_seconds": item.source_age_seconds,
            "evidence_state": _evidence_state(item),
            "automatic_live_change": False,
        }
    )
    capture = _one_route(captures, item.route, "capture coverage")
    capture.update(
        {"watcher_attached": True, "status": "exact_lifecycle_watcher_attached"}
    )
    if item.route in evidence:
        raise ValueError("V58 active route lifecycle evidence is duplicated")
    evidence[item.route] = dict(item.evidence)


def _status(item: V58RouteLifecycleItem) -> str:
    if not item.technical_complete:
        return "technically_censored"
    return "resolved_review_due" if item.resolved else "being_tested"


def _evidence_state(item: V58RouteLifecycleItem) -> str:
    if item.resolved:
        return "resolved_exact_live_lifecycle"
    if item.pending:
        return "open_exact_live_lifecycle"
    return "awaiting_first_eligible_signal"


def _require_report(report: Record, context: V58ActiveRouteContext) -> None:
    contract = _mapping(report.get("contract"), "report contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 continuous report authority differs")
    if context.execution_authority != "none":
        raise ValueError("V58 active route context has execution authority")
    _require_route_set(item.route for item in context.items)


def _require_overrides(payload: Record) -> None:
    expected = {"schema_version": 1, "mode": "v58_active_route_lifecycle_collectors"}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 active route collector override identity differs")
    contract = _mapping(payload.get("contract"), "collector override contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("V58 active route collector overrides have authority")


def _require_route_set(routes: object) -> None:
    observed = set(routes)
    if observed != _ROUTES:
        raise ValueError("V58 active route collector set is incomplete or aliased")


def _one_route(
    rows: list[dict[str, object]], route: str, label: str
) -> dict[str, object]:
    matches = [row for row in rows if row.get("route") == route]
    if len(matches) != 1:
        raise ValueError(f"V58 {label} route is missing or duplicated")
    return matches[0]


def _mutable_rows(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"V58 {label} must contain mutable objects")
    return value


def _json_mapping(path: Path, label: str) -> Record:
    return _mapping(json.loads(path.read_bytes()), label)


def _path_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 {label} must be nonnegative")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    output = float(value)
    if output < 0.0:
        raise ValueError(f"V58 {label} must be nonnegative")
    return output
