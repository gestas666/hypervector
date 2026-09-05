"""Continuous V58 monitor transport-recovery wiring."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

_SCRIPT = Path("scripts/v58_continuous_improvement.py")


def test_monitor_retries_a_classified_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient funding read cannot permanently stop V58 consolidation."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise RuntimeError("temporary venue throttle")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(module, "RequestException", RuntimeError)
    monkeypatch.setattr(
        module,
        "continuous_transient_failure_reason",
        lambda _exc: "http_429_retry_exhausted",
    )
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=1.0, max_cycles=1)

    result = module.run_monitor(
        args,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
    )

    assert result == 0
    assert calls == [
        "refresh",
        "degraded:http_429_retry_exhausted",
        "sleep:1.0",
        "refresh",
    ]


def test_monitor_retries_an_exact_concurrent_snapshot_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An atomic status replacement cannot permanently stop consolidation."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise ValueError("V58 ETH lifecycle status changed during path evaluation")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=1.0, max_cycles=1)

    result = module.run_monitor(
        args,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
    )

    assert result == 0
    assert calls == [
        "refresh",
        "degraded:concurrent_source_refresh",
        "sleep:1.0",
        "refresh",
    ]


def test_monitor_retries_an_exact_stale_route_lifecycle_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A route collector refresh race cannot stop central consolidation."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise ValueError("route lifecycle status is stale")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=120.0, max_cycles=1)

    result = module.run_monitor(
        args,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
    )

    assert result == 0
    assert calls == [
        "refresh",
        "degraded:concurrent_source_refresh",
        "sleep:1.0",
        "refresh",
    ]


def test_monitor_retries_a_transient_unsynchronized_return_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One mixed-source candle cycle cannot permanently stop consolidation."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise ValueError("V58 return context is not synchronized across symbols")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=120.0, max_cycles=1)

    result = module.run_monitor(
        args,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
    )

    assert result == 0
    assert calls == [
        "refresh",
        "degraded:concurrent_source_refresh",
        "sleep:1.0",
        "refresh",
    ]


def test_monitor_retries_the_observed_eth_exit_policy_checkpoint_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact ETH policy checkpoint race cannot stop the monitor."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise ValueError("V58 checkpoint changed during ETH exit-policy evaluation")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=1.0, max_cycles=1)

    assert module.run_monitor(args, sleep_fn=lambda _value: None) == 0
    assert calls == [
        "refresh",
        "degraded:concurrent_source_refresh",
        "refresh",
    ]


def test_monitor_breaks_the_120_second_checkpoint_refresh_phase_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A snapshot race must retry off-phase instead of waiting a full cycle."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise ValueError("V58 checkpoint changed during ETH exit-policy evaluation")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=120.0, max_cycles=1)

    result = module.run_monitor(
        args,
        sleep_fn=lambda value: calls.append(f"sleep:{value}"),
    )

    assert result == 0
    assert calls == [
        "refresh",
        "degraded:concurrent_source_refresh",
        "sleep:1.0",
        "refresh",
    ]


def test_monitor_retries_report_only_venue_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public valuation outage must not permanently stop consolidation."""
    module = _module()
    calls: list[str] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        del generators
        calls.append("refresh")
        if calls.count("refresh") == 1:
            raise ValueError("V58 venue portfolio is temporarily unavailable")

    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    monkeypatch.setattr(
        module,
        "report_transient_watch_failure",
        lambda reason, _exc: calls.append(f"degraded:{reason}"),
    )
    args = SimpleNamespace(interval_seconds=1.0, max_cycles=1)

    assert module.run_monitor(args, sleep_fn=lambda _value: None) == 0
    assert calls == ["refresh", "degraded:venue_portfolio_unavailable", "refresh"]


def test_monitor_still_rejects_an_unclassified_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema and logic failures remain fatal instead of success-shaped."""
    module = _module()
    monkeypatch.setattr(module, "_generator_references", lambda: {})
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(
        module,
        "refresh",
        lambda _args, **_kwargs: (_ for _ in ()).throw(ValueError("schema is invalid")),
    )
    args = SimpleNamespace(interval_seconds=1.0, max_cycles=1)

    with pytest.raises(ValueError, match="schema is invalid"):
        module.run_monitor(args, sleep_fn=lambda _value: None)


def test_monitor_binds_every_refresh_to_startup_generator_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recurring process cannot publish evidence for newly edited source bytes."""
    module = _module()
    frozen = {Path("loaded.py"): {"sha256": "loaded", "bytes": 1}}
    received: list[object] = []

    def refresh(_args: object, *, generators: object = None) -> None:
        received.append(generators)

    monkeypatch.setattr(module, "_generator_references", lambda: frozen)
    monkeypatch.setattr(module, "_require_unchanged", lambda _frozen: None)
    monkeypatch.setattr(module, "refresh", refresh)
    args = SimpleNamespace(interval_seconds=1.0, max_cycles=1)

    assert module.run_monitor(args, sleep_fn=lambda _value: None) == 0
    assert received == [frozen]


def test_default_funding_loader_preserves_nonfunding_refreshes() -> None:
    """The recurring report must bind the explicit funding degradation boundary."""
    module = _module()

    assert module._ContinuousLoaders().funding.__name__ == (
        "load_resilient_live_v58_current_funding_context"
    )


def _module() -> ModuleType:
    spec = spec_from_file_location("v58_continuous_improvement_monitor", _SCRIPT)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
