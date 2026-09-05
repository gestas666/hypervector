"""Tests for frozen BTC option-flow acceptance and bootstrap gates."""

from __future__ import annotations

from hypervector.research.btc_option_flow_acceptance import (
    evaluate_frozen_option_flow_acceptance,
    trade_bootstrap_90pct,
)


def test_constant_trade_bootstrap_has_exact_positive_lower_bound() -> None:
    """A deterministic positive sample should have a deterministic bound."""
    estimate = trade_bootstrap_90pct((1.0,) * 20, resamples=1_000, seed=58)

    assert estimate.point_mean_usd == 1.0
    assert estimate.lower_90pct_usd == 1.0
    assert estimate.upper_90pct_usd == 1.0


def test_acceptance_requires_all_oos_scenarios_controls_and_three_folds() -> None:
    """A fully repeated candidate can pass but still gains no live authority."""
    rows = _passing_rows()
    folds = [
        {"fold_id": index, "net_pnl_usd": 1.0 if index < 3 else -1.0}
        for index in range(5)
    ]

    result = evaluate_frozen_option_flow_acceptance(
        rows,
        folds,
        pooled_oos_trade_net_pnl_usd=(1.0,) * 20,
        bootstrap_resamples=1_000,
        bootstrap_seed=58,
    )

    assert result["candidate_supported_for_future_only_capture"] is True
    assert result["failed_checks"] == []
    assert result["live_promotion_authorized"] is False
    assert result["retuning_authorized"] is False


def test_acceptance_fails_delayed_loss_repeatability_and_control_comparison() -> None:
    """One weak OOS cell or concentrated result must reject the exact candidate."""
    rows = _passing_rows()
    delayed = next(
        row
        for row in rows
        if row["partition"] == "validation"
        and row["scenario"] == "delayed"
        and row["arm"] == "candidate"
    )
    delayed["net_pnl_usd"] = -1.0
    nominal = next(
        row
        for row in rows
        if row["partition"] == "pseudo_holdout"
        and row["scenario"] == "nominal"
        and row["arm"] == "sweep_control"
    )
    nominal["net_pnl_usd"] = 20.0
    folds = [{"fold_id": index, "net_pnl_usd": -1.0} for index in range(5)]

    result = evaluate_frozen_option_flow_acceptance(
        rows,
        folds,
        pooled_oos_trade_net_pnl_usd=(10.0, -20.0) * 10,
        bootstrap_resamples=1_000,
        bootstrap_seed=58,
    )

    failures = result["failed_checks"]
    assert "validation_delayed_positive_net" in failures
    assert "pseudo_holdout_nominal_exceeds_sweep_control" in failures
    assert "development_minimum_three_positive_folds" in failures
    assert "pooled_oos_bootstrap_90pct_lower_positive" in failures
    assert result["candidate_supported_for_future_only_capture"] is False


def test_acceptance_rejects_an_empty_oos_trade_bootstrap_without_crashing() -> None:
    """Zero candidate trades are a measured rejection, not an evaluation error."""
    rows = _passing_rows()
    for row in rows:
        if row["arm"] == "candidate":
            row["completed_trades"] = 0
            row["wins"] = 0
            row["losses"] = 0
    folds = [{"fold_id": index, "net_pnl_usd": 1.0} for index in range(5)]

    result = evaluate_frozen_option_flow_acceptance(
        rows,
        folds,
        pooled_oos_trade_net_pnl_usd=(),
        bootstrap_resamples=1_000,
        bootstrap_seed=58,
    )

    assert "pooled_oos_bootstrap_requires_completed_trades" in result["failed_checks"]
    assert result["pooled_oos_trade_bootstrap"] is None


def _passing_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for partition in ("validation", "pseudo_holdout"):
        for scenario in ("nominal", "stress", "delayed"):
            rows.append(_row(partition, scenario, "candidate", 10.0))
            rows.append(_row(partition, scenario, "direction_inverted_placebo", 0.0))
            rows.append(_row(partition, scenario, "sweep_control", 0.0))
            rows.append(_row(partition, scenario, "no_action", 0.0))
    return rows


def _row(partition: str, scenario: str, arm: str, net: float) -> dict[str, object]:
    return {
        "partition": partition,
        "scenario": scenario,
        "arm": arm,
        "completed_trades": 10 if arm == "candidate" else 0,
        "net_pnl_usd": net,
        "profit_factor": 2.0 if arm == "candidate" else None,
        "wins": 6 if arm == "candidate" else 0,
        "losses": 4 if arm == "candidate" else 0,
        "net_pnl_excluding_largest_winner_usd": net / 2.0,
        "liquidations": 0,
        "insolvent": False,
    }
