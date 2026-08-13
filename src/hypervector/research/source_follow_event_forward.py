"""Side-aware forward paths for live source-follow onset decisions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
from statistics import median
from typing import Literal

from hypervector.research.source_follow_range_forward import (
    RangeDecision,
    audit_range_forward_paths,
)

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class SourceEventDecision:
    """One confidence-qualified directional onset before the range gate."""

    sequence: int
    feed_at_utc: datetime
    available_at_utc: datetime
    reference_price: float
    direction: Direction
    signal_range_bps: float
    entry_allowed: bool
    exclusion_reason: str | None

    def __post_init__(self) -> None:
        _require_utc(self.feed_at_utc, "source-event feed time")
        _require_utc(self.available_at_utc, "source-event availability time")
        if self.available_at_utc <= self.feed_at_utc:
            raise ValueError("source-event availability must follow its feed time")
        _positive(self.reference_price, "source-event reference price")
        _nonnegative(self.signal_range_bps, "source-event range")


@dataclass(frozen=True)
class SourceEventMeasurementContract:
    """Thresholds and target reported by one live run at startup."""

    profile_id: str
    profile_fingerprint: str
    symbol: str
    minimum_range_bps: float
    maximum_range_bps: float
    target_price_fraction: float

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.profile_fingerprint.strip():
            raise ValueError("source-event profile identity must be non-empty")
        if not self.symbol.strip():
            raise ValueError("source-event contract symbol must be non-empty")
        _nonnegative(self.minimum_range_bps, "minimum range")
        _positive(self.maximum_range_bps, "maximum range")
        _positive(self.target_price_fraction, "target price fraction")
        if self.minimum_range_bps > self.maximum_range_bps:
            raise ValueError("minimum range must not exceed maximum range")


def extract_source_event_measurement_contract(
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: str,
) -> SourceEventMeasurementContract:
    """Extract the measurement parameters asserted by one live process."""
    identities = [
        row
        for row in rows
        if row.get("run_id") == run_id
        and row.get("event_type") == "configuration_identity"
    ]
    if len(identities) != 1:
        raise ValueError(
            f"live run requires exactly one configuration identity: {run_id}"
        )
    row = identities[0]
    payload = _mapping(row.get("payload"), "configuration identity payload")
    regime = _mapping(payload.get("regime_policy"), "regime policy")
    exits = _mapping(payload.get("exits"), "exit policy")
    return SourceEventMeasurementContract(
        profile_id=_text(row.get("profile_id"), "profile id"),
        profile_fingerprint=_text(
            row.get("profile_fingerprint"), "profile fingerprint"
        ),
        symbol=_text(payload.get("symbol"), "symbol"),
        minimum_range_bps=_nonnegative(
            regime.get("minimum_completed_5m_range_bps"), "minimum range"
        ),
        maximum_range_bps=_positive(
            regime.get("maximum_completed_5m_range_bps"), "maximum range"
        ),
        target_price_fraction=_positive(
            exits.get("target_price_fraction"), "target price fraction"
        ),
    )


def extract_source_event_decisions(
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: str,
) -> tuple[SourceEventDecision, ...]:
    """Extract all pre-range directional source events from one live run."""
    if not run_id.strip():
        raise ValueError("source-event forward audit run_id must be non-empty")
    selected: list[SourceEventDecision] = []
    for row in rows:
        if row.get("run_id") != run_id or row.get("event_type") != "regime_decision":
            continue
        payload = _mapping(row.get("payload"), "regime decision payload")
        if payload.get("source_event") is not True:
            continue
        selected.append(_event_decision(row, payload))
    ordered = tuple(sorted(selected, key=lambda item: item.available_at_utc))
    times = [item.available_at_utc for item in ordered]
    if len(times) != len(set(times)):
        raise ValueError("live run contains duplicate source-event timestamps")
    return ordered


def audit_source_event_forward_paths(
    database_path: Path,
    events: Sequence[SourceEventDecision],
    *,
    symbol: str,
    target_price_fraction: float,
    minimum_range_bps: float,
    maximum_range_bps: float,
    horizons_minutes: Sequence[int] = (5, 15, 30, 60),
) -> dict[str, object]:
    """Measure direction-aware paths without assuming an order or fill."""
    horizons = _validated_contract(
        symbol,
        target_price_fraction,
        minimum_range_bps,
        maximum_range_bps,
        horizons_minutes,
    )
    if not events:
        return _empty_report(
            symbol,
            target_price_fraction,
            minimum_range_bps,
            maximum_range_bps,
            horizons,
        )
    base = audit_range_forward_paths(
        database_path,
        tuple(_range_decision(item) for item in events),
        symbol=symbol,
        target_price_fraction=target_price_fraction,
        horizons_minutes=horizons,
    )
    paths = _enriched_paths(
        events, base, horizons, minimum_range_bps, maximum_range_bps
    )
    admissions = [
        _admission(item, minimum_range_bps, maximum_range_bps) for item in events
    ]
    return {
        **_contract(
            symbol, target_price_fraction, minimum_range_bps, maximum_range_bps
        ),
        "event_rows": len(events),
        "latest_trade_at_utc": base.get("latest_trade_at_utc"),
        "event_distribution": dict(sorted(Counter(admissions).items())),
        "horizons": _horizon_summaries(paths, horizons, admissions),
        "paths": paths,
        "limitations": _limitations(),
    }


def _event_decision(
    row: Mapping[str, object],
    payload: Mapping[str, object],
) -> SourceEventDecision:
    sequence = row.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError("source-event sequence must be an integer")
    direction = payload.get("structural_direction")
    if direction not in {"long", "short"}:
        raise ValueError("source event requires a long or short structural direction")
    entry_allowed = payload.get("entry_allowed")
    if not isinstance(entry_allowed, bool):
        raise ValueError("source-event entry_allowed must be boolean")
    reason = payload.get("regime_reason")
    if reason is not None and not isinstance(reason, str):
        raise ValueError("source-event regime reason must be text or null")
    return SourceEventDecision(
        sequence=sequence,
        feed_at_utc=_utc(payload.get("feed_ts"), "source-event feed timestamp"),
        available_at_utc=_utc(
            payload.get("available_at_utc"), "source-event availability timestamp"
        ),
        reference_price=_positive(
            payload.get("reference_price"), "source-event reference price"
        ),
        direction=direction,
        signal_range_bps=_nonnegative(
            payload.get("source_follow_signal_range_bps"), "source-event range"
        ),
        entry_allowed=entry_allowed,
        exclusion_reason=reason,
    )


def _validated_contract(
    symbol: str,
    target: float,
    minimum: float,
    maximum: float,
    horizons: Sequence[int],
) -> tuple[int, ...]:
    if not symbol.strip():
        raise ValueError("source-event symbol must be non-empty")
    _positive(target, "target price fraction")
    _nonnegative(minimum, "minimum range")
    _positive(maximum, "maximum range")
    if minimum > maximum:
        raise ValueError("minimum range must not exceed maximum range")
    if not horizons or any(
        isinstance(value, bool) or not isinstance(value, int) for value in horizons
    ):
        raise ValueError("source-event horizons must be non-empty integer minutes")
    if any(value <= 0 for value in horizons) or len(horizons) != len(set(horizons)):
        raise ValueError("source-event horizons must be positive and unique")
    return tuple(sorted(horizons))


def _empty_report(
    symbol: str,
    target: float,
    minimum: float,
    maximum: float,
    horizons: Sequence[int],
) -> dict[str, object]:
    return {
        **_contract(symbol, target, minimum, maximum),
        "event_rows": 0,
        "latest_trade_at_utc": None,
        "event_distribution": {},
        "horizons": {str(value): {} for value in horizons},
        "paths": [],
        "limitations": _limitations(),
    }


def _contract(
    symbol: str, target: float, minimum: float, maximum: float
) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "symbol": symbol,
        "target_price_fraction": target,
        "target_bps": target * 10_000.0,
        "minimum_range_bps": minimum,
        "maximum_range_bps": maximum,
    }


def _range_decision(event: SourceEventDecision) -> RangeDecision:
    return RangeDecision(
        sequence=event.sequence,
        feed_at_utc=event.feed_at_utc,
        available_at_utc=event.available_at_utc,
        reference_price=event.reference_price,
    )


def _enriched_paths(
    events: Sequence[SourceEventDecision],
    base: Mapping[str, object],
    horizons: Sequence[int],
    minimum: float,
    maximum: float,
) -> list[dict[str, object]]:
    raw_paths = base.get("paths")
    if not isinstance(raw_paths, list):
        raise ValueError("base forward audit paths must be a list")
    by_sequence = {_sequence(path): _mapping(path, "base path") for path in raw_paths}
    if len(by_sequence) != len(events):
        raise ValueError("base forward audit does not cover every source event")
    return [
        _enriched_path(event, by_sequence[event.sequence], horizons, minimum, maximum)
        for event in events
    ]


def _enriched_path(
    event: SourceEventDecision,
    base: Mapping[str, object],
    horizons: Sequence[int],
    minimum: float,
    maximum: float,
) -> dict[str, object]:
    raw_horizons = _mapping(base.get("horizons"), "base path horizons")
    return {
        "sequence": event.sequence,
        "feed_at_utc": event.feed_at_utc.isoformat(),
        "available_at_utc": event.available_at_utc.isoformat(),
        "reference_price": event.reference_price,
        "direction": event.direction,
        "signal_range_bps": event.signal_range_bps,
        "entry_allowed": event.entry_allowed,
        "exclusion_reason": event.exclusion_reason,
        "admission": _admission(event, minimum, maximum),
        "horizons": {
            str(value): _side_horizon(
                _mapping(raw_horizons.get(str(value)), "base path horizon"),
                event.direction,
            )
            for value in horizons
        },
    }


def _side_horizon(
    base: Mapping[str, object], direction: Direction
) -> dict[str, object]:
    upward = _optional_number(base.get("maximum_up_bps"), "maximum up")
    downward = _optional_number(base.get("maximum_down_bps"), "maximum down")
    ending = _optional_number(
        base.get("ending_displacement_bps"), "ending displacement"
    )
    target_key = "long_target_hit" if direction == "long" else "short_target_hit"
    favorable = upward if direction == "long" else downward
    adverse = downward if direction == "long" else upward
    signed_ending = ending if direction == "long" or ending is None else -ending
    return {
        **dict(base),
        "favorable_excursion_bps": favorable,
        "adverse_excursion_bps": adverse,
        "signed_ending_displacement_bps": signed_ending,
        "target_hit": _optional_bool(base.get(target_key), target_key),
    }


def _admission(event: SourceEventDecision, minimum: float, maximum: float) -> str:
    if event.entry_allowed:
        if not minimum <= event.signal_range_bps <= maximum:
            raise ValueError("runtime admitted a source event outside configured range")
        return "runtime_admitted"
    if event.signal_range_bps < minimum:
        return "range_below_minimum"
    if event.signal_range_bps > maximum:
        return "range_above_maximum"
    return "other_exclusion"


def _horizon_summaries(
    paths: Sequence[Mapping[str, object]],
    horizons: Sequence[int],
    admissions: Sequence[str],
) -> dict[str, object]:
    groups = sorted(set(admissions))
    return {
        str(minutes): {group: _group_summary(paths, minutes, group) for group in groups}
        for minutes in horizons
    }


def _group_summary(
    paths: Sequence[Mapping[str, object]],
    minutes: int,
    admission: str,
) -> dict[str, object]:
    selected = [item for item in paths if item.get("admission") == admission]
    rows = [
        _mapping(
            _mapping(item.get("horizons"), "path horizons").get(str(minutes)),
            "path horizon",
        )
        for item in selected
    ]
    usable = [item for item in rows if item.get("quality_usable") is True]
    return {
        "event_rows": len(rows),
        "usable_rows": len(usable),
        "target_rows": sum(item.get("target_hit") is True for item in usable),
        "median_favorable_excursion_bps": _median(usable, "favorable_excursion_bps"),
        "median_adverse_excursion_bps": _median(usable, "adverse_excursion_bps"),
        "median_signed_ending_displacement_bps": _median(
            usable, "signed_ending_displacement_bps"
        ),
    }


def _median(rows: Sequence[Mapping[str, object]], key: str) -> float | None:
    values = [
        value
        for row in rows
        if (value := _optional_number(row.get(key), key)) is not None
    ]
    return None if not values else float(median(values))


def _sequence(value: object) -> int:
    row = _mapping(value, "base path")
    sequence = row.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError("base path sequence must be an integer")
    return sequence


def _limitations() -> list[str]:
    return [
        "Paths begin at the decision reference; they do not assume an order or fill.",
        "Maker queue, fees, funding, slippage, and PnL are intentionally not inferred.",
        "Target touches measure directional follow-through, not executable profitability.",
        "Incomplete or recorder-gap horizons are excluded from group summaries.",
    ]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _finite(value, label)


def _optional_bool(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean or null")
    return value


def _positive(value: object, label: str) -> float:
    result = _finite(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative(value: object, label: str) -> float:
    result = _finite(value, label)
    if result < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    _require_utc(parsed, label)
    return parsed.astimezone(UTC)


def _require_utc(value: datetime, label: str) -> None:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC")
