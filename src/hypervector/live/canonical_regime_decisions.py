"""Causal completed-bar canonical regime decisions for live telemetry.

Every completed one-minute bar of the latest contiguous segment is classified by
the canonical multi-timeframe regime engine (1m execution state, completed 5m
state and 15m context) and annotated with the observe-only indicator
components. A decision depends only on the completed window and its bar
position. Nothing here emits an intent or gates an entry.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import math

import numpy as np
import pandas as pd

from hypervector.live.canonical_regime_components import build_regime_component_frame
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.regime.classifier import validate_regime_bars
from hypervector.regime.composite import classify_multitimeframe

_MINUTE = pd.Timedelta(minutes=1)
_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
_DIRECTIONS = frozenset({"long", "short", "neutral"})


@dataclass(frozen=True)
class CanonicalRegimeDecision:
    """One completed-bar canonical regime classification and its provenance."""

    decision_time_ms: int
    reference_price: float
    primary_regime: str
    state_1m: str
    state_5m: str
    context_15m: str
    confidence: float
    structural_direction: str
    readiness: SignalReadiness

    def __post_init__(self) -> None:
        """Reject malformed time, price, state or direction."""
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("decision_time_ms must be a nonnegative integer")
        if not math.isfinite(self.reference_price) or self.reference_price <= 0.0:
            raise ValueError("reference_price must be positive and finite")
        if not math.isfinite(self.confidence):
            raise ValueError("confidence must be finite")
        for name in ("primary_regime", "state_1m", "state_5m", "context_15m"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.structural_direction not in _DIRECTIONS:
            raise ValueError("structural_direction must be long, short, or neutral")


def completed_minute_bars(
    raw_bars: pd.DataFrame, *, observed_at: pd.Timestamp
) -> pd.DataFrame:
    """Return the latest contiguous segment of completed, validated 1m bars."""
    required = {"timestamp", *_OHLCV_COLUMNS}
    missing = required.difference(raw_bars.columns)
    if missing:
        raise ValueError(f"regime candle frame is missing columns: {sorted(missing)}")
    bars = raw_bars.loc[:, sorted(required)].copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.drop_duplicates("timestamp", keep="last").set_index("timestamp")
    bars = bars.sort_index().loc[:, list(_OHLCV_COLUMNS)]
    observed = _utc_timestamp(observed_at)
    complete = bars.loc[bars.index + _MINUTE <= observed]
    if complete.empty:
        raise ValueError("no completed one-minute candles for regime telemetry")
    deltas = complete.index[1:] - complete.index[:-1]
    resets = [position + 1 for position, delta in enumerate(deltas) if delta != _MINUTE]
    complete = complete.iloc[resets[-1] :] if resets else complete
    if not complete.index.floor("min").equals(complete.index):
        raise ValueError("1m regime bars require exact 1m open-time cadence")
    validate_regime_bars(complete)
    return complete


def build_completed_regime_decisions(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None = None,
) -> tuple[CanonicalRegimeDecision, ...]:
    """Return every unseen completed-bar decision in chronological order."""
    after = _optional_timestamp(after_decision_time_ms)
    bars = completed_minute_bars(raw_bars, observed_at=observed_at)
    positions = bars.index
    if after is not None:
        if after >= int((positions[-1] + _MINUTE).timestamp() * 1_000):
            return ()
        positions = positions[positions + _MINUTE > pd.Timestamp(after, unit="ms", tz="UTC")]
    # The unseen bars are a suffix of the completed window: a bad index is
    # refused by the frame alignment check before any decision is made.
    first = len(bars) - len(positions)
    shared = _SHARED_DECISIONS.get()
    key = _window_key(bars) if shared is not None else None
    if shared is None or key is None:
        return _decisions(_completed_frames(bars), first)
    cached = shared.get(key)
    if cached is not None and cached[0] <= first:
        shared.move_to_end(key)
        return cached[1][first - cached[0] :]
    frames = _completed_frames(bars)
    decisions = _decisions(frames, first)
    shared[key] = _retained_suffix(frames, first, decisions)
    while len(shared) > _SHARED_WINDOW_LIMIT:
        shared.popitem(last=False)
    return decisions


_CompletedFrames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
# Per poll: distinct windows remembered, and decisions kept for each. The
# retained suffix covers every steady-state lookback, so one frame build serves
# every consumer of a window; seed queries beyond it rebuild.
_SHARED_WINDOW_LIMIT = 64
_SHARED_DECISION_LIMIT = 128
_SHARED_DECISIONS: ContextVar[
    OrderedDict[tuple[object, ...], tuple[int, tuple[CanonicalRegimeDecision, ...]]]
    | None
] = ContextVar("completed_regime_decision_cycle", default=None)


@contextmanager
def shared_completed_regime_decisions() -> Iterator[None]:
    """Let consumers in one poll share decisions for bit-identical windows.

    A decision depends only on the completed window and its bar position, so a
    window already decided in this cycle answers later requests from the same
    immutable decisions instead of rebuilding every indicator frame. Nothing is
    shared outside the ``with`` block.
    """
    token = _SHARED_DECISIONS.set(OrderedDict())
    try:
        yield
    finally:
        _SHARED_DECISIONS.reset(token)


def _completed_frames(bars: pd.DataFrame) -> _CompletedFrames:
    """Build the regime and component frames for one completed window."""
    regimes = classify_multitimeframe(bars)
    _validate_alignment(bars, regimes)
    components = build_regime_component_frame(bars)
    _validate_alignment(bars, components)
    return bars, regimes, components


def _decisions(
    frames: _CompletedFrames, first: int
) -> tuple[CanonicalRegimeDecision, ...]:
    """Decide every bar from ``first`` on, in order, raising at the first failure."""
    readers = tuple(_RowReader(frame) for frame in frames)
    index = frames[0].index
    decisions: list[CanonicalRegimeDecision] = []
    for start in range(first, len(index), _ROW_CHUNK):
        locations = np.arange(start, min(start + _ROW_CHUNK, len(index)))
        rows = zip(*(reader.rows(locations) for reader in readers), strict=True)
        for location, row in zip(locations, rows, strict=True):
            decisions.append(_decision_at(index, int(location), row))
    return tuple(decisions)


def _decision_at(
    index: pd.Index, location: int, row: tuple[Mapping[str, object], ...]
) -> CanonicalRegimeDecision:
    decision_time = pd.Timestamp(index[location]) + _MINUTE
    decision_ms = int(decision_time.timestamp() * 1_000)
    return _decision_from_rows(decision_ms, *row)


def _retained_suffix(
    frames: _CompletedFrames,
    first: int,
    decisions: tuple[CanonicalRegimeDecision, ...],
) -> tuple[int, tuple[CanonicalRegimeDecision, ...]]:
    """Keep a bounded decided suffix, extended over older bars that decide cleanly.

    Older bars were not requested, so a bar that cannot be decided only ends the
    extension; its error is raised when a later request includes that bar.
    """
    length = len(frames[0])
    if len(decisions) >= _SHARED_DECISION_LIMIT or first == 0:
        kept = decisions[-_SHARED_DECISION_LIMIT:]
        return length - len(kept), kept
    lowest = max(0, first - (_SHARED_DECISION_LIMIT - len(decisions)))
    locations = np.arange(lowest, first)
    rows = list(zip(*(_RowReader(frame).rows(locations) for frame in frames), strict=True))
    older: list[CanonicalRegimeDecision] = []
    for location, row in zip(reversed(locations), reversed(rows), strict=True):
        try:
            older.append(_decision_at(frames[0].index, int(location), row))
        except Exception:  # noqa: BLE001 - an unrequested bar only ends the extension
            break
    return first - len(older), (*reversed(older), *decisions)


def _window_key(bars: pd.DataFrame) -> tuple[object, ...] | None:
    """Return a SHA-256 content key for an all-float64 window, or None.

    The key covers the exact bytes of every value and index timestamp, the
    column names, the index dtype, name and frequency, so equal keys mean
    bit-identical windows (NaN payloads and signed zeros included).
    """
    if not isinstance(bars.index, pd.DatetimeIndex):
        return None
    if not all(dtype == np.float64 for dtype in bars.dtypes):
        return None
    digest = hashlib.sha256(bars.index.asi8.tobytes())
    digest.update(np.ascontiguousarray(bars.to_numpy(dtype=np.float64)).tobytes())
    return (
        tuple(bars.columns),
        str(bars.index.dtype),
        bars.index.name,
        bars.index.freqstr,
        bars.shape,
        digest.digest(),
    )


# Rows extracted at once; bounds transient memory on long seed queries.
_ROW_CHUNK = 512


class _RowReader:
    """Read rows with exactly the values ``frame.iloc[location]`` would hold.

    A row Series keeps numpy scalars from numpy columns, extension scalars from
    extension columns and the stored objects from object columns, or casts all
    of them to one numpy dtype; the columns are sliced the same way here. The
    first and last row of every chunk are compared with ``iloc`` element by
    element, and any difference falls back to the row Series themselves.
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame
        self._columns = list(frame.columns)
        self._arrays: list[object] | None = None
        self._matrix: np.ndarray | None = None
        if len(frame) == 0 or len(self._columns) == 0 or frame.columns.has_duplicates:
            return
        if not all(isinstance(name, str) for name in self._columns):
            return
        row_dtype = frame.iloc[0].dtype
        if row_dtype == np.dtype(object):
            self._arrays = [
                frame.iloc[:, position]._values for position in range(len(self._columns))
            ]
        elif isinstance(row_dtype, np.dtype):
            self._matrix = frame.to_numpy(dtype=row_dtype)

    def rows(self, locations: np.ndarray) -> list[Mapping[str, object]] | list[pd.Series]:
        if len(locations) == 0:
            return []
        if self._arrays is not None:
            column_values = [list(values[locations]) for values in self._arrays]  # type: ignore[index]
        elif self._matrix is not None:
            block = self._matrix[locations]
            column_values = [list(block[:, position]) for position in range(block.shape[1])]
        else:
            return self._series(locations)
        rows = [
            dict(zip(self._columns, values, strict=True))
            for values in zip(*column_values, strict=True)
        ]
        for index in {0, len(rows) - 1}:
            expected = self._frame.iloc[int(locations[index])]._values
            if len(expected) != len(self._columns) or not all(
                _same_element(left, right)
                for left, right in zip(expected, rows[index].values(), strict=True)
            ):
                return self._series(locations)
        return rows

    def _series(self, locations: np.ndarray) -> list[pd.Series]:
        return [self._frame.iloc[int(location)] for location in locations]


