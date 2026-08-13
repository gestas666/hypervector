"""Fold-safe association screen for cross-asset impulse propagation."""

from __future__ import annotations

from dataclasses import asdict, fields
import math

import pandas as pd

from hypervector.research.cross_asset_impulse_evidence import (
    apply_impulse_eligibility,
    build_impulse_cells,
    impulse_collision_diagnostics,
    select_impulse_candidate,
)
from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseLabel,
    declared_impulse_folds,
    declared_impulse_pairs,
    declared_impulse_variants,
)

type Fold = tuple[str, pd.Timestamp, pd.Timestamp]

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_CONTROLS = declared_impulse_variants()[1:]
_PRIOR_RESIDUAL_CELLS = 90


def development_folds(
    config: CrossAssetImpulseConfig,
) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    """Return the exact declared chronological fold bounds."""
    return tuple((start, end) for _, start, end in declared_impulse_folds(config))


def summarize_impulse_labels(
    *,
    labels: tuple[CrossAssetImpulseLabel, ...],
    config: CrossAssetImpulseConfig,
    run_id: str,
    source_identity: dict[str, dict[str, object]],
    prior_search_identity: dict[str, object],
) -> dict[str, object]:
    """Retain every primary/control cell and select at most one primary."""
    _validate_inputs(labels, config, run_id, source_identity, prior_search_identity)
    folds = declared_impulse_folds(config)
    controls = build_impulse_cells(labels, config, folds, _CONTROLS, False)
    primary = build_impulse_cells(labels, config, folds, ("primary",), True)
    apply_impulse_eligibility(primary, controls, config)
    artifact = _artifact_identity(run_id, config, source_identity, folds)
    prior_count = int(prior_search_identity["selectable_cells"])
    artifact.update(
        primary_cells=primary,
        control_cells=controls,
        searched_set_count=len(primary),
        selected_candidate=select_impulse_candidate(primary),
        collision_diagnostics=impulse_collision_diagnostics(labels, config),
        search_accounting=_search_accounting(
            len(primary), len(controls), prior_count, prior_search_identity
        ),
    )
    return artifact


def build_impulse_development(
    *,
    minute_frames: dict[str, pd.DataFrame],
    config: CrossAssetImpulseConfig,
    run_id: str,
    source_identity: dict[str, dict[str, object]],
    prior_search_identity: dict[str, object],
) -> tuple[dict[str, object], pd.DataFrame]:
    """Build all primary/control labels using the causal signal APIs."""
    _validate_frames(minute_frames)
    frozen = _build_labels(minute_frames, config)
    artifact = summarize_impulse_labels(
        labels=frozen,
        config=config,
        run_id=run_id,
        source_identity=source_identity,
        prior_search_identity=prior_search_identity,
    )
    columns = [field.name for field in fields(CrossAssetImpulseLabel)]
    rows = pd.DataFrame.from_records(
        [asdict(label) for label in frozen], columns=columns
    )
    return artifact, rows


def _build_labels(
    minute_frames: dict[str, pd.DataFrame], config: CrossAssetImpulseConfig
) -> tuple[CrossAssetImpulseLabel, ...]:
    from hypervector.research.cross_asset_impulse_signal import (
        build_impulse_states,
        label_impulse_events,
        sample_impulse_events,
    )

    labels: list[CrossAssetImpulseLabel] = []
    for leader, follower in declared_impulse_pairs():
        leader_frame = minute_frames[leader]
        follower_frame = minute_frames[follower]
        states = build_impulse_states(
            _series(leader_frame, "close"),
            _series(follower_frame, "close"),
            config,
            leader_valid=_series(leader_frame, "source", "hl"),
            follower_valid=_series(follower_frame, "source", "hl"),
        )
        labels.extend(
            _label_pair(
                states,
                leader,
                follower,
                follower_frame,
                config,
                sample_impulse_events,
                label_impulse_events,
            )
        )
    return tuple(labels)


def _label_pair(
    states: pd.DataFrame,
    leader: str,
    follower: str,
    follower_frame: pd.DataFrame,
    config: CrossAssetImpulseConfig,
    sampler: object,
    labeler: object,
) -> list[CrossAssetImpulseLabel]:
    if not callable(sampler) or not callable(labeler):
        raise TypeError("impulse signal functions must be callable")
    labels: list[CrossAssetImpulseLabel] = []
    for variant in declared_impulse_variants():
        events = sampler(states, leader, follower, config, signal_variant=variant)
        labels.extend(labeler(events, follower_frame, config))
    return labels


