"""Eligibility and search-accounting tests for the breadth screen."""

from dataclasses import replace

import pandas as pd

from hypervector.research.cross_asset_breadth_models import (
    CrossAssetBreadthConfig,
    CrossAssetBreadthLabel,
)
from hypervector.research.cross_asset_breadth_screen import summarize_breadth_labels


def _label(
    decision: pd.Timestamp,
    variant: str,
    anchor: str,
    direction: str,
    gross_bps: float,
) -> CrossAssetBreadthLabel:
    delay = 1 if anchor == "delayed" else 0
    entry = decision + pd.Timedelta(minutes=delay)
    exit_time = entry + pd.Timedelta(minutes=60)
    return CrossAssetBreadthLabel(
        bar_open_at=(decision - pd.Timedelta(minutes=15)).isoformat(),
        decision_time_utc=decision.isoformat(),
        entry_time_utc=entry.isoformat(),
        exit_time_utc=exit_time.isoformat(),
        signal_variant=variant,  # type: ignore[arg-type]
        anchor=anchor,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        horizon_minutes=60,
        entry_price=100.0,
        exit_price=100.3,
        directional_gross_return_bps=gross_bps,
        status="resolved",
    )


def _qualifying_labels() -> tuple[CrossAssetBreadthLabel, ...]:
    rows: list[CrossAssetBreadthLabel] = []
    days = pd.date_range("2025-07-28T12:00:00Z", periods=184, freq="1D")
    for index, decision in enumerate(days):
        direction = "long" if index % 2 == 0 else "short"
        for variant, gross in (
            ("primary", 30.0),
            ("btc_only_momentum", 8.0),
            ("lagged_breadth_placebo", 4.0),
        ):
            rows.append(_label(decision, variant, "base", direction, gross))
            rows.append(_label(decision, variant, "delayed", direction, gross))
    return tuple(rows)


def _summary(labels: tuple[CrossAssetBreadthLabel, ...]) -> dict[str, object]:
    return summarize_breadth_labels(
        labels=labels,
        config=CrossAssetBreadthConfig(),
        run_id="cross_asset_breadth_development_v1",
        source_identity={
            symbol: {"sha256": symbol} for symbol in ("BTC", "ETH", "SOL", "HYPE")
        },
        prior_search_identity={
            "artifact": "data/logs/research/cross_asset_impulse_development_v1.json",
            "sha256": "5721bf0a11b7616068b2fd5d563cd7415ccd464062ef1cf73a68088faafbd5e4",
            "selectable_cells": 105,
        },
    )


def test_selects_only_primary_when_every_frozen_criterion_clears() -> None:
    artifact = _summary(_qualifying_labels())

    assert artifact["searched_set_count"] == 1
    assert artifact["selected_candidate"] == {
        "signal_variant": "primary",
        "horizon_minutes": 60,
    }
    primary = artifact["primary_cell"]
    assert isinstance(primary, dict)
    assert primary["eligible_for_replay"] is True
    assert primary["eligibility_failures"] == []
    assert artifact["search_accounting"] == {
        "within_family_selectable_cells": 1,
        "nonselectable_control_cells": 2,
        "known_prior_selectable_cells": 105,
        "known_cumulative_selectable_cells": 106,
        "prior_impulse_artifact": {
            "artifact": "data/logs/research/cross_asset_impulse_development_v1.json",
            "sha256": "5721bf0a11b7616068b2fd5d563cd7415ccd464062ef1cf73a68088faafbd5e4",
            "selectable_cells": 105,
        },
        "shared_development_window_disclosed": True,
        "project_trial_ledger_complete": False,
        "deflated_sharpe_ratio_computed": False,
    }


def test_one_subcost_delayed_fold_rejects_without_threshold_tuning() -> None:
    labels = list(_qualifying_labels())
    fold_two_start = pd.Timestamp("2025-09-28T00:00:00Z")
    fold_two_end = pd.Timestamp("2025-11-28T00:00:00Z")
    labels = [
        replace(label, directional_gross_return_bps=10.0)
        if label.signal_variant == "primary"
        and label.anchor == "delayed"
        and fold_two_start <= pd.Timestamp(label.decision_time_utc) < fold_two_end
        else label
        for label in labels
    ]

    artifact = _summary(tuple(labels))

    assert artifact["selected_candidate"] is None
    primary = artifact["primary_cell"]
    assert isinstance(primary, dict)
    assert primary["eligible_for_replay"] is False
    assert "delayed_fold_mean_not_above_nominal_cost" in primary["eligibility_failures"]
