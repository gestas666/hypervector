"""Generic HIP-3 development-only diagnostic contracts."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_development_diagnostic import (
    build_hip3_development_diagnostic,
)
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveCandidateResult,
    MuArchiveFamilyResult,
    MuArchiveTrial,
)
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)

_SYMBOL = "xyz:CL"
_CONFIG = Hip3BreakoutPressureConfig(32, 9, 21, 0.1, 80.0)


def _trade(direction: str, position: int, pnl: float) -> SharedPortfolioTrade:
    index = pd.date_range("2026-06-08T08:00:00Z", periods=12, freq="15min")
    return SharedPortfolioTrade(
        "hip3_breakout_pressure",
        direction,
        index[position - 1].isoformat(),
        index[position].isoformat(),
        index[position + 1].isoformat(),
        position - 1,
        position,
        position + 1,
        100.0,
        101.0 if direction == "long" else 99.0,
        None,
        99.2 if direction == "long" else 100.8,
        82.0 if direction == "long" else 118.0,
        1.0,
        15.0,
        75.0,
        5.0,
        pnl + 0.20,
        0.15,
        -0.05,
        pnl,
        500.0,
        500.0 + pnl,
        "signal",
        False,
    )


def _report(pnls: tuple[float, ...] = (1.0, 0.5)) -> SharedPortfolioReport:
    trades = tuple(
        _trade("long" if position % 2 else "short", position, pnl)
        for position, pnl in enumerate(pnls, start=1)
    )
    wins = sum(value > 0.0 for value in pnls)
    losses = sum(value < 0.0 for value in pnls)
    gross_profit = sum(max(value, 0.0) for value in pnls)
    gross_loss = -sum(min(value, 0.0) for value in pnls)
    return SharedPortfolioReport(
        500.0,
        500.0 + sum(pnls),
        sum(pnls),
        sum(pnls) / 5.0,
        -0.1,
        len(trades),
        wins,
        losses,
        gross_profit,
        gross_loss,
        gross_profit / gross_loss if gross_loss else None,
        0,
        0.15 * len(trades),
        -0.05 * len(trades),
        0,
        1,
        0,
        0,
        False,
        {"2026-06": sum(pnls)},
        (),
        trades,
    )


def _windows() -> MuChronologicalWindows:
    start = pd.Timestamp("2026-06-08T08:00:00Z")
    development_end = start + pd.Timedelta(hours=2)
    return MuChronologicalWindows(
        start,
        development_end,
        start + pd.Timedelta(hours=2, minutes=30),
        start + pd.Timedelta(hours=3),
        (
            (start, start + pd.Timedelta(minutes=40)),
            (
                start + pd.Timedelta(minutes=40),
                start + pd.Timedelta(minutes=80),
            ),
            (start + pd.Timedelta(minutes=80), development_end),
        ),
    )


def _candidate() -> MuArchiveCandidateResult:
    windows = _windows()
    development = MuPartitionResult(
        "development",
        windows.development_start_utc,
        windows.development_end_utc,
        _report(),
        _report((0.8, 0.3)),
    )
    trial = MuArchiveTrial(_CONFIG, _report(), (_report((0.2,)),) * 3)
    family = MuArchiveFamilyResult(
        "breakout_pressure",
        "hip3_cl_full_l2_breakout_pressure_bidirectional_15m_v1",
        "cl_full_l2_breakout_pressure_bidirectional_15m_research_v1",
        (trial,),
        _CONFIG,
        (development,),
    )
    return MuArchiveCandidateResult(_SYMBOL, "15m", windows, (family,))


def _bars(*, unresolved: bool = False) -> pd.DataFrame:
    index = pd.date_range("2026-06-08T08:00:00Z", periods=8, freq="15min")
    complete = [True] * len(index)
    if unresolved:
        complete[1] = False
    return pd.DataFrame(
        {
            "risk_path_source": ("0xarchive_mark_price_with_public_trade_context_v1"),
            "mark_path_complete": complete,
            "maximum_mark_interval_ms": 100.0,
            "mark_snapshot_count": 10,
            "trade_bundle_complete": True,
            "entry_mark_path_complete": complete,
            "entry_maximum_mark_interval_ms": 100.0,
            "entry_mark_snapshot_count": 10,
            "first_boundary_delay_ms": 100.0,
            "maximum_snapshot_interval_ms": 100.0,
            "end_boundary_age_ms": 100.0,
            "source_snapshot_count": 10,
        },
        index=index,
    )


def test_report_freezes_selection_without_oos_economics() -> None:
    result = build_hip3_development_diagnostic(
        (_candidate(),),
        {"15m": _bars()},
        expected_symbol=_SYMBOL,
        expected_start_utc=_windows().development_start_utc,
        expected_end_utc=_windows().holdout_end_utc,
        funding_complete=True,
    )

    assert result["development_selected_track"]["symbol"] == _SYMBOL
    assert (
        result["development_selected_track"]["config"]["breakout_lookback_bars"] == 32
    )
    assert result["out_of_sample_economics"] == "WITHHELD_NOT_EVALUATED"
    assert set(result["development_economics"]) == {"nominal", "stress"}
    assert result["development_economics"]["stress"]["diagnostics"]["all"][
        "net_without_largest_winner_usd"
    ] == pytest.approx(0.3)
    assert result["fold_stability"]["positive_folds"] == 3
    assert result["development_economics"]["nominal"]["total_fees_usd"] > 0.0
    assert result["development_economics"]["nominal"]["funding_cashflow_usd"] < 0.0
    assert (
        result["development_economics"]["nominal"][
            "scheduled_oracle_session_diagnostics"
        ]["status"]
        == "unclassified"
    )
    assert result["technical_path_evidence"]["status"] == "resolved"
    assert (
        result["development_path_thresholds"]["cumulative_thresholds_ms"]["5000"][
            "nominal"
        ]["affected_trades"]
        == 0
    )
    sensitivity = result["development_gap_loss_sensitivity"]
    assert sensitivity["stress"]["affected_trades"] == 0
    assert sensitivity["validation_accessed"] is False
    assert result["future_live_research_suitability"]["status"] == (
        "DEVELOPMENT_SUPPORTED_REQUIRES_UNTOUCHED_OOS_AND_RUNTIME_PARITY"
    )


def test_report_emits_exact_unresolved_lifecycle_causes() -> None:
    result = build_hip3_development_diagnostic(
        (_candidate(),),
        {"15m": _bars(unresolved=True)},
        expected_symbol=_SYMBOL,
        expected_start_utc=_windows().development_start_utc,
        expected_end_utc=_windows().holdout_end_utc,
        funding_complete=True,
    )

    causes = result["technical_path_evidence"]["nominal"]["lifecycles"]
    assert causes[0]["lifecycle_key"].startswith("long|")
    assert causes[0]["mark_path_unresolved"] is True
    assert causes[0]["entry_mark_path_unresolved"] is True
    assert result["future_live_research_suitability"]["status"] == (
        "NOT_SUITABLE_TECHNICALLY_UNRESOLVED"
    )


def test_report_rejects_any_out_of_sample_partition() -> None:
    candidate = _candidate()
    family = candidate.families[0]
    validation = replace(family.partitions[0], name="validation")
    contaminated = replace(
        candidate,
        families=(replace(family, partitions=(*family.partitions, validation)),),
    )

    with pytest.raises(ValueError, match="development partition only"):
        build_hip3_development_diagnostic(
            (contaminated,),
            {"15m": _bars()},
            expected_symbol=_SYMBOL,
            expected_start_utc=_windows().development_start_utc,
            expected_end_utc=_windows().holdout_end_utc,
            funding_complete=True,
        )


def test_report_fails_closed_on_identity_or_funding_mismatch() -> None:
    with pytest.raises(ValueError, match="exact symbol"):
        build_hip3_development_diagnostic(
            (_candidate(),),
            {"15m": _bars()},
            expected_symbol="xyz:MU",
            expected_start_utc=_windows().development_start_utc,
            expected_end_utc=_windows().holdout_end_utc,
            funding_complete=True,
        )
    with pytest.raises(ValueError, match="funding evidence"):
        build_hip3_development_diagnostic(
            (_candidate(),),
            {"15m": _bars()},
            expected_symbol=_SYMBOL,
            expected_start_utc=_windows().development_start_utc,
            expected_end_utc=_windows().holdout_end_utc,
            funding_complete=False,
        )