def _artifact_identity(
    run_id: str,
    config: CrossAssetImpulseConfig,
    source_identity: dict[str, dict[str, object]],
    folds: tuple[Fold, ...],
) -> dict[str, object]:
    return {
        "schema_version": "cross_asset_impulse_development_v1",
        "run_id": run_id,
        "segment": "development",
        "start_utc": config.development_start.isoformat(),
        "end_utc": config.development_end.isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "folds": [_fold_identity(fold) for fold in folds],
        "config": _config_payload(config),
        "source_identity": source_identity,
        "later_segments_status": "family_level_confirmation_only",
    }


def _search_accounting(
    primary_count: int,
    control_count: int,
    prior_count: int,
    prior_identity: dict[str, object],
) -> dict[str, object]:
    return {
        "within_family_selectable_cells": primary_count,
        "nonselectable_control_cells": control_count,
        "prior_residual_selectable_cells": prior_count,
        "known_cumulative_selectable_cells": prior_count + primary_count,
        "prior_residual_artifact": prior_identity,
        "shared_development_window_disclosed": True,
        "project_trial_ledger_complete": False,
        "deflated_sharpe_ratio_computed": False,
    }


def _validate_inputs(
    labels: tuple[CrossAssetImpulseLabel, ...],
    config: CrossAssetImpulseConfig,
    run_id: str,
    source_identity: dict[str, dict[str, object]],
    prior: dict[str, object],
) -> None:
    if not run_id.strip():
        raise ValueError("impulse screen run ID cannot be empty")
    if tuple(source_identity) != _SYMBOLS or any(
        not value for value in source_identity.values()
    ):
        raise ValueError("impulse source identity must cover ordered BTC/ETH/SOL/HYPE")
    required = {"artifact", "sha256", "selectable_cells"}
    if not required.issubset(prior) or int(prior["selectable_cells"]) != 90:
        raise ValueError(
            "impulse prior search identity must bind the 90-cell residual surface"
        )
    for label in labels:
        _validate_label(label, config)


def _validate_label(
    label: CrossAssetImpulseLabel, config: CrossAssetImpulseConfig
) -> None:
    if (label.leader_symbol, label.follower_symbol) not in declared_impulse_pairs():
        raise ValueError("impulse label contains an undeclared pair")
    if label.signal_variant not in declared_impulse_variants():
        raise ValueError("impulse label contains an undeclared signal variant")
    if label.horizon_minutes not in config.horizons_minutes:
        raise ValueError("impulse label contains an undeclared horizon")
    decision = _time(label.decision_time_utc)
    entry, exit_time = _time(label.entry_time_utc), _time(label.exit_time_utc)
    if not config.development_start <= decision < config.development_end:
        raise ValueError("impulse label decision lies outside development")
    if entry < decision or exit_time <= entry:
        raise ValueError("impulse label timestamps violate causal order")
    if label.execution_authority != "none" or not label.report_only:
        raise ValueError("impulse label has execution authority")
    value = label.directional_gross_return_bps
    if label.status == "resolved" and (value is None or not math.isfinite(value)):
        raise ValueError("resolved impulse label requires finite gross return")


def _validate_frames(frames: dict[str, pd.DataFrame]) -> None:
    if tuple(frames) != _SYMBOLS:
        raise ValueError("impulse builder requires ordered BTC/ETH/SOL/HYPE frames")
    required = {"timestamp", "open", "close", "source"}
    for symbol, frame in frames.items():
        if not required.issubset(frame.columns) or frame.empty:
            raise ValueError(f"{symbol} impulse frame is incomplete")
        if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
            raise ValueError(f"{symbol} impulse frame has unexpected source")


def _series(frame: pd.DataFrame, column: str, equals: str | None = None) -> pd.Series:
    if equals:
        values = frame[column].eq(equals).to_numpy(bool)
    else:
        values = frame[column].to_numpy(float)
    return pd.Series(values, index=pd.DatetimeIndex(frame["timestamp"]))


def _time(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("impulse timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _fold_identity(fold: Fold) -> dict[str, str]:
    return {
        "fold": fold[0],
        "start_utc": fold[1].isoformat(),
        "end_utc": fold[2].isoformat(),
    }


def _config_payload(config: CrossAssetImpulseConfig) -> dict[str, object]:
    values = asdict(config)
    for field in ("warmup_start", "development_start", "development_end"):
        values[field] = getattr(config, field).isoformat()
    return values
