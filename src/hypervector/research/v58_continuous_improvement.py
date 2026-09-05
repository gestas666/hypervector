"""Current report-only improvement state for the isolated V58 observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.report_only_lifecycle_watch import validate_watch_snapshot
from hypervector.research.v58_btc_sweep_status import (
    load_v58_btc_sweep_lifecycle_status,
)
from hypervector.research.v58_eth_censored_context import (
    current_eth_lifecycle_complete,
)
from hypervector.research.v58_hypothesis_ledger import complete_hypothesis_ledger
from hypervector.research.v58_lifecycle_capture import (
    highest_value_investigation,
    lifecycle_capture_coverage,
)
from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)
from hypervector.research.v58_route_opportunity import (
    RouteOpportunity as RouteOpportunity,
    RouteOpportunityCollection,
    opportunity_row,
    parse_route_opportunity,
    require_opportunity_routes,
)

Record = Mapping[str, object]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_BTC_ROUTE = "liquidity_sweep_long_1h_stop60_target60_v2|BTC"
_SP500_ROUTE = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
_DEPTH_ROUTES = {
    "ETH": "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
    "HYPE": "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
}
_ROUTES = (
    "hulk_expansion_short_robust_v3|BTC",
    "hulk_expansion_short_tuned_v2|BTC",
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
    _DEPTH_ROUTES["ETH"],
    "hulk_expansion_bidirectional_tuned_v2|SOL",
    _DEPTH_ROUTES["HYPE"],
    _SP500_ROUTE,
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK",
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
)


@dataclass(frozen=True)
class LifecycleEvidence:
    """Normalized state and exact bytes for one prospective lifecycle lane."""

    symbol: str
    route: str
    state: str
    pending: int
    resolved: int
    technical_complete: bool
    source_age_seconds: float
    evidence: dict[str, object]


@dataclass(frozen=True)
class V58LifecycleSources:
    """Mutable status paths consumed by one V58 consolidation cycle."""

    btc: Path
    eth: Path
    hype: Path
    sp500: Path


def load_v58_lifecycle_evidence(
    sources: V58LifecycleSources,
    *,
    observer_status: Record,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> tuple[LifecycleEvidence, ...]:
    """Load fresh, execution-incapable lifecycle statuses for exact V58."""
    _require_aware(observed_at)
    _require_positive(maximum_age_seconds, "maximum lifecycle age")
    _require_observer_identity(observer_status)
    run_id = _text(observer_status.get("run_id"), "observer run id")
    profile = _text(observer_status.get("profile_fingerprint"), "observer profile")
    btc = load_v58_btc_sweep_lifecycle_status(
        sources.btc,
        observer_run_id=run_id,
        observer_profile_fingerprint=profile,
        observed_at=observed_at,
        maximum_age_seconds=maximum_age_seconds,
    )
    return (
        LifecycleEvidence(
            "BTC",
            _BTC_ROUTE,
            btc.state,
            btc.pending,
            btc.resolved,
            btc.technical_complete,
            btc.source_age_seconds,
            btc.evidence,
        ),
        _load_depth_status(
            sources.eth, "ETH", run_id, profile, observed_at, maximum_age_seconds
        ),
        _load_depth_status(
            sources.hype, "HYPE", run_id, profile, observed_at, maximum_age_seconds
        ),
        _load_sp500_status(sources.sp500, observed_at, maximum_age_seconds),
    )


def load_v58_route_opportunities(
    path: Path, *, observer_status: Record
) -> RouteOpportunityCollection:
    """Load all exact route setup states without interpreting readiness as edge."""
    _require_observer_identity(observer_status)
    payload, evidence = _read_source(path, "V58 observer checkpoint")
    audit = _mapping(payload.get("audit"), "V58 observer audit")
    _require_route_observer_run(
        _mapping(audit.get("run"), "V58 observer run"), observer_status
    )
    readiness = _mapping(audit.get("readiness"), "V58 observer readiness")
    rows = _mapping(readiness.get("by_provider_symbol"), "V58 route readiness")
    scorecard = _mapping(audit.get("strategy_scorecard"), "V58 scorecard")
    scores = _mapping(scorecard.get("by_provider_symbol"), "V58 route scorecard")
    if set(rows) != set(_ROUTES) or set(scores) != set(_ROUTES):
        raise ValueError("V58 opportunity route set is incomplete or aliased")
    opportunities = tuple(
        parse_route_opportunity(route, rows[route], scores[route]) for route in _ROUTES
    )
    return RouteOpportunityCollection(opportunities, evidence)


def build_v58_continuous_improvement(
    observer: SuccessorObserverEvidence,
    btc: LifecycleEvidence,
    eth: LifecycleEvidence,
    hype: LifecycleEvidence,
    sp500: LifecycleEvidence,
    opportunities: RouteOpportunityCollection,
    *,
    generated_at: datetime,
) -> dict[str, object]:
    """Build one current hypothesis ledger without execution authority."""
    _require_aware(generated_at)
    _require_observer_identity(observer.status)
    lifecycles = _require_lifecycle_set((btc, eth, hype, sp500))
    routes = require_opportunity_routes(opportunities, _ROUTES)
    capture = lifecycle_capture_coverage(lifecycles, routes)
    ledger = complete_hypothesis_ledger(
        [_ledger_row(item) for item in lifecycles], routes
    )
    return {
        "schema_version": 1,
        "mode": "v58_continuous_improvement_report",
        "generated_at_utc": generated_at.astimezone(UTC).isoformat(),
        "contract": _report_contract(),
        "observer": dict(observer.status),
        "hypothesis_ledger": ledger,
        "opportunity_pipeline": [opportunity_row(item) for item in routes],
        "lifecycle_capture_coverage": capture,
        "highest_value_next_investigation": highest_value_investigation(
            lifecycles, routes
        ),
        "assessment": {
            "automatic_live_change": False,
            "evidence_sufficient_for_change": False,
            "recommendation": "continue_frozen_prospective_resolution",
        },
        "change_proposals": [],
        "human_approval_boundary": _approval_boundary(),
        "evidence": {
            "observer": dict(observer.evidence),
            "lifecycles": {item.route: dict(item.evidence) for item in lifecycles},
            "route_opportunities": dict(opportunities.evidence),
        },
    }


def _load_depth_status(
    path: Path,
    symbol: str,
    run_id: str,
    profile: str,
    observed_at: datetime,
    maximum_age: float,
) -> LifecycleEvidence:
    payload, evidence = _read_source(path, f"{symbol} lifecycle")
    _require_depth_contract(payload, symbol, run_id, profile)
    age = _source_age(payload.get("observed_at_utc"), observed_at, maximum_age)
    summary = _mapping(payload.get("summary"), f"{symbol} lifecycle summary")
    pending = _nonnegative_integer(summary.get("pending"), f"{symbol} pending")
    resolved = _nonnegative_integer(summary.get("resolved"), f"{symbol} resolved")
    incomplete = _nonnegative_integer(
        summary.get("technical_incomplete"), f"{symbol} incomplete"
    )
    snapshot = _require_snapshot_state(payload, resolved, symbol)
    if snapshot is not None:
        evidence = {**evidence, "resolved_snapshot": snapshot}
    return LifecycleEvidence(
        symbol=symbol,
        route=_DEPTH_ROUTES[symbol],
        state=_text(payload.get("watch_state"), f"{symbol} watch state"),
        pending=pending,
        resolved=resolved,
        technical_complete=(
            incomplete == 0
            or symbol == "ETH"
            and current_eth_lifecycle_complete(payload, summary)
        ),
        source_age_seconds=age,
        evidence=evidence,
    )


def _require_depth_contract(
    payload: Record, symbol: str, run_id: str, profile: str
) -> None:
    expected = {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError(f"{symbol} lifecycle source contract is invalid")
    contract = _mapping(payload.get("contract"), f"{symbol} lifecycle contract")
    safe = {
        "report_only": True,
        "execution_authority": "none",
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": False,
        "source_run_id": run_id,
        "source_strategy_id": _DEPTH_ROUTES[symbol].split("|", 1)[0],
        "symbol": symbol,
    }
    if any(contract.get(field) != value for field, value in safe.items()):
        raise ValueError(f"{symbol} lifecycle authority or identity is invalid")
    identity = _mapping(payload.get("identity"), f"{symbol} lifecycle identity")
    if any(
        identity.get(field) != value
        for field, value in (
            ("profile_id", _PROFILE_ID),
            ("profile_fingerprint", profile),
            ("source_run_id", run_id),
        )
    ):
        raise ValueError(f"{symbol} lifecycle observer identity is invalid")


def _load_sp500_status(
    path: Path, observed_at: datetime, maximum_age: float
) -> LifecycleEvidence:
    payload, evidence = _read_source(path, "SP500 lifecycle")
    expected = {
        "schema_version": "sp500_fresh15_lifecycle_watch_status_v1",
        "symbol": "xyz:SP500",
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "signing_client_constructed": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError("SP500 lifecycle authority or identity is invalid")
    timestamp = _nonnegative_integer(payload.get("observed_at_ms"), "SP500 observed")
    age = _source_age(timestamp / 1000.0, observed_at, maximum_age)
    nominal = _mapping(payload.get("nominal"), "SP500 nominal")
    summary = _mapping(nominal.get("summary"), "SP500 nominal summary")
    resolved = _nonnegative_integer(summary.get("resolved"), "SP500 resolved")
    technical = _mapping(payload.get("technical_assessment"), "SP500 technical")
    complete = technical.get("all_observed_paths_resolved") is True
    return LifecycleEvidence(
        symbol="xyz:SP500",
        route=_SP500_ROUTE,
        state=_text(payload.get("watch_state"), "SP500 watch state"),
        pending=0 if resolved else 1,
        resolved=resolved,
        technical_complete=complete,
        source_age_seconds=age,
        evidence=evidence,
    )


def _require_route_observer_run(run: Record, observer: Record) -> None:
    expected = {
        "profile_id": observer.get("profile_id"),
        "profile_fingerprint": observer.get("profile_fingerprint"),
        "run_id": observer.get("run_id"),
    }
    if any(run.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 opportunity observer identity is invalid")


def _ledger_row(item: LifecycleEvidence) -> dict[str, object]:
    state = "resolved_review_due" if item.resolved else "being_tested"
    if not item.technical_complete:
        state = "technically_censored"
    return {
        "route": item.route,
        "symbol": item.symbol,
        "status": state,
        "watch_state": item.state,
        "pending_lifecycles": item.pending,
        "resolved_lifecycles": item.resolved,
        "technical_complete": item.technical_complete,
        "source_age_seconds": item.source_age_seconds,
        "automatic_live_change": False,
    }


def _require_lifecycle_set(
    items: Sequence[LifecycleEvidence],
) -> tuple[LifecycleEvidence, ...]:
    output = tuple(items)
    expected = {"BTC", "ETH", "HYPE", "xyz:SP500"}
    if {item.symbol for item in output} != expected or len(output) != len(expected):
        raise ValueError("V58 lifecycle set is incomplete or duplicated")
    routes = {"BTC": _BTC_ROUTE, **_DEPTH_ROUTES, "xyz:SP500": _SP500_ROUTE}
    if any(item.route != routes[item.symbol] for item in output):
        raise ValueError("V58 lifecycle route identity is invalid")
    if any(item.pending < 0 or item.resolved < 0 for item in output):
        raise ValueError("V58 lifecycle counts must be nonnegative")
    return output


def _require_observer_identity(status: Record) -> None:
    expected = {
        "profile_id": _PROFILE_ID,
        "freshness_status": "fresh",
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 observer identity or authority is invalid")
    require_reportable_v58_observer_status(status, "V58 observer")


def _read_source(path: Path, label: str) -> tuple[Record, dict[str, object]]:
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), label)
    evidence = {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    return payload, evidence


def _source_age(value: object, observed_at: datetime, maximum_age: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = datetime.fromtimestamp(float(value), tz=UTC)
    else:
        text = _text(value, "lifecycle observation time")
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    age = (observed_at.astimezone(UTC) - timestamp).total_seconds()
    if age < 0.0:
        raise ValueError("V58 lifecycle status is from the future")
    if age > maximum_age:
        raise ValueError("V58 lifecycle status is stale")
    return age


def _require_snapshot_state(
    payload: Record, resolved: int, symbol: str
) -> dict[str, object] | None:
    value = payload.get("snapshot")
    if resolved and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{symbol} resolved lifecycle snapshot is missing")
    if resolved:
        return validate_watch_snapshot(Path(value), payload)
    if not resolved and value is not None:
        raise ValueError(f"{symbol} unresolved lifecycle has a snapshot")
    return None


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }


def _approval_boundary() -> dict[str, object]:
    return {
        "approval_requested": False,
        "required_before_live_change": True,
        "scope": "strategy_asset_route_parameter_leverage_sizing_risk_execution_deployment",
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("V58 improvement timestamp must be timezone-aware")


def _require_positive(value: float, label: str) -> None:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be positive")
