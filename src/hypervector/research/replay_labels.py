"""Conservative annotation labels from maker fill-assumption challengers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.research.maker_replay_models import (
    MakerReplayLifecycle,
    MakerReplayReport,
)

REQUIRED_FILL_RULES: tuple[str, ...] = ("touch", "through", "trade-through")
_RESOLVED_ZERO = frozenset(("expired", "canceled"))
_LABEL_COLUMNS: tuple[str, ...] = (
    "direction",
    "signal_time_utc",
    "signal_ts_ms",
    "outcome_ts_ms",
    "label",
    "touch_status",
    "through_status",
    "trade-through_status",
)
_BAR_DURATION = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class ReplayLabelResult:
    """Resolved labels plus explicit disagreement and censoring counts."""

    rows: pd.DataFrame
    nominal_signals: int
    resolved_signals: int
    unresolved_signals: int
    disagreement_signals: int
    positive_rate: float | None

    def summary(self) -> dict[str, int | float | None]:
        """Return JSON-safe label coverage metrics."""
        return {
            "nominal_signals": self.nominal_signals,
            "resolved_signals": self.resolved_signals,
            "unresolved_signals": self.unresolved_signals,
            "disagreement_signals": self.disagreement_signals,
            "positive_rate": self.positive_rate,
        }


def attach_runtime_features(labels: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Attach point-in-time 1m features using only bars closed by signal time."""
    if "signal_ts_ms" not in labels.columns:
        raise ValueError("replay labels require signal_ts_ms")
    if "timestamp" in bars.columns:
        timestamps = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    elif isinstance(bars.index, pd.DatetimeIndex):
        timestamps = bars.index
        if timestamps.tz is None:
            timestamps = timestamps.tz_localize("UTC")
        else:
            timestamps = timestamps.tz_convert("UTC")
    else:
        raise ValueError(
            "replay feature bars require a timestamp column or DatetimeIndex"
        )
    if timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise ValueError("replay feature bar timestamps must be unique and increasing")

    features = build_feature_matrix(bars, include_book=False).copy()
    features.index = timestamps + _BAR_DURATION
    signal_times = pd.DatetimeIndex(
        pd.to_datetime(labels["signal_ts_ms"], unit="ms", utc=True)
    )
    selected = features.reindex(signal_times)
    if selected.isna().any(axis=None):
        missing = signal_times[selected.isna().any(axis=1)].astype(str).tolist()
        raise ValueError(f"no completed 1m feature bar for signal times: {missing[:5]}")

    output = labels.reset_index(drop=True).copy()
    output[list(FEATURE_NAMES)] = selected.reset_index(drop=True)[list(FEATURE_NAMES)]
    return output


def _identity(lifecycle: MakerReplayLifecycle) -> tuple[str, str]:
    return lifecycle.direction, lifecycle.signal_time_utc


def _outcome(lifecycle: MakerReplayLifecycle) -> int | None:
    if lifecycle.status == "target_completed":
        return 1
    if lifecycle.status in _RESOLVED_ZERO:
        return 0
    return None


def _timestamp_ms(value: str) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"replay lifecycle timestamp is not timezone-aware: {value}")
    return int(timestamp.timestamp() * 1_000)


def _lifecycle_maps(
    reports: dict[str, MakerReplayReport],
) -> dict[str, dict[tuple[str, str], MakerReplayLifecycle]]:
    missing = set(REQUIRED_FILL_RULES).difference(reports)
    if missing:
        raise ValueError(f"replay labels missing fill rules: {sorted(missing)}")
    return {
        rule: {_identity(item): item for item in reports[rule].lifecycles}
        for rule in REQUIRED_FILL_RULES
    }


def _resolved_row(
    identity: tuple[str, str],
    lifecycles: tuple[MakerReplayLifecycle, ...],
    label: int,
) -> dict[str, object] | None:
    outcomes = [item.outcome_time_utc for item in lifecycles]
    if any(value is None for value in outcomes):
        return None
    outcome_values = [str(value) for value in outcomes]
    return {
        "direction": identity[0],
        "signal_time_utc": identity[1],
        "signal_ts_ms": _timestamp_ms(identity[1]),
        "outcome_ts_ms": max(_timestamp_ms(value) for value in outcome_values),
        "label": label,
        **{
            f"{rule}_status": item.status
            for rule, item in zip(REQUIRED_FILL_RULES, lifecycles, strict=True)
        },
    }


def build_conservative_replay_labels(
    reports: dict[str, MakerReplayReport],
) -> ReplayLabelResult:
    """Label only signals with resolved, agreeing outcomes under all fill rules."""
    maps = _lifecycle_maps(reports)
    identities = sorted(set().union(*(set(values) for values in maps.values())))
    rows: list[dict[str, object]] = []
    disagreements = 0
    for identity in identities:
        lifecycles = tuple(maps[rule].get(identity) for rule in REQUIRED_FILL_RULES)
        if any(item is None for item in lifecycles):
            disagreements += 1
            continue
        complete = tuple(item for item in lifecycles if item is not None)
        outcomes = tuple(_outcome(item) for item in complete)
        resolved = {outcome for outcome in outcomes if outcome is not None}
        if len(resolved) > 1 or (resolved and any(item is None for item in outcomes)):
            disagreements += 1
            continue
        if not resolved:
            continue
        row = _resolved_row(identity, complete, resolved.pop())
        if row is not None:
            rows.append(row)
    frame = pd.DataFrame(rows, columns=_LABEL_COLUMNS)
    positive_rate = None if frame.empty else float(frame["label"].mean())
    return ReplayLabelResult(
        rows=frame,
        nominal_signals=len(identities),
        resolved_signals=len(frame),
        unresolved_signals=len(identities) - len(frame),
        disagreement_signals=disagreements,
        positive_rate=positive_rate,
    )
