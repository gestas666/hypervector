"""Validated historical lineage for bounded live-cohort checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import math

from hypervector.research.cohort_trade_reflection_report import (
    ALL_TIME_REFLECTION_HISTORY_SCHEMA_VERSION,
)

_HISTORICAL_MECHANISM_KEYS = (
    "all_time_live_mechanism",
    "mature_profit_floor_all_time_live_mechanism",
    "risk_normalized_all_time_live_mechanism",
    "regime_conditioned_all_time_live_mechanism",
    "support_decay_all_time_live_mechanism",
    "support_decay_retrace_all_time_live_mechanism",
)


class HistoricalProjectionStale(ValueError):
    """Raised when cached complete history no longer matches live execution."""


def merge_complete_historical_projection(
    bounded: Mapping[str, object],
    complete: Mapping[str, object],
) -> dict[str, object]:
    """Join fresh bounded telemetry with signature-matched complete history."""
    bounded_audit = _validated_checkpoint_audit(bounded, "bounded")
    complete_audit = _validated_checkpoint_audit(complete, "complete")
    signature = _require_matching_execution_history(bounded_audit, complete_audit)
    closed = _require_matching_archive_history(bounded_audit, complete_audit)
    result = deepcopy(dict(bounded))
    result_audit = _mutable_mapping(result.get("audit"), "bounded audit")
    _copy_historical_sections(result_audit, complete_audit)
    _copy_retired_asset_evidence(result, complete)
    result_audit["historical_projection"] = {
        "schema_version": 1,
        "mode": "cached_complete_ledger_history_v1",
        "status": "current_by_execution_signature",
        "source_checkpoint_generated_at_utc": _history_source_time(complete),
        "verified_at_utc": _text(
            result.get("generated_at_utc"), "bounded generation time"
        ),
        "execution_history_sha256": signature,
        "closed_lifecycles": closed,
        "contract": _historical_projection_contract(),
    }
    return result


def _copy_retired_asset_evidence(
    target: dict[str, object], source: Mapping[str, object]
) -> None:
    """Retain provenance for retired ledgers used by cached all-time history."""
    target_evidence = target.get("evidence")
    source_evidence = source.get("evidence")
    if not isinstance(target_evidence, dict) or not isinstance(
        source_evidence, Mapping
    ):
        return
    retired = source_evidence.get("retired_assets")
    if isinstance(retired, Mapping):
        target_evidence["retired_assets"] = deepcopy(dict(retired))


def _validated_checkpoint_audit(
    checkpoint: Mapping[str, object],
    label: str,
) -> Mapping[str, object]:
    contract = _mapping(checkpoint.get("checkpoint_contract"), f"{label} contract")
    audit = _mapping(checkpoint.get("audit"), f"{label} audit")
    if checkpoint.get("schema_version") != 1:
        raise ValueError(f"{label} checkpoint schema is unsupported")
    if checkpoint.get("mode") != "multi_asset_bidirectional_live_checkpoint":
        raise ValueError(f"{label} checkpoint mode is unsupported")
    if contract.get("report_only") is not True:
        raise ValueError(f"{label} checkpoint must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError(f"{label} checkpoint execution authority must be none")
    if audit.get("mode") != "multi_asset_bidirectional_live_audit":
        raise ValueError(f"{label} checkpoint audit mode is unsupported")
    return audit


def _require_matching_execution_history(
    bounded: Mapping[str, object],
    complete: Mapping[str, object],
) -> str:
    bounded_run = _mapping(bounded.get("run"), "bounded run")
    complete_run = _mapping(complete.get("run"), "complete run")
    for key in ("run_id", "profile_fingerprint"):
        if bounded_run.get(key) != complete_run.get(key):
            raise HistoricalProjectionStale(f"execution history changed: {key}")
    current = _execution_history_signature(bounded)
    prior = _execution_history_signature(complete)
    if current != prior:
        raise HistoricalProjectionStale("execution history changed: fill signature")
    return current


def _execution_history_signature(audit: Mapping[str, object]) -> str:
    execution = _mapping(audit.get("execution"), "checkpoint execution")
    evidence = {
        "fills": execution.get("fills"),
        "closed_trades": execution.get("closed_trades"),
        "history_run_ids": execution.get("history_run_ids"),
        "fill_details": execution.get("fill_details"),
    }
    encoded = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_matching_archive_history(
    bounded: Mapping[str, object],
    complete: Mapping[str, object],
) -> int:
    archive_total = _archive_total(bounded)
    archive_closed = _closed_lifecycles(archive_total, "archive")
    complete_reflections = _mapping(
        _mapping(complete.get("trade_reflections"), "complete reflections").get(
            "all_time_live"
        ),
        "complete all-time reflections",
    )
    if (
        complete_reflections.get("history_schema_version")
        != ALL_TIME_REFLECTION_HISTORY_SCHEMA_VERSION
    ):
        raise HistoricalProjectionStale("historical reflection schema changed")
    reflected_closed = complete_reflections.get("closed_trades")
    if reflected_closed != archive_closed:
        raise HistoricalProjectionStale(
            "archive closed lifecycle count differs from complete history"
        )
    reflected_total = _mapping(
        _mapping(
            complete_reflections.get("performance"),
            "complete all-time reflection performance",
        ).get("total"),
        "complete all-time reflection total",
    )
    for field in ("net_pnl_usd", "maximum_closed_sequence_drawdown_usd"):
        archive_value = _number(archive_total.get(field), f"archive {field}")
        reflected_value = _number(
            reflected_total.get(field), f"complete reflection {field}"
        )
        if not math.isclose(archive_value, reflected_value, abs_tol=1e-9):
            raise HistoricalProjectionStale(
                f"archive {field} differs from complete history"
            )
    return archive_closed


def _archive_closed_lifecycles(audit: Mapping[str, object]) -> int:
    return _closed_lifecycles(_archive_total(audit), "archive")


def _archive_total(audit: Mapping[str, object]) -> Mapping[str, object]:
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    performance = _mapping(archive.get("performance"), "archive performance")
    return _mapping(performance.get("total"), "archive total")


def _closed_lifecycles(total: Mapping[str, object], label: str) -> int:
    value = total.get("closed_trades")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} closed lifecycle count must be nonnegative")
    return value


def _copy_historical_sections(
    target: dict[str, object],
    source: Mapping[str, object],
) -> None:
    for key in ("entry_alignment_mechanism", "hulk_entry_quality_challenger"):
        target[key] = deepcopy(source.get(key))
    target["side_composition"] = deepcopy(
        _validated_side_composition(source.get("side_composition"))
    )
    target_trade = _mutable_mapping(
        target.get("trade_reflections"), "trade reflections"
    )
    source_trade = _mapping(source.get("trade_reflections"), "complete reflections")
    for key in ("all_time_live", "provider_contract_history"):
        target_trade[key] = deepcopy(source_trade.get(key))
    target_performance = _mutable_mapping(
        target_trade.get("performance"), "trade performance"
    )
    source_performance = _mapping(
        source_trade.get("performance"), "complete trade performance"
    )
    target_performance["all_time_live"] = deepcopy(
        source_performance.get("all_time_live")
    )
    _copy_historical_mechanisms(target, source)


def _copy_historical_mechanisms(
    target: dict[str, object],
    source: Mapping[str, object],
) -> None:
    target_profit = _mutable_mapping(
        target.get("profit_lock_challenger"), "profit-lock challenger"
    )
    source_profit = _mapping(
        source.get("profit_lock_challenger"), "complete profit-lock challenger"
    )
    for key in _HISTORICAL_MECHANISM_KEYS:
        target_profit[key] = deepcopy(source_profit.get(key))


def _history_source_time(checkpoint: Mapping[str, object]) -> str:
    audit = _mapping(checkpoint.get("audit"), "complete audit")
    lineage = audit.get("historical_projection")
    if isinstance(lineage, Mapping):
        _validate_historical_lineage(lineage)
        return _text(
            lineage.get("source_checkpoint_generated_at_utc"),
            "historical source generation time",
        )
    return _text(checkpoint.get("generated_at_utc"), "complete generation time")


def _validated_side_composition(value: object) -> Mapping[str, object]:
    composition = _mapping(value, "side composition")
    contract = _mapping(composition.get("contract"), "side composition contract")
    if (
        composition.get("schema_version") != 2
        or composition.get("mode") != "cohort_separate_side_composition"
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("side composition contract is invalid")
    return composition


def _validate_historical_lineage(lineage: Mapping[str, object]) -> None:
    contract = _mapping(lineage.get("contract"), "historical projection contract")
    if (
        lineage.get("schema_version") != 1
        or lineage.get("mode") != "cached_complete_ledger_history_v1"
        or lineage.get("status") != "current_by_execution_signature"
    ):
        raise ValueError("complete historical projection identity is invalid")
    expected = _historical_projection_contract()
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("historical projection contract is invalid")


def _historical_projection_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _mutable_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mutable object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
