"""Shared exact route-friction extraction for HIP-3 shadow evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import math
from typing import cast

from hypervector.live.hip3_breakout_shadow_specs import Hip3BreakoutShadowSpec


def shadow_route_friction(
    diagnostic: Mapping[str, object],
    fee_report: Mapping[str, object],
    spec: Hip3BreakoutShadowSpec,
) -> tuple[float, float]:
    """Return exact one-way taker fee and nominal latency in basis points."""
    return _fee_bps(fee_report, spec), _development_latency(diagnostic, spec)


def _development_latency(
    report: Mapping[str, object], spec: Hip3BreakoutShadowSpec
) -> float:
    _require_diagnostic_contract(report)
    if report.get("symbol") != spec.symbol:
        raise ValueError("development diagnostic symbol is inconsistent")
    track = _selected_track(report)
    if (
        track.get("provider_id") != spec.provider_id
        or track.get("profile_id") != spec.profile_id
    ):
        raise ValueError("development diagnostic route identity is inconsistent")
    if track.get("timeframe") != "15m" or track.get("family") != "breakout_pressure":
        raise ValueError("development diagnostic track is unsupported")
    _require_signal_config(track, spec)
    schema = report.get("schema_version")
    if schema == "mu_development_path_threshold_diagnostic_v1":
        source = _mapping(report.get("inputs"), "diagnostic inputs")
    elif schema == "hip3_shadow_observer_route_contract_v1":
        source = _mapping(report.get("friction"), "observer route friction")
    else:
        source = _mapping(
            _mapping(report.get("route_specific_friction"), "route friction").get(
                "15m"
            ),
            "15m route friction",
        )
    return _nonnegative_number(
        source.get("nominal_latency_bps_per_side"), "nominal latency"
    )


def _require_signal_config(
    track: Mapping[str, object], spec: Hip3BreakoutShadowSpec
) -> None:
    observed = _mapping(track.get("config"), "selected signal config")
    if dict(observed) != asdict(spec.config):
        raise ValueError("development diagnostic signal config is inconsistent")


def _selected_track(report: Mapping[str, object]) -> Mapping[str, object]:
    schema = report.get("schema_version")
    if schema == "hip3_development_only_diagnostic_v1":
        return _mapping(report.get("development_selected_track"), "selected track")
    if schema == "mu_development_path_threshold_diagnostic_v1":
        diagnostic = _mapping(report.get("diagnostic"), "diagnostic")
        return _mapping(diagnostic.get("track"), "selected track")
    if schema == "hip3_shadow_observer_route_contract_v1":
        return _mapping(report.get("route"), "observer route")
    raise ValueError("development diagnostic schema is unsupported")


def _require_diagnostic_contract(report: Mapping[str, object]) -> None:
    schema = report.get("schema_version")
    generic = (
        schema == "hip3_development_only_diagnostic_v1"
        and report.get("report_only") is True
        and report.get("execution_authority") == "none"
    )
    mu_safe = (
        schema == "mu_development_path_threshold_diagnostic_v1"
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("validation_accessed") is False
        and report.get("holdout_accessed") is False
        and report.get("qualification_abort_preserved") is True
    )
    observer_safe = (
        schema == "hip3_shadow_observer_route_contract_v1"
        and report.get("report_only") is True
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("runtime_strategy_changed") is False
    )
    if not generic and not mu_safe and not observer_safe:
        raise ValueError("development diagnostic authority contract is invalid")


def _fee_bps(report: Mapping[str, object], spec: Hip3BreakoutShadowSpec) -> float:
    if (
        report.get("execution_authority") != "none"
        or report.get("report_only") is not True
    ):
        raise ValueError("fee evidence authority contract is invalid")
    profile = report.get("profile")
    if isinstance(profile, dict):
        values = cast(dict[str, object], profile)
        if values.get("symbol") != spec.symbol:
            raise ValueError("fee evidence symbol is inconsistent")
        fees = _mapping(values.get("fees"), "fee evidence")
        return _nonnegative_number(fees.get("one_way_taker_fee_bps"), "taker fee")
    if report.get("symbol") != spec.symbol:
        raise ValueError("fee evidence symbol is inconsistent")
    friction = _mapping(report.get("route_specific_friction"), "route friction")
    values = _mapping(friction.get("15m"), "15m route friction")
    rate = _nonnegative_number(values.get("effective_taker_fee_rate"), "taker rate")
    return rate * 10_000.0


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _nonnegative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number
