"""V82 fixed two-reward-to-one-risk ZEC challenger."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from hypervector.research.fixed_risk_signal_screen import FrictionProfile
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.zec_native15_transfer_screen import (
    portfolio_config as base_portfolio_config,
)
from hypervector.research.zec_native15_transfer_screen import (
    run_managed_transfer_partition,
)

HYPOTHESIS_ID = "v82-zec-two-r-managed-challenger-20260903"

_CANDIDATE_IDS = (
    "zero_lag_reclaim_long",
    "zero_lag_reclaim_short",
    "regime_trend_router_long",
)


def candidate_ids() -> tuple[str, ...]:
    """Return the exact V81 development-derived candidate subset."""
    return _CANDIDATE_IDS


def portfolio_config(profile: FrictionProfile) -> SharedPortfolioConfig:
    """Add the single preregistered 120-bps target to the V81 risk contract."""
    return replace(base_portfolio_config(profile), target_margin_pct=6.0)


def run_partition_screen(
    *,
    bars_path: Path,
    funding_paths: list[Path],
    source_start: datetime,
    score_start: datetime,
    end: datetime,
    partition: str,
) -> dict[str, object]:
    """Evaluate one V82 partition without granting execution authority."""
    return run_managed_transfer_partition(
        bars_path=bars_path,
        funding_paths=funding_paths,
        source_start=source_start,
        score_start=score_start,
        end=end,
        partition=partition,
        candidate_ids=candidate_ids(),
        config_builder=portfolio_config,
        hypothesis_id=HYPOTHESIS_ID,
        mode="v82_zec_two_r_managed_challenger_report_only",
    )
