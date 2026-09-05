"""Shared fixed-risk evaluation and attribution for causal asset screens."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from hypervector.research.causal_screen_inputs import (
    load_causal_bar_window,
    resample_complete_execution_bars,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_attribution import trade_attribution
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)

SignalBuilder = Callable[[pd.DataFrame], pd.DataFrame]
ConfigBuilder = Callable[["FrictionProfile"], SharedPortfolioConfig]


@dataclass(frozen=True)
class FrictionProfile:
    """One predeclared all-taker fee and slippage assumption."""

    name: str
    slippage_bps: float


DEFAULT_PROFILES = (
    FrictionProfile("nominal_14bps_rt", 2.5),
    FrictionProfile("stress_20bps_rt", 5.5),
)


def add_fixed_risk_screen_arguments(parser: argparse.ArgumentParser) -> None:
    """Add exact source, chronology, and immutable-output arguments."""
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument(
        "--bars-timeframe",
        choices=("1min", "15min"),
        default="1min",
    )
    parser.add_argument("--score-start", type=utc_datetime)
    parser.add_argument("--funding", required=True, type=Path, action="append")
    parser.add_argument("--start", required=True, type=utc_datetime)
    parser.add_argument("--end", required=True, type=utc_datetime)
    parser.add_argument("--output", required=True, type=Path)


def build_fixed_risk_screen_report(
    *,
    symbol: str,
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    bars_timeframe: str,
    score_start: datetime | None,
    signal_builder: SignalBuilder,
    config_builder: ConfigBuilder,
    mode: str,
    hypothesis_id: str,
    limitations: tuple[str, ...],
) -> dict[str, object]:
    """Build one exact-window report with shared causal and risk semantics."""
    source_bars, evidence = load_causal_bar_window(
        bars_path,
        funding_paths,
        start,
        end,
        bar_timeframe=bars_timeframe,
    )
    bars = (
        source_bars
        if bars_timeframe == "15min"
        else resample_complete_execution_bars(source_bars, "15min")
    )
    scored_start = score_start or start
    if not start <= scored_start < end:
        raise ValueError("score start must fall inside the source window")
    return {
        "schema_version": 1,
        "mode": mode,
        "hypothesis_id": hypothesis_id,
        "source_start_utc": start.isoformat(),
        "start_utc": scored_start.isoformat(),
        "end_exclusive_utc": end.isoformat(),
        "execution_timeframe": "15min",
        "execution_authority": "none",
        "automatic_live_change": False,
        "data_evidence": evidence,
        "asset": evaluate_asset_profiles(
            symbol=symbol,
            bars=bars,
            signal_builder=signal_builder,
            config_builder=config_builder,
            score_start=scored_start,
        ),
        "limitations": list(limitations),
    }


def utc_datetime(value: str) -> datetime:
    """Parse an explicitly UTC ISO-8601 command-line timestamp."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def fixed_risk_portfolio_config(
    *,
    symbol: str,
    venue_max_leverage: float,
    friction: FrictionProfile,
    margin_fraction: float,
) -> SharedPortfolioConfig:
    """Return the shared all-taker, structural-stop, fixed-risk contract."""
    return SharedPortfolioConfig(
        symbol=symbol,
        initial_equity=5_000.0,
        margin_fraction=margin_fraction,
        leverage=5.0,
        venue_max_leverage=venue_max_leverage,
        maximum_notional_usd=5_000.0,
        risk_fraction_per_position=0.0075,
        minimum_stop_distance_bps=20.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=friction.slippage_bps,
        market_exit_slippage_bps=friction.slippage_bps,
        max_hold_seconds=2_592_000,
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=True,
    )


def evaluate_asset_profiles(
    *,
    symbol: str,
    bars: pd.DataFrame,
    signal_builder: SignalBuilder,
    config_builder: ConfigBuilder,
    score_start: datetime | None = None,
) -> dict[str, object]:
    """Evaluate one frozen signal under both shared friction profiles."""
    signals = signal_builder(bars)
    scored_bars, scored_signals = scored_inputs(bars, signals, score_start)
    profiles = [
        _profile_report(
            profile,
            evaluate_shared_bar_portfolio(
                scored_bars,
                scored_signals,
                config_builder(profile),
            ),
        )
        for profile in DEFAULT_PROFILES
    ]
    return {
        "symbol": symbol,
        "signal_counts": {
            "long": int(scored_signals["long_entry"].sum()),
            "short": int(scored_signals["short_entry"].sum()),
        },
        "profiles": profiles,
        "supported_in_partition": all(_profile_supported(row) for row in profiles),
    }


def scored_inputs(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    score_start: datetime | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Slice precomputed causal signals without scoring warmup observations."""
    if not bars.index.equals(signals.index):
        raise ValueError("bars and signals must have identical timestamps")
    if score_start is None:
        return bars, signals
    selected = bars.index >= pd.Timestamp(score_start)
    if not selected.any():
        raise ValueError("score start leaves no execution bars")
    return bars.loc[selected], signals.loc[selected]


def _profile_report(
    profile: FrictionProfile,
    report: SharedPortfolioReport,
) -> dict[str, object]:
    metrics = report.to_dict()
    attribution = trade_attribution(report.trades)
    largest = max(
        float(attribution[side]["largest_winner_usd"] or 0.0)
        for side in ("long", "short")
    )
    keep = (
        "net_pnl_usd",
        "profit_factor",
        "maximum_drawdown_pct",
        "completed_trades",
        "wins",
        "losses",
        "liquidations",
        "total_fees_usd",
        "funding_cashflow_usd",
        "insolvent",
        "monthly_net_pnl_usd",
    )
    selected = {key: metrics[key] for key in keep}
    selected["largest_winner_usd"] = largest or None
    selected["net_excluding_largest_winner_usd"] = report.net_pnl_usd - largest
    return {
        "friction": asdict(profile),
        "metrics": selected,
        "attribution": attribution,
    }


def _profile_supported(row: dict[str, object]) -> bool:
    metrics = row["metrics"]
    if not isinstance(metrics, dict):
        raise TypeError("fixed-risk profile metrics must be a mapping")
    profit_factor = metrics["profit_factor"]
    return bool(
        metrics["completed_trades"]
        and metrics["net_pnl_usd"] > 0.0
        and profit_factor is not None
        and profit_factor > 1.0
        and metrics["net_excluding_largest_winner_usd"] > 0.0
        and metrics["liquidations"] == 0
        and not metrics["insolvent"]
    )
