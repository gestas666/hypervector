"""Causal event construction for cross-asset impulse propagation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseEvent,
    CrossAssetImpulseLabel,
    ImpulseAnchor,
    ImpulseDirection,
    ImpulseLabelStatus,
    ImpulseSignalVariant,
    declared_impulse_folds,
    declared_impulse_variants,
)

_BASE_STATE_COLUMNS = {
    "bar_open_at",
    "decision_time_utc",
    "leader_zscore",
    "follower_zscore",
    "catchup_gap_z",
    "lagged_leader_zscore",
    "lagged_catchup_gap_z",
    "lagged_leader_valid_returns",
    "leader_valid_returns",
    "follower_valid_returns",
}
_LABEL_COLUMNS = {"timestamp", "open", "source"}
_ALLOWED_SOURCES = {"hl", "hl_gap_fill"}


@dataclass(frozen=True)
class _SymbolState:
    returns: pd.Series
    return_valid: pd.Series
    valid_count: pd.Series
    volatility: pd.Series
    zscore: pd.Series


def build_impulse_states(
    leader_close: pd.Series,
    follower_close: pd.Series,
    config: CrossAssetImpulseConfig,
    *,
    leader_valid: pd.Series,
    follower_valid: pd.Series,
) -> pd.DataFrame:
    """Build append-invariant primary and control states from source masks."""
    leader, follower = _validated_close_pair(leader_close, follower_close)
    leader_mask = _validated_validity(leader_valid, leader.index, "leader")
    follower_mask = _validated_validity(follower_valid, follower.index, "follower")
    leader_state = _symbol_state(leader, leader_mask, config)
    follower_state = _symbol_state(follower, follower_mask, config)
    states = _base_state_frame(leader, leader_state, follower_state, config)
    return _with_variant_states(states, leader_state, follower_state, config)


def sample_impulse_events(
    states: pd.DataFrame,
    leader_symbol: str,
    follower_symbol: str,
    config: CrossAssetImpulseConfig,
    *,
    signal_variant: ImpulseSignalVariant = "primary",
) -> tuple[CrossAssetImpulseEvent, ...]:
    """Emit one variant's false-to-true onsets under its independent cooldown."""
    _validate_states(states, signal_variant)
    events: list[CrossAssetImpulseEvent] = []
    previous_qualifies = False
    next_eligible: pd.Timestamp | None = None
    qualifies_column = f"{signal_variant}_qualifies"
    for row in states.itertuples(index=False):
        decision = pd.Timestamp(getattr(row, "decision_time_utc"))
        bar_open = pd.Timestamp(getattr(row, "bar_open_at"))
        qualifies = bool(getattr(row, qualifies_column))
        onset = qualifies and not previous_qualifies
        inside = (
            config.development_start <= bar_open and decision < config.development_end
        )
        if onset and inside and (next_eligible is None or decision >= next_eligible):
            events.append(
                _event_from_row(
                    row,
                    leader_symbol,
                    follower_symbol,
                    signal_variant,
                )
            )
            next_eligible = decision + pd.Timedelta(minutes=config.cooldown_minutes)
        previous_qualifies = qualifies
    return tuple(events)


def label_impulse_events(
    events: tuple[CrossAssetImpulseEvent, ...],
    follower_bars: pd.DataFrame,
    config: CrossAssetImpulseConfig,
) -> tuple[CrossAssetImpulseLabel, ...]:
    """Label base and delayed anchors with exact path and boundary statuses."""
    bars = _validated_label_bars(follower_bars)
    labels = [
        _label_event(event, anchor, horizon, bars, config)
        for event in events
        for anchor in ("base", "delayed")
        for horizon in config.horizons_minutes
    ]
    return tuple(labels)


def _symbol_state(
    close: pd.Series,
    authentic: pd.Series,
    config: CrossAssetImpulseConfig,
) -> _SymbolState:
    width = config.impulse_return_minutes + 1
    return_valid = authentic.rolling(width, min_periods=width).sum().eq(width)
    returns = np.log(close).diff(config.impulse_return_minutes).where(return_valid)
    prior = returns.shift(1)
    valid_count = (
        prior.rolling(config.lookback_minutes, min_periods=1).count().astype(int)
    )
    volatility = prior.rolling(
        config.lookback_minutes,
        min_periods=config.minimum_valid_returns,
    ).std(ddof=1)
    full_window = pd.Series(
        np.arange(len(close)) >= config.lookback_minutes,
        index=close.index,
    )
    admitted = full_window & valid_count.ge(config.minimum_valid_returns)
    volatility = volatility.where(admitted)
    zscore = _finite_ratio(returns, volatility)
    return _SymbolState(returns, return_valid, valid_count, volatility, zscore)


