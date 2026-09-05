"""V79 acceptance for exact fill-cost and execution-quality evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.v79_poststart_acceptance import (
    build_v79_poststart_acceptance,
)
from test_v79_closed_lifecycle_acceptance import _closed_checkpoint
from test_v79_poststart_acceptance import _epoch

_NOW = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "field",
    ["expected_price", "slippage_bps", "acknowledgement_latency_ms"],
)
def test_v79_rejects_missing_entry_execution_quality(field: str) -> None:
    """Every accepted entry fill must retain reconstructable quality evidence."""
    config, checkpoint = _closed_checkpoint()
    checkpoint["audit"]["execution"]["fill_details"][0].pop(field)

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "execution_quality_incomplete" in report["reasons"]


def test_v79_rejects_slippage_that_disagrees_with_exact_fill() -> None:
    """Reported slippage must reproduce from expected price, fill, and side."""
    config, checkpoint = _closed_checkpoint()
    checkpoint["audit"]["execution"]["fill_details"][0]["slippage_bps"] = 1.0

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "execution_quality_metric_mismatch" in report["reasons"]


def test_v79_rejects_entry_slippage_above_asset_ioc_cap() -> None:
    """A BTC entry beyond its configured 20-bps IOC cap must be visible."""
    config, checkpoint = _closed_checkpoint()
    entry = checkpoint["audit"]["execution"]["fill_details"][0]
    entry.update({"expected_price": 100.0, "price": 99.79, "slippage_bps": 21.0})
    trade = checkpoint["audit"]["trade_reflections"]["trades"][0]
    trade["entry"]["price"] = 99.79

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "entry_slippage_cap_exceeded:BTC:10" in report["reasons"]


def test_v79_rejects_entry_fee_above_declared_route_model() -> None:
    """Realized entry fees above the declared model must reject acceptance."""
    config, checkpoint = _closed_checkpoint()
    entry = checkpoint["audit"]["execution"]["fill_details"][0]
    entry["fee_usd"] = 0.01

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "entry_fee_model_exceeded:BTC:10" in report["reasons"]


def test_v79_rejects_execution_quality_summary_drift() -> None:
    """Aggregate quality counters cannot disagree with exact fill evidence."""
    config, checkpoint = _closed_checkpoint()
    checkpoint["audit"]["execution"]["fee_rate_bps"]["count"] = 1

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "execution_quality_summary_mismatch" in report["reasons"]


def test_v79_accepts_explicit_no_fill_quality_state() -> None:
    """A fresh run with no fills reports zero quality coverage without invention."""
    config, checkpoint = _closed_checkpoint()
    execution = checkpoint["audit"]["execution"]
    execution.update(
        {
            "fills": 0,
            "current_run_fills": 0,
            "projected_fills": 0,
            "closed_trades": 0,
            "fees_usd": 0.0,
            "funding_usd": 0.0,
            "net_pnl_usd": 0.0,
            "wins": 0,
            "losses": 0,
            "fill_details": [],
            "fee_rate_bps": _no_fill_metric(),
            "slippage_bps": _no_fill_metric(),
            "acknowledgement_latency_ms": _no_fill_metric(),
        }
    )
    checkpoint["audit"]["trade_reflections"] = {"closed_trades": 0, "trades": []}

    report = _report(checkpoint, config)

    assert report["accepted"] is True
    assert report["checks"]["execution_attribution"]["costed_fills"] == 0


def _report(
    checkpoint: dict[str, object], config: MultiAssetLiveConfig
) -> dict[str, object]:
    return build_v79_poststart_acceptance(
        deepcopy(checkpoint),
        config,
        _epoch(),
        now_utc=_NOW,
    )


def _no_fill_metric() -> dict[str, object]:
    return {
        "status": "not_applicable_no_fills",
        "count": 0,
        "minimum": None,
        "median": None,
        "maximum": None,
        "mean": None,
    }
