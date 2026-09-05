"""Post-close funding and mark-path resolution for HYPE-native v54."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.hype_native_prospective_resolution import (
    HypeProxyExitUnconfirmedError,
    resolve_hype_native_prospective_lifecycles,
)


def _report(*, exit_reason: str = "maximum_hold") -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_prospective_lifecycle_report_only",
        "status": "resolved_proxy_lifecycle_evidence_available",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "execution": {
                "maximum_exit_delay_ms": 60_000,
                "fee_bps_per_side": 4.32,
                "residual_slippage_bps_per_side": 2.0,
            },
        },
        "identity": {
            "profile_id": "multi_asset_growth_first_5000_hype_native_long_challenger_v54",
            "profile_fingerprint": "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643",
            "strategy_id": "hype_native_breakout_onset_long_v3",
            "symbol": "HYPE",
        },
        "lifecycles": [
            {
                "decision_time_ms": 0,
                "side": "long",
                "entry_book_time_ms": 1_000,
                "entry_price": 100.0,
                "entry_quantity": 10.0,
                "stop_price": 99.0,
                "exit_book_time_ms": 5_000,
                "exit_reason": exit_reason,
                "net_pnl_usd_before_funding": 10.0,
                "technical_path_resolved": True,
            }
        ],
    }


def _funding() -> HlFundingEvidence:
    return HlFundingEvidence(
        symbol="HYPE",
        start_ms=0,
        end_ms=6_000,
        rows=(
            {"event_ts_ms": 2_000, "funding_rate": 0.001},
            {"event_ts_ms": 4_000, "funding_rate": -0.0005},
        ),
        evidence={"complete": True},
    )


def _prices(*, crossed: bool = False) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_ms": [1_000, 1_500, 2_500, 3_500, 4_500, 5_000],
            "mark_price": [100.0, 99.5, 98.9 if crossed else 99.4, 100.5, 101.0, 104.0],
            "oracle_price": [100.0, 100.0, 105.0, 110.0, 112.0, 104.0],
        }
    )


def test_resolved_path_adds_exact_funding_and_no_earlier_mark_stop() -> None:
    """A complete path produces after-funding economics and exact mark truth."""
    report = resolve_hype_native_prospective_lifecycles(
        _report(),
        _funding(),
        _prices(),
        maximum_oracle_staleness_ms=600,
        maximum_mark_gap_ms=1_000,
    )

    lifecycle = report["lifecycles"][0]
    assert lifecycle["funding_event_count"] == 2
    assert lifecycle["funding_cashflow_usd"] == pytest.approx(-0.45)
    assert lifecycle["net_pnl_usd_after_funding"] == pytest.approx(9.55)
    assert lifecycle["mark_stop_truth"] == "confirmed_no_earlier_mark_stop"
    assert lifecycle["maximum_mark_gap_ms"] == 1_000
    assert report["summary"]["net_pnl_usd_after_funding"] == pytest.approx(9.55)


def test_mark_cross_before_nonstop_exit_invalidates_proxy_lifecycle() -> None:
    """A real mark stop cannot be ignored by a later timer or signal exit."""
    with pytest.raises(ValueError, match="mark stop predates reported exit"):
        resolve_hype_native_prospective_lifecycles(
            _report(),
            _funding(),
            _prices(crossed=True),
            maximum_oracle_staleness_ms=600,
            maximum_mark_gap_ms=1_000,
        )


def test_bbo_stop_requires_exact_mark_cross_confirmation() -> None:
    """The provisional BBO proxy alone cannot establish a venue stop exit."""
    with pytest.raises(HypeProxyExitUnconfirmedError) as captured:
        resolve_hype_native_prospective_lifecycles(
            _report(exit_reason="protective_stop_bbo_proxy"),
            _funding(),
            _prices(),
            maximum_oracle_staleness_ms=600,
            maximum_mark_gap_ms=1_000,
        )
    assert captured.value.mark_evidence["mark_stop_truth"] == (
        "confirmed_no_earlier_mark_stop"
    )


def test_incomplete_mark_path_fails_closed() -> None:
    """Sparse marks cannot be success-shaped into complete stop evidence."""
    prices = _prices().iloc[[0, -1]].reset_index(drop=True)

    with pytest.raises(ValueError, match="mark path gap"):
        resolve_hype_native_prospective_lifecycles(
            _report(),
            _funding(),
            prices,
            maximum_oracle_staleness_ms=5_000,
            maximum_mark_gap_ms=1_000,
        )


def test_receipt_causal_websocket_marks_override_sparse_price_marks() -> None:
    """Dense public websocket marks provide stop truth while 0x supplies oracle."""
    report = resolve_hype_native_prospective_lifecycles(
        _report(exit_reason="protective_stop_bbo_proxy"),
        _funding(),
        _prices(),
        mark_prices=_local_marks(),
        stop_books=_stop_books(),
        maximum_oracle_staleness_ms=600,
        maximum_mark_gap_ms=1_000,
    )

    lifecycle = report["lifecycles"][0]
    assert lifecycle["mark_stop_truth"] == "confirmed_mark_stop"
    assert lifecycle["first_mark_stop_cross_time_ms"] == 2_500
    assert lifecycle["first_mark_stop_cross_received_ts_ns"] == 2_500_000_000
    assert lifecycle["proxy_exit_book_time_ms"] == 5_000
    assert lifecycle["exit_book_time_ms"] == 2_502
    assert lifecycle["exit_price"] == pytest.approx(98.94)
    assert lifecycle["exit_levels_consumed"] == 2
    assert lifecycle["mark_trigger_to_book_delay_ms"] == pytest.approx(2.0)
    assert lifecycle["net_pnl_usd_before_funding"] < 0.0
    assert lifecycle["funding_event_count"] == 1
    assert report["contract"]["mark_source"] == (
        "hyperliquid_ws_activeAssetCtx_local_receipt"
    )
    assert report["contract"]["stop_execution_source"] == (
        "hyperliquid_ws_l2Book_local_receipt_finite_depth"
    )
    assert report["contract"]["oracle_source"] == "0xarchive_hyperliquid_prices"


def _local_marks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_ms": [1_000, 1_500, 2_500, 3_500, 4_500, 5_000],
            "received_ts_ns": [
                value * 1_000_000
                for value in (1_000, 1_500, 2_500, 3_500, 4_500, 5_000)
            ],
            "mark_price": [100.0, 99.5, 98.9, 100.5, 101.0, 104.0],
        }
    )


def _stop_books() -> tuple[dict[str, object], ...]:
    return (
        {
            "symbol": "HYPE",
            "exchange_ts_ms": 2_501,
            "received_ts_ns": 2_502_000_000,
            "source": "hyperliquid_ws_l2Book",
            "bids": [{"price": 98.95, "size": 8.0}, {"price": 98.90, "size": 8.0}],
            "asks": [{"price": 99.00, "size": 20.0}],
        },
    )
