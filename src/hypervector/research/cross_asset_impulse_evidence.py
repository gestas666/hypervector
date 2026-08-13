"""Evidence aggregation helpers for the cross-asset impulse screen."""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from hypervector.research.cross_asset_impulse_metrics import (
    build_fold_payloads,
    calendar_days,
    impulse_cadence,
    impulse_direction_means,
    median_metric_means,
    minimum_metric_means,
)
from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseLabel,
    DirectedPair,
    ImpulseSignalVariant,
    declared_impulse_pairs,
)

type Fold = tuple[str, pd.Timestamp, pd.Timestamp]
type Cell = dict[str, object]


def build_impulse_cells(
    labels: tuple[CrossAssetImpulseLabel, ...],
    config: CrossAssetImpulseConfig,
    folds: tuple[Fold, ...],
    variants: tuple[ImpulseSignalVariant, ...],
    selectable: bool,
) -> list[Cell]:
    """Build complete fold evidence for every declared cell."""
    return [
        _build_cell(variant, pair, horizon, labels, folds, config, selectable)
        for variant in variants
        for pair in declared_impulse_pairs()
        for horizon in config.horizons_minutes
    ]


def apply_impulse_eligibility(
    primary: list[Cell],
    controls: list[Cell],
    config: CrossAssetImpulseConfig,
) -> None:
    """Apply the frozen eligibility contract to primary cells in place."""
    control_map = {_cell_key(cell): cell for cell in controls}
    for cell in primary:
        failures = _eligibility_failures(cell, control_map, config)
        cell.update(eligibility_failures=failures, eligible_for_replay=not failures)


def select_impulse_candidate(primary: list[Cell]) -> Cell | None:
    """Select exactly one eligible cell by the frozen lexicographic order."""
    eligible = [cell for cell in primary if cell["eligible_for_replay"]]
    if not eligible:
        return None
    order = {pair: index for index, pair in enumerate(declared_impulse_pairs())}
    winner = min(eligible, key=lambda cell: _ranking_key(cell, order))
    winner["selected_for_replay"] = True
    keys = ("leader_symbol", "follower_symbol", "horizon_minutes")
    return {key: winner[key] for key in keys}


def impulse_collision_diagnostics(
    labels: tuple[CrossAssetImpulseLabel, ...], config: CrossAssetImpulseConfig
) -> Cell:
    """Return dependence diagnostics without inflating effective sample size."""
    events = {
        (label.leader_symbol, label.follower_symbol, label.decision_time_utc)
        for label in labels
        if label.signal_variant == "primary" and label.anchor == "base"
    }
    by_time = _group_events(events, 2)
    by_leader = _group_events(events, (0, 2))
    by_follower = _group_events(events, (1, 2))
    distribution = Counter(len(values) for values in by_follower.values())
    return {
        "nominal_unique_pair_events": len(events),
        "same_leader_time_clusters": _collision_count(by_leader),
        "same_follower_time_collisions": _collision_count(by_follower),
        "cross_pair_overlap_timestamps": _collision_count(by_time),
        "cluster_size_distribution": {
            str(size): count for size, count in sorted(distribution.items())
        },
        "uniqueness_weighted_effective_count": sum(
            sum(1 / len(values) for _ in values) for values in by_follower.values()
        ),
        "portfolio_unique_follower_times": len(
            {(event[1], event[2]) for event in events}
        ),
        "calendar_days": calendar_days(config),
    }


def _build_cell(
    variant: ImpulseSignalVariant,
    pair: DirectedPair,
    horizon: int,
    labels: tuple[CrossAssetImpulseLabel, ...],
    folds: tuple[Fold, ...],
    config: CrossAssetImpulseConfig,
    selectable: bool,
) -> Cell:
    selected = tuple(
        label
        for label in labels
        if label.signal_variant == variant
        and (label.leader_symbol, label.follower_symbol) == pair
        and label.horizon_minutes == horizon
    )
    payloads = build_fold_payloads(selected, folds, config)
    cell: Cell = {
        "signal_variant": variant,
        "leader_symbol": pair[0],
        "follower_symbol": pair[1],
        "horizon_minutes": horizon,
        "selectable": selectable,
        "folds": payloads,
        "base_direction_means_bps": impulse_direction_means(selected, folds, config),
        "cadence": impulse_cadence(selected, folds, config) if selectable else None,
        "eligible_for_replay": False,
        "selected_for_replay": False,
        "execution_authority": "none",
    }
    cell["ranking_inputs"] = _ranking_inputs(cell)
    return cell


def _eligibility_failures(
    cell: Cell,
    controls: dict[tuple[str, str, str, int], Cell],
    config: CrossAssetImpulseConfig,
) -> list[str]:
    folds = cell["folds"]
    assert isinstance(folds, list)
    base = [fold["base"] for fold in folds]
    delayed = [fold["delayed"] for fold in folds]
    failures = _numeric_failures(cell, base, delayed, config)
    failures.extend(_dominance_failures(cell, base, controls))
    cadence = cell["cadence"]
    assert isinstance(cadence, dict)
    if cadence["events_per_calendar_day"] < config.minimum_events_per_day:
        failures.append("events_per_day_below_threshold")
    if _above(
        cadence["p90_interarrival_minutes"], config.maximum_p90_interarrival_minutes
    ):
        failures.append("p90_interarrival_above_threshold")
    return failures


