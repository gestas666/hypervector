"""Tests for independent BTC option-flow trade-summary reproduction."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_option_flow_result_reproduction import (
    reconcile_development_fold_summaries,
    reconcile_trade_summary,
)


def test_trade_summary_reconciles_net_costs_profit_factor_and_ex_largest() -> None:
    """Every reported economic aggregate must derive from its trade rows."""
    trades = pd.DataFrame(
        {
            "net_pnl_usd": [10.0, -5.0],
            "fees_usd": [1.0, 2.0],
            "funding_cashflow_usd": [0.5, -0.25],
            "exit_reason": ["target", "stop"],
        }
    )
    summary = {
        "completed_trades": 2,
        "wins": 1,
        "losses": 1,
        "net_pnl_usd": 5.0,
        "profit_factor": 2.0,
        "total_fees_usd": 3.0,
        "funding_cashflow_usd": 0.25,
        "largest_winner_usd": 10.0,
        "net_pnl_excluding_largest_winner_usd": -5.0,
        "exit_reasons": {"stop": 1, "target": 1},
    }

    reconcile_trade_summary(summary, trades)

    summary["net_pnl_usd"] = 6.0
    with pytest.raises(ValueError, match="net PnL"):
        reconcile_trade_summary(summary, trades)


def test_development_fold_summaries_reconcile_from_complete_trade_rows() -> None:
    """Frozen fold summaries must reproduce from their exact trade sidecar."""
    rows = [
        {"fold_id": 0, "completed_trades": 0, "net_pnl_usd": 0.0},
        {"fold_id": 1, "completed_trades": 2, "net_pnl_usd": 3.5},
    ]
    trades = pd.DataFrame(
        {
            "fold_id": [1, 1],
            "net_pnl_usd": [5.0, -1.5],
        }
    )

    reconcile_development_fold_summaries(rows, trades)

    rows[1]["completed_trades"] = 1
    with pytest.raises(ValueError, match="fold 1 completed trades"):
        reconcile_development_fold_summaries(rows, trades)


def test_development_fold_sidecar_rejects_unknown_fold() -> None:
    """A sidecar row outside the frozen fold set is an evidence defect."""
    rows = [{"fold_id": 0, "completed_trades": 0, "net_pnl_usd": 0.0}]
    trades = pd.DataFrame({"fold_id": [2], "net_pnl_usd": [1.0]})

    with pytest.raises(ValueError, match="unexpected fold IDs"):
        reconcile_development_fold_summaries(rows, trades)
