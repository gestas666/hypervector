"""Strict provider-cadence extraction from cohort configuration identity."""

import pytest

from hypervector.research.cohort_live_audit_values import provider_cadence_minutes


def test_provider_cadence_comes_from_declared_minute_timeframes() -> None:
    """Mixed provider clocks remain explicit rather than inferred from rows."""
    assert provider_cadence_minutes(_identity("1m", "15m")) == {
        "provider_a": 1,
        "provider_b": 15,
    }


def test_provider_cadence_normalizes_whole_hour_timeframe() -> None:
    """A valid hourly provider clock is represented in whole minutes."""
    assert provider_cadence_minutes(_identity("1h", "15m")) == {
        "provider_a": 60,
        "provider_b": 15,
    }


def test_provider_cadence_rejects_unsupported_timeframe() -> None:
    """An unsupported clock cannot silently receive a guessed cadence."""
    with pytest.raises(ValueError, match="whole minutes or hours"):
        provider_cadence_minutes(_identity("90s", "15m"))


def test_provider_cadence_is_unavailable_when_identity_omits_a_clock() -> None:
    """A legacy provider without a clock must not abort unrelated telemetry."""
    identity = _identity("1m", "15m")
    providers = identity["payload"]["providers"]
    assert isinstance(providers, list)
    assert isinstance(providers[1], dict)
    providers[1].pop("timeframe")

    assert provider_cadence_minutes(identity) is None


def _identity(first: str, second: str) -> dict[str, object]:
    return {
        "payload": {
            "providers": [
                {
                    "strategy_id": "provider_a",
                    "symbols": ["BTC"],
                    "timeframe": first,
                },
                {
                    "strategy_id": "provider_b",
                    "symbols": ["ETH"],
                    "timeframe": second,
                },
            ]
        }
    }
