"""Tests for the exact-v39 causal challenger research program."""

from __future__ import annotations

import pytest

from hypervector.research.v39_causal_challenger_program import (
    build_v39_causal_challenger_program,
)


def test_program_registers_one_entry_and_one_exit_challenger() -> None:
    """Registered challengers remain annotations without execution authority."""
    report = build_v39_causal_challenger_program(_forward(), _checkpoint())

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "current_v39_strategy_signals_authoritative": True,
        "entry_gate": False,
        "exit_authority": False,
        "position_sizing_authority": False,
        "automatic_retuning": False,
        "automatic_promotion": False,
        "performance_thresholds_are_execution_gates": False,
    }
    assert set(report["experiments"]) == {
        "entry_microstructure_ranker",
        "exit_momentum_support_decay",
    }
    entry = report["experiments"]["entry_microstructure_ranker"]
    exit_study = report["experiments"]["exit_momentum_support_decay"]
    assert entry["action"] == "rank_and_annotate_only"
    assert entry["model"]["family"] == "ridge_regression_l2"
    assert entry["features"][0]["name"] == "side_aligned_opi_depth10"
    assert exit_study["action"] == "label_and_annotate_only"
    assert exit_study["model"]["family"] == "logistic_regression_l2"
    assert exit_study["features"][0]["name"] == "directional_rsi_level"


def test_program_reports_exact_sample_and_scope_readiness() -> None:
    """Sparse resolved outcomes and absent HIP-3 regimes remain explicit."""
    report = build_v39_causal_challenger_program(_forward(), _checkpoint())

    assert report["current_exact_sample"] == {
        "eligible_evaluations": 12,
        "resolved_closed_lifecycles": 1,
        "provisional_open_lifecycles": 2,
        "canonical_regime_symbols": ["BTC", "ETH", "HYPE", "SOL"],
    }
    assert report["experiments"]["entry_microstructure_ranker"]["stage"] == (
        "capture_and_join_required_before_fit"
    )
    assert report["experiments"]["exit_momentum_support_decay"]["scope"] == (
        "core_symbols_with_canonical_regime_telemetry"
    )
    assert report["assessment"]["model_fit_now"] is False
    assert report["assessment"]["reason"] == "resolved_lifecycle_sample_is_sparse"


def test_program_rejects_authoritative_or_wrong_profile_input() -> None:
    """Research contracts fail closed on authority or profile aliasing."""
    forward = _forward()
    forward["contract"]["execution_authority"] = "live"
    with pytest.raises(ValueError, match="authority-none"):
        build_v39_causal_challenger_program(forward, _checkpoint())

    forward = _forward()
    forward["source"]["profile_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="v39 profile identity"):
        build_v39_causal_challenger_program(forward, _checkpoint())


def _forward() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "performance_gate": False,
        },
        "source": {
            "profile_id": (
                "multi_asset_bidirectional_hype_compression_"
                "range_retired_current_canary_v39"
            ),
            "profile_fingerprint": (
                "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5"
            ),
        },
        "summary": {
            "eligible_evaluations": 12,
            "closed_trades": 1,
        },
    }


def _checkpoint() -> dict[str, object]:
    return {
        "audit": {
            "open_trade_reflections": {"trades": [{}, {}]},
            "canonical_regime_telemetry": {
                "by_symbol": {symbol: {} for symbol in ("SOL", "BTC", "HYPE", "ETH")}
            },
        }
    }
