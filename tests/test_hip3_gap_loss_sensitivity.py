"""Conservative HIP-3 unresolved-path loss sensitivity contracts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.hip3_gap_loss_sensitivity import (
    conservative_gap_loss_sensitivity,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)


def _trade(entry: str, pnl: float, notional: float) -> SharedPortfolioTrade:
    return SharedPortfolioTrade(
        "signal",
        "long",
        "2026-01-01T00:00:00+00:00",
        entry,
        "2026-01-01T00:30:00+00:00",
        0,
        1,
        2,
        100.0,
        101.0,
        None,
        99.2,
        82.0,
        notional / 100.0,
        notional / 5.0,
        notional,
        5.0,
        pnl,
        0.0,
        0.0,
        pnl,
        500.0,
        500.0 + pnl,
        "signal",
        False,
    )


def _report() -> SharedPortfolioReport:
    trades = (
        _trade("2026-01-01T00:15:00+00:00", 2.0, 75.0),
        _trade("2026-01-01T01:15:00+00:00", -0.5, 50.0),
    )
    return SharedPortfolioReport(
        500.0,
        501.5,
        1.5,
        0.3,
        -0.1,
        2,
        1,
        1,
        2.0,
        0.5,
        4.0,
        0,
        0.0,
        0.0,
        0,
        1,
        0,
        0,
        False,
        {},
        (),
        trades,
    )


def _threshold() -> dict[str, object]:
    key = (
        "long|2026-01-01T00:00:00+00:00|"
        "2026-01-01T00:15:00+00:00|2026-01-01T00:30:00+00:00"
    )
    scenario = {"affected_trades": 1}
    unresolved = ({"lifecycle_key": key},)
    return {
        "nominal": scenario,
        "stress": scenario,
        "unresolved_lifecycles": {
            "nominal": unresolved,
            "stress": unresolved,
        },
    }


def test_sensitivity_replaces_only_unresolved_trade_with_synthetic_loss() -> None:
    result = conservative_gap_loss_sensitivity(
        _report(), _report(), _threshold(), threshold_ms=15_000
    )

    stress = result["stress"]
    assert stress["affected_trades"] == 1
    assert stress["forced_loss_total_usd"] == pytest.approx(-0.75)
    assert stress["net_pnl_usd"] == pytest.approx(-1.25)
    assert stress["profit_factor"] == 0.0
    assert result["qualification_authority"] == "none"
    assert result["qualification_path_resolved"] is False


def test_sensitivity_rejects_unmatched_or_duplicate_lifecycle_identity() -> None:
    broken = _threshold()
    broken["unresolved_lifecycles"]["stress"] = ({"lifecycle_key": "missing"},)
    with pytest.raises(ValueError, match="does not match one trade"):
        conservative_gap_loss_sensitivity(
            _report(), _report(), broken, threshold_ms=15_000
        )

    duplicate = replace(_report(), trades=(_report().trades[0],) * 2)
    with pytest.raises(ValueError, match="must be unique"):
        conservative_gap_loss_sensitivity(
            duplicate, _report(), _threshold(), threshold_ms=15_000
        )
