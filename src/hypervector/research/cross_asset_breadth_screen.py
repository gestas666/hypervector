"""Frozen one-cell development screen for BTC breadth expansion."""

from __future__ import annotations

from dataclasses import asdict, fields
import math

import pandas as pd

from hypervector.research.cross_asset_breadth_metrics import (
    apply_breadth_eligibility,
    build_breadth_cell,
)
from hypervector.research.cross_asset_breadth_models import (
    CrossAssetBreadthConfig,
    CrossAssetBreadthLabel,
    declared_breadth_folds,
    declared_breadth_variants,
)

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_PRIMARY = "primary"
_CONTROLS = declared_breadth_variants()[1:]
_KNOWN_PRIOR_SELECTABLE_CELLS = 105


def summarize_breadth_labels(
    *,
    labels: tuple[CrossAssetBreadthLabel, ...],
    config: CrossAssetBreadthConfig,
    run_id: str,
    source_identity: dict[str, dict[str, object]],
    prior_search_identity: dict[str, object],
) -> dict[str, object]:
    """Aggregate the one selectable cell and two fixed controls."""
    _validate_inputs(labels, config, run_id, source_identity, prior_search_identity)
    folds = declared_breadth_folds(config)
    grouped = {
        variant: tuple(label for label in labels if label.signal_variant == variant)
        for variant in declared_breadth_variants()
    }
    controls = [
        build_breadth_cell(grouped[variant], folds, config) for variant in _CONTROLS
    ]
    primary = build_breadth_cell(grouped[_PRIMARY], folds, config)
    apply_breadth_eligibility(primary, controls, config)
    artifact = _artifact_identity(run_id, config, source_identity)
    artifact.update(
        primary_cell=primary,
        control_cells=controls,
        searched_set_count=1,
        selected_candidate=_selected_candidate(primary, config),
        search_accounting=_search_accounting(prior_search_identity),
    )
    return artifact


def build_breadth_development(
    *,
    closes_15m: pd.DataFrame,
    validity_15m: pd.DataFrame,
    btc_minute_frame: pd.DataFrame,
    config: CrossAssetBreadthConfig,
    run_id: str,
    source_identity: dict[str, dict[str, object]],
    prior_search_identity: dict[str, object],
) -> tuple[dict[str, object], pd.DataFrame]:
    """Build all primary/control labels and their report-only summary."""
    from hypervector.research.cross_asset_breadth_signal import (
        build_breadth_states,
        label_breadth_events,
        sample_breadth_events,
    )

    states = build_breadth_states(closes_15m, validity_15m, config)
    labels: list[CrossAssetBreadthLabel] = []
    for variant in declared_breadth_variants():
        events = sample_breadth_events(states, config, signal_variant=variant)
        labels.extend(label_breadth_events(events, btc_minute_frame, config))
    frozen = tuple(labels)
    artifact = summarize_breadth_labels(
        labels=frozen,
        config=config,
        run_id=run_id,
        source_identity=source_identity,
        prior_search_identity=prior_search_identity,
    )
    columns = [field.name for field in fields(CrossAssetBreadthLabel)]
    rows = pd.DataFrame.from_records(
        [asdict(label) for label in frozen], columns=columns
    )
    return artifact, rows


def _validate_inputs(
    labels: tuple[CrossAssetBreadthLabel, ...],
    config: CrossAssetBreadthConfig,
    run_id: str,
    source_identity: dict[str, dict[str, object]],
    prior: dict[str, object],
) -> None:
    if not run_id.strip():
        raise ValueError("breadth screen run ID cannot be empty")
    if tuple(source_identity) != _SYMBOLS or any(
        not value for value in source_identity.values()
    ):
        raise ValueError("breadth source identity must cover ordered BTC/ETH/SOL/HYPE")
    required = {"artifact", "sha256", "selectable_cells"}
    if (
        not required.issubset(prior)
        or int(prior["selectable_cells"]) != _KNOWN_PRIOR_SELECTABLE_CELLS
    ):
        raise ValueError("breadth prior search identity must bind 105 selectable cells")
    observed = {label.signal_variant for label in labels}
    if observed != set(declared_breadth_variants()):
        raise ValueError("breadth labels must cover the primary and both controls")
    for label in labels:
        _validate_label(label, config)


def _validate_label(
    label: CrossAssetBreadthLabel,
    config: CrossAssetBreadthConfig,
) -> None:
    decision = _time(label.decision_time_utc)
    entry = _time(label.entry_time_utc)
    exit_time = _time(label.exit_time_utc)
    if not config.development_start <= decision < config.development_end:
        raise ValueError("breadth label decision lies outside development")
    if entry < decision or exit_time <= entry:
        raise ValueError("breadth label timestamps violate causal order")
    if label.horizon_minutes != config.horizon_minutes:
        raise ValueError("breadth label has an undeclared horizon")
    if label.execution_authority != "none" or not label.report_only:
        raise ValueError("breadth label has execution authority")
    value = label.directional_gross_return_bps
    if label.status == "resolved" and (value is None or not math.isfinite(value)):
        raise ValueError("resolved breadth label requires finite gross return")


def _artifact_identity(
    run_id: str,
    config: CrossAssetBreadthConfig,
    source_identity: dict[str, dict[str, object]],
) -> dict[str, object]:
    folds = declared_breadth_folds(config)
    return {
        "schema_version": "cross_asset_breadth_development_v1",
        "run_id": run_id,
        "segment": "development",
        "start_utc": config.development_start.isoformat(),
        "end_utc": config.development_end.isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "folds": [
            {"fold": name, "start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for name, start, end in folds
        ],
        "config": _config_payload(config),
        "source_identity": source_identity,
        "later_segments_status": "unloaded",
    }


def _search_accounting(prior: dict[str, object]) -> dict[str, object]:
    return {
        "within_family_selectable_cells": 1,
        "nonselectable_control_cells": 2,
        "known_prior_selectable_cells": _KNOWN_PRIOR_SELECTABLE_CELLS,
        "known_cumulative_selectable_cells": _KNOWN_PRIOR_SELECTABLE_CELLS + 1,
        "prior_impulse_artifact": prior,
        "shared_development_window_disclosed": True,
        "project_trial_ledger_complete": False,
        "deflated_sharpe_ratio_computed": False,
    }


def _selected_candidate(
    primary: dict[str, object],
    config: CrossAssetBreadthConfig,
) -> dict[str, object] | None:
    if primary.get("eligible_for_replay") is not True:
        return None
    return {"signal_variant": "primary", "horizon_minutes": config.horizon_minutes}


def _config_payload(config: CrossAssetBreadthConfig) -> dict[str, object]:
    values = asdict(config)
    for field in ("warmup_start", "development_start", "development_end"):
        values[field] = getattr(config, field).isoformat()
    return values


def _time(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError("breadth timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")
