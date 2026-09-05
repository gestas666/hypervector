"""Lifecycle-path evidence for public-trade Krown decisions."""

from __future__ import annotations

import pandas as pd

from hypervector.research.mu_hip3_archive_reporting import (
    partition_trade_path_quality,
)
from hypervector.research.mu_hip3_candidate import MuPartitionResult


def krown_partition_trade_path_quality(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
) -> dict[str, object]:
    """Require exact marks and quotes without inventing an L2 decision role."""
    quality = partition_trade_path_quality(
        bars,
        partition,
        timeframe="15m",
        family="swing_ha",
    )
    return {
        "status": quality["status"],
        "decision_source": "0xarchive_public_trade_ohlc_v1",
        "decision_l2_required": False,
        "entry_exit_l2_required": True,
        "risk_path_required": True,
        "adapter_basis": "price_only_family_path_without_pressure_decision_role",
        "nominal": quality["nominal"],
        "stress": quality["stress"],
    }
