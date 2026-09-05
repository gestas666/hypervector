"""Fail-closed audit of V58 BRENTOIL opposite-intent exit handling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


_SOURCE_RUN_ID = "bidirectional-live-1787166474078"
_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_PROFILE_FINGERPRINT = (
    "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
)
_STRATEGY_ID = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_SYMBOL = "xyz:BRENTOIL"
_LIFECYCLE_ID = "xyz:BRENTOIL:520642502465"
_OPPOSITE_SCOPE = "selected_opposite_from_any_executable_provider_same_symbol"


def build_v58_brentoil_opposite_exit_audit(
    checkpoint: Mapping[str, object],
    routing_rows: Sequence[Mapping[str, object]],
    ledger_prefix: Mapping[str, object],
) -> dict[str, object]:
    """Build an authority-none audit from one checkpoint and a frozen ledger prefix."""
    trade, runtime_run_id, source_run_id = _validated_open_trade(checkpoint)
    exit_plan = _mapping(trade.get("exit_plan"), "BRENTOIL exit plan")
    _validate_exit_plan(exit_plan)
    opened_at_ms = _integer(exit_plan.get("opened_at_ms"), "opened_at_ms")
    current_side = _string(trade.get("side"), "BRENTOIL position side")
    if current_side not in {"long", "short"}:
        raise ValueError("BRENTOIL position side must be long or short")
    counts = _audit_routing(
        routing_rows,
        opened_at_ms,
        current_side,
        frozenset({source_run_id, runtime_run_id}),
    )
    return {
        "schema_version": 1,
        "observed_at_utc": _string(
            checkpoint.get("generated_at_utc"), "checkpoint generated_at_utc"
        ),
        "identity": _identity(runtime_run_id, source_run_id),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_strategy_changes": False,
            "runtime_strategy_changed": False,
        },
        "live_exit_contract": dict(exit_plan),
        "path_since_entry": dict(
            _mapping(trade.get("path_since_entry"), "BRENTOIL path_since_entry")
        ),
        "opposite_exit_audit": counts,
        "source_ledger_prefix": _validated_prefix(ledger_prefix),
        "disposition": _disposition(counts),
        "limitations": [
            "absence of an eligible opposite intent is not evidence that no better exit exists",
            "the open lifecycle is hypothesis-forming and cannot estimate route expectancy",
            "routing telemetry does not substitute for final venue fill reconciliation",
        ],
    }


def _validated_open_trade(
    checkpoint: Mapping[str, object],
) -> tuple[Mapping[str, object], str, str]:
    runtime_run_id = _validate_checkpoint_identity(checkpoint)
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    if lifecycle.get("state") != "running_consistent":
        raise ValueError("V58 checkpoint lifecycle is not running_consistent")
    if lifecycle.get("backend_process_health") != "healthy":
        raise ValueError("V58 backend process is not healthy")
    if lifecycle.get("faulted_assets") != []:
        raise ValueError("V58 checkpoint contains faulted assets")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    reflections = _mapping(audit.get("open_trade_reflections"), "open reflections")
    trades = _sequence(reflections.get("trades"), "open reflection trades")
    matches = [
        _mapping(row, "open trade")
        for row in trades
        if isinstance(row, Mapping) and row.get("lifecycle_id") == _LIFECYCLE_ID
    ]
    if len(matches) != 1:
        raise ValueError("expected exactly one open V58 BRENTOIL lifecycle")
    trade = matches[0]
    _require_equal(trade, "symbol", _SYMBOL)
    _require_equal(trade, "strategy_id", _STRATEGY_ID)
    source_run_id = _string(trade.get("source_run_id"), "BRENTOIL source run id")
    if source_run_id != _SOURCE_RUN_ID:
        raise ValueError("source_run_id does not match the frozen V58 lifecycle")
    return trade, runtime_run_id, source_run_id


def _validate_checkpoint_identity(checkpoint: Mapping[str, object]) -> str:
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError("V58 checkpoint configuration does not match runtime")
    _require_equal(generation, "current_profile_fingerprint", _PROFILE_FINGERPRINT)
    _require_equal(generation, "runtime_profile_fingerprint", _PROFILE_FINGERPRINT)
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    run = _mapping(audit.get("run"), "checkpoint run")
    _require_equal(run, "profile_id", _PROFILE_ID)
    _require_equal(run, "profile_fingerprint", _PROFILE_FINGERPRINT)
    return _string(run.get("run_id"), "checkpoint run id")


def _validate_exit_plan(exit_plan: Mapping[str, object]) -> None:
    expected = {
        "maximum_hold_seconds": 86_400,
        "maximum_hold_policy": "fixed",
        "provider_recipe_exit_policy": "ignore",
        "profit_lock_policy": "none",
        "opposite_intent_exit_scope": _OPPOSITE_SCOPE,
    }
    for key, value in expected.items():
        _require_equal(exit_plan, key, value)


def _audit_routing(
    rows: Sequence[Mapping[str, object]],
    opened_at_ms: int,
    current_side: str,
    run_ids: frozenset[str],
) -> dict[str, object]:
    counts = {
        "post_entry_evaluations": 0,
        "eligible_same_side_evaluations": 0,
        "eligible_opposite_evaluations": 0,
        "routed_opposite_exit_actions": 0,
        "same_side_position_withheld": 0,
    }
    for row in rows:
        _audit_routing_row(row, opened_at_ms, current_side, run_ids, counts)
    missed = (
        counts["eligible_opposite_evaluations"]
        != counts["routed_opposite_exit_actions"]
    )
    if missed:
        raise ValueError("eligible opposite exit was not routed")
    counts["missed_eligible_opposite_exit"] = False
    counts["status"] = (
        "opposite_exit_routed"
        if counts["eligible_opposite_evaluations"]
        else "no_eligible_opposite_exit_observed"
    )
    return counts


def _audit_routing_row(
    row: Mapping[str, object],
    opened_at_ms: int,
    current_side: str,
    run_ids: frozenset[str],
    counts: dict[str, object],
) -> None:
    if not _matches_run(row, run_ids) or row.get("event_type") != "intent_routing":
        return
    payload = _mapping(row.get("payload"), "intent_routing payload")
    actions = _sequence(payload.get("actions"), "intent_routing actions")
    withheld = _sequence(payload.get("withheld"), "intent_routing withheld")
    evaluations = _sequence(payload.get("evaluations"), "intent_routing evaluations")
    for raw_evaluation in evaluations:
        evaluation = _mapping(raw_evaluation, "provider evaluation")
        if not _matches_route(evaluation, opened_at_ms):
            continue
        counts["post_entry_evaluations"] = _count(counts, "post_entry_evaluations") + 1
        if evaluation.get("eligible") is not True:
            continue
        _audit_eligible(evaluation, actions, withheld, current_side, counts)


def _audit_eligible(
    evaluation: Mapping[str, object],
    actions: Sequence[object],
    withheld: Sequence[object],
    current_side: str,
    counts: dict[str, object],
) -> None:
    side = _string(evaluation.get("side"), "eligible evaluation side")
    decision = _integer(evaluation.get("decision_time_ms"), "decision_time_ms")
    if side == current_side:
        counts["eligible_same_side_evaluations"] = (
            _count(counts, "eligible_same_side_evaluations") + 1
        )
        if _has_route_record(
            withheld, decision, side, "reason", "same_direction_position_open"
        ):
            counts["same_side_position_withheld"] = (
                _count(counts, "same_side_position_withheld") + 1
            )
        return
    if side not in {"long", "short"}:
        raise ValueError("eligible evaluation side must be long or short")
    counts["eligible_opposite_evaluations"] = (
        _count(counts, "eligible_opposite_evaluations") + 1
    )
    if _has_route_record(actions, decision, side, "action", "close"):
        counts["routed_opposite_exit_actions"] = (
            _count(counts, "routed_opposite_exit_actions") + 1
        )


def _has_route_record(
    rows: Sequence[object],
    decision_time_ms: int,
    side: str,
    field: str,
    expected: str,
) -> bool:
    for raw_row in rows:
        row = _mapping(raw_row, "routing record")
        if (
            row.get("strategy_id") == _STRATEGY_ID
            and row.get("symbol") == _SYMBOL
            and row.get("decision_time_ms") == decision_time_ms
            and row.get("side") == side
            and row.get(field) == expected
        ):
            return True
    return False


def _matches_run(row: Mapping[str, object], run_ids: frozenset[str]) -> bool:
    return (
        row.get("run_id") in run_ids
        and row.get("profile_id") == _PROFILE_ID
        and row.get("profile_fingerprint") == _PROFILE_FINGERPRINT
    )


def _matches_route(evaluation: Mapping[str, object], opened_at_ms: int) -> bool:
    decision = evaluation.get("decision_time_ms")
    return (
        evaluation.get("strategy_id") == _STRATEGY_ID
        and evaluation.get("symbol") == _SYMBOL
        and isinstance(decision, int)
        and not isinstance(decision, bool)
        and decision >= opened_at_ms
    )


def _identity(runtime_run_id: str, source_run_id: str) -> dict[str, str]:
    return {
        "run_id": runtime_run_id,
        "source_run_id": source_run_id,
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": _PROFILE_FINGERPRINT,
        "strategy_id": _STRATEGY_ID,
        "symbol": _SYMBOL,
        "lifecycle_id": _LIFECYCLE_ID,
    }


def _disposition(counts: Mapping[str, object]) -> dict[str, object]:
    return {
        "runtime_bug_observed": False,
        "live_change_supported": False,
        "diagnosis": (
            "profit giveback is consistent with the configured no-lock exit policy; "
            "no eligible opposite intent was observed in the audited prefix"
        ),
        "next_investigation": (
            "reconcile the authoritative close and collect future-only resolved "
            "long and short lifecycles under the frozen policy"
        ),
        "eligible_opposite_evaluations": counts["eligible_opposite_evaluations"],
    }


def _validated_prefix(prefix: Mapping[str, object]) -> dict[str, object]:
    path = _string(prefix.get("path"), "ledger prefix path")
    byte_count = _integer(prefix.get("bytes"), "ledger prefix bytes")
    sha256 = _string(prefix.get("sha256"), "ledger prefix sha256")
    if byte_count < 1 or len(sha256) != 64:
        raise ValueError("ledger prefix evidence is incomplete")
    return {"path": path, "bytes": byte_count, "sha256": sha256}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with string keys")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a sequence")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _require_equal(row: Mapping[str, object], key: str, expected: object) -> None:
    if row.get(key) != expected:
        raise ValueError(f"{key} does not match the frozen V58 contract")


def _count(counts: Mapping[str, object], key: str) -> int:
    return _integer(counts.get(key), key)
