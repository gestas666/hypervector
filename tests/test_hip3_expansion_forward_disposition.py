"""Evidence classification for prospective HIP-3 portfolio expansion."""

from __future__ import annotations

from collections.abc import Mapping
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.hip3_expansion_forward_disposition import (
    Hip3ExpansionEvidence,
    build_hip3_expansion_forward_disposition,
)


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }


def _development(symbol: str, ex_largest: float) -> dict[str, object]:
    summary = {
        "trades": 20,
        "net_pnl_usd": 4.0,
        "profit_factor": 1.4,
        "net_without_largest_winner_usd": ex_largest,
        "profit_factor_without_largest_winner": 1.1 if ex_largest > 0.0 else 0.9,
    }
    return {
        "schema_version": "hip3_development_only_diagnostic_v1",
        "symbol": symbol,
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "future_live_research_suitability": {
            "live_roster_change": False,
            "automatic_promotion": False,
            "status": "NOT_SUITABLE_TECHNICALLY_UNRESOLVED",
        },
        "development_economics": {
            "nominal": {**summary, "diagnostics": {"all": summary}},
            "stress": {**summary, "diagnostics": {"all": summary}},
        },
    }


def _evidence(
    symbol: str,
    *,
    sample: int,
    ex_15: float | None,
    ex_60: float | None,
    pressure_mismatches: int,
    development_ex_largest: float = 1.0,
) -> Hip3ExpansionEvidence:
    token = symbol.removeprefix("xyz:").lower()
    provider = f"hip3_{token}_full_l2_breakout_pressure_bidirectional_15m_v1"
    profile = f"{token}_full_l2_breakout_pressure_bidirectional_15m_research_v1"
    return Hip3ExpansionEvidence(
        symbol=symbol,
        development=_development(symbol, development_ex_largest),
        path_repair=_path_report(symbol),
        candle_parity=_candle_report(symbol),
        signal_parity=_signal_report(symbol, provider, profile, sample),
        observer_parity=_observer_report(
            symbol, provider, profile, sample, pressure_mismatches
        ),
        markouts=_markout_report(symbol, provider, profile, sample, ex_15, ex_60),
    )


def _path_report(symbol: str) -> dict[str, object]:
    return {
        "contract": _contract(),
        "source": {"symbol": symbol},
        "coverage": {"completed_bars": 100},
        "technical_assessment": {
            "prospective_bar_path_coverage_resolved": True,
            "original_unresolved_bars": 3,
            "repaired_bars": 3,
            "unresolved_bars": 0,
        },
    }


def _candle_report(symbol: str) -> dict[str, object]:
    return {
        "contract": _contract(),
        "scope": {"symbol": symbol},
        "coverage": {
            "expected_bars": 100,
            "exact_ohlc_bars": 80,
            "mismatched_ohlc_bars": 20,
        },
        "technical_assessment": {"candle_ohlc_parity_resolved": False},
    }


def _signal_report(
    symbol: str, provider: str, profile: str, sample: int
) -> dict[str, object]:
    return {
        "contract": _contract(),
        "scope": {"symbol": symbol, "provider_id": provider, "profile_id": profile},
        "coverage": {"decision_bars": 50, "venue_entry_events": max(sample - 1, 0)},
        "technical_assessment": {
            "prospective_signal_source_parity_resolved": True,
            "prospective_entry_signal_parity_non_vacuous": sample > 1,
            "signal_disagreement_bars": 0,
            "unresolved_pressure_bars": 0,
        },
    }


def _observer_report(
    symbol: str, provider: str, profile: str, sample: int, mismatches: int
) -> dict[str, object]:
    return {
        "contract": _contract(),
        "scope": {"symbol": symbol, "provider_id": provider, "profile_id": profile},
        "technical_assessment": {
            "comparison_decisions": 50,
            "archive_entry_events": max(sample - 1, 0),
            "observer_entry_events": sample,
            "non_vacuous_entry_comparison": sample > 0,
            "observer_archive_pressure_decision_parity_resolved": mismatches == 0,
            "pressure_decision_mismatches": mismatches,
        },
    }


def _markout_report(
    symbol: str,
    provider: str,
    profile: str,
    sample: int,
    ex_15: float | None,
    ex_60: float | None,
) -> dict[str, object]:
    horizons = {
        "15": {"summary": _markout_summary(sample, ex_15)},
        "60": {"summary": _markout_summary(sample, ex_60)},
        "240": {"summary": _markout_summary(max(sample - 1, 0), None)},
    }
    return {
        "symbol": symbol,
        "provider_id": provider,
        "profile_id": profile,
        "execution_authority": "none",
        "report_only": True,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "fills_assumed": False,
            "pnl_claimed": False,
        },
        "markouts": {"horizons": horizons},
    }


