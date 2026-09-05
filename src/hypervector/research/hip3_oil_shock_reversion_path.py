"""Lifecycle-path evidence for public-trade oil shock decisions."""

from __future__ import annotations

import pandas as pd

from hypervector.research.mu_hip3_archive_reporting import (
    partition_trade_path_quality,
)
from hypervector.research.mu_hip3_candidate import MuPartitionResult


def oil_partition_trade_path_quality(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
) -> dict[str, object]:
    """Require exact mark and executable-quote paths without L2 decisions."""
    quality = partition_trade_path_quality(
        bars,
        partition,
        timeframe="5m",
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
