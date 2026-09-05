"""Report-only replay of the restored HYPE route's production soft exit."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.live.canonical_regime_telemetry import (
    CANONICAL_REGIME_TELEMETRY_STRATEGY,
)
from hypervector.live.cohort_maximum_hold_policy import (
    maximum_hold_decision_payload,
)
from hypervector.live.multi_asset_live_config import (
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

HYPE_NATIVE_STRATEGY_ID = "hype_native_breakout_onset_bidirectional_v2"
_SYMBOL = "HYPE"
_PROVIDER_EVENT = "intent_routing"
_CANONICAL_EVENT = "canonical_regime_evaluations"
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_GENERATOR_PATHS = (
    Path(__file__).resolve(),
    _REPOSITORY_ROOT / "scripts/hype_native_soft_exit_replay.py",
    _PACKAGE_ROOT / "live/cohort_maximum_hold_policy.py",
    _PACKAGE_ROOT / "live/cohort_execution_plan.py",
    _PACKAGE_ROOT / "live/multi_asset_live_config.py",
    _PACKAGE_ROOT / "live/multi_asset_observer_config.py",
    _PACKAGE_ROOT / "live/multi_asset_signal_source.py",
)


def build_hype_native_soft_exit_report(
    *,
    config_path: Path,
    ledger_path: Path,
    opened_at_ms: int,
    observed_ms: int,
) -> dict[str, object]:
    """Replay one counterfactual soft deadline through production policy."""
    _validate_time(opened_at_ms, "opened_at_ms")
    _validate_time(observed_ms, "observed_ms")
    before = _input_evidence(config_path, ledger_path)
    config = load_multi_asset_live_config(config_path, mode="observe")
    observer = with_observer_ledger_root(config, ledger_path.parent)
    observer_identity = _observer_identity(
        ledger_path,
        observed_ms,
        profile_id=observer.profile_id,
        profile_fingerprint=observer.profile_fingerprint,
        config_path=config_path,
    )
    provider_config = _candidate_provider(config.providers)
    plan = provider_config.execution_for(_SYMBOL, "long").bind(
        strategy_id=HYPE_NATIVE_STRATEGY_ID,
        stop_anchor=None,
    )
    evaluations, receipts = _required_evaluations(ledger_path, observed_ms)
    decision = maximum_hold_decision_payload(
        plan=plan,
        symbol=_SYMBOL,
        entry_oid=0,
        side="long",
        opened_at_ms=opened_at_ms,
        observed_ms=observed_ms,
        evaluations=evaluations,
    )
    if decision is None:
        raise ValueError("HYPE native counterfactual has not reached its soft deadline")
    after = _input_evidence(config_path, ledger_path)
    if before != after:
        raise ValueError("HYPE native soft-exit inputs changed during replay")
    return _report(
        config.profile_fingerprint,
        observer_identity,
        opened_at_ms,
        observed_ms,
        before,
        receipts,
        decision,
    )


def _candidate_provider(
    providers: tuple[StrategyProviderConfig, ...],
) -> StrategyProviderConfig:
    matches = [
        provider
        for provider in providers
        if provider.strategy_id == HYPE_NATIVE_STRATEGY_ID
    ]
    if len(matches) != 1:
        raise ValueError("candidate config must contain one HYPE native provider")
    provider = matches[0]
    if provider.execution_symbols != (_SYMBOL,):
        raise ValueError("HYPE native provider must execute only HYPE")
    return provider


def _required_evaluations(
    path: Path,
    observed_ms: int,
) -> tuple[dict[tuple[str, str], ProviderEvaluation], dict[str, int]]:
    provider = _latest_evaluation(
        path, _PROVIDER_EVENT, HYPE_NATIVE_STRATEGY_ID, observed_ms
    )
    canonical = _latest_evaluation(
        path, _CANONICAL_EVENT, CANONICAL_REGIME_TELEMETRY_STRATEGY, observed_ms
    )
    if provider is None:
        raise ValueError(
            "HYPE native provider evaluation is unavailable at replay time"
        )
    if canonical is None:
        raise ValueError("HYPE canonical evaluation is unavailable at replay time")
    provider_receipt, provider_evaluation = provider
    canonical_receipt, canonical_evaluation = canonical
    evaluations = {
        (provider_evaluation.strategy_id, provider_evaluation.symbol): (
            provider_evaluation
        ),
        (canonical_evaluation.strategy_id, canonical_evaluation.symbol): (
            canonical_evaluation
        ),
    }
    return evaluations, {
        "provider": provider_receipt,
        "canonical": canonical_receipt,
    }


def _observer_identity(
    path: Path,
    observed_ms: int,
    *,
    profile_id: str,
    profile_fingerprint: str,
    config_path: Path,
) -> dict[str, str]:
    rows = _configuration_rows(path, observed_ms)
    if len(rows) != 1:
        raise ValueError("HYPE soft-exit ledger requires one observer identity")
    row = rows[0]
    if row.get("profile_id") != profile_id:
        raise ValueError("observer profile id differs from rebound candidate")
    if row.get("profile_fingerprint") != profile_fingerprint:
        raise ValueError("observer profile fingerprint differs from rebound candidate")
    if (
        row.get("execution_mode") != "observe"
        or row.get("execution_authority") != "none"
    ):
        raise ValueError("soft-exit evidence ledger is not report-only")
    payload = _mapping(row.get("payload"), "observer identity payload")
    if payload.get("profile_fingerprint") != profile_fingerprint:
        raise ValueError("observer payload fingerprint differs from ledger identity")
    if payload.get("config_source_path") != str(config_path):
        raise ValueError("observer config source differs from candidate config")
    return {
        "profile_id": profile_id,
        "profile_fingerprint": profile_fingerprint,
        "run_id": _text(row, "run_id"),
    }


def _configuration_rows(
    path: Path,
    observed_ms: int,
) -> tuple[Mapping[str, object], ...]:
    output: list[Mapping[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = _mapping(json.loads(line), f"ledger line {line_number}")
            if row.get("event_type") != "configuration_identity":
                continue
            if _event_time_ms(row, line_number) <= observed_ms:
                output.append(row)
    return tuple(output)


def _latest_evaluation(
    path: Path,
    event_type: str,
    strategy_id: str,
    observed_ms: int,
) -> tuple[int, ProviderEvaluation] | None:
    candidates: list[tuple[int, ProviderEvaluation]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = _mapping(json.loads(line), f"ledger line {line_number}")
            received_ms = _event_time_ms(row, line_number)
            if row.get("event_type") != event_type or received_ms > observed_ms:
                continue
            for payload in _evaluation_payloads(row, line_number):
                evaluation = _provider_evaluation(payload)
                if evaluation.decision_time_ms > received_ms:
                    raise ValueError(
                        f"ledger line {line_number} decision follows ledger receipt"
                    )
                if (
                    evaluation.strategy_id == strategy_id
                    and evaluation.symbol == _SYMBOL
                ):
                    if evaluation.decision_time_ms <= observed_ms:
                        candidates.append((received_ms, evaluation))
    return max(candidates, key=_evaluation_order) if candidates else None


def _evaluation_payloads(
    row: Mapping[str, object],
    line_number: int,
) -> tuple[Mapping[str, object], ...]:
    payload = _mapping(row.get("payload"), f"ledger line {line_number} payload")
    raw = payload.get("evaluations")
    if not isinstance(raw, list):
        raise ValueError(f"ledger line {line_number} evaluations must be a list")
    return tuple(
        _mapping(value, f"ledger line {line_number} evaluation") for value in raw
    )


def _provider_evaluation(row: Mapping[str, object]) -> ProviderEvaluation:
    readiness = _mapping(row.get("readiness"), "provider readiness")
    return ProviderEvaluation(
        strategy_id=_text(row, "strategy_id"),
        symbol=_text(row, "symbol"),
        decision_time_ms=_integer(row, "decision_time_ms"),
        reference_price=_number(row, "reference_price"),
        decision_action=_text(row, "decision_action"),
        eligible=_boolean(row, "eligible"),
        reason=_text(row, "reason"),
        side=_optional_text(row.get("side"), "side"),
        readiness=_readiness(readiness),
        score=_optional_integer(row.get("score"), "score"),
        minimum_score=_optional_integer(row.get("minimum_score"), "minimum_score"),
        trigger=_optional_text(row.get("trigger"), "trigger"),
        primary_regime=_optional_text(row.get("primary_regime"), "primary_regime"),
        state_1m=_optional_text(row.get("state_1m"), "state_1m"),
        state_5m=_optional_text(row.get("state_5m"), "state_5m"),
        context_15m=_optional_text(row.get("context_15m"), "context_15m"),
        confidence=_optional_number(row.get("confidence"), "confidence"),
        exit_sides=frozenset(_text_list(row.get("exit_sides", []), "exit_sides")),
        exit_reason=_optional_text(row.get("exit_reason"), "exit_reason"),
        backend_non_action_reason=_optional_text(
            row.get("backend_non_action_reason"), "backend_non_action_reason"
        ),
    )


def _readiness(row: Mapping[str, object]) -> SignalReadiness:
    metrics = _mapping(row.get("metrics", {}), "readiness metrics")
    return SignalReadiness(
        side=_optional_text(row.get("side"), "readiness side"),
        conditions_met=_integer(row, "conditions_met"),
        conditions_required=_integer(row, "conditions_required"),
        blockers=_text_list(row.get("blockers"), "readiness blockers"),
        indicators=_text_list(row.get("indicators"), "readiness indicators"),
        metrics=metrics,
    )


def _report(
    profile_fingerprint: str,
    observer_identity: Mapping[str, str],
    opened_at_ms: int,
    observed_ms: int,
    evidence: Mapping[str, object],
    receipts: Mapping[str, int],
    decision: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "authority": "none",
        "counterfactual_no_venue_order": True,
        "symbol": _SYMBOL,
        "side": "long",
        "provider_id": HYPE_NATIVE_STRATEGY_ID,
        "candidate_profile_fingerprint": profile_fingerprint,
        "observer_profile_fingerprint": observer_identity["profile_fingerprint"],
        "observer_run_id": observer_identity["run_id"],
        "opened_at_ms": opened_at_ms,
        "replay_observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, tz=UTC
        ).isoformat(),
        "input_evidence": dict(evidence),
        "selected_ledger_receipts_ms": dict(receipts),
        "decision": dict(decision),
        "limitations": [
            "This replays a counterfactual lifecycle, not an actual venue position.",
            "An extend outcome remains unresolved until a later exit condition fires.",
        ],
    }


def _input_evidence(config: Path, ledger: Path) -> dict[str, object]:
    return {
        "config": {"path": str(config), **file_evidence(config)},
        "ledger": {"path": str(ledger), **file_evidence(ledger)},
        "generator_files": [_file_record(path) for path in _GENERATOR_PATHS],
    }


def _file_record(path: Path) -> dict[str, object]:
    return {"path": str(path), **file_evidence(path)}


def _event_time_ms(row: Mapping[str, object], line_number: int) -> int:
    raw = _text(row, "observed_at_utc")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError(f"ledger line {line_number} observed_at_utc must be aware")
    return int(value.astimezone(UTC).timestamp() * 1_000)


def _evaluation_order(value: tuple[int, ProviderEvaluation]) -> tuple[int, int]:
    return value[1].decision_time_ms, value[0]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text when present")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer when present")
    return value


def _number(row: Mapping[str, object], key: str) -> float:
    return _required_number(row.get(key), key)


def _required_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _required_number(value, label)


def _boolean(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def _text_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a text list")
    return tuple(value)


def _validate_time(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
