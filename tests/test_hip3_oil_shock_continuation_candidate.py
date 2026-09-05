"""Tests for exact HIP-3 oil shock-continuation portfolio evaluation."""

from __future__ import annotations

from importlib import import_module, util

from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)


_MODULE = "hypervector.research.hip3_oil_shock_continuation_candidate"


def test_continuation_candidate_module_exists() -> None:
    """The continuation replay has an identity distinct from reversion."""
    assert util.find_spec(_MODULE) is not None


def test_continuation_replay_is_development_only_and_distinct() -> None:
    """The frozen continuation hypothesis cannot alias reversion or open OOS."""
    module = import_module(_MODULE)
    builder = getattr(module, "evaluate_hip3_oil_shock_continuation_development", None)
    assert callable(builder)
    fixtures = import_module("test_hip3_oil_shock_reversion_candidate")
    bars, windows = fixtures._development_bars()
    signal = Hip3OilShockReversionConfig(
        return_lookback_bars=2,
        threshold_lookback_bars=4,
        minimum_history_bars=4,
        shock_quantile=0.75,
    )

    result = builder(bars, fixtures._execution(), windows=windows, signal=signal)

    assert result.proposed_provider_id == (
        "hip3_brentoil_oil_shock_continuation_bidirectional_5m_research_v1"
    )
    assert result.proposed_profile_id == (
        "brentoil_oil_shock_continuation_5m_development_v1"
    )
    assert result.development.nominal.completed_trades > 0
    assert len(result.folds) == 3
    assert result.out_of_sample_economics == "WITHHELD_NOT_EVALUATED"
    assert result.execution_authority == "none"


def test_continuation_report_freezes_its_distinct_schema() -> None:
    """Durable evidence cannot be mislabeled as the rejected reversion family."""
    module = import_module(_MODULE)
    fixtures = import_module("test_hip3_oil_shock_reversion_candidate")
    reporting = import_module("hypervector.research.hip3_oil_shock_reversion_reporting")
    friction_module = import_module(
        "hypervector.research.hip3_oil_shock_reversion_friction"
    )
    bars, windows = fixtures._development_bars()
    result = module.evaluate_hip3_oil_shock_continuation_development(
        bars, fixtures._execution(), windows=windows
    )
    friction = friction_module.Hip3OilFrictionContract(
        fixtures._execution(),
        500.0,
        5_000.0,
        750.0,
        3.0,
        5.0,
        4.0,
        7.0,
        0.5,
        1.0,
        8.46,
        6,
    )

    report = reporting.build_hip3_oil_development_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        friction,
    )

    assert report["schema_version"] == "hip3_oil_shock_continuation_development_v1"
    assert report["strategy_identity"]["mechanism"] == "continuation"
    assert report["out_of_sample_economics"] == "WITHHELD_NOT_EVALUATED"