def _base_state_frame(
    leader: pd.Series,
    leader_state: _SymbolState,
    follower_state: _SymbolState,
    config: CrossAssetImpulseConfig,
) -> pd.DataFrame:
    leader_sign = np.sign(leader_state.zscore)
    gap = leader_state.zscore.abs() - leader_sign * follower_state.zscore
    lagged_leader = leader_state.zscore.shift(config.placebo_lag_minutes)
    lagged_gap = lagged_leader.abs() - np.sign(lagged_leader) * follower_state.zscore
    return pd.DataFrame(
        {
            "bar_open_at": leader.index,
            "decision_time_utc": leader.index + pd.Timedelta(minutes=1),
            "leader_return": leader_state.returns.to_numpy(),
            "follower_return": follower_state.returns.to_numpy(),
            "leader_return_valid": leader_state.return_valid.to_numpy(bool),
            "follower_return_valid": follower_state.return_valid.to_numpy(bool),
            "leader_valid_returns": leader_state.valid_count.to_numpy(int),
            "follower_valid_returns": follower_state.valid_count.to_numpy(int),
            "leader_vol": leader_state.volatility.to_numpy(),
            "follower_vol": follower_state.volatility.to_numpy(),
            "leader_zscore": leader_state.zscore.to_numpy(),
            "follower_zscore": follower_state.zscore.to_numpy(),
            "catchup_gap_z": gap.to_numpy(),
            "lagged_leader_zscore": lagged_leader.to_numpy(),
            "lagged_catchup_gap_z": lagged_gap.to_numpy(),
            "lagged_leader_valid_returns": leader_state.valid_count.shift(
                config.placebo_lag_minutes
            ).to_numpy(),
        }
    )


def _with_variant_states(
    states: pd.DataFrame,
    leader: _SymbolState,
    follower: _SymbolState,
    config: CrossAssetImpulseConfig,
) -> pd.DataFrame:
    base_valid = (
        leader.return_valid
        & follower.return_valid
        & leader.zscore.notna()
        & follower.zscore.notna()
    ).to_numpy(bool)
    leader_direction = _directions(states["leader_zscore"])
    follower_direction = _directions(states["follower_zscore"])
    placebo_direction = _directions(states["lagged_leader_zscore"])
    qualifications = _variant_qualifications(states, base_valid, config)
    directions = {
        "primary": leader_direction,
        "leader_only_ablation": leader_direction,
        "follower_only_momentum": follower_direction,
        "lagged_leader_placebo": placebo_direction,
    }
    for variant in declared_impulse_variants():
        states[f"{variant}_qualifies"] = qualifications[variant]
        states[f"{variant}_direction"] = directions[variant]
    states["qualifies"] = states["primary_qualifies"]
    states["direction"] = states["primary_direction"]
    return states


def _variant_qualifications(
    states: pd.DataFrame,
    base_valid: np.ndarray,
    config: CrossAssetImpulseConfig,
) -> dict[ImpulseSignalVariant, pd.Series]:
    leader = states["leader_zscore"]
    follower = states["follower_zscore"]
    placebo = states["lagged_leader_zscore"]
    primary = (
        base_valid
        & leader.abs().ge(config.leader_z_threshold)
        & states["catchup_gap_z"].ge(config.catchup_gap_threshold)
    )
    return {
        "primary": primary.astype(bool),
        "leader_only_ablation": (
            base_valid & leader.abs().ge(config.leader_z_threshold)
        ).astype(bool),
        "follower_only_momentum": (
            base_valid & follower.abs().ge(config.leader_z_threshold)
        ).astype(bool),
        "lagged_leader_placebo": (
            base_valid
            & placebo.notna()
            & placebo.abs().ge(config.leader_z_threshold)
            & states["lagged_catchup_gap_z"].ge(config.catchup_gap_threshold)
        ).astype(bool),
    }