def _numeric_failures(
    cell: Cell,
    base: list[Cell],
    delayed: list[Cell],
    config: CrossAssetImpulseConfig,
) -> list[str]:
    rules = (
        (_insufficient_events(base, config), "insufficient_resolved_events_per_fold"),
        (
            _insufficient_directions(base, config),
            "insufficient_direction_events_per_fold",
        ),
        (
            _fold_mean_fails(base, config.minimum_base_fold_mean_bps),
            "base_fold_mean_not_above_threshold",
        ),
        (
            _below(median_metric_means(base), config.minimum_base_median_fold_mean_bps),
            "base_median_fold_mean_below_threshold",
        ),
        (_direction_mean_fails(cell, config), "direction_mean_not_above_threshold"),
        (
            _fold_mean_fails(delayed, config.minimum_delayed_fold_mean_bps),
            "delayed_fold_mean_not_above_threshold",
        ),
        (
            _below(
                median_metric_means(delayed),
                config.minimum_delayed_median_fold_mean_bps,
            ),
            "delayed_median_fold_mean_below_threshold",
        ),
    )
    return [name for failed, name in rules if failed]


def _dominance_failures(
    cell: Cell,
    base: list[Cell],
    controls: dict[tuple[str, str, str, int], Cell],
) -> list[str]:
    failures: list[str] = []
    leader = _matching_control(cell, controls, "leader_only_ablation")
    placebo = _matching_control(cell, controls, "lagged_leader_placebo")
    if not _dominates(base, leader):
        failures.append("does_not_dominate_leader_only_every_fold")
    if not _dominates(base, placebo):
        failures.append("does_not_dominate_lagged_placebo_every_fold")
    return failures


def _ranking_inputs(cell: Cell) -> dict[str, float | None]:
    folds = cell["folds"]
    assert isinstance(folds, list)
    base = [fold["base"] for fold in folds]
    delayed = [fold["delayed"] for fold in folds]
    cadence = cell["cadence"]
    return {
        "worst_fold_delayed_mean_bps": minimum_metric_means(delayed),
        "worst_fold_base_mean_bps": minimum_metric_means(base),
        "median_fold_base_mean_bps": median_metric_means(base),
        "events_per_calendar_day": (
            cadence["events_per_calendar_day"] if isinstance(cadence, dict) else None
        ),
    }


def _ranking_key(
    cell: Cell, order: dict[DirectedPair, int]
) -> tuple[float, float, float, float, int, int]:
    values = cell["ranking_inputs"]
    assert isinstance(values, dict)
    pair = (str(cell["leader_symbol"]), str(cell["follower_symbol"]))
    return (
        -float(values["worst_fold_delayed_mean_bps"]),
        -float(values["worst_fold_base_mean_bps"]),
        -float(values["median_fold_base_mean_bps"]),
        -float(values["events_per_calendar_day"]),
        order[pair],
        int(cell["horizon_minutes"]),
    )


def _matching_control(
    cell: Cell,
    controls: dict[tuple[str, str, str, int], Cell],
    variant: str,
) -> Cell:
    key = (
        variant,
        str(cell["leader_symbol"]),
        str(cell["follower_symbol"]),
        int(cell["horizon_minutes"]),
    )
    return controls[key]


def _dominates(base: list[Cell], control: Cell) -> bool:
    folds = control["folds"]
    assert isinstance(folds, list)
    other = [fold["base"] for fold in folds]
    return all(
        left["mean_gross_bps"] is not None
        and right["mean_gross_bps"] is not None
        and left["mean_gross_bps"] > right["mean_gross_bps"]
        for left, right in zip(base, other, strict=True)
    )


def _direction_mean_fails(cell: Cell, config: CrossAssetImpulseConfig) -> bool:
    means = cell["base_direction_means_bps"]
    assert isinstance(means, dict)
    return any(
        _not_above(means[side], config.minimum_direction_mean_bps)
        for side in ("long", "short")
    )


def _insufficient_events(base: list[Cell], config: CrossAssetImpulseConfig) -> bool:
    return any(
        item["resolved_events"] < config.minimum_events_per_fold for item in base
    )


def _insufficient_directions(base: list[Cell], config: CrossAssetImpulseConfig) -> bool:
    minimum = config.minimum_direction_events_per_fold
    return any(
        item["long_events"] < minimum or item["short_events"] < minimum for item in base
    )


def _fold_mean_fails(metrics: list[Cell], threshold: float) -> bool:
    return any(_not_above(item["mean_gross_bps"], threshold) for item in metrics)


def _cell_key(cell: Cell) -> tuple[str, str, str, int]:
    return (
        str(cell["signal_variant"]),
        str(cell["leader_symbol"]),
        str(cell["follower_symbol"]),
        int(cell["horizon_minutes"]),
    )


def _group_events(
    events: set[tuple[str, str, str]], keys: int | tuple[int, int]
) -> dict[object, set[tuple[str, str]]]:
    grouped: dict[object, set[tuple[str, str]]] = defaultdict(set)
    for event in events:
        key = event[keys] if isinstance(keys, int) else (event[keys[0]], event[keys[1]])
        grouped[key].add((event[0], event[1]))
    return grouped


def _collision_count(groups: dict[object, set[tuple[str, str]]]) -> int:
    return sum(len(values) > 1 for values in groups.values())


def _not_above(value: object, threshold: float) -> bool:
    return value is None or float(value) <= threshold


def _below(value: object, threshold: float) -> bool:
    return value is None or float(value) < threshold


def _above(value: object, threshold: float) -> bool:
    return value is None or float(value) > threshold
