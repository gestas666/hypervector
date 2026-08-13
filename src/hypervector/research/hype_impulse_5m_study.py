"""Chronological report-only study for the corrected HYPE five-minute impulse fade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from hypervector.research.hype_impulse_5m_candidate import (
    HypeImpulseConfig,
    HypeImpulseReplay,
    build_impulse_signals,
    maximum_hold_bars,
    replay_impulse_signals,
)
from hypervector.research.hype_impulse_5m_signals import validate_five_minute_bars

PartitionName = Literal["development", "validation", "holdout"]


@dataclass(frozen=True)
class StudyWindow:
    """One half-open chronological study partition."""

    name: PartitionName
    start_position: int
    end_position: int
    start: pd.Timestamp
    end: pd.Timestamp


def chronological_windows(bars: pd.DataFrame) -> tuple[StudyWindow, ...]:
    """Create fixed positional 60/20/20 partitions on one canonical bar set."""
    frame = validate_five_minute_bars(bars)
    if len(frame) < 5:
        raise ValueError("HYPE impulse study requires at least five completed bars")
    development_end = int(len(frame) * 0.6)
    validation_end = int(len(frame) * 0.8)
    positions = (
        ("development", 0, development_end),
        ("validation", development_end, validation_end),
        ("holdout", validation_end, len(frame)),
    )
    return tuple(_window(frame, name, start, end) for name, start, end in positions)


def summarize_replay(replay: HypeImpulseReplay) -> dict[str, object]:
    """Summarize after-cost lifecycle economics without a promotion gate."""
    values = [trade.net_bps for trade in replay.trades]
    wins = [value for value in values if value > 0]
    losses = [-value for value in values if value < 0]
    return {
        "boundary_censored": replay.boundary_censored,
        "breakeven": sum(value == 0 for value in values),
        "candidate_signals": replay.candidate_signals,
        "closed_trades": len(values),
        "fees_and_slippage_bps": sum(trade.cost_bps for trade in replay.trades),
        "funding_bps": sum(trade.funding_bps for trade in replay.trades),
        "gap_censored": replay.gap_censored,
        "gross_bps": sum(trade.gross_bps for trade in replay.trades),
        "losses": len(losses),
        "maximum_closed_sequence_drawdown_bps": _maximum_drawdown(values),
        "mean_net_bps": sum(values) / len(values) if values else None,
        "median_net_bps": _median(values),
        "net_bps": sum(values),
        "net_bps_excluding_largest_winner": sum(values) - max(wins) if wins else None,
        "profit_factor": sum(wins) / sum(losses) if losses else None,
        "wins": len(wins),
    }


def build_study_report(
    bars: pd.DataFrame,
    funding_rates: pd.Series,
    *,
    nominal_cost_bps: float,
    stress_cost_bps: float,
) -> dict[str, object]:
    """Evaluate frozen temporal interpretations without selecting or promoting one."""
    _validate_costs(nominal_cost_bps, stress_cost_bps)
    frame = validate_five_minute_bars(bars)
    windows = chronological_windows(frame)
    variants = {
        "corrected_23m": HypeImpulseConfig(maximum_hold_minutes=23),
        "legacy_behavior_115m": HypeImpulseConfig(maximum_hold_minutes=115),
    }
    return {
        "contract": _report_contract(),
        "friction_bps": {"nominal": nominal_cost_bps, "stress": stress_cost_bps},
        "mode": "hype_impulse_5m_corrected_chronological_study_v1",
        "partitions": [_window_payload(window) for window in windows],
        "schema_version": 1,
        "variants": {
            name: _variant_report(
                frame, funding_rates, config, windows, nominal_cost_bps, stress_cost_bps
            )
            for name, config in variants.items()
        },
    }


def _variant_report(
    bars: pd.DataFrame,
    funding: pd.Series,
    config: HypeImpulseConfig,
    windows: tuple[StudyWindow, ...],
    nominal_cost: float,
    stress_cost: float,
) -> dict[str, object]:
    return {
        "maximum_hold_bars": maximum_hold_bars(config),
        "maximum_hold_minutes": config.maximum_hold_minutes,
        "sides": {
            side: _side_report(
                bars, funding, config, windows, side, nominal_cost, stress_cost
            )
            for side in ("long", "short")
        },
    }


def _side_report(
    bars: pd.DataFrame,
    funding: pd.Series,
    config: HypeImpulseConfig,
    windows: tuple[StudyWindow, ...],
    side: Literal["long", "short"],
    nominal_cost: float,
    stress_cost: float,
) -> dict[str, object]:
    signals, atr_bps = build_impulse_signals(bars, config=config, side=side)
    return {
        window.name: {
            "nominal": summarize_replay(
                _replay(
                    bars, signals, atr_bps, funding, config, side, nominal_cost, window
                )
            ),
            "stress": summarize_replay(
                _replay(
                    bars, signals, atr_bps, funding, config, side, stress_cost, window
                )
            ),
        }
        for window in windows
    }


def _replay(
    bars: pd.DataFrame,
    signals: pd.Series,
    atr_bps: pd.Series,
    funding: pd.Series,
    config: HypeImpulseConfig,
    side: Literal["long", "short"],
    cost: float,
    window: StudyWindow,
) -> HypeImpulseReplay:
    return replay_impulse_signals(
        bars,
        signals,
        atr_bps,
        funding,
        config=config,
        side=side,
        round_trip_cost_bps=cost,
        partition_start=window.start,
        partition_end=window.end,
    )


def _window(
    bars: pd.DataFrame,
    name: PartitionName,
    start: int,
    end: int,
) -> StudyWindow:
    if start >= end:
        raise ValueError(f"HYPE impulse {name} partition is empty")
    return StudyWindow(
        name=name,
        start_position=start,
        end_position=end,
        start=pd.Timestamp(bars.iloc[start]["timestamp"]),
        end=pd.Timestamp(bars.iloc[end - 1]["timestamp"]) + pd.Timedelta(minutes=5),
    )


def _window_payload(window: StudyWindow) -> dict[str, object]:
    return {
        "end": window.end.isoformat(),
        "end_position": window.end_position,
        "name": window.name,
        "start": window.start.isoformat(),
        "start_position": window.start_position,
    }


def _report_contract() -> dict[str, object]:
    return {
        "automatic_promotion": False,
        "execution_authority": "none",
        "performance_gate": False,
        "report_only": True,
        "runtime_strategy_changed": False,
    }


def _validate_costs(nominal: float, stress: float) -> None:
    if nominal < 0 or stress < 0:
        raise ValueError("HYPE impulse friction costs must be nonnegative")
    if stress < nominal:
        raise ValueError("HYPE impulse stress cost must not be cheaper than nominal")


def _maximum_drawdown(values: list[float]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