def _event_from_row(
    row: object,
    leader_symbol: str,
    follower_symbol: str,
    variant: ImpulseSignalVariant,
) -> CrossAssetImpulseEvent:
    direction = _row_direction(row, variant)
    placebo = variant == "lagged_leader_placebo"
    leader_z_field = "lagged_leader_zscore" if placebo else "leader_zscore"
    gap_field = "lagged_catchup_gap_z" if placebo else "catchup_gap_z"
    count_field = "lagged_leader_valid_returns" if placebo else "leader_valid_returns"
    decision = pd.Timestamp(getattr(row, "decision_time_utc"))
    return CrossAssetImpulseEvent(
        bar_open_at=pd.Timestamp(getattr(row, "bar_open_at")).isoformat(),
        decision_time_utc=decision.isoformat(),
        entry_time_utc=decision.isoformat(),
        leader_symbol=leader_symbol,
        follower_symbol=follower_symbol,
        signal_variant=variant,
        direction=direction,
        leader_zscore=float(getattr(row, leader_z_field)),
        follower_zscore=float(getattr(row, "follower_zscore")),
        catchup_gap_z=float(getattr(row, gap_field)),
        leader_valid_returns=int(getattr(row, count_field)),
        follower_valid_returns=int(getattr(row, "follower_valid_returns")),
    )


def _row_direction(row: object, variant: ImpulseSignalVariant) -> ImpulseDirection:
    value = str(getattr(row, f"{variant}_direction"))
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    raise ValueError(f"qualified {variant} state has invalid direction: {value}")


def _label_event(
    event: CrossAssetImpulseEvent,
    anchor: ImpulseAnchor,
    horizon: int,
    bars: pd.DataFrame,
    config: CrossAssetImpulseConfig,
) -> CrossAssetImpulseLabel:
    _validate_event_clock(event, config)
    delay = config.delayed_entry_minutes if anchor == "delayed" else 0
    entry = pd.Timestamp(event.entry_time_utc) + pd.Timedelta(minutes=delay)
    exit_time = entry + pd.Timedelta(minutes=horizon)
    status = _label_status(event, entry, exit_time, bars, config)
    entry_price, exit_price, gross = _label_values(
        event.direction,
        entry,
        exit_time,
        bars,
        status,
    )
    return CrossAssetImpulseLabel(
        bar_open_at=event.bar_open_at,
        decision_time_utc=event.decision_time_utc,
        entry_time_utc=entry.isoformat(),
        exit_time_utc=exit_time.isoformat(),
        leader_symbol=event.leader_symbol,
        follower_symbol=event.follower_symbol,
        signal_variant=event.signal_variant,
        anchor=anchor,
        direction=event.direction,
        horizon_minutes=horizon,
        entry_price=entry_price,
        exit_price=exit_price,
        directional_gross_return_bps=gross,
        status=status,
    )


