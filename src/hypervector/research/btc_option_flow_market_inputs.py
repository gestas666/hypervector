"""Gap-aware market inputs for the frozen BTC option-flow replay."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from hypervector.data.oxa_candles import repair_candle_cadence
from hypervector.data.provenance import normalize_ohlcv
from hypervector.research.btc_option_flow_candle_audit import audit_candle_cadence


_MINUTE = pd.Timedelta(minutes=1)
_HOUR = pd.Timedelta(hours=1)


@dataclass(frozen=True)
class OptionFlowMarketInputs:
    """Observed execution bars and repaired signal-only continuity bars."""

    execution_bars: pd.DataFrame
    signal_bars: pd.DataFrame
    observed_rows: int
    gap_fill_rows: int
    gap_run_count: int
    maximum_gap_minutes: int
    funding_event_count: int
    funding_events_shifted_after_gap: int

    def evidence(self) -> dict[str, int]:
        """Return source-preparation counts without market outcomes."""
        return {
            "observed_rows": self.observed_rows,
            "gap_fill_rows": self.gap_fill_rows,
            "gap_run_count": self.gap_run_count,
            "maximum_gap_minutes": self.maximum_gap_minutes,
            "funding_event_count": self.funding_event_count,
            "funding_events_shifted_after_gap": (self.funding_events_shifted_after_gap),
        }


def prepare_gap_aware_option_flow_market(
    native_candles: pd.DataFrame,
    hourly_funding: pd.Series,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    maximum_repair_minutes: int,
) -> OptionFlowMarketInputs:
    """Prepare execution and signal paths without inventing tradable gap bars."""
    start_at, end_at = _validated_bounds(start, end)
    native = normalize_ohlcv(native_candles)
    if not native["source"].eq("hl").all():
        raise ValueError("option-flow native candles must use the hl source identity")
    audit = audit_candle_cadence(
        native,
        start=start_at,
        end=end_at,
        maximum_repair_minutes=maximum_repair_minutes,
    )
    if not audit.contract_pass:
        raise ValueError("option-flow candle source failed the registered cadence gate")
    repaired, fills = repair_candle_cadence(
        native,
        start=start_at.to_pydatetime(),
        end=end_at.to_pydatetime(),
        max_gap_minutes=maximum_repair_minutes,
    )
    if fills != audit.missing_rows:
        raise ValueError("option-flow candle repair count differs from cadence audit")
    execution = _execution_bars(native)
    execution, shifted = _attach_funding(execution, hourly_funding, start_at, end_at)
    signals = repaired.set_index("timestamp")
    return OptionFlowMarketInputs(
        execution,
        signals,
        len(native),
        fills,
        audit.gap_run_count,
        audit.maximum_gap_minutes,
        len(hourly_funding),
        shifted,
    )


def _execution_bars(native: pd.DataFrame) -> pd.DataFrame:
    output = native.set_index("timestamp").copy()
    missing_before = output.index.to_series().diff().div(_MINUTE).sub(1.0).fillna(0.0)
    if not missing_before.mod(1).eq(0).all() or (missing_before < 0).any():
        raise ValueError("option-flow candle gaps are not whole nonnegative minutes")
    output["gap_before_bars"] = missing_before.astype(int).to_numpy()
    return output


def _attach_funding(
    bars: pd.DataFrame,
    funding: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, int]:
    rates = _validated_funding(funding, start, end)
    output = bars.copy()
    output["funding_rate"] = 0.0
    used_positions: set[int] = set()
    shifted = 0
    for timestamp, value in rates.items():
        position = int(output.index.searchsorted(timestamp))
        if position >= len(output) or output.index[position] >= timestamp + _HOUR:
            raise ValueError("option-flow funding event has no bounded observed candle")
        if position in used_positions:
            raise ValueError(
                "option-flow funding events collide on one observed candle"
            )
        used_positions.add(position)
        output.iloc[position, output.columns.get_loc("funding_rate")] = float(value)
        shifted += int(output.index[position] != timestamp)
    return output, shifted


def _validated_funding(
    funding: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    if not isinstance(funding.index, pd.DatetimeIndex) or funding.index.tz is None:
        raise ValueError("option-flow funding requires an aware DatetimeIndex")
    output = funding.copy()
    output.index = output.index.tz_convert("UTC")
    if output.index.has_duplicates or not output.index.is_monotonic_increasing:
        raise ValueError("option-flow funding timestamps must be ordered and unique")
    expected = pd.date_range(start.ceil("h"), end, freq="1h", inclusive="left")
    if not output.index.equals(expected):
        raise ValueError("option-flow funding must cover every exact hourly event")
    values = pd.to_numeric(output, errors="raise").astype(float)
    if not values.map(math.isfinite).all():
        raise ValueError("option-flow funding rates must be finite")
    return values


def _validated_bounds(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_at, end_at = pd.Timestamp(start), pd.Timestamp(end)
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("option-flow market bounds must be timezone-aware")
    start_at, end_at = start_at.tz_convert("UTC"), end_at.tz_convert("UTC")
    if start_at != start_at.floor("min") or end_at != end_at.floor("min"):
        raise ValueError("option-flow market bounds must be minute-aligned")
    if end_at <= start_at:
        raise ValueError("option-flow market bounds must be increasing")
    return start_at, end_at
