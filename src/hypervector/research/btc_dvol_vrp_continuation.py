"""Preregistered BTC DVOL-VRP long signal and mechanism controls."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


_REQUIRED_COLUMNS = {
    "source_timestamp",
    "decision_time",
    "btc_close",
    "ema24",
    "vrp",
    "vrp_median",
    "high_vrp",
    "low_vrp",
    "bullish_structure",
}
_EXECUTION_SEMANTICS = "next_minute_open_strictly_after_event"


@dataclass(frozen=True)
class DvolVrpSignals:
    """Four frozen long-only signal frames for one falsification trial."""

    primary: pd.DataFrame
    price_only: pd.DataFrame
    high_vrp_only: pd.DataFrame
    low_vrp_placebo: pd.DataFrame

    def frames(self) -> tuple[pd.DataFrame, ...]:
        """Return every signal frame in preregistered trial-arm order."""
        return (
            self.primary,
            self.price_only,
            self.high_vrp_only,
            self.low_vrp_placebo,
        )


def build_btc_dvol_vrp_signals(features: pd.DataFrame) -> DvolVrpSignals:
    """Build one-shot causal long entries and completed-hour strategic exits."""
    frame = _validated_features(features)
    vrp_valid = frame["vrp"].notna()
    bullish = _boolean_state(frame["bullish_structure"])
    high_vrp = _boolean_state(frame["high_vrp"]) & vrp_valid
    low_vrp = _boolean_state(frame["low_vrp"]) & vrp_valid
    exit_condition = _strategic_exit(frame)
    return DvolVrpSignals(
        primary=_signal_frame(
            frame,
            high_vrp & bullish,
            exit_condition,
            "dvol_vrp_bullish_breakout_long",
        ),
        price_only=_signal_frame(
            frame,
            bullish,
            exit_condition,
            "price_only_bullish_breakout_long",
        ),
        high_vrp_only=_signal_frame(
            frame,
            high_vrp,
            exit_condition,
            "high_vrp_only_long",
        ),
        low_vrp_placebo=_signal_frame(
            frame,
            low_vrp & bullish,
            exit_condition,
            "low_vrp_bullish_breakout_long_placebo",
        ),
    )


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"BTC DVOL-VRP feature frame lacks columns: {missing}")
    frame = features.copy().reset_index(drop=True)
    source = _timestamps(frame["source_timestamp"], "source")
    decision = _timestamps(frame["decision_time"], "decision")
    _validate_ordered_unique(source, "source")
    _validate_ordered_unique(decision, "decision")
    if not decision.equals(source + pd.Timedelta(hours=1)):
        raise ValueError("BTC DVOL-VRP decision time must be exactly one hour later")
    frame["source_timestamp"] = source
    frame["decision_time"] = decision
    return frame


def _timestamps(values: pd.Series, label: str) -> pd.DatetimeIndex:
    try:
        timestamps = pd.DatetimeIndex(values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"BTC DVOL-VRP {label} timestamps are invalid") from exc
    if timestamps.tz is None or str(timestamps.tz) != "UTC":
        raise ValueError(f"BTC DVOL-VRP {label} timestamps must be timezone-aware UTC")
    return timestamps


def _validate_ordered_unique(timestamps: pd.DatetimeIndex, label: str) -> None:
    if timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise ValueError(f"BTC DVOL-VRP {label} timestamps must be ordered and unique")


def _boolean_state(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(bool)


def _strategic_exit(frame: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(frame["btc_close"], errors="coerce")
    ema = pd.to_numeric(frame["ema24"], errors="coerce")
    vrp = pd.to_numeric(frame["vrp"], errors="coerce")
    median = pd.to_numeric(frame["vrp_median"], errors="coerce")
    lost_ema = close.notna() & ema.notna() & close.lt(ema)
    lost_vrp = vrp.notna() & median.notna() & vrp.lt(median)
    return lost_ema | lost_vrp


def _signal_frame(
    features: pd.DataFrame,
    state: pd.Series,
    exit_condition: pd.Series,
    signal_name: str,
) -> pd.DataFrame:
    active = state.fillna(False).astype(bool)
    entry = active & ~active.shift(1, fill_value=False)
    signals = pd.DataFrame(
        {
            "event_time": features["decision_time"],
            "long_entry": entry,
            "short_entry": False,
            "long_exit": exit_condition.fillna(False).astype(bool),
            "short_exit": False,
            "signal_name": signal_name,
        }
    )
    signals.attrs["execution_semantics"] = _EXECUTION_SEMANTICS
    return signals
