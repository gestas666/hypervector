"""Robustness diagnostics for selected maker-risk candidates."""

from __future__ import annotations

from importlib import import_module
import importlib.util
from pathlib import Path

import pytest


def _load_script() -> object:
    path = Path("scripts/hypervelocity_maker_risk_robustness.py")
    if not path.is_file():
        pytest.fail("maker risk robustness script is not implemented")
    spec = importlib.util.spec_from_file_location("maker_risk_robustness_script", path)
    if spec is None or spec.loader is None:
        pytest.fail("maker risk robustness script is not loadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _block(
    final_equity: float,
    trades: list[dict[str, object]],
    *,
    leverage: float = 30.0,
) -> dict[str, object]:
    return {
        "replay_window": {
            "data_start": "2026-01-01T00:00:00+00:00",
            "data_end": "2026-01-08T00:00:00+00:00",
        },
        "fresh": {
            "candidates": {
                "alloc70_lev30": {
                    "margin_fraction": 0.7,
                    "leverage": leverage,
                    "target_margin_pct": 8.0,
                    "replay": {
                        "initial_equity": 100.0,
                        "final_equity": final_equity,
                        "entry_fills": len(trades),
                        "completed_trades": len(trades),
                        "liquidations": sum(
                            trade["status"] == "liquidated" for trade in trades
                        ),
                        "maximum_drawdown_pct": -20.0,
                        "trades": trades,
                    },
                }
            }
        },
    }


def test_summary_reports_concentration_and_break_even_loss_rate() -> None:
    """The audit must expose compounding, concentration, and loss tolerance."""
    try:
        module = import_module("hypervector.research.maker_risk_robustness")
    except ModuleNotFoundError:
        pytest.fail("maker risk robustness summarizer is not implemented")
    blocks = [
        _block(
            120.0,
            [
                {"status": "target_completed", "net_pnl": 10.0, "fees": 1.0},
                {"status": "target_completed", "net_pnl": 10.0, "fees": 1.0},
            ],
        ),
        _block(
            80.0,
            [
                {"status": "target_completed", "net_pnl": 10.0, "fees": 1.0},
                {"status": "liquidated", "net_pnl": -30.0, "fees": 2.0},
            ],
        ),
    ]

    summary = module.summarize_candidate_blocks(blocks, "alloc70_lev30")

    assert summary["block_count"] == 2
    assert summary["positive_blocks"] == 1
    assert summary["product_ending_equity"] == pytest.approx(96.0)
    assert summary["completed_trade_count"] == 4
    assert summary["profitable_trade_count"] == 3
    assert summary["losing_trade_count"] == 1
    assert summary["gross_profit"] == pytest.approx(30.0)
    assert summary["gross_loss"] == pytest.approx(30.0)
    assert summary["aggregate_reset_block_pnl"] == pytest.approx(0.0)
    assert summary["largest_profitable_block_share"] == pytest.approx(1.0)
    assert summary["status_counts"] == {"liquidated": 1, "target_completed": 3}
    assert summary["worst_block_drawdown_pct"] == pytest.approx(-20.0)
    assert summary["profit_factor"] == pytest.approx(1.0)
    assert summary["largest_profitable_trade_share"] == pytest.approx(1.0 / 3.0)
    assert summary["observed_loss_rate"] == pytest.approx(0.25)
    assert summary["empirical_break_even_loss_rate"] == pytest.approx(0.25)
    assert summary["leave_one_block_out_product_min"] == pytest.approx(80.0)
    assert summary["leave_one_block_out_product_max"] == pytest.approx(120.0)
    assert summary["portfolio_paths_stitched_across_gaps"] is False


def test_summary_quantifies_loss_rate_sampling_uncertainty() -> None:
    """A profitable point estimate must retain its finite-sample uncertainty."""
    module = import_module("hypervector.research.maker_risk_robustness")
    blocks = [
        _block(
            100.0,
            [
                {"status": "target_completed", "net_pnl": 10.0, "fees": 1.0},
                {"status": "target_completed", "net_pnl": 10.0, "fees": 1.0},
                {"status": "target_completed", "net_pnl": 10.0, "fees": 1.0},
                {"status": "liquidated", "net_pnl": -30.0, "fees": 2.0},
            ],
        )
    ]

    summary = module.summarize_candidate_blocks(blocks, "alloc70_lev30")

    assert summary["loss_rate_wilson_95_lower"] == pytest.approx(0.0455873)
    assert summary["loss_rate_wilson_95_upper"] == pytest.approx(0.6993582)
    assert (
        summary["wilson_interval_assumption"]
        == "approximately_independent_stationary_binary_outcomes"
    )
    assert summary["loss_rate_upper_below_break_even"] is False
    assert summary["additional_zero_loss_trades_for_upper_below_break_even"] == 15


def test_summary_rejects_mixed_candidate_contracts() -> None:
    """Unlike leverage contracts must not be pooled into one robustness claim."""
    module = import_module("hypervector.research.maker_risk_robustness")
    target = [{"status": "target_completed", "net_pnl": 10.0, "fees": 1.0}]

    with pytest.raises(ValueError, match="candidate contract mismatch"):
        module.summarize_candidate_blocks(
            [_block(110.0, target), _block(110.0, target, leverage=40.0)],
            "alloc70_lev30",
        )


def test_summary_accepts_legacy_named_fresh_partition() -> None:
    """Older maker artifacts call the evaluated partition fresh_20260727."""
    module = import_module("hypervector.research.maker_risk_robustness")
    block = _block(
        110.0,
        [{"status": "target_completed", "net_pnl": 10.0, "fees": 1.0}],
    )
    block["fresh_20260727"] = block.pop("fresh")

    summary = module.summarize_candidate_blocks([block], "alloc70_lev30")

    assert summary["product_ending_equity"] == pytest.approx(110.0)


def test_summary_represents_zero_observed_losses_without_infinity() -> None:
    """JSON output must remain finite when every completed trade won."""
    module = import_module("hypervector.research.maker_risk_robustness")
    target = [{"status": "target_completed", "net_pnl": 10.0, "fees": 1.0}]

    summary = module.summarize_candidate_blocks(
        [_block(110.0, target)],
        "alloc70_lev30",
    )

    assert summary["profit_factor"] is None
    assert summary["empirical_break_even_loss_rate"] == 1.0
    assert summary["additional_zero_loss_trades_for_upper_below_break_even"] == 0


def test_summary_rejects_blocks_without_completed_trade_economics() -> None:
    """An empty population cannot support a loss-rate robustness claim."""
    module = import_module("hypervector.research.maker_risk_robustness")

    with pytest.raises(ValueError, match="completed trade economics"):
        module.summarize_candidate_blocks(
            [_block(100.0, [])],
            "alloc70_lev30",
        )


def test_robustness_script_contract_is_report_only() -> None:
    """The artifact generator must not imply runtime or promotion authority."""
    module = _load_script()
    args = module._parser().parse_args(
        ["--block", "block.json", "--out", "robustness.json"]
    )

    contract = module._experiment_contract(args)

    assert args.candidate == "alloc70_lev30"
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["selection_is_promotion"] is False
    assert contract["portfolio_paths_stitched_across_gaps"] is False