def _label_status(
    event: CrossAssetImpulseEvent,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    bars: pd.DataFrame,
    config: CrossAssetImpulseConfig,
) -> ImpulseLabelStatus:
    decision = pd.Timestamp(event.decision_time_utc)
    if exit_time >= config.development_end:
        return "right_censored"
    fold_end = _decision_fold_end(decision, config)
    if exit_time >= fold_end:
        return "fold_boundary_purged"
    if entry not in bars.index or exit_time not in bars.index:
        return "right_censored"
    path = bars.loc[entry:exit_time, "source"]
    if len(path) != int((exit_time - entry).total_seconds() // 60) + 1:
        raise ValueError("follower label path is not contiguous")
    if not path.eq("hl").all():
        return "technical_gap"
    return "resolved"


def _label_values(
    direction: ImpulseDirection,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    bars: pd.DataFrame,
    status: ImpulseLabelStatus,
) -> tuple[float | None, float | None, float | None]:
    if status != "resolved":
        return None, None, None
    entry_price = float(bars.loc[entry, "open"])
    exit_price = float(bars.loc[exit_time, "open"])
    sign = 1.0 if direction == "long" else -1.0
    gross = sign * (exit_price / entry_price - 1.0) * 10_000.0
    return entry_price, exit_price, gross


def _decision_fold_end(
    decision: pd.Timestamp,
    config: CrossAssetImpulseConfig,
) -> pd.Timestamp:
    for _, start, end in declared_impulse_folds(config):
        if start <= decision < end:
            return end
    raise ValueError(f"impulse decision is outside development folds: {decision}")


def _validate_event_clock(
    event: CrossAssetImpulseEvent,
    config: CrossAssetImpulseConfig,
) -> None:
    bar_open = pd.Timestamp(event.bar_open_at)
    decision = pd.Timestamp(event.decision_time_utc)
    entry = pd.Timestamp(event.entry_time_utc)
    if bar_open.tz is None or decision.tz is None or entry.tz is None:
        raise ValueError("impulse event clock must be timezone-aware")
    if decision != bar_open + pd.Timedelta(minutes=1) or entry != decision:
        raise ValueError("impulse event clock violates bar/decision/entry identity")
    if not config.development_start <= decision < config.development_end:
        raise ValueError("impulse event decision is outside development window")


def _validated_label_bars(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_LABEL_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"follower bars missing columns: {missing}")
    timestamps = pd.DatetimeIndex(frame["timestamp"])
    if timestamps.empty or timestamps.tz is None:
        raise ValueError("follower bar timestamps must be timezone-aware")
    timestamps = timestamps.tz_convert("UTC")
    expected = pd.date_range(timestamps[0], periods=len(timestamps), freq="1min")
    if not timestamps.equals(expected):
        raise ValueError("follower bars must be contiguous one-minute bars")
    sources = frame["source"]
    unexpected = sorted(set(sources.dropna()).difference(_ALLOWED_SOURCES))
    if sources.isna().any() or unexpected:
        raise ValueError(f"follower bars contain unexpected source: {unexpected}")
    opens = pd.to_numeric(frame["open"], errors="raise").astype(float)
    if opens.empty or not np.isfinite(opens).all() or opens.le(0.0).any():
        raise ValueError("follower opens must be positive and finite")
    return pd.DataFrame(
        {"open": opens.to_numpy(), "source": sources.to_numpy(object)},
        index=timestamps,
    )


def _validated_close_pair(
    leader: pd.Series,
    follower: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    left = _validated_close(leader, "leader")
    right = _validated_close(follower, "follower")
    if not left.index.equals(right.index):
        raise ValueError("leader and follower close timestamps must match exactly")
    return left, right


def _validated_close(series: pd.Series, label: str) -> pd.Series:
    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(f"{label} close series cannot be empty")
    if series.index.tz is None:
        raise ValueError(f"{label} close index must be timezone-aware")
    index = series.index.tz_convert("UTC")
    expected = pd.date_range(index[0], periods=len(index), freq="1min")
    if not index.equals(expected):
        raise ValueError(f"{label} close timestamps must be contiguous one-minute bars")
    values = pd.to_numeric(series, errors="raise").astype(float)
    if not np.isfinite(values).all() or values.le(0.0).any():
        raise ValueError(f"{label} close values must be positive and finite")
    return pd.Series(values.to_numpy(), index=index)


def _validated_validity(
    values: pd.Series,
    expected_index: pd.DatetimeIndex,
    label: str,
) -> pd.Series:
    if not isinstance(values, pd.Series) or not values.index.equals(expected_index):
        raise ValueError(f"{label} validity mask timestamps must match closes")
    if values.isna().any() or not pd.api.types.is_bool_dtype(values.dtype):
        raise ValueError(f"{label} validity mask must contain only booleans")
    return values.astype(bool)


def _validate_states(states: pd.DataFrame, variant: ImpulseSignalVariant) -> None:
    if variant not in declared_impulse_variants():
        raise ValueError(f"unsupported impulse signal variant: {variant}")
    required = {
        *_BASE_STATE_COLUMNS,
        f"{variant}_qualifies",
        f"{variant}_direction",
    }
    missing = sorted(required.difference(states.columns))
    if missing:
        raise ValueError(f"impulse states missing columns: {missing}")
    decisions = pd.DatetimeIndex(states["decision_time_utc"])
    bars = pd.DatetimeIndex(states["bar_open_at"])
    if decisions.tz is None or bars.tz is None:
        raise ValueError("impulse state clocks must be timezone-aware")
    if decisions.has_duplicates or not decisions.is_monotonic_increasing:
        raise ValueError("impulse state decisions must be unique and ordered")
    if not decisions.equals(bars + pd.Timedelta(minutes=1)):
        raise ValueError("impulse state decision must follow bar open by one minute")


def _finite_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    output = numerator / denominator.where(denominator.gt(0.0))
    return output.where(np.isfinite(output))


def _directions(zscore: pd.Series) -> pd.Series:
    values = np.where(zscore.gt(0.0), "long", np.where(zscore.lt(0.0), "short", None))
    return pd.Series(values, index=zscore.index, dtype="object")
