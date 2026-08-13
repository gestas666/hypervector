"""Tests for the resolved/provisional ignored-provider-exit scorecard."""

from importlib import import_module


def test_scorecard_separates_resolved_and_provisional_exit_modes() -> None:
    """Open continuation must never be pooled with authoritative closed paths."""
    module = import_module(
        "hypervector.research.cohort_ignored_provider_exit_scorecard"
    )
    closed = (
        _trade(
            "closed-a",
            "xyz:GOLD",
            "commodity-swing",
            "ignored_provider_exit_outcome",
            "ha_flip",
            "hip3_swing_ha_flip",
            15.0,
            ignored_signals=2,
        ),
        _no_signal_trade(
            "closed-b",
            "xyz:SPCX",
            "index-swing",
            "ignored_provider_exit_outcome",
        ),
    )
    opened = (
        _trade(
            "open-a",
            "xyz:GOLD",
            "commodity-swing",
            "ignored_provider_exit_observer",
            "ha_flip",
            "hip3_swing_ha_flip",
            7.0,
            ignored_signals=18,
        ),
        _trade(
            "open-b",
            "xyz:SPCX",
            "index-swing",
            "ignored_provider_exit_observer",
            "alignment_loss",
            "hip3_swing_alignment_loss",
            362.0,
            ignored_signals=18,
        ),
    )

    scorecard = module.build_ignored_provider_exit_policy_scorecard(
        closed_trades=closed,
        open_trades=opened,
    )

    assert scorecard["contract"] == {
        "automatic_promotion": False,
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
    }
    assert scorecard["resolved"]["total_lifecycles"] == 2
    assert scorecard["resolved"]["observed_ignored_exit_lifecycles"] == 1
    assert scorecard["resolved"]["continuation_bps"] == {
        "count": 1,
        "favorable_count": 1,
        "maximum": 15.0,
        "mean": 15.0,
        "mean_excluding_largest": None,
        "median": 15.0,
        "minimum": 15.0,
        "nonpositive_count": 0,
    }
    assert scorecard["provisional_open"]["continuation_bps"]["mean"] == 184.5
    assert (
        scorecard["provisional_open"]["continuation_bps"]["mean_excluding_largest"]
        == 7.0
    )
    trajectory = scorecard["provisional_open"]["path_trajectory_bps"]
    assert trajectory["observed_lifecycles"] == 2
    assert trajectory["unavailable_lifecycles"] == 0
    assert trajectory["maximum_favorable_excursion"]["mean"] == 194.5
    assert trajectory["maximum_adverse_excursion"]["mean"] == 4.0
    assert trajectory["peak_giveback"]["mean"] == 10.0
    modes = scorecard["provisional_open"]["by_provider_exit_mode"]
    assert [row["exit_mode"] for row in modes] == ["ha_flip", "alignment_loss"]
    assert [row["ignored_signal_count"] for row in modes] == [18, 18]
    assert modes[0]["path_trajectory_bps"]["peak_giveback"]["mean"] == 5.0
    assert modes[1]["path_trajectory_bps"]["peak_giveback"]["mean"] == 15.0
    assert scorecard["decision"] == "insufficient_resolved_exit_evidence"


def test_scorecard_labels_missing_recorded_exit_mode_as_unavailable() -> None:
    """Legacy evidence must remain auditable without inventing an exit mode."""
    trade = _trade(
        "closed-legacy",
        "BTC",
        "hulk",
        "ignored_provider_exit_outcome",
        "placeholder",
        "hulk_exit_flip",
        -4.0,
        ignored_signals=1,
    )
    evidence = trade["ignored_provider_exit_outcome"]
    assert isinstance(evidence, dict)
    first_signal = evidence["first_signal"]
    assert isinstance(first_signal, dict)
    readiness = first_signal["readiness"]
    assert isinstance(readiness, dict)
    readiness["metrics"] = {}

    module = import_module(
        "hypervector.research.cohort_ignored_provider_exit_scorecard"
    )
    scorecard = module.build_ignored_provider_exit_policy_scorecard(
        closed_trades=(trade,),
        open_trades=(),
    )

    resolved = scorecard["resolved"]
    assert resolved["exit_mode_unavailable_lifecycles"] == 1
    grouped = resolved["by_provider_exit_mode"]
    assert grouped[0]["exit_mode"] == "unavailable"
    assert grouped[0]["exit_mode_status"] == (
        "unavailable_in_recorded_readiness_metrics"
    )


def test_scorecard_counts_unavailable_excursion_path_without_inventing_values() -> None:
    """A mark-only path must not become fabricated completed-candle excursion."""
    trade = _trade(
        "open-mark-only",
        "xyz:GOLD",
        "commodity-swing",
        "ignored_provider_exit_observer",
        "ha_flip",
        "hip3_swing_ha_flip",
        4.0,
        ignored_signals=1,
    )
    evidence = trade["ignored_provider_exit_observer"]
    assert isinstance(evidence, dict)
    evidence["path_since_first_signal"] = {
        "status": "unavailable",
        "current_directional_return_bps": 4.0,
        "maximum_favorable_excursion_bps": None,
        "maximum_adverse_excursion_bps": None,
        "peak_giveback_bps": None,
    }

    module = import_module(
        "hypervector.research.cohort_ignored_provider_exit_scorecard"
    )
    scorecard = module.build_ignored_provider_exit_policy_scorecard(
        closed_trades=(),
        open_trades=(trade,),
    )

    trajectory = scorecard["provisional_open"]["path_trajectory_bps"]
    assert trajectory["observed_lifecycles"] == 0
    assert trajectory["unavailable_lifecycles"] == 1
    assert trajectory["maximum_favorable_excursion"]["count"] == 0
    assert trajectory["peak_giveback"]["mean"] is None


def _trade(
    lifecycle_id: str,
    symbol: str,
    strategy_id: str,
    evidence_key: str,
    exit_mode: str,
    exit_reason: str,
    continuation_bps: float,
    *,
    ignored_signals: int,
) -> dict[str, object]:
    favorable = continuation_bps + 5.0
    path = {
        "status": "observed",
        "current_directional_return_bps": continuation_bps,
        "maximum_favorable_excursion_bps": favorable,
        "maximum_adverse_excursion_bps": 4.0,
        "peak_giveback_bps": 5.0,
    }
    if symbol == "xyz:SPCX":
        path.update(
            maximum_favorable_excursion_bps=377.0,
            maximum_adverse_excursion_bps=4.0,
            peak_giveback_bps=15.0,
        )
    continuation_fields: dict[str, object]
    if evidence_key == "ignored_provider_exit_outcome":
        continuation_fields = {
            "gross_continuation_from_signal_bps": continuation_bps,
            "path_from_first_signal_to_actual_exit": path,
        }
    else:
        continuation_fields = {"path_since_first_signal": path}
    return {
        "lifecycle_id": lifecycle_id,
        "symbol": symbol,
        "strategy_id": strategy_id,
        evidence_key: {
            "status": "observed",
            "ignored_signal_count": ignored_signals,
            "first_signal": {
                "exit_reason": exit_reason,
                "readiness": {"metrics": {"exit_mode": exit_mode}},
            },
            **continuation_fields,
        },
    }


def _no_signal_trade(
    lifecycle_id: str,
    symbol: str,
    strategy_id: str,
    evidence_key: str,
) -> dict[str, object]:
    return {
        "lifecycle_id": lifecycle_id,
        "symbol": symbol,
        "strategy_id": strategy_id,
        evidence_key: {
            "status": "no_ignored_exit_observed",
            "ignored_signal_count": 0,
            "first_signal": None,
        },
    }
