"""Report-only HIP-3 close-only opposite-direction exit comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

import pandas as pd

from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_lifecycle_replay import (
    build_hip3_shadow_lifecycle_replay,
)


def build_close_only_opposite_exit_comparison(
    *,
    decision_rows: Sequence[Mapping[str, object]],
    book_rows: Sequence[Mapping[str, object]],
    candles: pd.DataFrame,
    mark_rows: Sequence[Mapping[str, object]],
    funding_rows: pd.DataFrame,
    config: Hip3ShadowLifecycleConfig,
    profit_lock_bars: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Compare a one-sided control with close-only opposite signal authority."""
    entry_side, close_side = _one_sided_contract(config)
    control_config = replace(config, opposite_entry_exit_enabled=False)
    challenger_config = replace(config, opposite_entry_exit_enabled=True)
    arguments = {
        "decision_rows": decision_rows,
        "book_rows": book_rows,
        "candles": candles,
        "mark_rows": mark_rows,
        "funding_rows": funding_rows,
        "profit_lock_bars": profit_lock_bars,
    }
    control = build_hip3_shadow_lifecycle_replay(config=control_config, **arguments)
    challenger = build_hip3_shadow_lifecycle_replay(
        config=challenger_config, **arguments
    )
    return {
        "schema_version": "hip3_close_only_opposite_exit_comparison_v1",
        "symbol": config.symbol,
        "provider_id": config.provider_id,
        "profile_id": config.profile_id,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "contract": _contract(entry_side, close_side),
        "control": control,
        "challenger": challenger,
    }


def _one_sided_contract(config: Hip3ShadowLifecycleConfig) -> tuple[str, str]:
    if len(config.entry_sides) != 1:
        raise ValueError("close-only comparison requires exactly one entry side")
    entry_side = next(iter(config.entry_sides))
    close_side = "long" if entry_side == "short" else "short"
    return entry_side, close_side


def _contract(entry_side: str, close_side: str) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "entry_sides": [entry_side],
        "close_only_sides": [close_side],
    }
