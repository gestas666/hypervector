"""Finalized fold, metric, cadence, and selection contract tests."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseLabel,
    declared_impulse_folds,
)
from hypervector.research.cross_asset_impulse_screen import (
    build_impulse_development,
    development_folds,
    summarize_impulse_labels,
)


def _identity() -> dict[str, dict[str, object]]:
    return {
        symbol: {"sha256": symbol.lower(), "authentic_rows": 1, "gap_rows": 0}
        for symbol in ("BTC", "ETH", "SOL", "HYPE")
    }


def _prior_search() -> dict[str, object]:
    return {
        "artifact": "data/logs/research/cross_asset_residual_exit_surface_v1.json",
        "sha256": "residual-sha",
        "selectable_cells": 90,
    }


def _fixture_config() -> CrossAssetImpulseConfig:
    return CrossAssetImpulseConfig(
        warmup_start=pd.Timestamp("2025-12-24T23:55:00Z"),
        development_start=pd.Timestamp("2026-01-01T00:00:00Z"),
        development_end=pd.Timestamp("2026-01-10T00:00:00Z"),
        horizons_minutes=(5,),
        fold_count=3,
    )


def _label(
    decision: pd.Timestamp,
    gross_bps: float | None,
    *,
    pair: tuple[str, str] = ("BTC", "ETH"),
    variant: str = "primary",
    anchor: str = "base",
    direction: str = "long",
    horizon: int = 5,
    status: str = "resolved",
    exit_time: pd.Timestamp | None = None,
) -> CrossAssetImpulseLabel:
    entry = decision + pd.Timedelta(minutes=int(anchor == "delayed"))
    exit_at = exit_time or entry + pd.Timedelta(minutes=horizon)
    entry_price = 100.0 if status == "resolved" else None
    exit_price = (
        100.0 * (1.0 + float(gross_bps) / 10_000.0)
        if status == "resolved" and gross_bps is not None
        else None
    )
    return CrossAssetImpulseLabel(
        bar_open_at=(decision - pd.Timedelta(minutes=1)).isoformat(),
        decision_time_utc=decision.isoformat(),
        entry_time_utc=entry.isoformat(),
        exit_time_utc=exit_at.isoformat(),
        leader_symbol=pair[0],
        follower_symbol=pair[1],
        signal_variant=variant,  # type: ignore[arg-type]
        anchor=anchor,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        horizon_minutes=horizon,
        entry_price=entry_price,
        exit_price=exit_price,
        directional_gross_return_bps=gross_bps,
        status=status,  # type: ignore[arg-type]
    )


def _eligible_labels(
    config: CrossAssetImpulseConfig,
    *,
    pair: tuple[str, str] = ("BTC", "ETH"),
    base: float = 40.0,
    delayed: float = 30.0,
    leader_only: float = 10.0,
    placebo: float = 5.0,
) -> tuple[CrossAssetImpulseLabel, ...]:
    values: list[CrossAssetImpulseLabel] = []
    controls = {
        "leader_only_ablation": leader_only,
        "follower_only_momentum": 50.0,
        "lagged_leader_placebo": placebo,
    }
    for _, start, _ in declared_impulse_folds(config):
        for index in range(30):
            decision = start + pd.Timedelta(minutes=60 * index)
            direction = "long" if index < 15 else "short"
            values.extend(
                (
                    _label(decision, base, pair=pair, direction=direction),
                    _label(
                        decision,
                        delayed,
                        pair=pair,
                        anchor="delayed",
                        direction=direction,
                    ),
                )
            )
            for variant, gross in controls.items():
                values.extend(
                    _control_labels(decision, gross, pair, variant, direction)
                )
    return tuple(values)


def _control_labels(
    decision: pd.Timestamp,
    gross: float,
    pair: tuple[str, str],
    variant: str,
    direction: str,
) -> tuple[CrossAssetImpulseLabel, CrossAssetImpulseLabel]:
    shared = {"pair": pair, "variant": variant, "direction": direction}
    return (
        _label(decision, gross, **shared),  # type: ignore[arg-type]
        _label(decision, gross, anchor="delayed", **shared),  # type: ignore[arg-type]
    )


def _summary(
    labels: tuple[CrossAssetImpulseLabel, ...],
    config: CrossAssetImpulseConfig,
) -> dict[str, object]:
    return summarize_impulse_labels(
        labels=labels,
        config=config,
        run_id="fixture",
        source_identity=_identity(),
        prior_search_identity=_prior_search(),
    )


def _primary_cell(
    artifact: dict[str, object], pair: tuple[str, str], horizon: int
) -> dict[str, object]:
    cells = artifact["primary_cells"]
    assert isinstance(cells, list)
    return next(
        cell
        for cell in cells
        if (cell["leader_symbol"], cell["follower_symbol"]) == pair
        and cell["horizon_minutes"] == horizon
    )


def test_default_development_folds_use_declared_calendar_boundaries() -> None:
    config = CrossAssetImpulseConfig()

    assert development_folds(config) == tuple(
        (start, end) for _, start, end in declared_impulse_folds(config)
    )


def test_screen_retains_15_primary_and_45_nonselectable_control_cells() -> None:
    artifact = _summary((), CrossAssetImpulseConfig())

    assert len(artifact["primary_cells"]) == 15
    assert len(artifact["control_cells"]) == 45
    assert artifact["report_only"] is True
    assert artifact["execution_authority"] == "none"
    assert all(not cell["selectable"] for cell in artifact["control_cells"])
    assert all(not cell["selected_for_replay"] for cell in artifact["control_cells"])


def test_fold_metrics_include_rich_base_delayed_and_exclusion_evidence() -> None:
    config = _fixture_config()
    _, fold_start, fold_end = declared_impulse_folds(config)[0]
    gross = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 900.0]
    labels = tuple(
        _label(
            fold_start + pd.Timedelta(minutes=index * 10),
            value,
            direction="long" if index < 5 else "short",
        )
        for index, value in enumerate(gross)
    ) + (
        _label(fold_start, 25.0, anchor="delayed"),
        _label(fold_start, None, status="technical_gap"),
        _label(fold_start, None, status="right_censored"),
        _label(fold_start, 30.0, exit_time=fold_end),
    )

    cell = _primary_cell(_summary(labels, config), ("BTC", "ETH"), 5)
    fold = cell["folds"][0]
    base = fold["base"]

    assert base["resolved_events"] == 10
    assert base["excluded"] == {
        "technical_gap": 1,
        "fold_boundary_purged": 1,
        "right_censored": 1,
    }
    assert base["long_events"] == 5
    assert base["short_events"] == 5
    assert base["mean_gross_bps"] == pytest.approx(np.mean(gross))
    assert base["median_gross_bps"] == pytest.approx(np.median(gross))
    assert base["trimmed_mean_gross_bps"] == pytest.approx(45.0)
    assert base["std_gross_bps"] == pytest.approx(np.std(gross, ddof=1))
    assert base["p25_gross_bps"] == pytest.approx(np.quantile(gross, 0.25))
    assert base["p75_gross_bps"] == pytest.approx(np.quantile(gross, 0.75))
    assert base["fraction_above_20_bps"] == pytest.approx(7 / 10)
    assert base["mean_minus_nominal_bps"] == pytest.approx(np.mean(gross) - 13.0)
    assert base["mean_minus_stress_bps"] == pytest.approx(np.mean(gross) - 20.0)
    assert fold["delayed"]["resolved_events"] == 1
    assert cell["base_direction_means_bps"] == {"long": 20.0, "short": 232.0}


def test_fold_exit_at_boundary_is_purged_and_never_moves_to_next_fold() -> None:
    config = _fixture_config()
    _, _, fold_end = declared_impulse_folds(config)[0]
    label = _label(fold_end - pd.Timedelta(minutes=5), 100.0, exit_time=fold_end)

    cell = _primary_cell(_summary((label,), config), ("BTC", "ETH"), 5)

    assert cell["folds"][0]["base"]["resolved_events"] == 0
    assert cell["folds"][0]["base"]["excluded"]["fold_boundary_purged"] == 1
    assert cell["folds"][1]["base"]["resolved_events"] == 0


def test_per_cell_cadence_uses_resolved_primary_events_only() -> None:
    config = _fixture_config()
    start = config.development_start
    labels = (
        _label(start + pd.Timedelta(hours=1), 30.0),
        _label(start + pd.Timedelta(hours=2), 30.0),
        _label(start + pd.Timedelta(hours=2), 30.0, anchor="delayed"),
        _label(start + pd.Timedelta(hours=3), None, status="technical_gap"),
    )

    cell = _primary_cell(_summary(labels, config), ("BTC", "ETH"), 5)
    cadence = cell["cadence"]

    assert cadence["resolved_events"] == 2
    assert cadence["events_per_calendar_day"] == pytest.approx(2 / 9)
    assert cadence["active_utc_day_fraction"] == pytest.approx(1 / 9)
    assert cadence["median_interarrival_minutes"] == 60.0
    assert cadence["p90_interarrival_minutes"] == 60.0
    assert cadence["maximum_interarrival_minutes"] == 60.0
    assert cadence["longest_eventless_minutes"] == pytest.approx(8 * 1440 + 22 * 60)


def test_collision_diagnostics_report_clusters_and_effective_count() -> None:
    config = _fixture_config()
    decision = config.development_start + pd.Timedelta(hours=1)
    labels = (
        _label(decision, 30.0, pair=("BTC", "ETH")),
        _label(decision, 30.0, pair=("BTC", "SOL")),
        _label(decision, 30.0, pair=("ETH", "SOL")),
        _label(decision + pd.Timedelta(hours=1), 30.0, pair=("BTC", "ETH")),
    )

    collisions = _summary(labels, config)["collision_diagnostics"]

    assert collisions["nominal_unique_pair_events"] == 4
    assert collisions["same_leader_time_clusters"] == 1
    assert collisions["same_follower_time_collisions"] == 1
    assert collisions["cross_pair_overlap_timestamps"] == 1
    assert collisions["cluster_size_distribution"] == {"1": 2, "2": 1}
    assert collisions["uniqueness_weighted_effective_count"] == pytest.approx(3.0)


def test_all_frozen_eligibility_conditions_select_one_candidate() -> None:
    config = _fixture_config()
    artifact = _summary(_eligible_labels(config), config)
    cell = _primary_cell(artifact, ("BTC", "ETH"), 5)

    assert cell["eligibility_failures"] == []
    assert cell["eligible_for_replay"] is True
    assert cell["selected_for_replay"] is True
    assert sum(value["selected_for_replay"] for value in artifact["primary_cells"]) == 1
    assert artifact["selected_candidate"] == {
        "leader_symbol": "BTC",
        "follower_symbol": "ETH",
        "horizon_minutes": 5,
    }


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        ({"minimum_events_per_fold": 31}, "insufficient_resolved_events_per_fold"),
        (
            {"minimum_direction_events_per_fold": 16, "minimum_events_per_fold": 32},
            "insufficient_direction_events_per_fold",
        ),
        ({"minimum_base_fold_mean_bps": 40.0}, "base_fold_mean_not_above_threshold"),
        (
            {"minimum_base_median_fold_mean_bps": 41.0},
            "base_median_fold_mean_below_threshold",
        ),
        ({"minimum_direction_mean_bps": 40.0}, "direction_mean_not_above_threshold"),
        (
            {"minimum_delayed_fold_mean_bps": 30.0},
            "delayed_fold_mean_not_above_threshold",
        ),
        (
            {"minimum_delayed_median_fold_mean_bps": 31.0},
            "delayed_median_fold_mean_below_threshold",
        ),
        ({"minimum_events_per_day": 11.0}, "events_per_day_below_threshold"),
        (
            {"maximum_p90_interarrival_minutes": 30.0},
            "p90_interarrival_above_threshold",
        ),
    ],
)
def test_each_numeric_eligibility_boundary_fails_independently(
    changes: dict[str, object], failure: str
) -> None:
    config = replace(_fixture_config(), **changes)
    cell = _primary_cell(_summary(_eligible_labels(config), config), ("BTC", "ETH"), 5)

    assert failure in cell["eligibility_failures"]
    assert cell["eligible_for_replay"] is False


@pytest.mark.parametrize(
    ("leader_only", "placebo", "failure"),
    [
        (40.0, 5.0, "does_not_dominate_leader_only_every_fold"),
        (10.0, 40.0, "does_not_dominate_lagged_placebo_every_fold"),
    ],
)
def test_primary_requires_strict_foldwise_control_dominance(
    leader_only: float, placebo: float, failure: str
) -> None:
    config = _fixture_config()
    labels = _eligible_labels(config, leader_only=leader_only, placebo=placebo)
    cell = _primary_cell(_summary(labels, config), ("BTC", "ETH"), 5)

    assert failure in cell["eligibility_failures"]
    assert cell["selected_for_replay"] is False


def test_lexicographic_selection_prefers_worst_delayed_then_declared_pair() -> None:
    config = _fixture_config()
    labels = _eligible_labels(config, pair=("BTC", "ETH"), delayed=30.0)
    labels += _eligible_labels(config, pair=("BTC", "SOL"), delayed=31.0)
    artifact = _summary(labels, config)

    assert _primary_cell(artifact, ("BTC", "SOL"), 5)["selected_for_replay"] is True

    tied = _summary(
        _eligible_labels(config, pair=("BTC", "ETH"))
        + _eligible_labels(config, pair=("BTC", "SOL")),
        config,
    )
    assert _primary_cell(tied, ("BTC", "ETH"), 5)["selected_for_replay"] is True
    assert sum(value["selected_for_replay"] for value in tied["primary_cells"]) == 1


def test_search_accounting_preserves_prior_exposure_without_dsr_claim() -> None:
    artifact = _summary((), CrossAssetImpulseConfig())
    accounting = artifact["search_accounting"]

    assert accounting["within_family_selectable_cells"] == 15
    assert accounting["nonselectable_control_cells"] == 45
    assert accounting["prior_residual_selectable_cells"] == 90
    assert accounting["known_cumulative_selectable_cells"] == 105
    assert accounting["prior_residual_artifact"] == _prior_search()
    assert accounting["project_trial_ledger_complete"] is False
    assert accounting["deflated_sharpe_ratio_computed"] is False
    assert artifact["later_segments_status"] == "family_level_confirmation_only"


def test_development_builder_integrates_all_variants_and_row_authority() -> None:
    config = CrossAssetImpulseConfig(
        warmup_start=pd.Timestamp("2025-12-31T23:40:00Z"),
        development_start=pd.Timestamp("2026-01-01T00:00:00Z"),
        development_end=pd.Timestamp("2026-01-01T01:30:00Z"),
        impulse_return_minutes=2,
        lookback_minutes=6,
        minimum_valid_returns=5,
        leader_z_threshold=1.0,
        catchup_gap_threshold=0.0,
        cooldown_minutes=5,
        horizons_minutes=(2, 5),
        placebo_lag_minutes=4,
        minimum_events_per_fold=2,
        minimum_direction_events_per_fold=1,
    )
    times = pd.date_range(
        config.warmup_start, config.development_end, freq="1min", inclusive="left"
    )
    frames = {
        symbol: pd.DataFrame(
            {
                "timestamp": times,
                "open": 100.0 + offset + np.sin(np.arange(len(times)) / scale),
                "close": 100.1 + offset + np.sin((np.arange(len(times)) + 1) / scale),
                "source": "hl",
            }
        )
        for symbol, offset, scale in (
            ("BTC", 0.0, 1.5),
            ("ETH", 10.0, 2.0),
            ("SOL", 20.0, 2.5),
            ("HYPE", 30.0, 3.0),
        )
    }

    artifact, rows = build_impulse_development(
        minute_frames=frames,
        config=config,
        run_id="integrated-fixture",
        source_identity=_identity(),
        prior_search_identity=_prior_search(),
    )

    assert len(artifact["primary_cells"]) == 10
    assert len(artifact["control_cells"]) == 30
    assert set(rows["signal_variant"]) == {
        "primary",
        "leader_only_ablation",
        "follower_only_momentum",
        "lagged_leader_placebo",
    }
    assert rows["report_only"].all()
    assert rows["execution_authority"].eq("none").all()
