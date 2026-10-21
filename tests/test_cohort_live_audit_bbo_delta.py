"""Executable-BBO episode maturity contracts for immutable audit deltas."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module

import pytest

from cohort_live_audit_delta_fixtures import audit as _audit

_PROVIDER = "test_fade_1m|BTC"


def test_delta_reports_newly_resolved_executable_bbo_episode() -> None:
    """A matured episode must expose its identity and after-cost economics."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _with_bbo(resolved=False)
    after = _with_bbo(resolved=True)

    delta = build(before, after)

    maturity = delta["executable_bbo_episode_maturity"]
    assert maturity["comparable"] is True
    assert maturity["newly_matured_episode_onsets"] is True
    assert maturity["providers_added"] == []
    provider = maturity["changed_providers"][0]
    assert provider["provider_symbol"] == _PROVIDER
    horizon = provider["horizons"]["60"]
    assert horizon["coverage_delta"] == {
        "eligible_signals": 0,
        "entry_matched": 0,
        "entry_censored": 0,
        "entry_gap": 0,
        "resolved": 1,
        "exit_censored": -1,
        "exit_gap": 0,
        "friction_contract_missing": 0,
    }
    assert horizon["independent_resolved_delta"] == 1
    assert horizon["after_modeled_friction_bps"] == {
        "mean_before": None,
        "mean_after": 12.5,
        "median_before": None,
        "median_after": 12.5,
        "leave_largest_before": None,
        "leave_largest_after": None,
    }
    assert horizon["new_independent_paths"][0]["decision_time_ms"] == 1_000
    assert delta["assessment"]["executable_bbo_episode_maturity_change"] is True
    assert delta["assessment"]["journal_revision_recommended"] is True


def test_delta_reports_new_right_censored_provider_without_false_maturity() -> None:
    """A first unresolved provider episode is evidence, but not a scored path."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _audit(row_count=10, timestamp="2026-08-08T10:00:00+00:00")
    before["orderbook_opportunity"] = _orderbook({})
    after = _with_bbo(resolved=False)

    delta = build(before, after)

    maturity = delta["executable_bbo_episode_maturity"]
    assert maturity["providers_added"] == [_PROVIDER]
    assert maturity["newly_matured_episode_onsets"] is False
    assert maturity["path_identity_complete"] is True
    horizon = maturity["changed_providers"][0]["horizons"]["60"]
    assert horizon["coverage_delta"]["eligible_signals"] == 1
    assert horizon["coverage_delta"]["exit_censored"] == 1
    assert horizon["independent_resolved_delta"] == 0
    assert delta["assessment"]["journal_revision_recommended"] is False


def test_delta_rejects_rewritten_resolved_executable_bbo_path() -> None:
    """A previously published resolved BBO path cannot change in-place."""
    build = import_module(
        "hypervector.research.cohort_live_audit_delta"
    ).build_live_audit_delta
    before = _with_bbo(resolved=True)
    after = deepcopy(before)
    after["run"]["row_count"] = 30
    after["run"]["last_observed_at_utc"] = "2026-08-08T12:00:00+00:00"
    episode = _episode(after)
    episode["independent_paths"][0]["after_modeled_friction_bps"] = -99.0

    with pytest.raises(ValueError, match="resolved executable BBO path cannot change"):
        build(before, after)


def _with_bbo(*, resolved: bool) -> dict[str, object]:
    result = _audit(
        row_count=20 if resolved else 10,
        timestamp=(
            "2026-08-08T11:00:00+00:00" if resolved else "2026-08-08T10:00:00+00:00"
        ),
    )
    result["orderbook_opportunity"] = _orderbook(
        {_PROVIDER: _provider(resolved=resolved)}
    )
    return result


def _orderbook(providers: dict[str, object]) -> dict[str, object]:
    return {"eligible_signal_context": {"by_provider_symbol": providers}}


def _provider(*, resolved: bool) -> dict[str, object]:
    return {
        "executable_bbo_markouts": {
            "horizons": {"60": {"episode_onsets": _episode_payload(resolved)}}
        }
    }


def _episode_payload(resolved: bool) -> dict[str, object]:
    count = int(resolved)
    return {
        "status": "available",
        "provider_cadence_minutes": 1,
        "coverage": {
            "eligible_signals": 1,
            "entry_matched": 1,
            "entry_censored": 0,
            "entry_gap": 0,
            "resolved": count,
            "exit_censored": 1 - count,
            "exit_gap": 0,
            "friction_contract_missing": 0,
        },
        "independent_resolved": count,
        "all": _group(count, 12.5 if resolved else None),
        "by_side": {
            "long": _group(count, 12.5 if resolved else None),
            "short": _group(0, None),
        },
        "by_pressure_stance": {
            "aligned": _group(count, 12.5 if resolved else None),
            "neutral": _group(0, None),
            "opposed": _group(0, None),
            "unavailable": _group(0, None),
        },
        "independent_paths": [_path()] if resolved else [],
    }


def _group(paths: int, value: float | None) -> dict[str, object]:
    return {
        "paths": paths,
        "mean_after_modeled_friction_bps": value,
        "median_after_modeled_friction_bps": value,
        "mean_excluding_largest_after_modeled_friction_bps": None,
    }


def _path() -> dict[str, object]:
    return {
        "source_run_id": "run-1",
        "decision_time_ms": 1_000,
        "signal_available_time_ms": 1_100,
        "entry_book_time_ms": 1_200,
        "exit_book_time_ms": 3_601_200,
        "horizon_minutes": 60,
        "side": "long",
        "after_modeled_friction_bps": 12.5,
    }


def _episode(audit: dict[str, object]) -> dict[str, object]:
    orderbook = audit["orderbook_opportunity"]
    assert isinstance(orderbook, dict)
    context = orderbook["eligible_signal_context"]
    assert isinstance(context, dict)
    providers = context["by_provider_symbol"]
    assert isinstance(providers, dict)
    provider = providers[_PROVIDER]
    assert isinstance(provider, dict)
    markouts = provider["executable_bbo_markouts"]
    assert isinstance(markouts, dict)
    horizons = markouts["horizons"]
    assert isinstance(horizons, dict)
    horizon = horizons["60"]
    assert isinstance(horizon, dict)
    episode = horizon["episode_onsets"]
    assert isinstance(episode, dict)
    return episode
