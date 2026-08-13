"""Causal feature, event, and label construction for breadth expansion."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_breadth_models import (
    BreadthAnchor,
    BreadthDirection,
    BreadthLabelStatus,
    BreadthSignalVariant,
    CrossAssetBreadthConfig,
    CrossAssetBreadthEvent,
    CrossAssetBreadthLabel,
    declared_breadth_folds,
)

_LABEL_COLUMNS = {"timestamp", "open", "source"}
_ALLOWED_SOURCES = {"hl", "hl_gap_fill"}


@dataclass(frozen=True)
class _BreadthInputs:
    normalized: pd.DataFrame
    btc_direction: pd.Series
    valid_symbols: pd.Series


def build_breadth_states(
    closes: pd.DataFrame,
    validity: pd.DataFrame,
    config: CrossAssetBreadthConfig,
) -> pd.DataFrame:
    """Build point-in-time primary and control states on completed 15m bars."""
    prices, valid = _validated_feature_inputs(closes, validity, config)
    inputs = _normalized_returns(prices, valid, config)
    states = pd.DataFrame(
        {
            "bar_open_at": prices.index,
            "decision_time_utc": prices.index
            + pd.Timedelta(minutes=config.bar_minutes),
            "BTC_normalized_return": inputs.normalized["BTC"],
        },
        index=prices.index,
    )
    _add_primary_state(states, inputs, config)
    _add_btc_control(states, inputs, config)
    _add_placebo_state(states, inputs, config)
    return states


def sample_breadth_events(
    states: pd.DataFrame,
    config: CrossAssetBreadthConfig,
    *,
    signal_variant: BreadthSignalVariant,
) -> tuple[CrossAssetBreadthEvent, ...]:
    """Emit false-to-true signal onsets under one shared variant cooldown."""
    _validate_states(states, signal_variant)
    events: list[CrossAssetBreadthEvent] = []
    previous_qualifies = False
    next_eligible: pd.Timestamp | None = None
    qualify = f"{signal_variant}_qualifies"
    for row in states.itertuples(index=False):
        decision = pd.Timestamp(getattr(row, "decision_time_utc"))
        bar_open = pd.Timestamp(getattr(row, "bar_open_at"))
        current = bool(getattr(row, qualify))
        onset = current and not previous_qualifies
        inside = config.development_start <= bar_open < config.development_end
        if onset and inside and (next_eligible is None or decision >= next_eligible):
            events.append(_event_from_row(row, signal_variant))
            next_eligible = decision + pd.Timedelta(minutes=config.cooldown_minutes)
        previous_qualifies = current
    return tuple(events)


def label_breadth_events(
    events: tuple[CrossAssetBreadthEvent, ...],
    btc_bars: pd.DataFrame,
    config: CrossAssetBreadthConfig,
) -> tuple[CrossAssetBreadthLabel, ...]:
    """Label immediate and delayed 60-minute BTC anchors."""
    bars = _validated_label_bars(btc_bars)
    return tuple(
        _label_event(event, anchor, bars, config)
        for event in events
        for anchor in ("base", "delayed")
    )


def _normalized_returns(
    closes: pd.DataFrame,
    validity: pd.DataFrame,
    config: CrossAssetBreadthConfig,
) -> _BreadthInputs:
    log_prices = np.log(closes)
    one_valid = validity & validity.shift(1, fill_value=False)
    one_return = log_prices.diff().where(one_valid)
    width = config.return_bars + 1
    path_valid = validity.rolling(width, min_periods=width).sum().eq(width)
    horizon_return = log_prices.diff(config.return_bars).where(path_valid)
    prior = one_return.shift(1)
    volatility = prior.rolling(
        config.lookback_bars,
        min_periods=config.minimum_valid_bars,
    ).std(ddof=1)
    normalized = (horizon_return / volatility).replace([np.inf, -np.inf], np.nan)
    direction = np.sign(normalized["BTC"]).replace(0.0, np.nan)
    return _BreadthInputs(normalized, direction, normalized.notna().sum(axis=1))


def _add_primary_state(
    states: pd.DataFrame,
    inputs: _BreadthInputs,
    config: CrossAssetBreadthConfig,
) -> None:
    breadth = _directional_breadth(inputs.normalized, inputs.btc_direction)
    dispersion = inputs.normalized.std(axis=1, ddof=0).where(
        inputs.valid_symbols.eq(len(config.symbols))
    )
    threshold, crossed = _strictly_prior_cross(dispersion, config)
    qualifies = crossed & breadth.ge(config.breadth_required)
    _store_variant(
        states,
        "primary",
        qualifies,
        inputs.btc_direction,
        breadth,
        dispersion,
        threshold,
        inputs.valid_symbols,
    )


def _add_btc_control(
    states: pd.DataFrame,
    inputs: _BreadthInputs,
    config: CrossAssetBreadthConfig,
) -> None:
    magnitude = inputs.normalized["BTC"].abs()
    threshold, crossed = _strictly_prior_cross(magnitude, config)
    valid = magnitude.notna().astype(int)
    _store_variant(
        states,
        "btc_only_momentum",
        crossed,
        inputs.btc_direction,
        valid,
        magnitude,
        threshold,
        valid,
    )
    states["btc_momentum_threshold"] = threshold


def _add_placebo_state(
    states: pd.DataFrame,
    inputs: _BreadthInputs,
    config: CrossAssetBreadthConfig,
) -> None:
    placebo = inputs.normalized.copy()
    peers = [symbol for symbol in config.symbols if symbol != "BTC"]
    placebo[peers] = placebo[peers].shift(config.placebo_lag_bars)
    valid_symbols = placebo.notna().sum(axis=1)
    breadth = _directional_breadth(placebo, inputs.btc_direction)
    dispersion = placebo.std(axis=1, ddof=0).where(
        valid_symbols.eq(len(config.symbols))
    )
    threshold, crossed = _strictly_prior_cross(dispersion, config)
    qualifies = crossed & breadth.ge(config.breadth_required)
    _store_variant(
        states,
        "lagged_breadth_placebo",
        qualifies,
        inputs.btc_direction,
        breadth,
        dispersion,
        threshold,
        valid_symbols,
    )


def _strictly_prior_cross(
    values: pd.Series,
    config: CrossAssetBreadthConfig,
) -> tuple[pd.Series, pd.Series]:
    threshold = (
        values.shift(1)
        .rolling(
            config.lookback_bars,
            min_periods=config.minimum_valid_bars,
        )
        .quantile(config.dispersion_quantile)
    )
    above = values.gt(threshold) & values.notna() & threshold.notna()
    return threshold, above & ~above.shift(1, fill_value=False)


def _directional_breadth(
    normalized: pd.DataFrame,
    btc_direction: pd.Series,
) -> pd.Series:
    signs = np.sign(normalized)
    return (
        signs.eq(btc_direction, axis="index")
        .sum(axis=1)
        .where(
            btc_direction.notna(),
            0,
        )
    )


def _store_variant(
    states: pd.DataFrame,
    variant: BreadthSignalVariant,
    qualifies: pd.Series,
    direction: pd.Series,
    breadth: pd.Series,
    dispersion: pd.Series,
    threshold: pd.Series,
    valid_symbols: pd.Series,
) -> None:
    states[f"{variant}_qualifies"] = qualifies.fillna(False).astype(bool)
    states[f"{variant}_direction"] = _directions(direction)
    states[f"{variant}_breadth_count"] = breadth.fillna(0).astype(int)
    states[f"{variant}_dispersion"] = dispersion
    states[f"{variant}_dispersion_threshold"] = threshold
    states[f"{variant}_valid_symbols"] = valid_symbols.fillna(0).astype(int)
    if variant == "primary":
        states["breadth_count"] = states[f"{variant}_breadth_count"]
        states["dispersion"] = dispersion
        states["dispersion_threshold"] = threshold
        states["valid_symbols"] = states[f"{variant}_valid_symbols"]


def _event_from_row(
    row: object,
    variant: BreadthSignalVariant,
) -> CrossAssetBreadthEvent:
    direction = _row_direction(row, variant)
    decision = pd.Timestamp(getattr(row, "decision_time_utc"))
    return CrossAssetBreadthEvent(
        bar_open_at=pd.Timestamp(getattr(row, "bar_open_at")).isoformat(),
        decision_time_utc=decision.isoformat(),
        entry_time_utc=decision.isoformat(),
        signal_variant=variant,
        direction=direction,
        btc_normalized_return=float(getattr(row, "BTC_normalized_return")),
        breadth_count=int(getattr(row, _metric_column(variant, "breadth_count"))),
        dispersion=float(getattr(row, _metric_column(variant, "dispersion"))),
        dispersion_threshold=float(
            getattr(row, _metric_column(variant, "dispersion_threshold"))
        ),
        valid_symbols=int(getattr(row, _metric_column(variant, "valid_symbols"))),
    )


def _label_event(
    event: CrossAssetBreadthEvent,
    anchor: BreadthAnchor,
    bars: pd.DataFrame,
    config: CrossAssetBreadthConfig,
) -> CrossAssetBreadthLabel:
    delay = config.delayed_entry_minutes if anchor == "delayed" else 0
    entry = pd.Timestamp(event.entry_time_utc) + pd.Timedelta(minutes=delay)
    exit_time = entry + pd.Timedelta(minutes=config.horizon_minutes)
    status = _label_status(event, entry, exit_time, bars, config)
    entry_price, exit_price, gross = _label_values(
        event.direction, entry, exit_time, bars, status
    )
    return CrossAssetBreadthLabel(
        bar_open_at=event.bar_open_at,
        decision_time_utc=event.decision_time_utc,
        entry_time_utc=entry.isoformat(),
        exit_time_utc=exit_time.isoformat(),
        signal_variant=event.signal_variant,
        anchor=anchor,
        direction=event.direction,
        horizon_minutes=config.horizon_minutes,
        entry_price=entry_price,
        exit_price=exit_price,
        directional_gross_return_bps=gross,
        status=status,
    )


def _label_status(
    event: CrossAssetBreadthEvent,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    bars: pd.DataFrame,
    config: CrossAssetBreadthConfig,
) -> BreadthLabelStatus:
    if exit_time >= config.development_end:
        return "right_censored"
    decision = pd.Timestamp(event.decision_time_utc)
    fold = next(
        (
            (start, end)
            for _, start, end in declared_breadth_folds(config)
            if start <= decision < end
        ),
        None,
    )
    if fold is None or exit_time >= fold[1]:
        return "fold_boundary_purged"
    if not _authentic_anchor(bars, entry) or not _authentic_anchor(bars, exit_time):
        return "technical_gap"
    return "resolved"


def _label_values(
    direction: BreadthDirection,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    bars: pd.DataFrame,
    status: BreadthLabelStatus,
) -> tuple[float | None, float | None, float | None]:
    if status != "resolved":
        return None, None, None
    entry_price = float(bars.at[entry, "open"])
    exit_price = float(bars.at[exit_time, "open"])
    sign = 1.0 if direction == "long" else -1.0
    gross = sign * (exit_price / entry_price - 1.0) * 10_000.0
    return entry_price, exit_price, gross


def _authentic_anchor(bars: pd.DataFrame, timestamp: pd.Timestamp) -> bool:
    return timestamp in bars.index and bars.at[timestamp, "source"] == "hl"


def _directions(values: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(values.gt(0.0), "long", np.where(values.lt(0.0), "short", None)),
        index=values.index,
        dtype="object",
    )


def _row_direction(row: object, variant: BreadthSignalVariant) -> BreadthDirection:
    value = getattr(row, f"{variant}_direction")
    if value in {"long", "short"}:
        return value
    raise ValueError(f"qualified {variant} state has invalid direction: {value}")


def _validated_feature_inputs(
    closes: pd.DataFrame,
    validity: pd.DataFrame,
    config: CrossAssetBreadthConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if list(closes.columns) != list(config.symbols) or not closes.index.equals(
        validity.index
    ):
        raise ValueError("breadth inputs must share the frozen symbol/time grid")
    if list(validity.columns) != list(config.symbols):
        raise ValueError("breadth validity columns differ from prices")
    if not isinstance(closes.index, pd.DatetimeIndex) or closes.index.tz is None:
        raise ValueError("breadth input index must be timezone-aware")
    if not closes.index.is_unique or not closes.index.is_monotonic_increasing:
        raise ValueError("breadth input timestamps must be unique and increasing")
    prices = closes.astype(float)
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0.0).any(axis=None):
        raise ValueError("breadth prices must be positive and finite")
    return prices, validity.astype(bool)


def _validated_label_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = _LABEL_COLUMNS.difference(bars.columns)
    if missing:
        raise ValueError(f"BTC label bars missing columns: {sorted(missing)}")
    frame = bars.copy()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("timestamp"), utc=True))
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("BTC label timestamps must be unique and increasing")
    if not frame["source"].isin(_ALLOWED_SOURCES).all():
        raise ValueError("BTC label bars contain an unsupported source")
    prices = frame["open"].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ValueError("BTC label opens must be positive and finite")
    return frame


def _validate_states(states: pd.DataFrame, variant: BreadthSignalVariant) -> None:
    required = {
        "bar_open_at",
        "decision_time_utc",
        "BTC_normalized_return",
        f"{variant}_qualifies",
        f"{variant}_direction",
        _metric_column(variant, "breadth_count"),
        _metric_column(variant, "dispersion"),
        _metric_column(variant, "dispersion_threshold"),
        _metric_column(variant, "valid_symbols"),
    }
    missing = required.difference(states.columns)
    if missing:
        raise ValueError(f"breadth states missing columns: {sorted(missing)}")


def _metric_column(variant: BreadthSignalVariant, name: str) -> str:
    return name if variant == "primary" else f"{variant}_{name}"
