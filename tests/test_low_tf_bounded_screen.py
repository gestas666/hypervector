"""Evidence-contract tests for bounded low-timeframe challenger results."""

from __future__ import annotations

from hypervector.research.low_tf_bounded_screen import (
    BoundedCellResult,
    build_bounded_frozen_artifact,
)


def _cell(partition: str, friction: str, net: float) -> BoundedCellResult:
    """Return one compact deterministic cell fixture."""
    return BoundedCellResult(
        partition=partition,
        symbol="ETH",
        family="three_drive_rsi_reversal_v1",
        side="long",
        friction=friction,
        signal_count=3,
        completed_trades=2,
        wins=1,
        losses=1,
        net_pnl_usd=net,
        profit_factor=0.8,
        maximum_drawdown_pct=0.2,
        liquidations=0,
        rejections=1,
        net_without_largest_winner_usd=net - 2.0,
    )


def test_bounded_artifact_reports_every_frozen_partition_without_authority() -> None:
    cells = tuple(
        _cell(partition, friction, -float(index + 1))
        for index, partition in enumerate(
            ("development", "validation", "pseudo_holdout")
        )
        for friction in ("nominal_13bps", "stress_20bps")
    )
    artifact = build_bounded_frozen_artifact(
        run_id="bounded-v1",
        start_utc="2025-07-28T00:00:00+00:00",
        end_utc="2026-01-28T00:00:00+00:00",
        cells=cells,
        source_identity={"ETH": {"bars_sha256": "abc"}},
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["evaluated_partitions"] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert artifact["parameter_updates_after_development"] is False
    assert artifact["cells"][1]["net_without_largest_winner_usd"] == -3.0


def test_bounded_artifact_requires_nominal_and_stress_for_each_cell() -> None:
    try:
        build_bounded_frozen_artifact(
            run_id="bounded-v1",
            start_utc="2025-07-28T00:00:00+00:00",
            end_utc="2026-01-28T00:00:00+00:00",
            cells=(_cell("development", "nominal_13bps", -1.0),),
            source_identity={"ETH": {"bars_sha256": "abc"}},
        )
    except ValueError as exc:
        assert "nominal and stress" in str(exc)
    else:
        raise AssertionError("incomplete friction pair was accepted")
