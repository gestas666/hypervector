"""Source-bound external candidates for continuous portfolio research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

Record = Mapping[str, object]

_SYMBOL = "xyz:BRENTOIL"
_CANDIDATE_ID = "hip3_brentoil_oil_shock_reversion_bidirectional_5m_shadow_v1"
_OBSERVER_MODE = "brentoil_oil_shock_shadow_observer"
_DEVELOPMENT_PROVIDER = "hip3_brentoil_oil_shock_reversion_bidirectional_5m_research_v1"
_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_live_change": False,
    "automatic_promotion": False,
    "runtime_strategy_changed": False,
}


@dataclass(frozen=True)
class ExternalOpportunityPaths:
    """Exact sources for one BRENTOIL external-opportunity assessment."""

    canary: Path
    development: Path
    parity: Path
    observer: Path


def load_brentoil_external_opportunity(
    paths: ExternalOpportunityPaths,
    *,
    observed_at: datetime,
    maximum_observer_age_seconds: float,
) -> tuple[dict[str, object], dict[str, object]]:
    """Load and rank exact BRENTOIL evidence without execution authority."""
    _validate_time(observed_at, maximum_observer_age_seconds)
    sources, evidence = _load_sources(paths)
    canary = sources["canary"]
    development = sources["development"]
    parity = sources["parity"]
    observer = sources["observer"]
    _validate_canary(canary)
    _validate_development(development)
    _validate_parity(parity)
    _validate_observer(observer, observed_at, maximum_observer_age_seconds)
    candidate = _candidate(canary, development, parity, observer)
    highest = _CANDIDATE_ID if candidate["validation_priority"] is not None else None
    return {
        "schema_version": 1,
        "mode": "external_candidate_opportunity_pipeline",
        "contract": dict(_CONTRACT),
        "candidates": [candidate],
        "highest_value_external_investigation": highest,
        "limitations": [
            "external-candidate priority is separate from active v51 route priority",
            "development evidence is not out-of-sample evidence",
            "a liquid asset does not establish strategy edge",
        ],
    }, evidence


def _load_sources(
    paths: ExternalOpportunityPaths,
) -> tuple[dict[str, Record], dict[str, object]]:
    loaded: dict[str, Record] = {}
    evidence: dict[str, object] = {}
    for name, path in (
        ("canary", paths.canary),
        ("development", paths.development),
        ("parity", paths.parity),
        ("observer", paths.observer),
    ):
        raw = path.read_bytes()
        value = json.loads(raw)
        loaded[name] = _mapping(value, f"BRENTOIL {name}")
        evidence[name] = {
            "path": str(path.resolve()),
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    return loaded, evidence


def _validate_canary(canary: Record) -> None:
    expected = {
        "schema_version": "brentoil_live_canary_lifecycle_reconciliation_v1",
        "mode": "report_only",
        "symbol": _SYMBOL,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }
    if any(canary.get(key) != value for key, value in expected.items()):
        raise ValueError("BRENTOIL live-canary contract is invalid")
    conclusion = _mapping(canary.get("conclusion"), "BRENTOIL conclusion")
    conclusion_expected = {
        "asset_data_available": True,
        "asset_liquidity_rejected": False,
        "existing_strategy_edge_established": False,
        "live_addition_authorized": False,
    }
    if any(conclusion.get(key) != value for key, value in conclusion_expected.items()):
        raise ValueError("BRENTOIL live-canary conclusion is invalid")


def _validate_development(development: Record) -> None:
    expected = {
        "schema_version": "hip3_oil_shock_reversion_development_v1",
        "symbol": _SYMBOL,
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "live_roster_change": False,
    }
    if any(development.get(key) != value for key, value in expected.items()):
        raise ValueError("BRENTOIL development contract is invalid")
    if development.get("validation_accessed") is not False:
        raise ValueError("BRENTOIL development scope is invalid")
    if development.get("holdout_accessed") is not False:
        raise ValueError("BRENTOIL development scope is invalid")
    identity = _mapping(
        development.get("strategy_identity"), "BRENTOIL development identity"
    )
    if identity.get("provider_id") != _DEVELOPMENT_PROVIDER:
        raise ValueError("BRENTOIL development identity is invalid")
    if identity.get("timeframe") != "5m":
        raise ValueError("BRENTOIL development timeframe is invalid")


def _validate_parity(parity: Record) -> None:
    if parity.get("schema_version") != "hip3_prospective_candle_parity_v1":
        raise ValueError("BRENTOIL parity schema is invalid")
    scope = _mapping(parity.get("scope"), "BRENTOIL parity scope")
    contract = _mapping(parity.get("contract"), "BRENTOIL parity contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    if scope.get("symbol") != _SYMBOL:
        raise ValueError("BRENTOIL parity identity is invalid")
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("BRENTOIL parity contract is invalid")


def _validate_observer(
    observer: Record,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> None:
    if observer.get("symbol") != _SYMBOL or observer.get("mode") != _OBSERVER_MODE:
        raise ValueError("BRENTOIL observer identity is invalid")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "orders_supported": False,
        "signing_client_constructed": False,
    }
    if any(observer.get(key) != value for key, value in expected.items()):
        raise ValueError("BRENTOIL observer contract is invalid")
    observed_ms = _nonnegative_int(observer.get("observed_at_ms"), "observed at")
    source_time = datetime.fromtimestamp(observed_ms / 1000.0, tz=UTC)
    age = (observed_at.astimezone(UTC) - source_time).total_seconds()
    if age < 0.0:
        raise ValueError("BRENTOIL observer timestamp is in the future")
    if age > maximum_age_seconds:
        raise ValueError("BRENTOIL observer is stale")


def _candidate(
    canary: Record,
    development: Record,
    parity: Record,
    observer: Record,
) -> dict[str, object]:
    conclusion = _mapping(canary.get("conclusion"), "BRENTOIL conclusion")
    status, priority, next_experiment = _candidate_research_state(development)
    return {
        "candidate_id": _CANDIDATE_ID,
        "symbol": _SYMBOL,
        "status": status,
        "validation_priority": priority,
        "hypothesis": "a new oil-shock mechanism can exploit a liquid BRENTOIL lane",
        "live_canary": _live_canary(canary, observer),
        "liquidity": _liquidity(canary),
        "development": _development_summary(development),
        "source_parity": _parity_summary(parity),
        "prospective_observation": _observer_summary(observer),
        "existing_strategy_edge_established": conclusion.get(
            "existing_strategy_edge_established"
        ),
        "live_change_supported": False,
        "expected_economic_value": "unquantified_until_resolved_oos_lifecycles",
        "next_experiment": next_experiment,
        "minimum_additional_evidence": {
            "technical": "resolve candle parity and mark/L2 lifecycle paths",
            "economic": "predeclared validation after realistic live-derived friction",
            "forward": "at least one resolved lifecycle per configured direction",
        },
        "execution_effect": "report_only",
    }


def _candidate_research_state(
    development: Record,
) -> tuple[str, int | None, str]:
    economics = _mapping(
        development.get("development_economics"), "development economics"
    )
    stress = _mapping(economics.get("stress"), "stress economics")
    stress_net = _rounded(stress.get("net_pnl_usd"), "stress net")
    stress_pf = _rounded(stress.get("profit_factor"), "stress PF")
    if stress_net <= 0.0 or stress_pf <= 1.0:
        return (
            "deferred_negative_development_stress",
            None,
            "passive_collection_or_new_mechanism",
        )
    disposition = _mapping(
        development.get("research_disposition"), "development disposition"
    )
    supported = "DEVELOPMENT_SUPPORTED_REQUIRES_UNTOUCHED_OOS_AND_RUNTIME_PARITY"
    if disposition.get("status") != supported:
        return (
            "deferred_technical_paths_unresolved",
            None,
            "resolve_existing_evidence_or_new_mechanism",
        )
    return "being_tested", 1, "collect_exact_eligible_oil_shock_lifecycles"


def _live_canary(canary: Record, observer: Record) -> dict[str, object]:
    coverage = _mapping(canary.get("ledger_coverage"), "BRENTOIL coverage")
    live = _mapping(
        canary.get("descriptive_all_live_lifecycles"), "BRENTOIL live summary"
    )
    return {
        "closed_lifecycles": _nonnegative_int(
            coverage.get("reconciled_closed_lifecycles"), "closed lifecycles"
        ),
        "wins": _nonnegative_int(live.get("wins"), "wins"),
        "losses": _nonnegative_int(live.get("losses"), "losses"),
        "net_pnl_usd": _rounded(live.get("net_pnl_usd"), "live net"),
        "profit_factor": _rounded(live.get("profit_factor"), "live PF"),
        "net_excluding_largest_winner_usd": _rounded(
            live.get("net_pnl_excluding_largest_winner_usd"), "live ex-largest"
        ),
        "maximum_observed_slippage_bps": _rounded(
            observer.get("live_canary_max_abs_slippage_bps"), "live slippage"
        ),
    }


def _liquidity(canary: Record) -> dict[str, object]:
    value = _mapping(canary.get("current_liquidity_snapshot"), "BRENTOIL liquidity")
    return {
        "global_rank": _positive_int(value.get("global_hip3_volume_rank"), "rank"),
        "day_notional_volume_usd": _rounded(
            value.get("day_notional_volume_usd"), "day volume"
        ),
        "spread_bps": _rounded(value.get("spread_bps"), "spread"),
        "asset_liquidity_rejected": False,
    }


def _development_summary(development: Record) -> dict[str, object]:
    economics = _mapping(
        development.get("development_economics"), "development economics"
    )
    nominal = _mapping(economics.get("nominal"), "nominal economics")
    stress = _mapping(economics.get("stress"), "stress economics")
    path = _mapping(development.get("technical_path_evidence"), "development path")
    disposition = _mapping(
        development.get("research_disposition"), "development disposition"
    )
    return {
        "nominal_trades": _nonnegative_int(nominal.get("completed_trades"), "trades"),
        "nominal_net_pnl_usd": _rounded(nominal.get("net_pnl_usd"), "nominal net"),
        "nominal_profit_factor": _rounded(nominal.get("profit_factor"), "nominal PF"),
        "stress_trades": _nonnegative_int(stress.get("completed_trades"), "trades"),
        "stress_net_pnl_usd": _rounded(stress.get("net_pnl_usd"), "stress net"),
        "stress_profit_factor": _rounded(stress.get("profit_factor"), "stress PF"),
        "technical_path_status": _text(path.get("status"), "path status"),
        "disposition": _text(disposition.get("status"), "disposition"),
        "validation_accessed": False,
        "holdout_accessed": False,
    }


def _parity_summary(parity: Record) -> dict[str, object]:
    coverage = _mapping(parity.get("coverage"), "parity coverage")
    technical = _mapping(parity.get("technical_assessment"), "parity assessment")
    return {
        "overlap_bars": _nonnegative_int(coverage.get("overlap_bars"), "overlap"),
        "mismatched_ohlc_bars": _nonnegative_int(
            coverage.get("mismatched_ohlc_bars"), "mismatches"
        ),
        "resolved": _boolean(
            technical.get("candle_ohlc_parity_resolved"), "parity resolved"
        ),
    }


def _observer_summary(observer: Record) -> dict[str, object]:
    eligible = _nonnegative_int(observer.get("eligible_decisions_total"), "eligible")
    late = _nonnegative_int(
        observer.get("late_non_warmup_candle_rows_total", 0), "late candles"
    )
    revisions = _nonnegative_int(
        observer.get("source_revision_rows_total", 0), "source revisions"
    )
    revision_fields = _text_list(
        observer.get("source_revision_fields_total", []), "source revision fields"
    )
    return {
        "observed_at_ms": _nonnegative_int(observer.get("observed_at_ms"), "observed"),
        "candle_rows": _nonnegative_int(observer.get("candle_rows_total"), "candles"),
        "decision_rows": _nonnegative_int(observer.get("decision_rows_total"), "rows"),
        "eligible_decisions": eligible,
        "status": "waiting_eligible_onset" if eligible == 0 else "eligible_observed",
        "late_non_warmup_candle_rows": late,
        "source_revision_rows": revisions,
        "source_revision_fields": revision_fields,
        "technical_path_status": (
            "unresolved_late_candles" if late else "no_known_candle_gap"
        ),
        "last_non_action_reason": _text(
            observer.get("last_non_action_reason"), "non-action reason"
        ),
        "promotion_blockers": _text_list(
            observer.get("promotion_blockers"), "promotion blockers"
        ),
    }


def _validate_time(observed_at: datetime, maximum_age_seconds: float) -> None:
    if observed_at.tzinfo is None:
        raise ValueError("external opportunity observed_at must be timezone-aware")
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("external opportunity maximum age must be positive and finite")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: object, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result == 0:
        raise ValueError(f"{label} must be positive")
    return result


def _rounded(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return round(result, 6)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_text(item, label) for item in value]
