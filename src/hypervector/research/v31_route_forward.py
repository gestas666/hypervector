"""Prospective report-only tracking for the v31 HIP-3 route prune."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    text,
    text_list,
)
from hypervector.research.route_forward_spec import (
    CandidateRouteForwardSpec,
    V31_ROUTE_FORWARD_SPEC,
)

Record = Mapping[str, object]

REMOVED_ROUTES = V31_ROUTE_FORWARD_SPEC.removed_routes
RETAINED_CONTROL_ROUTES = V31_ROUTE_FORWARD_SPEC.retained_control_routes


def build_v31_route_forward_snapshot(
    checkpoint: Record,
    journal: Record,
    source_path: Path,
    candidate_path: Path,
) -> dict[str, object]:
    """Build one strict v25/v31 route-forward evidence snapshot."""
    return build_candidate_route_forward_snapshot(
        checkpoint,
        journal,
        source_path,
        candidate_path,
        spec=V31_ROUTE_FORWARD_SPEC,
    )


def build_candidate_route_forward_snapshot(
    checkpoint: Record,
    journal: Record,
    source_path: Path,
    candidate_path: Path,
    *,
    spec: CandidateRouteForwardSpec,
) -> dict[str, object]:
    """Build one exact versioned route-forward evidence snapshot."""
    source = load_multi_asset_live_config(source_path, mode="observe")
    candidate = load_multi_asset_live_config(candidate_path, mode="observe")
    _validate_candidate(source, candidate, spec)
    contract = _checkpoint_contract(checkpoint)
    protocol = _tracking_protocol(journal, candidate_path, spec)
    audit = mapping(checkpoint.get("audit"), "checkpoint audit")
    run = mapping(audit.get("run"), "checkpoint run")
    phase, executable, observe_only = _phase(run, source, candidate, spec)
    scores = mapping(
        mapping(audit.get("strategy_scorecard"), "strategy scorecard").get(
            "by_provider_symbol"
        ),
        "provider-symbol scorecards",
    )
    _require_routes(scores, spec)
    routes = [
        _route_snapshot(route, scores, executable, observe_only, candidate, phase, spec)
        for route in spec.tracked_routes
    ]
    live_state = _live_state(checkpoint, audit)
    return {
        "schema_version": spec.schema_version,
        "contract": contract,
        "source_checkpoint_generated_at_utc": text(
            checkpoint.get("generated_at_utc"), "checkpoint generation time"
        ),
        "phase": phase,
        "tracking_state": _tracking_state(phase, spec),
        "protocol": protocol,
        "source_run": _run_identity(run),
        "candidate": _candidate_identity(candidate, spec),
        "routes": routes,
        "live_state": live_state,
        "assessment": _assessment(phase, routes, live_state, spec),
        "limitations": _limitations(),
    }


def _validate_candidate(
    source: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
    spec: CandidateRouteForwardSpec,
) -> None:
    if source.profile_id != spec.source_profile:
        raise ValueError("source config is not the exact v25 profile")
    if candidate.profile_id != spec.candidate_profile:
        raise ValueError(
            f"candidate config is not the exact {spec.version_label} profile"
        )
    if source.symbols != candidate.symbols or source.maximum_positions != 9:
        raise ValueError(
            f"{spec.version_label} must retain the v25 nine-asset capacity"
        )
    observed_source = _observed_routes(source)
    observed_candidate = _observed_routes(candidate)
    if observed_source != observed_candidate:
        raise ValueError(f"{spec.version_label} observed provider-symbol scope changed")
    if source.executable_provider_symbols != observed_source:
        raise ValueError("v25 source is not fully executable")
    removed = source.executable_provider_symbols - candidate.executable_provider_symbols
    if _route_strings(removed) != set(spec.removed_routes):
        raise ValueError(f"{spec.version_label} removed route scope is not exact")
    _validate_candidate_directions(candidate, spec)


def _validate_candidate_directions(
    candidate: MultiAssetLiveConfig, spec: CandidateRouteForwardSpec
) -> None:
    for provider, symbol in candidate.executable_provider_symbols:
        sides = {
            side
            for route_provider, route_symbol, side in (
                candidate.executable_provider_directions
            )
            if (route_provider, route_symbol) == (provider, symbol)
        }
        if sides != {"long", "short"}:
            raise ValueError(
                f"{spec.version_label} route is not bidirectional: {provider}|{symbol}"
            )


def _checkpoint_contract(checkpoint: Record) -> dict[str, object]:
    contract = mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if contract.get(field) != value:
            raise ValueError(f"checkpoint has invalid {field}")
    return {
        **expected,
        "automatic_promotion": False,
        "automatic_transition": False,
        "counterfactual_fills_claimed": False,
        "capital_reallocation_claimed": False,
    }


def _tracking_protocol(
    journal: Record, candidate_path: Path, spec: CandidateRouteForwardSpec
) -> dict[str, object]:
    expected = {
        "hypothesis_id": "hip3-route-authority-pruning",
        "revision_number": spec.journal_revision,
        "status": "candidate",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    for field, value in expected.items():
        if journal.get(field) != value:
            raise ValueError(f"route-pruning journal has invalid {field}")
    declared = text(journal.get("created_at_utc"), "journal creation time")
    cutoff = _timestamp_ms(declared)
    _verify_candidate_evidence(journal, candidate_path, spec)
    return {
        "hypothesis_id": expected["hypothesis_id"],
        "revision_number": spec.journal_revision,
        "declared_at_utc": declared,
        "entry_cutoff_timestamp_ms": cutoff,
        "counters_are_cumulative_from_run_start": True,
        "same_run_delta_required_for_post_protocol_change": True,
        "profile_transition_starts_new_baseline": True,
    }


def _verify_candidate_evidence(
    journal: Record, candidate_path: Path, spec: CandidateRouteForwardSpec
) -> None:
    evidence = mapping_list(journal.get("evidence"), "journal evidence")
    candidates = [
        row for row in evidence if row.get("role") == spec.candidate_evidence_role
    ]
    if len(candidates) != 1:
        raise ValueError("journal must identify one inactive candidate config")
    expected = candidates[0]
    content = candidate_path.read_bytes()
    if expected.get("bytes") != len(content):
        raise ValueError("candidate config byte count does not match journal")
    if expected.get("sha256") != sha256(content).hexdigest():
        raise ValueError("candidate config SHA-256 does not match journal")


def _phase(
    run: Record,
    source: MultiAssetLiveConfig,
    candidate: MultiAssetLiveConfig,
    spec: CandidateRouteForwardSpec,
) -> tuple[str, set[str], set[str]]:
    profile = text(run.get("profile_id"), "run profile id")
    fingerprint = text(run.get("profile_fingerprint"), "run profile fingerprint")
    executable = set(
        text_list(run.get("executable_provider_symbols"), "executable routes")
    )
    observe_only = set(
        text_list(run.get("observe_only_provider_symbols"), "observe-only routes")
    )
    if executable.intersection(observe_only):
        raise ValueError("run route authorities overlap")
    if profile == source.profile_id and fingerprint == source.profile_fingerprint:
        _validate_run_authority(executable, observe_only, source, "source")
        return "pretransition_v25_baseline", executable, observe_only
    if profile == candidate.profile_id and fingerprint == candidate.profile_fingerprint:
        _validate_run_authority(executable, observe_only, candidate, "candidate")
        return spec.candidate_phase, executable, observe_only
    raise ValueError(
        f"checkpoint run is not v25 or {spec.version_label} exact identity"
    )


def _validate_run_authority(
    executable: set[str],
    observe_only: set[str],
    config: MultiAssetLiveConfig,
    label: str,
) -> None:
    expected_executable = _route_strings(config.executable_provider_symbols)
    expected_observe = _route_strings(
        _observed_routes(config).difference(config.executable_provider_symbols)
    )
    if executable != expected_executable:
        raise ValueError(f"{label} executable route scope does not match config")
    if observe_only != expected_observe:
        raise ValueError(f"{label} observe-only route scope does not match config")


def _route_snapshot(
    route: str,
    scores: Record,
    executable: set[str],
    observe_only: set[str],
    candidate: MultiAssetLiveConfig,
    phase: str,
    spec: CandidateRouteForwardSpec,
) -> dict[str, object]:
    score = mapping(scores.get(route), f"scorecard {route}")
    performance = _execution_performance(score, route)
    current_authority = _authority(route, executable, observe_only)
    candidate_executable = _route_strings(candidate.executable_provider_symbols)
    candidate_authority = (
        "executable" if route in candidate_executable else "observe_only"
    )
    if phase == spec.candidate_phase and route in spec.removed_routes:
        if performance is not None and performance["closed_trades"] != 0:
            raise ValueError(
                f"removed {spec.version_label} route has current-profile execution: {route}"
            )
    return {
        "route": route,
        "group": "removed" if route in spec.removed_routes else "control",
        "current_authority": current_authority,
        "candidate_authority": candidate_authority,
        "forward_evaluations": nonnegative_int(
            score.get("forward_evaluations"), f"{route} forward evaluations"
        ),
        "eligible_signals": nonnegative_int(
            score.get("eligible_signals"), f"{route} eligible signals"
        ),
        "resolved_signal_horizons": nonnegative_int(
            score.get("resolved_signal_horizons"), f"{route} resolved horizons"
        ),
        "forward_assessment": text(
            score.get("forward_assessment"), f"{route} forward assessment"
        ),
        "eligible_signal_horizons": dict(
            mapping(score.get("eligible_signal_horizons"), f"{route} horizons")
        ),
        "execution_performance": performance,
        "execution_performance_by_side": dict(
            _optional_mapping(score.get("execution_performance_by_side"), route) or {}
        ),
        "net_pnl_excluding_largest_winner_usd": _repeatability_net(score, route),
    }


def _execution_performance(score: Record, route: str) -> dict[str, object] | None:
    performance = _optional_mapping(score.get("execution_performance"), route)
    if performance is None:
        return None
    counts = {
        field: nonnegative_int(performance.get(field), f"{route} {field}")
        for field in ("closed_trades", "wins", "losses")
    }
    values = {
        field: number(performance.get(field), f"{route} {field}")
        for field in ("fees_usd", "funding_usd", "net_pnl_usd")
    }
    profit_factor = performance.get("profit_factor")
    return {
        **counts,
        **values,
        "profit_factor": (
            None if profit_factor is None else number(profit_factor, "profit factor")
        ),
    }


def _repeatability_net(score: Record, route: str) -> float | None:
    repeatability = _optional_mapping(score.get("repeatability_evidence"), route)
    if repeatability is None:
        return None
    value = repeatability.get("net_pnl_excluding_largest_winner_usd")
    return None if value is None else number(value, f"{route} net excluding largest")


def _live_state(checkpoint: Record, audit: Record) -> dict[str, object]:
    health = mapping(audit.get("health"), "audit health")
    assets = mapping(health.get("assets"), "asset health")
    positions = [
        _open_position(symbol, mapping(asset, f"asset {symbol}"))
        for symbol, asset in sorted(assets.items())
        if mapping(asset, f"asset {symbol}").get("final_state") == "OPEN"
    ]
    return {
        "mode": text(checkpoint.get("mode"), "checkpoint mode"),
        "transition_drain": dict(
            mapping(checkpoint.get("transition_drain"), "transition drain")
        ),
        "faults": nonnegative_int(health.get("faults"), "fault count"),
        "open_positions": positions,
        "all_open_positions_protected": all(
            row["protected_if_open"] is True for row in positions
        ),
        "execution": dict(mapping(audit.get("execution"), "audit execution")),
        "portfolio": dict(mapping(audit.get("portfolio"), "audit portfolio")),
    }


def _open_position(symbol: str, asset: Record) -> dict[str, object]:
    protected = asset.get("protected_if_open")
    if not isinstance(protected, bool):
        raise ValueError(f"{symbol} protection state must be boolean")
    return {
        "symbol": symbol,
        "position_size_signed": number(
            asset.get("position_size_signed"), f"{symbol} position size"
        ),
        "protected_if_open": protected,
        "stop_oid": asset.get("stop_oid"),
        "open_order_ids": asset.get("open_order_ids"),
    }


def _assessment(
    phase: str,
    routes: list[dict[str, object]],
    live_state: Record,
    spec: CandidateRouteForwardSpec,
) -> dict[str, object]:
    removed = [row for row in routes if row["group"] == "removed"]
    return {
        "confidence": "medium" if phase.startswith("pretransition") else "low",
        "removed_route_eligible_signals": sum(
            int(row["eligible_signals"]) for row in removed
        ),
        "removed_route_resolved_horizons": sum(
            int(row["resolved_signal_horizons"]) for row in removed
        ),
        "current_open_positions": len(list(live_state["open_positions"])),
        "candidate_active": phase == spec.candidate_phase,
        "automatic_transition_authorized": False,
        "recommendation": (
            spec.waiting_recommendation
            if phase == "pretransition_v25_baseline"
            else spec.forward_recommendation
        ),
    }


def _candidate_identity(
    candidate: MultiAssetLiveConfig, spec: CandidateRouteForwardSpec
) -> dict[str, object]:
    return {
        "profile_id": candidate.profile_id,
        "profile_fingerprint": candidate.profile_fingerprint,
        "symbols": list(candidate.symbols),
        "maximum_positions": candidate.maximum_positions,
        "removed_routes": list(spec.removed_routes),
        "retained_control_routes": list(spec.retained_control_routes),
        "both_directions": _all_routes_bidirectional(candidate),
    }


def _run_identity(run: Record) -> dict[str, str]:
    return {
        field: text(run.get(field), f"run {field}")
        for field in ("run_id", "profile_id", "profile_fingerprint")
    }


def _observed_routes(config: MultiAssetLiveConfig) -> frozenset[tuple[str, str]]:
    return frozenset(
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    )


def _route_strings(routes: Iterable[tuple[str, str]]) -> set[str]:
    return {f"{provider}|{symbol}" for provider, symbol in routes}


def _all_routes_bidirectional(candidate: MultiAssetLiveConfig) -> bool:
    directions = candidate.executable_provider_directions
    return all(
        {
            side
            for route_provider, route_symbol, side in directions
            if (route_provider, route_symbol) == (provider, symbol)
        }
        == {"long", "short"}
        for provider, symbol in candidate.executable_provider_symbols
    )


def _require_routes(scores: Record, spec: CandidateRouteForwardSpec) -> None:
    missing = sorted(set(spec.tracked_routes).difference(scores))
    if missing:
        raise ValueError(f"missing tracked route scorecards: {missing}")


def _authority(route: str, executable: set[str], observe_only: set[str]) -> str:
    if route in executable:
        return "executable"
    if route in observe_only:
        return "observe_only"
    raise ValueError(f"tracked route has no current authority: {route}")


def _optional_mapping(value: object, label: str) -> Record | None:
    return None if value is None else mapping(value, f"optional {label}")


def _timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("journal creation time must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def _tracking_state(phase: str, spec: CandidateRouteForwardSpec) -> str:
    if phase == "pretransition_v25_baseline":
        return "candidate_inactive_baseline_captured"
    if phase == spec.candidate_phase:
        return "candidate_forward_tracking"
    raise ValueError(f"unknown {spec.version_label} tracking phase: {phase}")


def _limitations() -> list[str]:
    return [
        "route counters are cumulative within one exact run and profile",
        "a profile transition starts a new baseline rather than a numeric delta",
        "completed-candle markouts are not orders or counterfactual fills",
        "removed routes may displace or expose other same-symbol opportunities",
        "open marks are provisional and excluded from route economics",
        "the tracker cannot route, size, enter, close, pause, restart, or promote",
    ]
