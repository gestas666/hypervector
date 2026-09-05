"""Argument contract for the authority-none V58 continuous consolidator."""

from __future__ import annotations

import argparse
from pathlib import Path

_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_OBSERVER = Path("data/runtime/research/v58_eight_asset_observer_latest.json")
_LIVE_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_VENUE_PREFLIGHT = Path("data/runtime/research/v58_current_venue_preflight_latest.json")
_BTC = Path("data/runtime/research/v58_btc_sweep_lifecycle_latest.json")
_ETH = Path("data/runtime/research/v58_eth_pullback_first_lifecycle_latest.json")
_HYPE = Path("data/runtime/research/v58_hype_alignment_shadow_lifecycle_latest.json")
_SP500 = Path("data/runtime/research/v58_sp500_fresh15_first_lifecycle_latest.json")
_BRENTOIL = Path("data/runtime/research/v58_brentoil_live_lifecycle_latest.json")
_ACTIVE_ROUTE_OVERRIDES = Path(
    "configs/research/v58_active_route_lifecycle_collectors.json"
)
_SP500_RECOVERY = Path(
    "data/logs/research/v58_sp500_fresh15_outage_gap_recovery_20260819_v2.json"
)
_SP500_RECOVERY_JOURNAL = Path(
    "docs/research-journal/"
    "v58-sp500-outage-mark-gap-recovery-disposition-20260819-v2.json"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)
_ETH_EXIT_JOURNAL = Path(
    "docs/research-journal/eth-breakout-precompression-pullback-v5.json"
)
_ETH_EXIT_DURATION = Path(
    "data/logs/research/bidirectional_cohort/"
    "eth_pullback_mechanism_duration_20260809T203358Z.json"
)
_ETH_RISK_LOCK_DISPOSITION = Path(
    "docs/research-journal/"
    "v58-eth-risk-normalized-profit-lock-historical-disposition-20260819-v1.json"
)
_ETH_DURATION_CHECKPOINT = Path(
    "data/logs/research/v58_eth_duration_checkpoint_20260820T045524Z_v1.json"
)
_ETH_HISTORICAL_FUNDING_STRESS = Path(
    "data/logs/research/v58_eth_historical_funding_stress_20260820_v2.json"
)
_BTC_LONG_COVERAGE_RESULT = Path(
    "docs/research-journal/"
    "v58-btc-trend-pullback-reacceleration-result-20260821-v1.json"
)
_OUTPUT = Path("data/runtime/research/v58_continuous_improvement_latest.json")


def build_v58_continuous_parser(description: str) -> argparse.ArgumentParser:
    """Return the execution-incapable V58 consolidation parser."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--observer", type=Path, default=_OBSERVER)
    parser.add_argument("--live-checkpoint", type=Path, default=_LIVE_CHECKPOINT)
    parser.add_argument("--venue-preflight", type=Path, default=_VENUE_PREFLIGHT)
    parser.add_argument("--btc", type=Path, default=_BTC)
    parser.add_argument("--eth", type=Path, default=_ETH)
    parser.add_argument("--hype", type=Path, default=_HYPE)
    parser.add_argument("--sp500", type=Path, default=_SP500)
    parser.add_argument("--brentoil", type=Path, default=_BRENTOIL)
    parser.add_argument(
        "--active-route-overrides", type=Path, default=_ACTIVE_ROUTE_OVERRIDES
    )
    parser.add_argument("--sp500-recovery", type=Path, default=_SP500_RECOVERY)
    parser.add_argument(
        "--sp500-recovery-journal", type=Path, default=_SP500_RECOVERY_JOURNAL
    )
    parser.add_argument("--stress", type=Path, default=_STRESS)
    parser.add_argument("--eth-exit-journal", type=Path, default=_ETH_EXIT_JOURNAL)
    parser.add_argument("--eth-exit-duration", type=Path, default=_ETH_EXIT_DURATION)
    parser.add_argument(
        "--eth-risk-lock-disposition", type=Path, default=_ETH_RISK_LOCK_DISPOSITION
    )
    parser.add_argument(
        "--eth-duration-checkpoint", type=Path, default=_ETH_DURATION_CHECKPOINT
    )
    parser.add_argument(
        "--eth-historical-funding-stress",
        type=Path,
        default=_ETH_HISTORICAL_FUNDING_STRESS,
    )
    parser.add_argument(
        "--btc-long-coverage-result",
        type=Path,
        default=_BTC_LONG_COVERAGE_RESULT,
    )
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    parser.add_argument("--maximum-age-seconds", type=float, default=180.0)
    parser.add_argument("--interval-seconds", type=float, default=120.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    return parser
