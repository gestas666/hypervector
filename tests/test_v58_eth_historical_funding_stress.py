"""Historical funding stress for the active V58 ETH route."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.v58_eth_historical_funding_stress import (
    build_v58_eth_historical_funding_stress,
    load_v58_eth_historical_funding_stress,
)


def test_reports_side_specific_rolling_twelve_hour_distribution() -> None:
    """Rolling costs preserve side and quantify frozen/current assumptions."""
    funding = _funding_frame([0.00001] * 12 + [0.00002])

    report = build_v58_eth_historical_funding_stress(
        funding,
        frozen_projection_bps=0.25,
        current_projection_bps=1.25,
        notional_usd=750.0,
    )

    long = report["rolling_12h_cost_bps"]["long"]
    short = report["rolling_12h_cost_bps"]["short"]
    assert long["p50"] == pytest.approx(1.25)
    assert long["p90"] == pytest.approx(1.29)
    assert long["p99"] == pytest.approx(1.299)
    assert short["p50"] == pytest.approx(-1.25)
    assert report["comparisons"]["frozen_projection"]["empirical_percentile"] == 0.0
    assert report["comparisons"]["current_projection"]["empirical_percentile"] == 0.5
    assert report["comparisons"]["p99_minus_frozen_loss_usd"] == pytest.approx(
        (1.299 - 0.25) * 750.0 / 10_000.0
    )
    assert report["execution_authority"] == "none"
    assert report["sizing_input"] is False
    assert report["live_change_supported"] is False
    assert report["disposition"]["status"] == "report_only_stress_recalibration"
    assert report["disposition"]["proposed_live_change"] is None
    assert report["disposition"]["confidence"] == "high_on_historical_measurement"
    assert "rolling windows overlap" in report["limitations"]
    assert "historical window is not a funding forecast" in report["limitations"]


def test_rejects_non_contiguous_hourly_evidence() -> None:
    """A missing settlement hour cannot be hidden inside a rolling window."""
    funding = _funding_frame([0.00001] * 13)
    funding.loc[7, "timestamp"] = funding.loc[7, "timestamp"] + pd.Timedelta(hours=1)

    with pytest.raises(ValueError, match="ordered contiguous UTC hours"):
        build_v58_eth_historical_funding_stress(
            funding,
            frozen_projection_bps=0.25,
            current_projection_bps=1.25,
            notional_usd=750.0,
        )


def test_rejects_event_timestamp_outside_declared_hour() -> None:
    """A rate must remain bound to its exact official settlement hour."""
    funding = _funding_frame([0.00001] * 13)
    funding.loc[7, "event_ts_ms"] = funding.loc[7, "event_ts_ms"] - 3_600_000

    with pytest.raises(ValueError, match="event timestamps"):
        build_v58_eth_historical_funding_stress(
            funding,
            frozen_projection_bps=0.25,
            current_projection_bps=1.25,
            notional_usd=750.0,
        )


def test_loader_binds_complete_bundle_and_point_in_time_comparisons(
    tmp_path: Path,
) -> None:
    """The durable report derives assumptions from exact source artifacts."""
    funding_path, manifest_path = _write_bundle(tmp_path)
    stress_path = tmp_path / "stress.json"
    stress_path.write_text(json.dumps(_stress()), encoding="utf-8")
    current_path = tmp_path / "current.json"
    current_path.write_text(json.dumps(_current()), encoding="utf-8")

    report = load_v58_eth_historical_funding_stress(
        funding_path=funding_path,
        manifest_path=manifest_path,
        stress_path=stress_path,
        current_context_path=current_path,
    )

    assert report["comparisons"]["frozen_projection"]["cost_bps"] == 0.25
    assert report["comparisons"]["current_projection"]["cost_bps"] == 1.25
    assert report["route_identity"] == {
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "notional_usd": 750.0,
        "hold_hours": 12,
    }
    assert (
        report["source_evidence"]["funding"]["sha256"]
        == file_evidence(funding_path)["sha256"]
    )
    assert (
        report["source_evidence"]["manifest"]["sha256"]
        == file_evidence(manifest_path)["sha256"]
    )
    assert report["generated_at_utc"].endswith("+00:00")


def test_loader_rejects_manifest_bounds_that_do_not_match_funding(
    tmp_path: Path,
) -> None:
    """A count-complete manifest cannot lie about the frozen UTC window."""
    funding_path, manifest_path = _write_bundle(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requested_end"] = "2026-01-02T00:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    stress_path = tmp_path / "stress.json"
    stress_path.write_text(json.dumps(_stress()), encoding="utf-8")
    current_path = tmp_path / "current.json"
    current_path.write_text(json.dumps(_current()), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest UTC bounds"):
        load_v58_eth_historical_funding_stress(
            funding_path=funding_path,
            manifest_path=manifest_path,
            stress_path=stress_path,
            current_context_path=current_path,
        )


def _funding_frame(rates: list[float]) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=len(rates), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": times,
            "funding_rate": rates,
            "source": ["hl_funding_history"] * len(rates),
            "event_ts_ms": [int(timestamp.timestamp() * 1_000) for timestamp in times],
        }
    )


def _write_bundle(tmp_path: Path) -> tuple[Path, Path]:
    funding_path = tmp_path / "funding.parquet"
    frame = _funding_frame([0.00001] * 12 + [0.00002])
    frame.to_parquet(funding_path, index=False)
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "schema_version": 1,
        "symbol": "ETH",
        "source": "hl_funding_history",
        "venue": "hyperliquid",
        "complete": True,
        "expected_hour_count": len(frame),
        "observed_hour_count": len(frame),
        "missing_hour_count": 0,
        "requested_start": "2026-01-01T00:00:00+00:00",
        "requested_end": "2026-01-01T13:00:00+00:00",
        "first_observed": "2026-01-01T00:00:00+00:00",
        "last_observed": "2026-01-01T12:00:00+00:00",
        "files": {"funding.parquet": file_evidence(funding_path)},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return funding_path, manifest_path


def _stress() -> dict[str, object]:
    route = {
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "maximum_hold_hours": 12.0,
        "planned_notional_usd": 750.0,
        "friction_components_bps": {"adverse_maximum_hold_funding": 0.25},
    }
    return {"scenarios": [{"asset_slots": {"ETH": {"routes": [route]}}}]}


def _current() -> dict[str, object]:
    route = {
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "maximum_hold_hours": 12.0,
        "current_worst_side_cost_bps": 1.25,
    }
    return {
        "current_funding_context": {
            "execution_authority": "none",
            "sizing_input": False,
            "routes": [route],
        }
    }
