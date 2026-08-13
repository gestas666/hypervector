"""Point-in-time dataset tests for the Hypervelocity metalabel challenger."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.hypervelocity_metalabel import (
    BASE_FEATURE_NAMES,
    BOOK_FEATURE_NAMES,
    SEQUENCE_BOOK_FEATURE_NAMES,
    _directionalize_features,
    assert_observe_only_policy,
    build_metalabel_rows,
    resolved_candidate_lifecycles,
    resolved_comparison_candidate_lifecycles,
    resolved_margin_stop_lifecycles,
    resolved_recovery_lifecycles,
    signal_times_utc,
)
from hypervector.research.hypervelocity_metalabel_features import load_model_bars
from hypervector.research.hypervelocity_metalabel_report import (
    metalabel_population_contract,
    resolved_population_for_contract,
    runtime_observe_contract,
    verify_recovery_source_files,
)
from hypervector.research.hypervelocity_metalabel_shape import (
    loss_risk_shape_diagnostics,
)


def test_bar_loader_can_retain_strictly_prior_causal_warmup(
    tmp_path: Path,
) -> None:
    """Independent replay windows must not cold-start their regime features."""
    index = pd.date_range("2026-01-01T00:00:00Z", periods=8, freq="1min")
    path = tmp_path / "bars.parquet"
    pd.DataFrame(
        {
            "timestamp": index,
            "open": [100.0] * len(index),
            "high": [101.0] * len(index),
            "low": [99.0] * len(index),
            "close": [100.0] * len(index),
            "volume": [1.0] * len(index),
        }
    ).to_parquet(path)
    start = index[5].to_pydatetime()
    end = (index[-1] + pd.Timedelta(minutes=1)).to_pydatetime()

    bounded = load_model_bars(path, start, end)
    warmed = load_model_bars(path, start, end, include_prior=True)

    assert bounded.index.equals(index[5:])
    assert warmed.index.equals(index)
    assert (warmed.index < start).sum() == 5


def test_comparison_population_extracts_only_resolved_target_and_liquidation() -> None:
    """Strict-source replay extraction must exclude expired entry attempts."""
    base = {
        "direction": "long",
        "signal_time_utc": "2026-01-01T00:00:00+00:00",
        "entry_time_utc": "2026-01-01T00:00:01+00:00",
        "outcome_time_utc": "2026-01-01T00:10:00+00:00",
    }
    payload = {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "metalabel_policy": {
            "mode": "observe",
            "may_filter": False,
            "may_scale": False,
        },
        "comparison": {
            "candidates": {
                "strict_source_control": {
                    "replay": {
                        "lifecycles": [
                            {**base, "lifecycle_id": 0, "status": "target_completed"},
                            {**base, "lifecycle_id": 1, "status": "liquidated"},
                            {
                                **base,
                                "lifecycle_id": 2,
                                "status": "expired",
                                "entry_time_utc": None,
                            },
                        ]
                    }
                }
            }
        },
    }

    rows = resolved_comparison_candidate_lifecycles(
        payload,
        candidate_name="strict_source_control",
    )

    assert rows["status"].tolist() == ["target_completed", "liquidated"]
    assert rows["liquidation_risk"].tolist() == [0, 1]


def _recovery_payload() -> dict[str, object]:
    return {
        "ok": True,
        "report_only": True,
        "event_candidate": "5m_bbwp_hard_range_25_recovery_6_cooldown_300s",
        "metalabel_policy": {
            "mode": "observe",
            "may_filter": False,
            "may_scale": False,
        },
        "event_replay": {
            "lifecycles": [
                {
                    "lifecycle_id": 1,
                    "direction": "long",
                    "signal_time_utc": "2026-01-01T00:01:00+00:00",
                    "entry_time_utc": "2026-01-01T00:01:01+00:00",
                    "outcome_time_utc": "2026-01-01T00:03:00+00:00",
                    "status": "target_completed",
                },
                {
                    "lifecycle_id": 2,
                    "direction": "short",
                    "signal_time_utc": "2026-01-01T00:02:00+00:00",
                    "entry_time_utc": "2026-01-01T00:02:01+00:00",
                    "outcome_time_utc": "2026-01-01T00:04:00.123000+00:00",
                    "status": "liquidated",
                },
                {
                    "lifecycle_id": 3,
                    "direction": "long",
                    "signal_time_utc": "2026-01-01T00:05:00+00:00",
                    "entry_time_utc": None,
                    "outcome_time_utc": "2026-01-01T00:10:00+00:00",
                    "status": "expired",
                },
            ]
        },
    }


def _margin_stop_payload() -> dict[str, object]:
    lifecycles = _recovery_payload()["event_replay"]["lifecycles"]
    assert isinstance(lifecycles, list)
    values = [dict(row) for row in lifecycles]
    values[1]["status"] = "stopped"
    values.append(
        {
            "lifecycle_id": 4,
            "direction": "long",
            "signal_time_utc": "2026-01-01T00:06:00+00:00",
            "entry_time_utc": "2026-01-01T00:06:01+00:00",
            "outcome_time_utc": "2026-01-01T00:07:00+00:00",
            "status": "liquidated",
        }
    )
    return {
        "ok": True,
        "report_only": True,
        "runtime_strategy_changed": False,
        "metalabel_policy": {
            "mode": "observe",
            "may_filter": False,
            "may_scale": False,
        },
        "comparison": {
            "candidates": {
                "stop_14pct_margin": {
                    "fixed_margin_stop_pct": 14.0,
                    "replay": {
                        "fill_rule": "trade-through",
                        "lifecycles": values,
                    },
                }
            }
        },
    }


def test_resolved_recovery_lifecycles_keep_only_filled_binary_outcomes() -> None:
    """Canceled or expired maker intents must not become negative labels."""
    rows = resolved_recovery_lifecycles(_recovery_payload())

    assert rows["lifecycle_id"].tolist() == [1, 2]
    assert rows["liquidation_risk"].tolist() == [0, 1]
    assert rows["signal_ts_ms"].lt(rows["outcome_ts_ms"]).all()


def test_resolved_candidate_lifecycles_accept_canonical_pressure_identity() -> None:
    """Canonical event outcomes require their own immutable candidate identity."""
    payload = _recovery_payload()
    payload.pop("event_candidate")
    payload["candidate"] = "canonical_breakout_confirmed_first_opposed_obi5_snapshot"

    rows = resolved_candidate_lifecycles(
        payload,
        identity_field="candidate",
        expected_identity=("canonical_breakout_confirmed_first_opposed_obi5_snapshot"),
    )

    assert rows["lifecycle_id"].tolist() == [1, 2]
    assert rows["liquidation_risk"].tolist() == [0, 1]


def test_margin_stop_lifecycles_label_only_filled_losses() -> None:
    """Stops and liquidation are risks; expired maker intent is not a loss."""
    rows = resolved_margin_stop_lifecycles(_margin_stop_payload())

    assert rows["lifecycle_id"].tolist() == [1, 2, 4]
    assert rows["status"].tolist() == ["target_completed", "stopped", "liquidated"]
    assert rows["loss_risk"].tolist() == [0, 1, 1]
    assert "liquidation_risk" not in rows


def test_margin_stop_lifecycles_reject_wrong_stop_identity() -> None:
    """A neighboring stop threshold must not silently alter the label recipe."""
    payload = _margin_stop_payload()
    payload["comparison"]["candidates"]["stop_14pct_margin"][
        "fixed_margin_stop_pct"
    ] = 10.0

    with pytest.raises(ValueError, match="14%"):
        resolved_margin_stop_lifecycles(payload)


def test_stop14_contract_routes_to_loss_population() -> None:
    """The assembly contract must select the nested stop parser and loss label."""
    contract = metalabel_population_contract("faithful-stop14")

    rows = resolved_population_for_contract(_margin_stop_payload(), contract)

    assert rows["loss_risk"].tolist() == [0, 1, 1]


def test_observe_policy_rejects_filter_or_scale_authority() -> None:
    """Research training fails closed if the runtime policy gains authority."""
    assert_observe_only_policy(
        {"mode": "observe", "may_filter": False, "may_scale": False}
    )

    with pytest.raises(ValueError, match="observe-only"):
        assert_observe_only_policy(
            {"mode": "observe", "may_filter": True, "may_scale": False}
        )


def test_metalabel_features_use_prior_completed_bar_and_causal_book() -> None:
    """Signal rows see t-1 bar features and backward-aligned signal-time L2."""
    decision_index = pd.date_range("2026-01-01T00:00:00Z", periods=2, freq="1min")
    signal_index = decision_index + pd.Timedelta(minutes=1)
    decisions = pd.DataFrame(
        {
            "ema_gap_bps_signed": [2.0, -3.0],
            "rsi": [52.0, 40.0],
            "rsi_ema": [50.0, 45.0],
            "bbwp_percentile": [30.0, 40.0],
            "bbwp_1m_compression_age_bars": [6.0, 7.0],
            "regime_strength_score": [0.6, 0.8],
            "regime_strength_percentile": [0.7, 0.9],
            "breakout_volume_ratio": [1.2, 1.5],
            "context_15m": ["TREND_UP", "TREND_DOWN"],
        },
        index=decision_index,
    )
    context_5m = pd.DataFrame(
        {
            "bbwp_percentile": [35.0, 45.0],
            "ema_gap_bps_signed": [4.0, -5.0],
        },
        index=decision_index,
    )
    bar_annotations = pd.DataFrame(
        {
            "regime_age_bars": [3.0, 9.0],
            "directional_structure_distance_bps": [20.0, 80.0],
        },
        index=decision_index,
    )
    books = pd.DataFrame(
        {
            "book_snapshot_age_ms": [20.0, 30.0],
            "obi_5": [0.4, 0.3],
            "obi_20": [0.2, 0.1],
            "obi_5_trailing_median": [0.3, 0.2],
            "obi_20_trailing_median": [0.15, 0.05],
            "spread_bps": [0.2, 0.3],
            "micro_price_delta_bps": [0.1, 0.2],
            "ofi_top_5s_normalized": [0.5, -0.4],
            "book_window_snapshots": [10, 8],
        },
        index=signal_index,
    )
    lifecycles = resolved_recovery_lifecycles(_recovery_payload())

    rows = build_metalabel_rows(
        lifecycles,
        decisions,
        context_5m,
        bar_annotations,
        books,
    )

    assert set(BASE_FEATURE_NAMES + BOOK_FEATURE_NAMES).issubset(rows.columns)
    assert rows["directional_ema_gap_bps_1m"].tolist() == [2.0, 3.0]
    assert rows["directional_rsi_gap_1m"].tolist() == [2.0, 5.0]
    assert rows["bbwp_1m_percentile"].tolist() == [30.0, 40.0]
    assert rows["context_15m_alignment"].tolist() == [1.0, 1.0]
    assert rows["directional_obi_5"].tolist() == pytest.approx([0.4, -0.3])
    assert rows["directional_ofi_top_5s_normalized"].tolist() == pytest.approx(
        [0.5, 0.4]
    )


def test_metalabel_directionalizes_causal_sequence_features() -> None:
    raw = pd.DataFrame(
        {
            "direction": ["long", "short"],
            "ema_gap_bps_signed_1m": [0.0, 0.0],
            "rsi_gap_1m": [0.0, 0.0],
            "context_15m": ["TREND_UP", "TREND_DOWN"],
            "ema_gap_bps_signed_5m": [0.0, 0.0],
            "obi_5": [0.0, 0.0],
            "obi_20": [0.0, 0.0],
            "obi_5_trailing_median": [0.0, 0.0],
            "obi_20_trailing_median": [0.0, 0.0],
            "micro_price_delta_bps": [0.0, 0.0],
            "ofi_top_5s_normalized": [0.0, 0.0],
            "book_sequence_snapshots_15s": [2, 3],
            "obi_5_mean_15s": [0.2, 0.3],
            "obi_5_delta_15s": [0.1, -0.2],
            "ofi_top_15s_normalized": [0.4, -0.5],
            "book_sequence_snapshots_60s": [8, 9],
            "obi_5_mean_60s": [0.25, 0.35],
            "obi_5_delta_60s": [0.15, -0.25],
            "obi_5_sign_mean_60s": [0.5, -0.75],
            "ofi_top_60s_normalized": [0.6, -0.7],
            "micro_price_delta_bps_mean_60s": [0.3, -0.4],
            "spread_bps_median_60s": [0.2, 0.3],
        }
    )

    observed = _directionalize_features(raw)

    assert set(SEQUENCE_BOOK_FEATURE_NAMES).issubset(observed.columns)
    assert observed["directional_obi_5_mean_15s"].tolist() == [0.2, -0.3]
    assert observed["directional_obi_5_delta_15s"].tolist() == [0.1, 0.2]
    assert observed["directional_ofi_top_60s_normalized"].tolist() == [0.6, 0.7]


def test_irregular_signal_uses_latest_available_completed_bar() -> None:
    """An intraminute event must not lose features or consume a future bar."""
    decision_index = pd.date_range("2026-01-01T00:00:00Z", periods=2, freq="1min")
    decisions = pd.DataFrame(
        {
            "ema_gap_bps_signed": [2.0, 99.0],
            "rsi": [52.0, 99.0],
            "rsi_ema": [50.0, 0.0],
            "bbwp_percentile": [30.0, 99.0],
            "bbwp_1m_compression_age_bars": [6.0, 99.0],
            "regime_strength_score": [0.6, 0.99],
            "regime_strength_percentile": [60.0, 99.0],
            "breakout_volume_ratio": [1.2, 9.9],
            "context_15m": ["TREND_UP", "TREND_DOWN"],
        },
        index=decision_index,
    )
    context_5m = pd.DataFrame(
        {
            "bbwp_percentile": [35.0, 99.0],
            "ema_gap_bps_signed": [4.0, 99.0],
        },
        index=decision_index,
    )
    annotations = pd.DataFrame(
        {
            "regime_age_bars": [3.0, 99.0],
            "directional_structure_distance_bps": [20.0, 99.0],
        },
        index=decision_index,
    )
    signal = pd.Timestamp("2026-01-01T00:01:00.500Z")
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
        index=pd.DatetimeIndex([signal]),
    )
    lifecycles = pd.DataFrame(
        {
            "direction": ["long"],
            "signal_time_utc": [signal.isoformat()],
            "liquidation_risk": [0],
        }
    )

    rows = build_metalabel_rows(
        lifecycles,
        decisions,
        context_5m,
        annotations,
        books,
        bar_alignment="backward",
    )

    assert rows.loc[0, "directional_ema_gap_bps_1m"] == 2.0
    assert rows.loc[0, "bbwp_1m_percentile"] == 30.0


def test_canonical_population_contract_is_frozen() -> None:
    """Canonical training must fail if the replay population silently changes."""
    contract = metalabel_population_contract("canonical-pressure")

    assert contract.identity_field == "candidate"
    assert contract.expected_resolved == 302
    assert contract.expected_liquidations == 41
    assert contract.bar_alignment == "backward"

    stop_contract = metalabel_population_contract("faithful-stop14")
    assert stop_contract.expected_resolved == 371
    assert stop_contract.expected_positives == 144
    assert stop_contract.label_column == "loss_risk"
    assert stop_contract.decision_profile == "faithful"
    assert stop_contract.bar_alignment == "backward"

    with pytest.raises(ValueError, match="unknown metalabel candidate profile"):
        metalabel_population_contract("unknown")


def test_loss_risk_shape_uses_lowest_half_within_each_fold() -> None:
    """Economic shape must preserve fold boundaries when ranking risk."""
    predictions = pd.DataFrame(
        {
            "candidate": ["model"] * 8,
            "fold_id": [0] * 4 + [1] * 4,
            "loss_risk": [0, 1, 0, 1, 0, 0, 1, 1],
            "prediction": [0.1, 0.2, 0.8, 0.9, 0.1, 0.2, 0.8, 0.9],
        }
    )

    result = loss_risk_shape_diagnostics(predictions)
    model = result["candidates"]["model"]

    assert result["theoretical_break_even_target_rate_pct"] == pytest.approx(
        70.6896551724
    )
    assert model["lowest_risk_target_rate_pct"] == 75.0
    assert [row["target_rate_pct"] for row in model["folds"]] == [50.0, 100.0]
    assert model["folds_above_break_even"] == 1
    assert model["all_folds_above_break_even"] is False


def test_signal_times_accept_mixed_iso8601_precision() -> None:
    """Whole-second and microsecond event timestamps may coexist in one tape."""
    rows = pd.DataFrame(
        {
            "signal_time_utc": [
                "2026-06-15T09:35:00+00:00",
                "2026-06-15T09:36:00.507000+00:00",
            ]
        }
    )

    observed = signal_times_utc(rows)

    assert observed[0] == pd.Timestamp("2026-06-15T09:35:00Z")
    assert observed[1] == pd.Timestamp("2026-06-15T09:36:00.507Z")


def test_report_sources_require_exact_files_and_runtime_observe_contract(
    tmp_path: Path,
) -> None:
    """Source checksums and all four observe flags are immutable evidence."""
    bars_path = tmp_path / "bars.parquet"
    bars_path.write_bytes(b"venue bars")
    config_path = tmp_path / "faithful.toml"
    config_path.write_text(
        """
[model]
mode = "observe"
may_filter = false
may_scale = false
[runtime]
metalabel_mode = "observe"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    payload = _recovery_payload()
    from hypervector.data.oxa_storage import file_evidence

    payload["source_evidence"] = {
        "bars": file_evidence(bars_path),
        "runtime_config": file_evidence(config_path),
    }

    evidence = verify_recovery_source_files(payload, bars_path, config_path)

    assert evidence["bars"] == file_evidence(bars_path)
    assert runtime_observe_contract(config_path)["runtime_mode"] == "observe"
    bars_path.write_bytes(b"different bars")
    with pytest.raises(ValueError, match="source evidence differs"):
        verify_recovery_source_files(payload, bars_path, config_path)
