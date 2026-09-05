"""Funding reconciliation tests for one HYPE-native exact-depth path."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.hype_native_path_funding import (
    reconcile_hype_native_path_funding,
)

_ENTRY_MS = 1_786_998_016_699
_EXIT_MS = _ENTRY_MS + 28_800_000


def _path(*, side: str = "long") -> dict[str, object]:
    return {
        "contract": {"report_only": True, "execution_authority": "none"},
        "identity": {
            "candidate_strategy_id": "hype_native_breakout_onset_bidirectional_v2",
            "symbol": "HYPE",
        },
        "source_signal": {"side": side},
        "execution_path": {
            "entry_book_time_ms": _ENTRY_MS,
            "entry_price": 100.0,
            "entry_quantity": 10.0,
            "horizons": {
                "480": {
                    "status": "resolved_bbo_proxy",
                    "book_time_ms": _EXIT_MS,
                    "net_pnl_usd": 10.0,
                }
            },
        },
    }


def _funding() -> HlFundingEvidence:
    return HlFundingEvidence(
        symbol="HYPE",
        start_ms=_ENTRY_MS - 3_600_000,
        end_ms=_EXIT_MS + 3_600_000,
        rows=(
            {
                "event_ts_ms": _ENTRY_MS,
                "funding_rate": 0.5,
                "source": "hl_funding_history",
            },
            {
                "event_ts_ms": _ENTRY_MS + 3_600_000,
                "funding_rate": 0.001,
                "source": "hl_funding_history",
            },
            {
                "event_ts_ms": _ENTRY_MS + 7_200_000,
                "funding_rate": -0.0005,
                "source": "hl_funding_history",
            },
            {
                "event_ts_ms": _EXIT_MS + 1,
                "funding_rate": 0.5,
                "source": "hl_funding_history",
            },
        ),
        evidence={"complete": True},
    )


def _oracles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_ms": [_ENTRY_MS + 3_599_000, _ENTRY_MS + 7_199_000],
            "oracle_price": [100.0, 110.0],
        }
    )


def test_long_path_uses_only_open_interval_settlements_and_causal_oracles() -> None:
    """Funding must exclude entry/after-exit events and use signed oracle notional."""
    report = reconcile_hype_native_path_funding(
        _path(), _funding(), _oracles(), maximum_oracle_staleness_ms=2_000
    )

    assert report["funding_event_count"] == 2
    assert report["funding_cashflow_usd"] == pytest.approx(-0.45)
    assert report["net_pnl_usd_before_funding"] == pytest.approx(10.0)
    assert report["net_pnl_usd_after_funding"] == pytest.approx(9.55)
    assert [row["oracle_staleness_ms"] for row in report["funding_events"]] == [
        1_000,
        1_000,
    ]


def test_short_path_inverts_funding_cashflow_without_changing_market_pnl() -> None:
    """Short funding must be the exact sign inverse of the long calculation."""
    report = reconcile_hype_native_path_funding(
        _path(side="short"),
        _funding(),
        _oracles(),
        maximum_oracle_staleness_ms=2_000,
    )

    assert report["funding_cashflow_usd"] == pytest.approx(0.45)
    assert report["net_pnl_usd_after_funding"] == pytest.approx(10.45)


def test_resolved_stop_path_uses_actual_exit_instead_of_timer_horizon() -> None:
    """A stopped lifecycle must reconcile its actual exit, not a later horizon."""
    path = _path()
    execution = path["execution_path"]
    execution["status"] = "resolved"
    execution["exit_book_time_ms"] = _EXIT_MS
    execution["net_pnl_usd_before_funding"] = -12.0

    report = reconcile_hype_native_path_funding(
        path,
        _funding(),
        _oracles(),
        maximum_oracle_staleness_ms=2_000,
        horizon_minutes=None,
    )

    assert report["exit_basis"] == "resolved_path_exit"
    assert report["horizon_minutes"] is None
    assert report["net_pnl_usd_after_funding"] == pytest.approx(-12.45)


def test_stale_oracle_or_execution_capable_input_fails_closed() -> None:
    """The report cannot substitute stale prices or accept execution authority."""
    with pytest.raises(LookupError, match="stale"):
        reconcile_hype_native_path_funding(
            _path(), _funding(), _oracles(), maximum_oracle_staleness_ms=500
        )
    path = _path()
    path["contract"] = {"report_only": False, "execution_authority": "mainnet"}
    with pytest.raises(ValueError, match="report-only"):
        reconcile_hype_native_path_funding(
            path, _funding(), _oracles(), maximum_oracle_staleness_ms=2_000
        )


def test_non_hype_path_identity_fails_closed() -> None:
    """A strategy-name alias cannot attach HYPE funding to another market."""
    path = _path()
    path["identity"]["symbol"] = "SOL"

    with pytest.raises(ValueError, match="HYPE symbol"):
        reconcile_hype_native_path_funding(
            path,
            _funding(),
            _oracles(),
            maximum_oracle_staleness_ms=2_000,
        )
