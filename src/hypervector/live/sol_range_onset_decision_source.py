"""Convert completed Hyperliquid candles into causal SOL live decisions."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import math

import numpy as np
import pandas as pd

from hypervector.live.sol_range_onset_controller import SolLiveDecision
from hypervector.live.provider_readiness import ReadinessMetric, SignalReadiness
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.component_telemetry import build_regime_component_frame
from hypervector.research.range_onset_observation import (
    completed_range_onset_bars,
)
from hypervector.research.range_onset_signals import build_range_onset_signals

_MINUTE = pd.Timedelta(minutes=1)


def build_completed_live_decisions(
    raw_bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int | None = None,
) -> tuple[SolLiveDecision, ...]:
    """Return every unseen completed-bar decision in chronological order."""
    after = _optional_timestamp(after_decision_time_ms)
    bars = completed_range_onset_bars(raw_bars, observed_at=observed_at)
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


_CompletedFrames = tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]
# Per poll: distinct windows remembered, and decisions kept for each. The
# retained suffix covers every steady-state lookback (at most 61 bars), so one
# frame build serves every consumer of a window; seed queries beyond it rebuild.
_SHARED_WINDOW_LIMIT = 64
_SHARED_DECISION_LIMIT = 128
_SHARED_DECISIONS: ContextVar[
    OrderedDict[tuple[object, ...], tuple[int, tuple[SolLiveDecision, ...]]] | None
] = ContextVar("completed_decision_cycle", default=None)


@contextmanager
def shared_completed_decisions() -> Iterator[None]:
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
    """Build every indicator frame for one completed window, classifying once."""
    regimes = classify_multitimeframe(bars)
    signals = build_range_onset_signals(bars, regimes=regimes)
    _validate_alignment(bars, signals, regimes)
    components = build_regime_component_frame(bars)
    _validate_alignment(bars, components, regimes)
    return bars, signals, regimes, components


def _decisions(frames: _CompletedFrames, first: int) -> tuple[SolLiveDecision, ...]:
    """Decide every bar from ``first`` on, in order, raising at the first failure."""
    readers = tuple(_RowReader(frame) for frame in frames)
    index = frames[0].index
    decisions: list[SolLiveDecision] = []
    for start in range(first, len(index), _ROW_CHUNK):
        locations = np.arange(start, min(start + _ROW_CHUNK, len(index)))
        rows = zip(*(reader.rows(locations) for reader in readers), strict=True)
        for location, row in zip(locations, rows, strict=True):
            decisions.append(_decision_at(index, int(location), row))
    return tuple(decisions)


def _decision_at(
    index: pd.Index, location: int, row: tuple[Mapping[str, object], ...]
) -> SolLiveDecision:
    decision_time = pd.Timestamp(index[location]) + _MINUTE
    decision_ms = int(decision_time.timestamp() * 1_000)
    return _decision_from_rows(decision_ms, *row)


def _retained_suffix(
    frames: _CompletedFrames,
    first: int,
    decisions: tuple[SolLiveDecision, ...],
) -> tuple[int, tuple[SolLiveDecision, ...]]:
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
    older: list[SolLiveDecision] = []
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
        if len(frame) == 0 or frame.columns.has_duplicates:
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
    signal: Mapping[str, object],
    regime: Mapping[str, object],
    components: Mapping[str, object],
) -> SolLiveDecision:
    return SolLiveDecision(
        decision_time_ms=decision_time_ms,
        reference_price=_positive_float(bar.get("close"), "close"),
        long_entry=_boolean(signal.get("long_entry"), "long_entry"),
        short_entry=_boolean(signal.get("short_entry"), "short_entry"),
        long_exit=_boolean(signal.get("long_exit"), "long_exit"),
        short_exit=_boolean(signal.get("short_exit"), "short_exit"),
        primary_regime=_text(regime.get("primary_regime"), "primary_regime"),
        state_1m=_text(regime.get("state_1m"), "state_1m"),
        state_5m=_text(regime.get("state_5m"), "state_5m"),
        context_15m=_text(regime.get("context_15m"), "context_15m"),
        confidence=_finite_float(regime.get("confidence"), "confidence"),
        structural_direction=_text(
            signal.get("structural_direction"),
            "structural_direction",
        ),
        regime_admitted=_boolean(signal.get("regime_admitted"), "regime_admitted"),
        open_price=_positive_float(bar.get("open"), "open"),
        high_price=_positive_float(bar.get("high"), "high"),
        low_price=_positive_float(bar.get("low"), "low"),
        volume=_nonnegative_float(bar.get("volume"), "volume"),
        readiness=_range_readiness(signal, regime, components),
        breakout_side=_regime_breakout_side(regime),
    )


def _regime_breakout_side(regime: Mapping[str, object]) -> str | None:
    if regime.get("state_5m") != "BREAKOUT":
        return None
    value = regime.get("structural_direction")
    if value in {None, "neutral"} or pd.isna(value):
        return None
    if value not in {"long", "short"}:
        raise ValueError("5m breakout structural_direction must be long or short")
    return str(value)


def _range_readiness(
    signal: Mapping[str, object],
    regime: Mapping[str, object],
    components: Mapping[str, object],
) -> SignalReadiness:
    fields = signal.index if isinstance(signal, pd.Series) else signal.keys()
    if not _RANGE_READINESS_FIELDS.issubset(fields):
        return _unavailable_readiness()
    fast = float(signal["sma_fast"])  # type: ignore[arg-type]
    slow = float(signal["sma_slow"])  # type: ignore[arg-type]
    gap = float(signal["sma_gap_bps"])  # type: ignore[arg-type]
    history_ready = all(math.isfinite(value) for value in (fast, slow, gap))
    long_cross = bool(signal["raw_long_cross"])
    short_cross = bool(signal["raw_short_cross"])
    crossed = long_cross or short_cross
    admitted = bool(signal["regime_admitted"])
    conditions = (history_ready, admitted, crossed)
    blockers = tuple(name for name, met in zip(_RANGE_BLOCKERS, conditions, strict=True) if not met)
    structural = str(signal["structural_direction"])
    side = (
        "long"
        if long_cross or (not short_cross and structural == "long")
        else "short"
        if short_cross or structural == "short"
        else None
    )
    context_indicator, context_admitted = _dual_mtf_challenger(side, components)
    return SignalReadiness(
        side=side,
        conditions_met=sum(conditions),
        conditions_required=len(conditions),
        blockers=blockers,
        indicators=(
            _sma_value("SMA10", fast),
            _sma_value("SMA30", slow),
            _sma_gap(gap),
            f"RAW CROSS {'LONG' if long_cross else 'SHORT' if short_cross else 'NONE'}",
            f"5m REGIME {'ADMITTED' if admitted else 'BLOCKED'}",
            f"STRUCT {structural.upper()}",
            *_regime_indicators(regime),
            *_component_indicators(components),
            context_indicator,
        ),
        metrics={
            **_range_metrics(fast, slow, gap, long_cross, short_cross, admitted, structural),
            **_regime_metrics(regime),
            **_component_metrics(components),
            "dual_mtf_context_challenger_admitted": context_admitted,
            "dual_mtf_context_challenger_authority": "report_only",
        },
    )


_RANGE_READINESS_FIELDS = {
    "raw_long_cross",
    "raw_short_cross",
    "sma_fast",
    "sma_slow",
    "sma_gap_bps",
    "regime_admitted",
    "structural_direction",
}
_RANGE_BLOCKERS = (
    "hourly_sma_warmup",
    "5m_regime_not_admitted",
    "awaiting_hourly_sma_cross",
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


def _range_metrics(
    fast: float,
    slow: float,
    gap: float,
    long_cross: bool,
    short_cross: bool,
    admitted: bool,
    structural: str,
) -> dict[str, ReadinessMetric]:
    return {
        "raw_long_cross": long_cross,
        "raw_short_cross": short_cross,
        "regime_admitted": admitted,
        "sma_fast": _optional_metric(fast),
        "sma_gap_bps": _optional_metric(gap),
        "sma_slow": _optional_metric(slow),
        "structural_direction": structural,
    }


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


CANONICAL_COMPONENT_METRIC_FIELDS = (
    "ema_21_55_gap_bps",
    "ema_21_55_direction",
    "sma_100_200_gap_bps",
    "sma_100_200_direction",
    "cipher_a_direction",
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
        "cipher_a_direction",
        "harsi_direction",
        "mtf_5m_bias",
        "mtf_15m_bias",
    }
)


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


def _component_indicators(values: Mapping[str, object]) -> tuple[str, ...]:
    return (
        _indicator("EMA21/55", values.get("ema_21_55_gap_bps"), "bps"),
        _indicator("SMA100/200", values.get("sma_100_200_gap_bps"), "bps"),
        _direction_indicator("CIPHER A", values.get("cipher_a_direction")),
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


def _dual_mtf_challenger(
    side: str | None,
    values: Mapping[str, object],
) -> tuple[str, bool | None]:
    five = _optional_metric(values.get("mtf_5m_bias"))
    fifteen = _optional_metric(values.get("mtf_15m_bias"))
    if side not in {"long", "short"} or five is None or fifteen is None:
        return "DUAL-MTF CHALLENGER N/A [REPORT ONLY]", None
    side_sign = 1.0 if side == "long" else -1.0
    opposed = five * side_sign < 0.0 and fifteen * side_sign < 0.0
    state = "OPPOSED" if opposed else "CLEAR"
    return f"DUAL-MTF CHALLENGER {state} [REPORT ONLY]", not opposed


def _sma_value(label: str, value: float) -> str:
    return f"{label} {value:.4f}" if math.isfinite(value) else f"{label} N/A"


def _sma_gap(value: float) -> str:
    return f"SMA GAP {value:+.1f}bps" if math.isfinite(value) else "SMA GAP N/A"


def _unavailable_readiness() -> SignalReadiness:
    return SignalReadiness(
        side=None,
        conditions_met=0,
        conditions_required=1,
        blockers=("indicator_telemetry_unavailable",),
        indicators=("INDICATOR TELEMETRY UNAVAILABLE",),
    )


def _validate_alignment(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    regimes: pd.DataFrame,
) -> None:
    if not bars.index.equals(signals.index) or not bars.index.equals(regimes.index):
        raise ValueError("SOL live bars, signals, and regimes must share one index")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("SOL live decision index must be unique and increasing")


def _optional_timestamp(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("after_decision_time_ms must be a nonnegative integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"SOL live {label} must be boolean")
    return bool(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"SOL live {label} must be non-empty text")
    return value.strip()


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"SOL live {label} must be numeric")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SOL live {label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"SOL live {label} must be finite")
    return result


def _positive_float(value: object, label: str) -> float:
    result = _finite_float(value, label)
    if result <= 0.0:
        raise ValueError(f"SOL live {label} must be positive")
    return result


def _nonnegative_float(value: object, label: str) -> float:
    result = _finite_float(value, label)
    if result < 0.0:
        raise ValueError(f"SOL live {label} must be nonnegative")
    return result
