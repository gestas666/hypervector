"""Causal point-in-time signals from official IBIT shares outstanding."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


_AVAILABILITY_DELAY = pd.Timedelta(days=1, hours=12)
_CANDIDATE_NAME = "ibit_two_creation_persistence_long_v1"
_SINGLE_CREATION_NAME = "ibit_single_creation_onset_long_control_v1"
_REDEMPTION_PLACEBO_NAME = "ibit_two_redemption_persistence_long_placebo_v1"
_HISTORY_COLUMNS = {
    "as_of_date",
    "nav_per_share",
    "shares_outstanding",
}


@dataclass(frozen=True)
class BtcIbitCreationSignals:
    """Hold the three frozen long-only arms and exact source availability."""

    candidate_entries: pd.DataFrame
    single_creation_control_entries: pd.DataFrame
    redemption_placebo_entries: pd.DataFrame
    candidate_event_times_utc: tuple[str, ...]
    single_creation_event_times_utc: tuple[str, ...]
    redemption_placebo_event_times_utc: tuple[str, ...]
    candidate_market_gap_times_utc: tuple[str, ...]
    single_creation_market_gap_times_utc: tuple[str, ...]
    redemption_placebo_market_gap_times_utc: tuple[str, ...]
    report_only: bool = True
    execution_authority: str = "none"


def build_btc_ibit_creation_signals(
    history: pd.DataFrame,
    market_index: pd.DatetimeIndex,
) -> BtcIbitCreationSignals:
    """Map frozen issuer-state onsets to exact delayed UTC market minutes."""
    source = _validated_history(history)
    index = _validated_market_index(market_index)
    changes = source["shares_outstanding"].diff()
    positive = changes.gt(0.0)
    negative = changes.lt(0.0)
    candidate = (
        positive
        & positive.shift(1, fill_value=False)
        & ~positive.shift(2, fill_value=False)
    )
    single = positive & ~positive.shift(1, fill_value=False)
    redemption = (
        negative
        & negative.shift(1, fill_value=False)
        & ~negative.shift(2, fill_value=False)
    )
    availability = _availability(source["as_of_date"])
    candidate_events = availability[candidate.to_numpy()]
    single_events = availability[single.to_numpy()]
    redemption_events = availability[redemption.to_numpy()]
    return _signal_result(index, candidate_events, single_events, redemption_events)


def _validated_history(history: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_HISTORY_COLUMNS.difference(history.columns))
    if missing:
        raise ValueError(f"IBIT history is missing columns: {missing}")
    if history.empty:
        raise ValueError("IBIT history contains no issuer observations")
    result = history.loc[:, sorted(_HISTORY_COLUMNS)].copy()
    result["as_of_date"] = pd.to_datetime(result["as_of_date"], errors="raise")
    dates = pd.DatetimeIndex(result["as_of_date"])
    if dates.tz is not None or not dates.equals(dates.normalize()):
        raise ValueError("IBIT history requires timezone-naive as-of calendar dates")
    if dates.has_duplicates:
        raise ValueError("IBIT history contains duplicate as-of dates")
    if not dates.is_monotonic_increasing:
        raise ValueError("IBIT history requires increasing as-of dates")
    _validate_economic_fields(result)
    return result


def _validate_economic_fields(history: pd.DataFrame) -> None:
    nav = pd.to_numeric(history["nav_per_share"], errors="raise").to_numpy(float)
    shares = pd.to_numeric(history["shares_outstanding"], errors="raise").to_numpy(
        float
    )
    if not np.isfinite(nav).all() or (nav <= 0.0).any():
        raise ValueError("IBIT NAV must be finite and positive")
    if not np.isfinite(shares).all() or (shares <= 0.0).any():
        raise ValueError("IBIT shares outstanding must be finite and positive")
    if not np.equal(shares, np.rint(shares)).all():
        raise ValueError("IBIT shares outstanding must be whole units")
    history["nav_per_share"] = nav
    history["shares_outstanding"] = shares.astype(np.int64)


def _validated_market_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("IBIT signal market index must be timezone-aware")
    if index.empty:
        raise ValueError("IBIT signal market index must not be empty")
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("IBIT signal market index must be unique increasing")
    utc = index.tz_convert("UTC")
    if not utc.equals(utc.floor("min")):
        raise ValueError("IBIT signal market index requires exact minute labels")
    return utc


def _availability(dates: pd.Series) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(dates).tz_localize("UTC")
    return index + _AVAILABILITY_DELAY


def _signal_result(
    index: pd.DatetimeIndex,
    candidate: pd.DatetimeIndex,
    single: pd.DatetimeIndex,
    redemption: pd.DatetimeIndex,
) -> BtcIbitCreationSignals:
    return BtcIbitCreationSignals(
        candidate_entries=_project(index, candidate, _CANDIDATE_NAME),
        single_creation_control_entries=_project(index, single, _SINGLE_CREATION_NAME),
        redemption_placebo_entries=_project(
            index, redemption, _REDEMPTION_PLACEBO_NAME
        ),
        candidate_event_times_utc=_times(candidate),
        single_creation_event_times_utc=_times(single),
        redemption_placebo_event_times_utc=_times(redemption),
        candidate_market_gap_times_utc=_gap_times(index, candidate),
        single_creation_market_gap_times_utc=_gap_times(index, single),
        redemption_placebo_market_gap_times_utc=_gap_times(index, redemption),
    )


def _project(
    index: pd.DatetimeIndex,
    events: pd.DatetimeIndex,
    signal_name: str,
) -> pd.DataFrame:
    output = pd.DataFrame(
        {
            "long_entry": False,
            "short_entry": False,
            "long_exit": False,
            "short_exit": False,
            "signal_name": signal_name,
        },
        index=index,
    )
    mapped = events[events.isin(index)]
    output.loc[mapped, "long_entry"] = True
    return output


def _gap_times(
    index: pd.DatetimeIndex,
    events: pd.DatetimeIndex,
) -> tuple[str, ...]:
    covered = events[(events >= index[0]) & (events <= index[-1])]
    return _times(covered[~covered.isin(index)])


def _times(events: pd.DatetimeIndex) -> tuple[str, ...]:
    return tuple(timestamp.isoformat() for timestamp in events)
