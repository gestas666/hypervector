"""Source-bound report-only disposition for prospective HIP-3 expansion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import cast


@dataclass(frozen=True)
class Hip3ExpansionEvidence:
    """Exact reports required to classify one candidate without authority."""

    symbol: str
    development: Mapping[str, object]
    path_repair: Mapping[str, object]
    candle_parity: Mapping[str, object]
    signal_parity: Mapping[str, object]
    observer_parity: Mapping[str, object]
    markouts: Mapping[str, object]


def build_hip3_expansion_forward_disposition(
    candidates: Sequence[Hip3ExpansionEvidence],
) -> dict[str, object]:
    """Classify frozen expansion evidence without changing live authority."""
    if not candidates:
        raise ValueError("HIP-3 expansion disposition requires candidates")
    rows = [_candidate(candidate) for candidate in candidates]
    symbols = [cast(str, row["symbol"]) for row in rows]
    if len(set(symbols)) != len(symbols):
        raise ValueError("HIP-3 expansion candidate symbols must be unique")
    ordered = sorted(rows, key=_priority_key)
    return {
        "schema_version": "hip3_expansion_forward_disposition_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_promotion": False,
            "runtime_strategy_changed": False,
            "performance_gate": False,
        },
        "candidate_count": len(rows),
        "candidates": rows,
        "research_priority_order": [row["symbol"] for row in ordered],
        "live_roster_changes": [],
        "limitations": [
            "fixed-horizon BBO markouts are not fills or strategy PnL",
            "small prospective samples do not establish repeatable edge",
            "research priority grants no execution, sizing, or promotion authority",
        ],
    }


def _candidate(evidence: Hip3ExpansionEvidence) -> dict[str, object]:
    _validate_symbol(evidence.symbol)
    _validate_authority(evidence)
    provider, profile = _validate_identity(evidence)
    technical = _technical_summary(evidence)
    markouts = _markout_summaries(evidence.markouts)
    development = _development_summary(evidence.development)
    economics = _economics_classification(markouts)
    disposition = _research_disposition(technical, markouts, economics)
    return {
        "symbol": evidence.symbol,
        "provider_id": provider,
        "profile_id": profile,
        "development": development,
        "development_robustness": _development_robustness(development),
        "technical_evidence": technical,
        "forward_markouts": markouts,
        "prospective_economics": economics,
        "research_disposition": disposition,
        "live_readiness_claimed": False,
        "automatic_live_promotion": False,
    }


def _validate_authority(evidence: Hip3ExpansionEvidence) -> None:
    development = evidence.development
    schema = development.get("schema_version")
    generic = (
        schema == "hip3_development_only_diagnostic_v1"
        and development.get("report_only") is True
        and development.get("execution_authority") == "none"
        and development.get("automatic_promotion") is False
    )
    mu = (
        schema == "mu_development_path_threshold_diagnostic_v1"
        and development.get("execution_authority") == "none"
        and development.get("automatic_promotion") is False
        and development.get("validation_accessed") is False
        and development.get("holdout_accessed") is False
        and development.get("qualification_abort_preserved") is True
    )
    if not generic and not mu:
        raise ValueError("HIP-3 expansion development authority is invalid")
    for report in (
        evidence.path_repair,
        evidence.candle_parity,
        evidence.signal_parity,
        evidence.observer_parity,
    ):
        _require_report_contract(report)
    _require_markout_contract(evidence.markouts)


def _require_report_contract(report: Mapping[str, object]) -> None:
    contract = _mapping(report.get("contract"), "report contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("HIP-3 expansion evidence authority is invalid")


def _require_markout_contract(report: Mapping[str, object]) -> None:
    contract = _mapping(report.get("contract"), "markout contract")
    valid = (
        report.get("report_only") is True
        and report.get("execution_authority") == "none"
        and contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("fills_assumed") is False
        and contract.get("pnl_claimed") is False
    )
    if not valid:
        raise ValueError("HIP-3 expansion markout authority is invalid")


def _validate_identity(evidence: Hip3ExpansionEvidence) -> tuple[str, str]:
    symbol = evidence.symbol
    identities = (
        evidence.development.get("symbol"),
        _mapping(evidence.path_repair.get("source"), "path source").get("symbol"),
        _mapping(evidence.candle_parity.get("scope"), "candle scope").get("symbol"),
        _mapping(evidence.signal_parity.get("scope"), "signal scope").get("symbol"),
        _mapping(evidence.observer_parity.get("scope"), "observer scope").get("symbol"),
        evidence.markouts.get("symbol"),
    )
    if any(value != symbol for value in identities):
        raise ValueError("HIP-3 expansion symbol identity is inconsistent")
    signal = _mapping(evidence.signal_parity.get("scope"), "signal scope")
    observer = _mapping(evidence.observer_parity.get("scope"), "observer scope")
    provider = _text(signal.get("provider_id"), "provider id")
    profile = _text(signal.get("profile_id"), "profile id")
    route_identities = (
        observer.get("provider_id"),
        evidence.markouts.get("provider_id"),
        observer.get("profile_id"),
        evidence.markouts.get("profile_id"),
    )
    if route_identities != (provider, provider, profile, profile):
        raise ValueError("HIP-3 expansion route identity is inconsistent")
    return provider, profile


def _technical_summary(evidence: Hip3ExpansionEvidence) -> dict[str, object]:
    path = _mapping(evidence.path_repair.get("technical_assessment"), "path assessment")
    candle = _mapping(evidence.candle_parity.get("coverage"), "candle coverage")
    signal = _mapping(
        evidence.signal_parity.get("technical_assessment"), "signal assessment"
    )
    observer = _mapping(
        evidence.observer_parity.get("technical_assessment"), "observer assessment"
    )
    return {
        "prospective_path_resolved": _boolean(
            path.get("prospective_bar_path_coverage_resolved"), "path resolution"
        ),
        "path_bars_repaired": _integer(path.get("repaired_bars"), "repaired bars"),
        "path_bars_unresolved": _integer(
            path.get("unresolved_bars"), "unresolved bars"
        ),
        "candle_bars": _integer(candle.get("expected_bars"), "candle bars"),
        "exact_candle_ohlc_bars": _integer(
            candle.get("exact_ohlc_bars"), "exact candles"
        ),
        "candle_ohlc_mismatch_bars": _integer(
            candle.get("mismatched_ohlc_bars"), "candle mismatches"
        ),
        "signal_source_parity_resolved": _boolean(
            signal.get("prospective_signal_source_parity_resolved"), "signal parity"
        ),
        "signal_entry_parity_non_vacuous": _boolean(
            signal.get("prospective_entry_signal_parity_non_vacuous"), "signal coverage"
        ),
        "observer_pressure_parity_resolved": _boolean(
            observer.get("observer_archive_pressure_decision_parity_resolved"),
            "observer pressure parity",
        ),
        "observer_pressure_mismatches": _integer(
            observer.get("pressure_decision_mismatches"), "pressure mismatches"
        ),
        "observer_comparison_decisions": _integer(
            observer.get("comparison_decisions"), "comparison decisions"
        ),
    }


def _markout_summaries(report: Mapping[str, object]) -> dict[str, object]:
    markouts = _mapping(report.get("markouts"), "markouts")
    horizons = _mapping(markouts.get("horizons"), "markout horizons")
    return {
        horizon: _markout_summary(
            _mapping(_mapping(horizons.get(horizon), horizon).get("summary"), "summary")
        )
        for horizon in ("15", "60", "240")
    }


def _markout_summary(summary: Mapping[str, object]) -> dict[str, object]:
    return {
        "independent_paths": _integer(summary.get("independent_paths"), "paths"),
        "mean_after_friction_bps": _optional_number(
            summary.get("mean_after_modeled_friction_bps"), "mean markout"
        ),
        "mean_excluding_largest_bps": _optional_number(
            summary.get("mean_excluding_largest_after_modeled_friction_bps"),
            "ex-largest markout",
        ),
        "positive_paths": _integer(
            summary.get("positive_after_modeled_friction_count"), "positive paths"
        ),
        "positive_rate": _optional_number(
            summary.get("positive_after_modeled_friction_rate"), "positive rate"
        ),
    }


def _development_summary(report: Mapping[str, object]) -> dict[str, object]:
    economics = _mapping(report.get("development_economics"), "development economics")
    return {
        "source_status": _development_status(report),
        "nominal": _development_scenario(economics, "nominal", report),
        "stress": _development_scenario(economics, "stress", report),
    }


def _development_scenario(
    economics: Mapping[str, object], name: str, report: Mapping[str, object]
) -> dict[str, object]:
    scenario = _mapping(economics.get(name), f"development {name}")
    if report.get("schema_version") == "mu_development_path_threshold_diagnostic_v1":
        summary = _mapping(scenario.get("portfolio"), "MU portfolio")
        robust = _mapping(
            _mapping(scenario.get("robustness"), "robustness").get("all"),
            "all robustness",
        )
    else:
        summary = scenario
        robust = _mapping(
            _mapping(scenario.get("diagnostics"), "diagnostics").get("all"),
            "all diagnostics",
        )
    return {
        "trades": _integer(robust.get("trades"), "development trades"),
        "net_pnl_usd": _number(summary.get("net_pnl_usd"), "development net"),
        "profit_factor": _number(
            summary.get("profit_factor"), "development profit factor"
        ),
        "net_without_largest_winner_usd": _number(
            robust.get("net_without_largest_winner_usd"), "development ex-largest net"
        ),
        "profit_factor_without_largest_winner": _number(
            robust.get("profit_factor_without_largest_winner"),
            "development ex-largest PF",
        ),
    }


def _development_status(report: Mapping[str, object]) -> str:
    if report.get("schema_version") == "mu_development_path_threshold_diagnostic_v1":
        return _text(report.get("status"), "MU development status")
    suitability = _mapping(
        report.get("future_live_research_suitability"), "suitability"
    )
    return _text(suitability.get("status"), "development status")


def _economics_classification(markouts: Mapping[str, object]) -> str:
    short = _mapping(markouts.get("15"), "15m markouts")
    medium = _mapping(markouts.get("60"), "60m markouts")
    if _integer(short.get("independent_paths"), "15m paths") < 4:
        return "sparse"
    ex_short = _optional_number(
        short.get("mean_excluding_largest_bps"), "15m ex-largest"
    )
    ex_medium = _optional_number(
        medium.get("mean_excluding_largest_bps"), "60m ex-largest"
    )
    medium_paths = _integer(medium.get("independent_paths"), "60m paths")
    if ex_short is not None and ex_medium is not None:
        if ex_short > 0.0 and ex_medium > 0.0 and medium_paths >= 3:
            return "positive_ex_largest_15m_60m"
        if ex_short < 0.0 and ex_medium < 0.0:
            return "weak_ex_largest_15m_60m"
    return "mixed_or_concentrated"


def _research_disposition(
    technical: Mapping[str, object],
    markouts: Mapping[str, object],
    economics: str,
) -> str:
    if technical.get("observer_pressure_parity_resolved") is not True:
        return "pressure_transport_parity_unresolved"
    if economics == "weak_ex_largest_15m_60m":
        return "revise_or_hold"
    short = _mapping(markouts.get("15"), "15m markouts")
    if _integer(short.get("independent_paths"), "15m paths") < 4:
        return "continue_sparse_capture"
    if technical.get("signal_entry_parity_non_vacuous") is not True:
        return "continue_non_vacuous_signal_capture"
    return "continue_forward_lifecycle_research"


def _priority_key(row: Mapping[str, object]) -> tuple[int, str]:
    economics = row.get("prospective_economics")
    robust = row.get("development_robustness") == "positive_ex_largest_stress"
    if economics == "positive_ex_largest_15m_60m":
        rank = 0
    elif economics == "sparse" and robust:
        rank = 1
    elif robust:
        rank = 2
    else:
        rank = 3
    return rank, _text(row.get("symbol"), "candidate symbol")


def _development_robustness(development: Mapping[str, object]) -> str:
    stress = _mapping(development.get("stress"), "stress development")
    net = _number(stress.get("net_without_largest_winner_usd"), "stress ex-largest net")
    factor = _number(
        stress.get("profit_factor_without_largest_winner"), "stress ex-largest PF"
    )
    if net > 0.0 and factor > 1.0:
        return "positive_ex_largest_stress"
    return "largest_winner_dependent_stress"


def _validate_symbol(symbol: str) -> None:
    if not symbol.startswith("xyz:") or not symbol.removeprefix("xyz:"):
        raise ValueError("HIP-3 expansion symbol identity is invalid")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 expansion {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HIP-3 expansion {label} must be text")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"HIP-3 expansion {label} must be boolean")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HIP-3 expansion {label} must be nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 expansion {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"HIP-3 expansion {label} must be finite")
    return result


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)
