"""Report-only post-start acceptance for the exact V79 live cohort."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.multi_asset_cohort_payloads import (
    asset_config_payload,
    provider_config_payload,
)
from hypervector.research.cohort_configuration_exit_policy import (
    provider_exit_expectation,
    provider_exit_policy_evidence,
)
from hypervector.research.cohort_friction_contracts import runtime_contract
from hypervector.research.seven_asset_poststart_profile import (
    require_exact_seven_asset_profile,
)
from hypervector.research.v79_execution_fill_guard import (
    fill_direction_matches_route,
    fill_run_provenance_matches,
)
from hypervector.research.v79_execution_quality_guard import (
    validate_v79_execution_quality,
)
from hypervector.research.v79_closed_lifecycle_guard import (
    validate_v79_closed_lifecycles,
)
from hypervector.research.v79_open_lifecycle_guard import (
    validate_v79_open_lifecycles,
)

Record = Mapping[str, object]
_OPERATIONS = frozenset({"entry", "protective_stop", "reduce_only_close", "target"})
_PLACEHOLDERS = frozenset({"unattributed", "unknown"})


def build_v79_poststart_acceptance(
    checkpoint: Record,
    config: MultiAssetLiveConfig,
    accounting_epoch: Record,
    *,
    now_utc: datetime,
    maximum_checkpoint_age_seconds: float = 90.0,
) -> dict[str, object]:
    """Validate fresh monitoring, protection, costs, and attribution without orders."""
    profile = require_exact_seven_asset_profile(config)
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    checks = {
        "checkpoint_contract": _checkpoint_contract_check(checkpoint),
        "runtime_identity": _runtime_identity_check(audit, config),
        "runtime_freshness": _freshness_check(
            checkpoint, now_utc, maximum_checkpoint_age_seconds
        ),
        "runtime_execution_contracts": _runtime_contract_check(
            checkpoint, audit, config
        ),
        "provider_monitoring": _provider_monitoring_check(audit, config),
        "position_protection": _position_protection_check(checkpoint, audit, config),
        "execution_attribution": _execution_attribution_check(audit, config),
        "closed_lifecycle_integrity": _closed_lifecycle_check(audit, config),
        "accounting_epoch": _accounting_epoch_check(
            audit,
            accounting_epoch,
            config.profile_fingerprint,
        ),
    }
    reasons = _reasons(checks.values())
    return {
        "schema_version": profile.schema_version,
        "contract": _report_contract(),
        "accepted": not reasons,
        "decision": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "run": dict(_mapping(audit.get("run"), "checkpoint run")),
        "checks": checks,
        "limitations": _limitations(),
    }


def _checkpoint_contract_check(checkpoint: Record) -> dict[str, object]:
    contract = _mapping(checkpoint.get("checkpoint_contract"), "checkpoint contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_pause": False,
        "automatic_retuning": False,
        "runtime_strategy_changed": False,
    }
    reasons = [
        f"checkpoint_contract_invalid:{key}"
        for key, value in expected.items()
        if contract.get(key) != value
    ]
    return _check(reasons)


def _runtime_identity_check(
    audit: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    run = _mapping(audit.get("run"), "checkpoint run")
    routing = _mapping(audit.get("routing"), "checkpoint routing")
    expected_routes = _routes(config)
    expected_observe_only = _observed_routes(config).difference(expected_routes)
    exact = (
        run.get("profile_id") == config.profile_id
        and run.get("profile_fingerprint") == config.profile_fingerprint
        and _text_tuple(run.get("symbols"), "run symbols") == config.symbols
        and set(_text_tuple(run.get("executable_provider_symbols"), "run routes"))
        == expected_routes
        and set(_text_tuple(run.get("observe_only_provider_symbols"), "observe routes"))
        == expected_observe_only
        and _integer(run.get("maximum_concurrent_positions"), "position limit") == 7
        and set(
            _text_tuple(routing.get("executable_provider_symbols"), "routing routes")
        )
        == expected_routes
    )
    reasons = [] if exact else ["runtime_identity_mismatch"]
    return _check(reasons, assets=len(config.assets), routes=len(expected_routes))


def _freshness_check(
    checkpoint: Record,
    now_utc: datetime,
    maximum_age_seconds: float,
) -> dict[str, object]:
    now = _aware(now_utc, "acceptance clock")
    maximum_age = _positive_number(maximum_age_seconds, "maximum checkpoint age")
    generated = _timestamp(checkpoint.get("generated_at_utc"), "checkpoint time")
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    age = (now - generated).total_seconds()
    heartbeat = _number(lifecycle.get("cohort_heartbeat_age_seconds"), "heartbeat age")
    exact = (
        -5.0 <= age <= maximum_age
        and 0.0 <= heartbeat <= maximum_age
        and lifecycle.get("state") == "running_consistent"
        and lifecycle.get("backend_process_health") == "healthy"
        and lifecycle.get("cohort_heartbeat_status") == "running"
        and not _text_tuple(lifecycle.get("faulted_assets"), "faulted assets")
    )
    reasons = [] if exact else ["runtime_not_fresh_and_healthy"]
    return _check(reasons, checkpoint_age_seconds=age, heartbeat_age_seconds=heartbeat)


def _runtime_contract_check(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    execution = _mapping(audit.get("execution"), "audit execution")
    friction = _mapping(execution.get("friction_parity"), "friction parity")
    observed = _mapping(friction.get("by_provider_symbol"), "friction routes")
    expected = _expected_runtime_contracts(config)
    current_exits = provider_exit_policy_evidence(provider_exit_expectation(config))
    entry_caps = {
        asset.symbol: asset.effective_entry_slippage_cap_fraction
        for asset in config.assets
    }
    close_caps = {
        asset.symbol: asset.market_slippage_cap_fraction for asset in config.assets
    }
    exact_generation = (
        generation.get("state") == "current_runtime_configuration"
        and generation.get("matches_runtime") is True
        and generation.get("runtime_profile_fingerprint") == config.profile_fingerprint
        and generation.get("current_profile_fingerprint") == config.profile_fingerprint
        and generation.get("current_provider_exit_policies") == current_exits
        and generation.get("current_provider_execution_directions")
        == _direction_payload(config)
        and generation.get("current_asset_entry_slippage_caps") == entry_caps
        and generation.get("current_asset_market_slippage_caps") == close_caps
    )
    exact_runtime = set(observed) == set(expected) and all(
        _mapping(observed[route], f"{route} friction").get("runtime_contract")
        == contract
        for route, contract in expected.items()
    )
    reasons = (
        []
        if exact_generation and exact_runtime
        else ["runtime_execution_contract_drift"]
    )
    return _check(reasons, checked_routes=len(expected))


def _expected_runtime_contracts(
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    assets = {asset.symbol: asset_config_payload(asset) for asset in config.assets}
    output: dict[str, object] = {}
    for provider in config.providers:
        provider_payload = provider_config_payload(provider)
        for symbol in provider.symbols:
            contract, _source = runtime_contract(provider_payload, assets[symbol])
            output[f"{provider.strategy_id}|{symbol}"] = contract
    return output


def _direction_payload(config: MultiAssetLiveConfig) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for strategy, symbol in config.executable_provider_symbols:
        output[f"{strategy}|{symbol}"] = sorted(
            side
            for provider_id, provider_symbol, side in (
                config.executable_provider_directions
            )
            if provider_id == strategy and provider_symbol == symbol
        )
    return output


def _provider_monitoring_check(
    audit: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    readiness = _mapping(audit.get("readiness"), "audit readiness")
    rows = _mapping(readiness.get("by_provider_symbol"), "provider readiness")
    expected = _observed_routes(config)
    evaluated = 0
    with_metrics = 0
    for route in expected.intersection(rows):
        row = _mapping(rows[route], f"{route} readiness")
        evaluated += _integer(row.get("count"), f"{route} evaluations") > 0
        metrics = _mapping(row.get("latest_metrics"), f"{route} metrics")
        with_metrics += bool(metrics) and metrics.get("technical_availability") != (
            "unavailable"
        )
    exact = (
        set(rows) == expected
        and evaluated == len(expected)
        and with_metrics == len(expected)
    )
    reasons = [] if exact else ["provider_monitoring_incomplete"]
    return _check(
        reasons,
        expected_routes=len(expected),
        evaluated_routes=evaluated,
        routes_with_metrics=with_metrics,
    )


def _position_protection_check(
    checkpoint: Record,
    audit: Record,
    config: MultiAssetLiveConfig,
) -> dict[str, object]:
    result = validate_v79_open_lifecycles(checkpoint, audit, config)
    return _check(list(result.reasons), open_positions=result.open_positions)


def _execution_attribution_check(
    audit: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    execution = _mapping(audit.get("execution"), "audit execution")
    details = _record_sequence(execution.get("fill_details"), "fill details")
    counts = (
        _integer(execution.get("fills"), "fills"),
        _integer(execution.get("projected_fills"), "projected fills"),
        len(details),
    )
    current_run_fills = _integer(
        execution.get("current_run_fills"), "current run fills"
    )
    reasons: list[str] = []
    if len(set(counts)) != 1:
        reasons.append("execution_fill_projection_mismatch")
    run = _mapping(audit.get("run"), "audit run")
    if not fill_run_provenance_matches(
        run.get("run_id"),
        execution.get("history_run_ids"),
        details,
        current_run_fills,
    ):
        reasons.append("execution_fill_run_provenance_mismatch")
    _nonnegative_number(execution.get("fees_usd"), "fees")
    _number(execution.get("funding_usd"), "funding")
    valid_routes = _routes(config)
    attributed = [_fill_is_attributed(row, valid_routes) for row in details]
    if not all(attributed):
        reasons.append("execution_fill_attribution_incomplete")
    if any(
        is_attributed
        and not fill_direction_matches_route(row, config.executable_provider_directions)
        for row, is_attributed in zip(details, attributed, strict=True)
    ):
        reasons.append("execution_fill_direction_invalid")
    quality = validate_v79_execution_quality(audit, config)
    reasons.extend(quality.reasons)
    return _check(
        reasons,
        fills=len(details),
        costed_fills=quality.costed_fills,
    )


def _closed_lifecycle_check(
    audit: Record, config: MultiAssetLiveConfig
) -> dict[str, object]:
    result = validate_v79_closed_lifecycles(audit, config)
    return _check(list(result.reasons), closed_trades=result.closed_trades)


def _fill_is_attributed(fill: Record, routes: set[str]) -> bool:
    strategy = fill.get("strategy_id")
    symbol = fill.get("symbol")
    operation = fill.get("operation")
    basic = (
        isinstance(strategy, str)
        and strategy not in _PLACEHOLDERS
        and isinstance(symbol, str)
        and f"{strategy}|{symbol}" in routes
        and operation in _OPERATIONS
        and _valid_positive(fill.get("price"))
        and _valid_positive(fill.get("size"))
        and _valid_nonnegative(fill.get("fee_usd"))
        and _valid_nonnegative_integer(fill.get("trade_id"))
        and _valid_nonnegative_integer(fill.get("oid"))
        and _valid_nonnegative_integer(fill.get("venue_timestamp_ms"))
    )
    if not basic or operation == "entry":
        return basic
    controller = fill.get("exit_controller_id")
    reason = fill.get("exit_reason")
    return (
        isinstance(controller, str)
        and controller.strip() not in _PLACEHOLDERS
        and isinstance(reason, str)
        and reason.strip() not in _PLACEHOLDERS
    )


def _accounting_epoch_check(
    audit: Record,
    expected_epoch: Record,
    profile_fingerprint: str,
) -> dict[str, object]:
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    observed = _mapping(archive.get("accounting_epoch"), "accounting epoch")
    expected = dict(expected_epoch)
    exact = (
        expected.get("profile_fingerprint") == profile_fingerprint
        and observed == expected
    )
    reasons = [] if exact else ["accounting_epoch_mismatch"]
    return _check(reasons, epoch_id=observed.get("epoch_id"))


def _routes(config: MultiAssetLiveConfig) -> set[str]:
    return {
        f"{strategy}|{symbol}"
        for strategy, symbol in config.executable_provider_symbols
    }


def _observed_routes(config: MultiAssetLiveConfig) -> set[str]:
    return {
        f"{provider.strategy_id}|{symbol}"
        for provider in config.providers
        for symbol in provider.symbols
    }


def _reasons(checks: Sequence[Record]) -> list[str]:
    return [
        reason
        for check in checks
        for reason in _text_tuple(check.get("reasons"), "check reasons")
    ]


def _check(reasons: list[str], **evidence: object) -> dict[str, object]:
    return {"passed": not reasons, "reasons": reasons, **evidence}


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _record_sequence(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"{label} must be an array of objects")
    return tuple(value)


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} must be an array of non-empty strings")
    return tuple(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _positive_number(value: object, label: str) -> float:
    parsed = _number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _nonnegative_number(value: object, label: str) -> float:
    parsed = _number(value, label)
    if parsed < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return parsed


def _valid_positive(value: object) -> bool:
    return _valid_number(value) and float(value) > 0.0


def _valid_nonnegative(value: object) -> bool:
    return _valid_number(value) and float(value) >= 0.0


def _valid_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _valid_nonnegative_integer(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be RFC3339 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be RFC3339 text") from exc
    return _aware(parsed, label)


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_pause": False,
        "automatic_retuning": False,
        "performance_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "technical acceptance does not establish strategy profitability",
        "zero fills cannot validate realized execution economics",
        "one live run cannot establish a durable strategy edge",
        "this report cannot route, resize, pause, retune, or submit an order",
    ]
