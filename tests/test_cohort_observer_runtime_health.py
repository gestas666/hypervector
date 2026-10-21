"""Schedule-aware observer runtime continuity tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypervector.research.cohort_observer_runtime_health import (
    observer_runtime_coverage_gaps,
)


def test_late_scheduled_decision_is_not_hidden_by_fresh_heartbeats() -> None:
    """Timely heartbeats cannot validate an evaluation submitted after its cap."""
    identity = _row(
        "configuration_identity",
        {
            "providers": [
                {
                    "strategy_id": "provider-a",
                    "symbols": ["BTC"],
                    "timeframe": "30m",
                    "maximum_entry_delay_seconds": 30,
                }
            ]
        },
        _time(0),
    )
    heartbeats = [
        _row("heartbeat", {"status": "running"}, _time(offset))
        for offset in range(3, 1_804, 30)
    ]
    routings = [
        _routing(0, 2),
        _routing(1_800, 1_831),
    ]
    records = sorted([identity, *heartbeats, *routings], key=_observed_at)

    assert observer_runtime_coverage_gaps(records, identity) == [
        "observer_heartbeat_gap_exceeds_entry_delay"
    ]


def test_startup_unavailability_shares_the_preactivation_cycle_boundary() -> None:
    """One unavailable seed must not become an off-grid prospective decision."""
    providers = [
        {
            "strategy_id": strategy,
            "symbols": [symbol],
            "timeframe": "1m",
            "maximum_entry_delay_seconds": 30,
        }
        for strategy, symbol in (("provider-a", "BTC"), ("provider-b", "ETH"))
    ]
    identity = _row("configuration_identity", {"providers": providers}, _time(1))
    startup = _row(
        "intent_routing",
        {
            "evaluations": [
                {
                    "strategy_id": "provider-a",
                    "symbol": "BTC",
                    "decision_time_ms": _milliseconds(-60),
                    "backend_non_action_reason": "pre_activation_readiness_seed",
                },
                {
                    "strategy_id": "provider-b",
                    "symbol": "ETH",
                    "decision_time_ms": _milliseconds(2),
                    "backend_non_action_reason": "source_unavailable",
                },
            ]
        },
        _time(2),
    )
    prospective = _row(
        "intent_routing",
        {
            "evaluations": [
                {
                    "strategy_id": strategy,
                    "symbol": symbol,
                    "decision_time_ms": _milliseconds(60),
                }
                for strategy, symbol in (("provider-a", "BTC"), ("provider-b", "ETH"))
            ]
        },
        _time(65),
    )
    heartbeat = _row("heartbeat", {"status": "running"}, _time(92))

    assert (
        observer_runtime_coverage_gaps(
            [identity, startup, prospective, heartbeat], identity
        )
        == []
    )


def test_timely_polling_status_covers_its_scheduled_boundary() -> None:
    """An explicit bars-incomplete status proves a provider checked on time."""
    identity = _row(
        "configuration_identity",
        {
            "providers": [
                {
                    "strategy_id": "cash-open-provider",
                    "symbols": ["xyz:BBB"],
                    "timeframe": "15m",
                    "maximum_entry_delay_seconds": 30,
                }
            ]
        },
        _time(1),
    )
    status = _polling_status(decision_offset=903, arrival_offset=915)
    heartbeat = _row("heartbeat", {"status": "running"}, _time(930))

    assert observer_runtime_coverage_gaps([identity, status, heartbeat], identity) == []


def test_late_polling_status_does_not_cover_its_scheduled_boundary() -> None:
    """A status arriving after the entry-delay cap must preserve the gap."""
    identity = _row(
        "configuration_identity",
        {
            "providers": [
                {
                    "strategy_id": "cash-open-provider",
                    "symbols": ["xyz:BBB"],
                    "timeframe": "15m",
                    "maximum_entry_delay_seconds": 30,
                }
            ]
        },
        _time(1),
    )
    status = _polling_status(decision_offset=903, arrival_offset=931)
    heartbeat = _row("heartbeat", {"status": "running"}, _time(961))

    assert observer_runtime_coverage_gaps([identity, status, heartbeat], identity) == [
        "observer_heartbeat_gap_exceeds_entry_delay"
    ]


def _polling_status(*, decision_offset: int, arrival_offset: int) -> dict[str, object]:
    evaluation = {
        "strategy_id": "cash-open-provider",
        "symbol": "xyz:BBB",
        "decision_time_ms": _milliseconds(decision_offset),
        "backend_non_action_reason": "cash_open_trade_bars_incomplete",
    }
    return _row(
        "intent_routing",
        {"evaluations": [evaluation]},
        _time(arrival_offset),
    )


def _routing(decision_offset: int, arrival_offset: int) -> dict[str, object]:
    evaluation = {
        "strategy_id": "provider-a",
        "symbol": "BTC",
        "decision_time_ms": _milliseconds(decision_offset),
    }
    return _row(
        "intent_routing",
        {"evaluations": [evaluation]},
        _time(arrival_offset),
    )


def _row(
    event_type: str,
    payload: dict[str, object],
    observed_at_utc: str,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "observed_at_utc": observed_at_utc,
        "payload": payload,
    }


def _observed_at(record: dict[str, object]) -> str:
    value = record["observed_at_utc"]
    assert isinstance(value, str)
    return value


def _time(offset_seconds: int) -> str:
    value = datetime(2026, 8, 1, 12, tzinfo=timezone.utc) + timedelta(
        seconds=offset_seconds
    )
    return value.isoformat()


def _milliseconds(offset_seconds: int) -> int:
    return int(
        (
            datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
            + timedelta(seconds=offset_seconds)
        ).timestamp()
        * 1_000
    )
