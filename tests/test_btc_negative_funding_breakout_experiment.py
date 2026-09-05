from __future__ import annotations

from hypervector.research.btc_negative_funding_breakout_experiment import (
    BtcNegativeFundingBreakoutCell,
    build_btc_negative_funding_breakout_report,
)
from hypervector.research.btc_negative_funding_breakout_replay import (
    evaluate_btc_negative_funding_breakout,
)

from btc_negative_funding_breakout_fixtures import (
    negative_funding_breakout_bars,
)


def test_report_publishes_all_frozen_cells_and_rejects_sparse_results() -> None:
    """Publish every arm and scenario even when the candidate fails usefulness."""
    bars, funding, _, _ = negative_funding_breakout_bars()
    bars["funding_rate"] = 0.0
    cells: list[BtcNegativeFundingBreakoutCell] = []
    scenarios = {
        "nominal": (2.0, 0),
        "stress": (5.0, 0),
        "one_minute_entry_delay": (2.0, 1),
    }
    for partition in ("development", "validation", "pseudo_holdout"):
        for scenario, (slippage, delay) in scenarios.items():
            replay = evaluate_btc_negative_funding_breakout(
                bars,
                funding,
                slippage,
                entry_delay_minutes=delay,
            )
            cells.append(
                BtcNegativeFundingBreakoutCell(
                    partition,
                    scenario,
                    90.0,
                    replay,
                )
            )
    result = build_btc_negative_funding_breakout_report(cells)
    assert len(result.report["summary_rows"]) == 27
    assert len(result.report["comparisons"]) == 9
    assert not result.report["acceptance"]["candidate_supported"]
    assert (
        "validation_minimum_thirteen_trades"
        in result.report["acceptance"]["failed_checks"]
    )
    assert not result.report["acceptance"]["live_promotion_authorized"]
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.trade_rows


def test_report_rejects_incomplete_scenario_matrix() -> None:
    """Fail closed if any partition, scenario, or arm would be hidden."""
    bars, funding, _, _ = negative_funding_breakout_bars()
    bars["funding_rate"] = 0.0
    replay = evaluate_btc_negative_funding_breakout(bars, funding, 2.0)
    cell = BtcNegativeFundingBreakoutCell(
        "development",
        "nominal",
        90.0,
        replay,
    )
    try:
        build_btc_negative_funding_breakout_report([cell])
    except ValueError as error:
        assert "incomplete" in str(error)
    else:
        raise AssertionError("incomplete result matrix was accepted")
