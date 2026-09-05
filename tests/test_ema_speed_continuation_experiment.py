"""Development-only orchestration tests for the EMA-speed challenger."""

from __future__ import annotations

from hypervector.research.ema_speed_continuation_experiment import (
    assess_ema_speed_development,
    registered_development_folds,
)


def test_registered_folds_are_purged_and_never_open_oos() -> None:
    """The experiment exposes only three frozen development intervals."""
    folds = registered_development_folds()
    assert len(folds) == 3
    assert folds[0].start_utc.isoformat() == "2025-05-01T00:00:00+00:00"
    assert folds[-1].end_utc.isoformat() == "2026-05-01T00:00:00+00:00"
    assert (folds[1].start_utc - folds[0].end_utc).total_seconds() == 86_400
    assert (folds[2].start_utc - folds[1].end_utc).total_seconds() == 86_400


def test_positive_economics_cannot_bypass_unresolved_path() -> None:
    """Missing mark truth blocks validation even when every economic check passes."""
    assessment = assess_ema_speed_development(
        pooled_nominal=_pooled(),
        pooled_stress=_pooled(),
        stress_folds=(_pooled(), _pooled(), _pooled()),
        side_stress={"long": _side(), "short": _side()},
        technical_ready=False,
    )
    assert assessment["economic_acceptance"] is True
    assert assessment["validation_open_authorized"] is False
    assert assessment["status"] == "not_suitable_technical_path_unresolved"


def test_negative_fold_rejects_without_parameter_rescue() -> None:
    """One losing development fold is a frozen economic falsifier."""
    losing = _pooled()
    losing["net_pnl_usd"] = -0.01
    assessment = assess_ema_speed_development(
        pooled_nominal=_pooled(),
        pooled_stress=_pooled(),
        stress_folds=(_pooled(), losing, _pooled()),
        side_stress={"long": _side(), "short": _side()},
        technical_ready=True,
    )
    assert assessment["economic_acceptance"] is False
    assert assessment["status"] == "rejected_development_economics"
    assert assessment["retuning_authorized"] is False


def _pooled() -> dict[str, float]:
    return {
        "net_pnl_usd": 10.0,
        "profit_factor": 1.2,
        "net_pnl_excluding_largest_winner_usd": 3.0,
    }


def _side() -> dict[str, float]:
    return {"net_pnl_usd": 2.0}