def _same_element(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if left is right:
        return True
    try:
        if bool(left == right):
            return True
    except (TypeError, ValueError):
        return False
    return bool(pd.isna(left)) and bool(pd.isna(right))


def _decision_from_rows(
    decision_time_ms: int,
    bar: Mapping[str, object],
    regime: Mapping[str, object],
    components: Mapping[str, object],
) -> CanonicalRegimeDecision:
    structural = _structural_direction(regime.get("structural_direction"))
    return CanonicalRegimeDecision(
        decision_time_ms=decision_time_ms,
        reference_price=_positive_float(bar.get("close"), "close"),
        primary_regime=_text(regime.get("primary_regime"), "primary_regime"),
        state_1m=_text(regime.get("state_1m"), "state_1m"),
        state_5m=_text(regime.get("state_5m"), "state_5m"),
        context_15m=_text(regime.get("context_15m"), "context_15m"),
        confidence=_finite_float(regime.get("confidence"), "confidence"),
        structural_direction=structural,
        readiness=_regime_readiness(regime, components, structural),
    )


def _structural_direction(value: object) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "neutral"
    if value not in _DIRECTIONS:
        raise ValueError("regime structural_direction must be long, short, or neutral")
    return str(value)


def _regime_readiness(
    regime: Mapping[str, object],
    components: Mapping[str, object],
    structural: str,
) -> SignalReadiness:
    primary = _text(regime.get("primary_regime"), "primary_regime")
    classified = primary != "UNKNOWN"
    return SignalReadiness(
        side=structural if structural in {"long", "short"} else None,
        conditions_met=int(classified),
        conditions_required=1,
        blockers=() if classified else ("regime_unclassified",),
        indicators=(
            f"REGIME {primary}",
            f"STRUCT {structural.upper()}",
            *_regime_indicators(regime),
            *_component_indicators(components),
        ),
        metrics={
            "structural_direction": structural,
            **_regime_metrics(regime),
            **_component_metrics(components),
        },
    )


CANONICAL_REGIME_METRIC_FIELDS = (
    "rsi",
    "regime_1m_reason",
    "regime_5m_reason",
    "regime_15m_reason",
    "regime_1m_strength_percentile",
    "regime_5m_strength_percentile",
    "regime_15m_strength_percentile",
    "regime_1m_bbwp_percentile",
    "regime_5m_bbwp_percentile",
    "regime_15m_bbwp_percentile",
    "regime_1m_ema_gap_bps",
    "regime_5m_ema_gap_bps",
    "regime_15m_ema_gap_bps",
    "regime_1m_coiling",
    "regime_5m_coiling",
    "regime_15m_coiling",
    "regime_1m_range_cause_coiling",
    "regime_5m_range_cause_coiling",
    "regime_15m_range_cause_coiling",
    "regime_1m_range_cause_strength",
    "regime_5m_range_cause_strength",
    "regime_15m_range_cause_strength",
    "regime_1m_range_cause_gap",
    "regime_5m_range_cause_gap",
    "regime_15m_range_cause_gap",
    "regime_1m_range_cause_filter",
    "regime_5m_range_cause_filter",
    "regime_15m_range_cause_filter",
    "regime_1m_breakout_volume_ratio",
    "regime_5m_breakout_volume_ratio",
    "regime_15m_breakout_volume_ratio",
    "regime_range_filter_name",
    "regime_bbwp_threshold_pct",
    "regime_minimum_gap_bps",
    "regime_range_strength_threshold_pct",
    "regime_trend_strength_threshold_pct",
    "regime_breakout_volume_multiple",
)
CANONICAL_REGIME_TEXT_METRIC_FIELDS = frozenset(
    {name for name in CANONICAL_REGIME_METRIC_FIELDS if name.endswith("reason")}
    | {"regime_range_filter_name"}
)
CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS = frozenset(
    name for name in CANONICAL_REGIME_METRIC_FIELDS if "coiling" in name or "range_cause" in name
)
CANONICAL_COMPONENT_METRIC_FIELDS = (
    "ema_21_55_gap_bps",
    "ema_21_55_direction",
    "sma_100_200_gap_bps",
    "sma_100_200_direction",
    "ema_11_34_direction",
    "harsi_direction",
    "harsi_smoothed_rsi",
    "choppiness_14",
    "mtf_5m_bias",
    "mtf_15m_bias",
    "trend_slope_bps",
    "trend_r2",
    "self_aware_tqi",
)
CANONICAL_COMPONENT_CATEGORICAL_FIELDS = frozenset(
    {
        "ema_21_55_direction",
        "sma_100_200_direction",
        "ema_11_34_direction",
        "harsi_direction",
        "mtf_5m_bias",
        "mtf_15m_bias",
    }
)


def _regime_metrics(values: Mapping[str, object]) -> dict[str, ReadinessMetric]:
    """Copy typed canonical diagnostic values into report-only readiness."""
    output: dict[str, ReadinessMetric] = {}
    for name in CANONICAL_REGIME_METRIC_FIELDS:
        raw = values.get(name)
        if name in CANONICAL_REGIME_TEXT_METRIC_FIELDS:
            output[name] = _optional_text_metric(raw)
        elif name in CANONICAL_REGIME_BOOLEAN_METRIC_FIELDS:
            output[name] = _optional_boolean_metric(raw)
        else:
            output[name] = _optional_metric(raw)
    return output


def _regime_indicators(values: Mapping[str, object]) -> tuple[str, ...]:
    bbwp = _ratio_indicator(
        values.get("regime_5m_bbwp_percentile"),
        values.get("regime_bbwp_threshold_pct"),
    )
    gap = _ratio_indicator(
        values.get("regime_5m_ema_gap_bps"),
        values.get("regime_minimum_gap_bps"),
    )
    causes = _range_cause_indicator(values)
    return (f"5M BBWP {bbwp}", f"5M EMA GAP {gap}bps", causes)


def _range_cause_indicator(values: Mapping[str, object]) -> str:
    names = ("FILTER", "COILING", "WEAK", "GAP")
    fields = (
        "regime_5m_range_cause_filter",
        "regime_5m_range_cause_coiling",
        "regime_5m_range_cause_strength",
        "regime_5m_range_cause_gap",
    )
    active = [name for name, field in zip(names, fields, strict=True) if values.get(field) is True]
    return "5M RANGE CAUSES " + ("+".join(active) if active else "NONE/UNAVAILABLE")


def _ratio_indicator(value: object, threshold: object) -> str:
    left = _optional_metric(value)
    right = _optional_metric(threshold)
    if left is None or right is None:
        return "N/A"
    return f"{left:.1f}/{right:.1f}"


def _component_metrics(values: Mapping[str, object]) -> dict[str, ReadinessMetric]:
    metrics: dict[str, ReadinessMetric] = {
        "component_authority": "observe_only",
        "component_provenance": "causal_completed_1m_v1",
        "component_weight_mode": "unweighted_observe_v1",
    }
    for name in CANONICAL_COMPONENT_METRIC_FIELDS:
        raw = values.get(name)
        metrics[name] = (
            _optional_integer_metric(raw)
            if name in CANONICAL_COMPONENT_CATEGORICAL_FIELDS
            else _optional_metric(raw)
        )
    return metrics


def _component_indicators(values: Mapping[str, object]) -> tuple[str, ...]:
    return (
        _indicator("EMA21/55", values.get("ema_21_55_gap_bps"), "bps"),
        _indicator("SMA100/200", values.get("sma_100_200_gap_bps"), "bps"),
        _direction_indicator("EMA11/34", values.get("ema_11_34_direction")),
        _direction_indicator("HARSI", values.get("harsi_direction")),
        _indicator("CHOP14", values.get("choppiness_14"), ""),
        _bias_indicator(values),
        _indicator("TREND R2", values.get("trend_r2"), ""),
        _indicator("TQI", values.get("self_aware_tqi"), ""),
    )


def _indicator(label: str, value: object, suffix: str) -> str:
    number = _optional_metric(value)
    return f"{label} N/A" if number is None else f"{label} {number:+.2f}{suffix}"


def _direction_indicator(label: str, value: object) -> str:
    number = _optional_metric(value)
    state = (
        "N/A" if number is None else "UP" if number > 0.0 else "DOWN" if number < 0.0 else "NEUTRAL"
    )
    return f"{label} {state}"


def _bias_indicator(values: Mapping[str, object]) -> str:
    five = _optional_metric(values.get("mtf_5m_bias"))
    fifteen = _optional_metric(values.get("mtf_15m_bias"))
    left = "N/A" if five is None else f"{five:+.0f}"
    right = "N/A" if fifteen is None else f"{fifteen:+.0f}"
    return f"MTF BIAS 5M {left} / 15M {right}"


def _optional_metric(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_integer_metric(value: object) -> int | None:
    number = _optional_metric(value)
    if number is None:
        return None
    integer = int(number)
    if number != integer:
        raise ValueError("categorical regime component must be integer-valued")
    return integer


def _optional_boolean_metric(value: object) -> bool | None:
    return bool(value) if isinstance(value, (bool, np.bool_)) else None


def _optional_text_metric(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _validate_alignment(bars: pd.DataFrame, frame: pd.DataFrame) -> None:
    if not bars.index.equals(frame.index):
        raise ValueError("regime bars and derived frames must share one index")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("regime decision index must be unique and increasing")


def _optional_timestamp(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value


def _utc_timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("regime telemetry timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"canonical regime {label} must be non-empty text")
    return value.strip()


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"canonical regime {label} must be numeric")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"canonical regime {label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"canonical regime {label} must be finite")
    return result


def _positive_float(value: object, label: str) -> float:
    result = _finite_float(value, label)
    if result <= 0.0:
        raise ValueError(f"canonical regime {label} must be positive")
    return result
