"""Descriptive failure attribution for the rejected BTC pullback route."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from statistics import mean, median

import pandas as pd


_PARTITIONS = frozenset(("development", "validation", "pseudo_holdout"))
_OUTCOMES = frozenset(("stop", "target"))
_MFE_THRESHOLDS_BPS = (20.0, 40.0)
_MINUTE = pd.Timedelta(minutes=1)
_SIGNAL_NAME = "btc_trend_pullback_reacceleration_long_v1"
_TRADE_COLUMNS = frozenset(
    {
        "arm",
        "direction",
        "entry_price",
        "entry_time_utc",
        "exit_reason",
        "exit_time_utc",
        "fees_usd",
        "funding_cashflow_usd",
        "gross_pnl_usd",
        "net_pnl_usd",
        "partition",
        "scenario",
        "scope",
        "signal_name",
        "signal_time_utc",
    }
)
_DIAGNOSTIC_COLUMNS = frozenset(
    {
        "close",
        "ema21",
        "ema55",
        "long_entry",
        "low",
        "prior_local_high",
        "pullback_armed",
    }
)


@dataclass(frozen=True)
class BtcTrendPullbackFailureObservation:
    """One completed candidate trade with causal entry and path diagnostics."""

    partition: str
    outcome: str
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    holding_hours: float
    ema_gap_bps: float
    close_above_ema21_bps: float
    breakout_excess_bps: float
    pullback_age_bars: int
    pullback_depth_bps: float
    maximum_favorable_excursion_bps: float
    maximum_adverse_excursion_bps: float
    forward_return_15m_bps: float
    forward_return_60m_bps: float
    forward_return_240m_bps: float

    def __post_init__(self) -> None:
        """Reject identity drift or non-finite descriptive measurements."""
        if self.partition not in _PARTITIONS or self.outcome not in _OUTCOMES:
            raise ValueError("BTC failure observation identity is invalid")
        if self.pullback_age_bars < 0:
            raise ValueError("BTC failure pullback age must be nonnegative")
        numeric = tuple(
            value
            for key, value in asdict(self).items()
            if key not in {"partition", "outcome", "pullback_age_bars"}
        )
        if any(
            not isinstance(value, (int, float)) or not isfinite(value)
            for value in numeric
        ):
            raise ValueError("BTC failure measurements must be finite")


def attribute_btc_trend_pullback_failures(
    minute_bars: pd.DataFrame,
    diagnostics_15m: pd.DataFrame,
    trade_sidecar: pd.DataFrame,
) -> tuple[BtcTrendPullbackFailureObservation, ...]:
    """Join frozen standalone trades to causal signal and exact path evidence."""
    bars = _validated_frame(minute_bars, frozenset({"close", "high", "low"}), "bars")
    diagnostics = _validated_frame(diagnostics_15m, _DIAGNOSTIC_COLUMNS, "diagnostics")
    trades = _selected_trades(trade_sidecar)
    return tuple(
        _attribute_trade(bars, diagnostics, row) for _, row in trades.iterrows()
    )


def _validated_frame(
    frame: pd.DataFrame, required: frozenset[str], label: str
) -> pd.DataFrame:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"BTC failure {label} missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"BTC failure {label} require an aware DatetimeIndex")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError(f"BTC failure {label} timestamps must be unique and ordered")
    return frame


def _selected_trades(trades: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_TRADE_COLUMNS.difference(trades.columns))
    if missing:
        raise ValueError(f"BTC failure trades missing columns: {missing}")
    selected = trades.loc[
        trades["arm"].eq("candidate")
        & trades["scenario"].eq("nominal")
        & trades["scope"].isna()
    ].copy()
    if selected.empty:
        raise ValueError("BTC failure standalone nominal candidate trades are empty")
    if not selected["partition"].isin(_PARTITIONS).all():
        raise ValueError("BTC failure trade partition drifted")
    if not selected["exit_reason"].isin(_OUTCOMES).all():
        raise ValueError("BTC failure trade exit reason drifted")
    if not selected["direction"].eq("long").all():
        raise ValueError("BTC failure trade direction drifted")
    if not selected["signal_name"].eq(_SIGNAL_NAME).all():
        raise ValueError("BTC failure trade signal identity drifted")
    return selected


def _attribute_trade(
    bars: pd.DataFrame, diagnostics: pd.DataFrame, row: pd.Series
) -> BtcTrendPullbackFailureObservation:
    signal, entry, exit_time = _trade_times(row)
    age, depth, ema_gap, above_ema, excess = _entry_features(diagnostics, signal)
    holding, mfe, mae, forward = _path_features(
        bars, entry, exit_time, _finite_value(row, "entry_price")
    )
    gross = _finite_value(row, "gross_pnl_usd")
    fees = _finite_value(row, "fees_usd")
    funding = _finite_value(row, "funding_cashflow_usd")
    net = _finite_value(row, "net_pnl_usd")
    if abs((gross - fees + funding) - net) > 1e-8:
        raise ValueError("BTC failure trade economics do not reconcile")
    return BtcTrendPullbackFailureObservation(
        partition=str(row["partition"]),
        outcome=str(row["exit_reason"]),
        gross_pnl_usd=gross,
        fees_usd=fees,
        funding_cashflow_usd=funding,
        net_pnl_usd=net,
        holding_hours=holding,
        ema_gap_bps=ema_gap,
        close_above_ema21_bps=above_ema,
        breakout_excess_bps=excess,
        pullback_age_bars=age,
        pullback_depth_bps=depth,
        maximum_favorable_excursion_bps=mfe,
        maximum_adverse_excursion_bps=mae,
        forward_return_15m_bps=forward[0],
        forward_return_60m_bps=forward[1],
        forward_return_240m_bps=forward[2],
    )


def _trade_times(row: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    signal = _aware_timestamp(row, "signal_time_utc")
    entry = _aware_timestamp(row, "entry_time_utc")
    exit_time = _aware_timestamp(row, "exit_time_utc")
    if signal.floor("15min") + pd.Timedelta(minutes=14) != signal:
        raise ValueError(
            "BTC failure signal is not a completed fifteen-minute endpoint"
        )
    if entry != signal + _MINUTE or exit_time < entry:
        raise ValueError("BTC failure trade timing is inconsistent")
    return signal, entry, exit_time


def _entry_features(
    diagnostics: pd.DataFrame, signal: pd.Timestamp
) -> tuple[int, float, float, float, float]:
    decision = signal.floor("15min")
    if decision not in diagnostics.index:
        raise ValueError("BTC failure signal diagnostic is absent")
    position = diagnostics.index.get_loc(decision)
    if not isinstance(position, int) or not bool(
        diagnostics.iloc[position]["long_entry"]
    ):
        raise ValueError("BTC failure signal diagnostic is not a long entry")
    start = max(0, position - 8)
    prior = diagnostics.iloc[start : position + 1]
    armed = prior.index[prior["pullback_armed"].astype(bool)]
    if armed.empty:
        raise ValueError("BTC failure signal has no causal pullback arm")
    arm_position = diagnostics.index.get_loc(armed[-1])
    if not isinstance(arm_position, int):
        raise ValueError("BTC failure pullback identity is ambiguous")
    arm = diagnostics.iloc[arm_position]
    signal_row = diagnostics.iloc[position]
    return (
        position - arm_position,
        _ratio_bps(arm["low"], arm["ema21"]),
        _ratio_bps(signal_row["ema21"], signal_row["ema55"]),
        _ratio_bps(signal_row["close"], signal_row["ema21"]),
        _ratio_bps(signal_row["close"], signal_row["prior_local_high"]),
    )


def _path_features(
    bars: pd.DataFrame,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
) -> tuple[float, float, float, tuple[float, float, float]]:
    expected = pd.date_range(entry, exit_time, freq="1min")
    path = bars.loc[entry:exit_time]
    if not path.index.equals(expected):
        raise ValueError("BTC failure actual-exit path lacks minute coverage")
    horizon_minutes = (15, 60, 240)
    horizon_times = tuple(
        entry + pd.Timedelta(minutes=value) for value in horizon_minutes
    )
    if any(timestamp not in bars.index for timestamp in horizon_times):
        raise ValueError("BTC failure fixed horizon lacks minute coverage")
    forward = tuple(
        _ratio_bps(bars.loc[timestamp, "close"], entry_price)
        for timestamp in horizon_times
    )
    mfe = max(0.0, _ratio_bps(path["high"].max(), entry_price))
    mae = max(0.0, -_ratio_bps(path["low"].min(), entry_price))
    return (exit_time - entry).total_seconds() / 3600.0, mfe, mae, forward


def _aware_timestamp(row: pd.Series, field: str) -> pd.Timestamp:
    value = pd.Timestamp(row[field])
    if value.tzinfo is None:
        raise ValueError(f"BTC failure {field} must be timezone-aware")
    return value.tz_convert("UTC")


def _finite_value(row: pd.Series, field: str) -> float:
    value = float(row[field])
    if not isfinite(value):
        raise ValueError(f"BTC failure {field} must be finite")
    return value


def _ratio_bps(numerator: object, denominator: object) -> float:
    first, second = float(numerator), float(denominator)
    if not isfinite(first) or not isfinite(second) or second <= 0.0:
        raise ValueError("BTC failure ratio inputs must be finite and positive")
    return (first / second - 1.0) * 10_000.0


def build_btc_trend_pullback_failure_report(
    observations: Sequence[BtcTrendPullbackFailureObservation],
) -> dict[str, object]:
    """Summarize entry edge, cost drag, path timing, and extension proxies."""
    rows = tuple(observations)
    winners = tuple(row for row in rows if row.outcome == "target")
    losers = tuple(row for row in rows if row.outcome == "stop")
    if not rows or not winners or not losers:
        raise ValueError("BTC failure attribution requires target and stop outcomes")
    economics = _economics(rows, winners, losers)
    by_outcome = {
        "stop": _group_summary(losers),
        "target": _group_summary(winners),
    }
    return {
        "schema_version": "v58_btc_trend_pullback_failure_attribution_v1",
        "status": "complete_posthoc_descriptive",
        "authority": _authority(),
        "economics": economics,
        "by_outcome": by_outcome,
        "by_partition": _partition_summaries(rows),
        "stop_path": _stop_path(losers),
        "diagnosis": _diagnosis(economics, by_outcome),
        "limitations": _limitations(),
    }


def _economics(
    rows: tuple[BtcTrendPullbackFailureObservation, ...],
    winners: tuple[BtcTrendPullbackFailureObservation, ...],
    losers: tuple[BtcTrendPullbackFailureObservation, ...],
) -> dict[str, object]:
    mean_win = mean(row.net_pnl_usd for row in winners)
    mean_loss = mean(row.net_pnl_usd for row in losers)
    if mean_win <= 0.0 or mean_loss >= 0.0:
        raise ValueError("BTC failure outcome economics are inconsistent")
    break_even = abs(mean_loss) / (mean_win + abs(mean_loss))
    return {
        "completed_trades": len(rows),
        "wins": len(winners),
        "losses": len(losers),
        "gross_pnl_usd": sum(row.gross_pnl_usd for row in rows),
        "fees_usd": sum(row.fees_usd for row in rows),
        "funding_cashflow_usd": sum(row.funding_cashflow_usd for row in rows),
        "net_pnl_usd": sum(row.net_pnl_usd for row in rows),
        "mean_net_win_usd": mean_win,
        "mean_net_loss_usd": mean_loss,
        "actual_win_rate": len(winners) / len(rows),
        "after_cost_break_even_win_rate": break_even,
    }


def _group_summary(
    rows: tuple[BtcTrendPullbackFailureObservation, ...],
) -> dict[str, object]:
    return {
        "completed_trades": len(rows),
        "net_pnl_usd": sum(row.net_pnl_usd for row in rows),
        "mean_holding_hours": _mean(rows, "holding_hours"),
        "mean_ema_gap_bps": _mean(rows, "ema_gap_bps"),
        "mean_close_above_ema21_bps": _mean(rows, "close_above_ema21_bps"),
        "mean_breakout_excess_bps": _mean(rows, "breakout_excess_bps"),
        "mean_pullback_age_bars": _mean(rows, "pullback_age_bars"),
        "mean_pullback_depth_bps": _mean(rows, "pullback_depth_bps"),
        "mean_maximum_favorable_excursion_bps": _mean(
            rows, "maximum_favorable_excursion_bps"
        ),
        "mean_maximum_adverse_excursion_bps": _mean(
            rows, "maximum_adverse_excursion_bps"
        ),
        "mean_forward_return_15m_bps": _mean(rows, "forward_return_15m_bps"),
        "mean_forward_return_60m_bps": _mean(rows, "forward_return_60m_bps"),
        "mean_forward_return_240m_bps": _mean(rows, "forward_return_240m_bps"),
    }


def _partition_summaries(
    rows: tuple[BtcTrendPullbackFailureObservation, ...],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for partition in sorted({row.partition for row in rows}):
        selected = tuple(row for row in rows if row.partition == partition)
        output[partition] = {
            "all": _group_summary(selected),
            "stop": _group_summary(
                tuple(row for row in selected if row.outcome == "stop")
            ),
            "target": _group_summary(
                tuple(row for row in selected if row.outcome == "target")
            ),
        }
    return output


def _stop_path(
    rows: tuple[BtcTrendPullbackFailureObservation, ...],
) -> dict[str, object]:
    favorable = tuple(row.maximum_favorable_excursion_bps for row in rows)
    return {
        "stops": len(rows),
        "reached_20bps_mfe_before_exit": sum(
            value >= _MFE_THRESHOLDS_BPS[0] for value in favorable
        ),
        "reached_40bps_mfe_before_exit": sum(
            value >= _MFE_THRESHOLDS_BPS[1] for value in favorable
        ),
        "median_maximum_favorable_excursion_bps": median(favorable),
        "median_maximum_adverse_excursion_bps": median(
            row.maximum_adverse_excursion_bps for row in rows
        ),
    }


def _diagnosis(
    economics: dict[str, object], by_outcome: dict[str, dict[str, object]]
) -> dict[str, object]:
    stopped = by_outcome["stop"]
    target = by_outcome["target"]
    return {
        "costs_only_diagnosis_falsified": float(economics["gross_pnl_usd"]) < 0.0,
        "realized_payoff_requirement_failed": (
            float(economics["actual_win_rate"])
            < float(economics["after_cost_break_even_win_rate"])
        ),
        "stopped_entries_adverse_at_15m_and_60m": (
            float(stopped["mean_forward_return_15m_bps"]) < 0.0
            and float(stopped["mean_forward_return_60m_bps"]) < 0.0
        ),
        "stops_more_hourly_extended_than_targets": (
            float(stopped["mean_ema_gap_bps"]) > float(target["mean_ema_gap_bps"])
        ),
        "candidate_remains_rejected": True,
        "subgroup_selection_supported": False,
        "retuning_supported": False,
        "live_change_supported": False,
    }


def _mean(rows: tuple[BtcTrendPullbackFailureObservation, ...], field: str) -> float:
    if not rows:
        raise ValueError("BTC failure attribution subgroup is empty")
    return mean(float(getattr(row, field)) for row in rows)


def _authority() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "live_configuration_changed": False,
        "automatic_promotion": False,
        "retuning_authorized": False,
        "subgroup_selection_authorized": False,
    }


def _limitations() -> list[str]:
    return [
        "economics and preliminary attribution were opened before this contract",
        "outcome groups are descriptive and cannot validate a discovered filter",
        "fixed-horizon returns may extend beyond an earlier modeled exit",
        "one-minute bars do not establish exact mark or BBO ordering",
    ]