def _markout_summary(sample: int, ex_largest: float | None) -> Mapping[str, object]:
    return {
        "independent_paths": sample,
        "mean_after_modeled_friction_bps": 5.0 if sample else None,
        "mean_excluding_largest_after_modeled_friction_bps": ex_largest,
        "positive_after_modeled_friction_count": sample // 2,
        "positive_after_modeled_friction_rate": 0.5 if sample else None,
    }


def test_pressure_mismatch_remains_unresolved_despite_robust_markouts() -> None:
    """Positive small-sample economics must not erase transport disagreement."""
    report = build_hip3_expansion_forward_disposition(
        [_evidence("xyz:MU", sample=5, ex_15=1.2, ex_60=18.0, pressure_mismatches=1)]
    )
    candidate = report["candidates"][0]

    assert candidate["prospective_economics"] == "positive_ex_largest_15m_60m"
    assert candidate["research_disposition"] == "pressure_transport_parity_unresolved"
    assert candidate["live_readiness_claimed"] is False
    assert report["contract"]["automatic_live_promotion"] is False
    assert report["contract"]["execution_authority"] == "none"


def test_sparse_and_weak_forward_evidence_remain_distinct() -> None:
    """One positive event is sparse while repeated negative ex-largest is weak."""
    report = build_hip3_expansion_forward_disposition(
        [
            _evidence(
                "xyz:SKHX", sample=1, ex_15=None, ex_60=None, pressure_mismatches=1
            ),
            _evidence(
                "xyz:SILVER", sample=4, ex_15=-7.5, ex_60=-6.0, pressure_mismatches=0
            ),
            _evidence(
                "xyz:CL",
                sample=2,
                ex_15=-7.4,
                ex_60=-16.6,
                pressure_mismatches=0,
                development_ex_largest=-1.0,
            ),
        ]
    )
    rows = {row["symbol"]: row for row in report["candidates"]}

    assert rows["xyz:SKHX"]["prospective_economics"] == "sparse"
    assert (
        rows["xyz:SKHX"]["research_disposition"]
        == "pressure_transport_parity_unresolved"
    )
    assert rows["xyz:SILVER"]["prospective_economics"] == "weak_ex_largest_15m_60m"
    assert rows["xyz:SILVER"]["research_disposition"] == "revise_or_hold"
    assert rows["xyz:CL"]["prospective_economics"] == "sparse"
    assert rows["xyz:CL"]["research_disposition"] == "continue_sparse_capture"
    assert rows["xyz:SKHX"]["development_robustness"] == "positive_ex_largest_stress"
    assert rows["xyz:CL"]["development_robustness"] == "largest_winner_dependent_stress"
    assert report["research_priority_order"] == ["xyz:SKHX", "xyz:SILVER", "xyz:CL"]


def test_identity_or_authority_mismatch_fails_closed() -> None:
    """A report cannot combine aliased route identity or execution-shaped input."""
    candidate = _evidence(
        "xyz:MU", sample=5, ex_15=1.0, ex_60=2.0, pressure_mismatches=0
    )
    candidate.observer_parity["scope"]["symbol"] = "xyz:CL"

    with pytest.raises(ValueError, match="identity"):
        build_hip3_expansion_forward_disposition([candidate])

    candidate = _evidence(
        "xyz:MU", sample=5, ex_15=1.0, ex_60=2.0, pressure_mismatches=0
    )
    candidate.path_repair["contract"]["execution_authority"] = "live"
    with pytest.raises(ValueError, match="authority"):
        build_hip3_expansion_forward_disposition([candidate])


def _script() -> ModuleType:
    path = Path("scripts/hip3_expansion_forward_disposition.py")
    spec = importlib.util.spec_from_file_location(
        "hip3_expansion_disposition_script", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("HIP-3 expansion disposition script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_arguments(tmp_path: Path) -> list[str]:
    evidence = _evidence(
        "xyz:MU", sample=5, ex_15=1.2, ex_60=18.0, pressure_mismatches=1
    )
    values = (
        evidence.development,
        evidence.path_repair,
        evidence.candle_parity,
        evidence.signal_parity,
        evidence.observer_parity,
        evidence.markouts,
    )
    paths: list[str] = []
    for index, value in enumerate(values):
        path = tmp_path / f"input-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(str(path))
    return ["--candidate", "xyz:MU", *paths]


def test_script_publishes_immutable_source_bound_disposition(tmp_path: Path) -> None:
    """Publication must retain every exact source hash and remain authority-none."""
    script = _script()
    output = tmp_path / "disposition.json"
    arguments = [*_candidate_arguments(tmp_path), "--output", str(output)]

    report = script.run_command(script.build_parser().parse_args(arguments))

    assert output.is_file()
    assert report["contract"]["execution_authority"] == "none"
    assert set(report["input_evidence"]["xyz:MU"]) == {
        "development",
        "path_repair",
        "candle_parity",
        "signal_parity",
        "observer_parity",
        "markouts",
    }
    with pytest.raises(FileExistsError):
        script.run_command(script.build_parser().parse_args(arguments))
