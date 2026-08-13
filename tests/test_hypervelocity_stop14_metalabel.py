"""Target-before-stop feature assembly contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.hypervelocity_metalabel import build_metalabel_rows
from hypervector.research import hypervelocity_metalabel_features as feature_module
from hypervector.research import hypervelocity_metalabel_report as report_module


def test_feature_builder_preserves_explicit_loss_label() -> None:
    """Causal features must not require a semantically false liquidation label."""
    decision_time = pd.Timestamp("2026-01-01T00:00:00Z")
    signal_time = decision_time + pd.Timedelta(minutes=1)
    decisions = pd.DataFrame(
        {
            "ema_gap_bps_signed": [2.0],
            "rsi": [52.0],
            "rsi_ema": [50.0],
            "bbwp_percentile": [30.0],
            "bbwp_1m_compression_age_bars": [6.0],
            "regime_strength_score": [0.6],
            "regime_strength_percentile": [70.0],
            "breakout_volume_ratio": [1.2],
            "context_15m": ["TREND_UP"],
        },
        index=pd.DatetimeIndex([decision_time]),
    )
    context = pd.DataFrame(
        {"bbwp_percentile": [35.0], "ema_gap_bps_signed": [4.0]},
        index=decisions.index,
    )
    bars = pd.DataFrame(
        {
            "regime_age_bars": [3.0],
            "directional_structure_distance_bps": [20.0],
        },
        index=decisions.index,
    )
    books = pd.DataFrame(
        {
            "book_snapshot_age_ms": [20.0],
            "obi_5": [0.4],
            "obi_20": [0.2],
            "obi_5_trailing_median": [0.3],
            "obi_20_trailing_median": [0.15],
            "spread_bps": [0.2],
            "micro_price_delta_bps": [0.1],
            "ofi_top_5s_normalized": [0.5],
            "book_window_snapshots": [10],
        },
        index=pd.DatetimeIndex([signal_time]),
    )
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": [signal_time.isoformat()],
            "loss_risk": [1],
        }
    )

    result = build_metalabel_rows(
        lifecycles,
        decisions,
        context,
        bars,
        books,
        label_column="loss_risk",
    )

    assert result["loss_risk"].tolist() == [1]
    assert "liquidation_risk" not in result


def test_faithful_feature_decisions_are_annotated_without_entry_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop-label features must annotate, but not filter, faithful entries."""
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    bars = pd.DataFrame({"close": [100.0, 101.0]}, index=index)
    decisions = pd.DataFrame(
        {
            "entry_direction": ["long", "long"],
            "bbwp_percentile": [10.0, 30.0],
        },
        index=index,
    )
    context = pd.DataFrame({"close": [100.0, 101.0]}, index=index)
    regime_config = SimpleNamespace(bbwp_compression_threshold=25.0)
    monkeypatch.setattr(
        feature_module,
        "load_hypervelocity_profile",
        lambda _path: SimpleNamespace(regime_config=regime_config),
    )
    monkeypatch.setattr(
        feature_module,
        "classify_multitimeframe",
        lambda frame, config: decisions
        if frame is bars and config is regime_config
        else None,
    )
    monkeypatch.setattr(
        feature_module,
        "_completed_context",
        lambda *_args: context,
    )
    monkeypatch.setattr(
        feature_module,
        "apply_5m_bbwp_range_precedence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("faithful profile was rewritten")
        ),
    )

    observed, observed_context, observed_config = feature_module.candidate_decisions(
        bars,
        Path("config.toml"),
        "faithful",
    )

    assert observed["entry_direction"].tolist() == ["long", "long"]
    assert observed["bbwp_1m_compression_age_bars"].tolist() == [0.0, 1.0]
    assert "bbwp_1m_compression_age_bars" not in decisions
    assert observed_context is context
    assert observed_config is regime_config


def test_frozen_stop_population_validates_losses_and_liquidation() -> None:
    """Population drift in either loss count or liquidation count must fail."""
    statuses = ["target_completed"] * 227 + ["stopped"] * 143 + ["liquidated"]
    rows = pd.DataFrame(
        {
            "status": statuses,
            "loss_risk": [0] * 227 + [1] * 144,
        }
    )
    contract = report_module.metalabel_population_contract("faithful-stop14")

    report_module._validate_frozen_population(rows, contract)

    rows.loc[0, "loss_risk"] = 1
    with pytest.raises(ValueError, match="positive population changed"):
        report_module._validate_frozen_population(rows, contract)


def test_stop14_limitations_describe_the_actual_loss_label() -> None:
    """A target-before-stop report must not describe a liquidation-only label."""
    contract = report_module.metalabel_population_contract("faithful-stop14")

    limitations = report_module._report_limitations(
        label_column=contract.label_column,
        expected_resolved=contract.expected_resolved,
        expected_positives=contract.expected_positives,
    )

    assert any("144 stop-or-liquidation" in value for value in limitations)
    assert all("Few liquidation labels" not in value for value in limitations)


def test_source_limitations_report_actual_folds_and_gap_separated_scope() -> None:
    """Extended source reports must not inherit the old 90-day/three-fold text."""
    limitations = report_module._report_limitations(
        label_column="liquidation_risk",
        expected_resolved=213,
        expected_positives=39,
        fold_count=5,
        exploration_scope=(
            "The 4 non-overlapping replay blocks remain exploration evidence, "
            "not a sealed holdout."
        ),
    )

    assert any("39 liquidation labels" in value for value in limitations)
    assert any("5 folds" in value for value in limitations)
    assert any("4 non-overlapping replay blocks" in value for value in limitations)
    assert all("90-day" not in value for value in limitations)
