"""Advisory venue-protection warnings for still-open cohort lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.live.cohort_breakeven_events import (
    BREAKEVEN_ATTEMPT_EVENT,
    RAISE_EXHAUSTED_EVENT,
)

Record = Mapping[str, object]
Lifecycle = tuple[str, int]


def protection_warnings(
    cohort_records: Sequence[Record],
    latest_snapshot: Record | None,
) -> list[dict[str, object]]:
    """Return exhausted venue-stop raises whose lifecycle is open and still unraised.

    A later successful raise for the same lifecycle clears its warning, and a
    lifecycle that has closed no longer carries one. Each open lifecycle reports
    at most one warning, stamped with its first unresolved exhaustion.
    """
    open_lifecycles = _open_lifecycles(latest_snapshot)
    if not open_lifecycles:
        return []
    warnings: dict[Lifecycle, dict[str, object]] = {}
    for row in cohort_records:
        event_type = row.get("event_type")
        if event_type not in {RAISE_EXHAUSTED_EVENT, BREAKEVEN_ATTEMPT_EVENT}:
            continue
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError(f"{event_type} payload must be an object")
        lifecycle = _lifecycle(payload, str(event_type))
        if lifecycle not in open_lifecycles:
            continue
        if event_type == BREAKEVEN_ATTEMPT_EVENT:
            if payload.get("raised") is True:
                warnings.pop(lifecycle, None)
            continue
        strategy = payload.get("strategy_id")
        warnings.setdefault(
            lifecycle,
            {
                "symbol": lifecycle[0],
                "strategy_id": strategy if isinstance(strategy, str) else None,
                "entry_oid": lifecycle[1],
                "reason": RAISE_EXHAUSTED_EVENT,
                "observed_at_utc": row.get("observed_at_utc"),
            },
        )
    return [warnings[key] for key in sorted(warnings)]


def _open_lifecycles(snapshot: Record | None) -> frozenset[Lifecycle]:
    if snapshot is None:
        return frozenset()
    payload = snapshot.get("payload")
    assets = payload.get("assets") if isinstance(payload, Mapping) else None
    if not isinstance(assets, list):
        return frozenset()
    return frozenset(
        (asset["symbol"], asset["entry_oid"])
        for asset in assets
        if isinstance(asset, Mapping)
        and isinstance(asset.get("symbol"), str)
        and _oid(asset.get("entry_oid"))
        and asset.get("position_size_signed") not in {None, 0, 0.0}
    )


def _lifecycle(payload: Mapping[str, object], event_type: str) -> Lifecycle:
    symbol, entry_oid = payload.get("symbol"), payload.get("entry_oid")
    if not isinstance(symbol, str) or not symbol.strip() or not _oid(entry_oid):
        raise ValueError(f"{event_type} requires symbol and entry_oid")
    return symbol, entry_oid  # type: ignore[return-value]


def _oid(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
