"""Tests for exact provider-symbol configuration-contract history."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.cohort_provider_contract_history import (
    build_provider_contract_history,
)

_HYPE = "test_fade_1m"
_ETH = "test_pullback_1m"


def test_unrelated_observer_does_not_erase_matching_hype_execution_history() -> None:
    """An ETH report-only addition must not invalidate an unchanged HYPE contract."""
    prior = _identity("prior-run", "prior-profile", [_provider(_HYPE, "HYPE")])
    current = _identity(
        "current-run",
        "current-profile",
        [_provider(_HYPE, "HYPE"), _provider(_ETH, "ETH", executable=False)],
    )
    report = build_provider_contract_history(
        [prior, current],
        current,
        [
            _trade("prior-run", "prior-profile", _HYPE, "HYPE", 1.0),
            _trade("current-run", "current-profile", _HYPE, "HYPE", -0.25),
        ],
    )

    performance = report["performance"]
    pair = performance["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert report["scope"] == "provider_execution_contract_history"
    assert report["compatible_trades"] == 2
    assert report["incompatible_trades"] == 0
    assert pair["closed_trades"] == 2
    assert pair["net_pnl_usd"] == pytest.approx(0.75)
    repeatability = report["repeatability"]["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert repeatability["closed_trades"] == 2
    assert repeatability["net_pnl_usd"] == pytest.approx(0.75)
    evidence = report["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert evidence["source_run_ids"] == ["current-run", "prior-run"]
    assert evidence["configuration_contract_match"] is True
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["performance_gate"] is False


def test_changed_target_exit_contract_is_not_pooled() -> None:
    """A changed stop must remain a different provider execution generation."""
    changed_provider = _provider(_HYPE, "HYPE")
    changed_provider["execution"]["stop_bps"] = 100.0
    changed = _identity("changed-run", "changed-profile", [changed_provider])
    current = _identity("current-run", "current-profile", [_provider(_HYPE, "HYPE")])
    report = build_provider_contract_history(
        [changed, current],
        current,
        [
            _trade("changed-run", "changed-profile", _HYPE, "HYPE", 5.0),
            _trade("current-run", "current-profile", _HYPE, "HYPE", -0.25),
        ],
    )

    pair = report["performance"]["by_provider_symbol"][f"{_HYPE}|HYPE"]
    assert report["compatible_trades"] == 1
    assert report["incompatible_trades"] == 1
    assert pair["closed_trades"] == 1
    assert pair["net_pnl_usd"] == pytest.approx(-0.25)


def test_omitted_default_recipe_exit_matches_explicit_ignore() -> None:
    """Legacy omission and the typed ignore default are one execution contract."""
    prior_provider = _provider(_HYPE, "HYPE")
    current_provider = _provider(_HYPE, "HYPE")
    current_provider["execution"]["provider_recipe_exit_policy"] = "ignore"
    prior = _identity("prior-run", "prior-profile", [prior_provider])
    current = _identity("current-run", "current-profile", [current_provider])

    report = build_provider_contract_history(
        [prior, current],
        current,
        [
            _trade("prior-run", "prior-profile", _HYPE, "HYPE", 1.0),
            _trade("current-run", "current-profile", _HYPE, "HYPE", 0.5),
        ],
    )

    assert report["compatible_trades"] == 2
    assert report["incompatible_trades"] == 0


def test_current_observe_only_pair_does_not_inherit_old_executable_outcomes() -> None:
    """Past authority cannot turn a current observer into an execution sample."""
    prior = _identity("prior-run", "prior-profile", [_provider(_ETH, "ETH")])
    current = _identity(
        "current-run",
        "current-profile",
        [_provider(_ETH, "ETH", executable=False)],
    )
    report = build_provider_contract_history(
        [prior, current],
        current,
        [_trade("prior-run", "prior-profile", _ETH, "ETH", 1.0)],
    )

    assert report["compatible_trades"] == 0
    assert report["not_currently_executable_trades"] == 1
    assert report["performance"]["by_provider_symbol"] == {}


def test_missing_source_identity_fails_instead_of_silently_dropping_a_trade() -> None:
    """Every reflected lifecycle must retain an auditable configuration source."""
    current = _identity("current-run", "current-profile", [_provider(_HYPE, "HYPE")])

    with pytest.raises(ValueError, match="source configuration identity"):
        build_provider_contract_history(
            [current],
            current,
            [_trade("missing-run", "missing-profile", _HYPE, "HYPE", 1.0)],
        )


def test_incomplete_legacy_source_contract_is_reported_unverifiable() -> None:
    """A legacy identity must not erase the checkpoint or masquerade as compatible."""
    legacy_provider = _provider(_HYPE, "HYPE")
    legacy_provider.pop("execution")
    legacy = _identity("legacy-run", "legacy-profile", [legacy_provider])
    current = _identity("current-run", "current-profile", [_provider(_HYPE, "HYPE")])

    report = build_provider_contract_history(
        [legacy, current],
        current,
        [_trade("legacy-run", "legacy-profile", _HYPE, "HYPE", 1.0)],
    )

    assert report["compatible_trades"] == 0
    assert report["unverifiable_source_contract_trades"] == 1
    assert report["performance"]["by_provider_symbol"] == {}


def test_missing_source_implementation_hash_is_explicit_not_a_sort_failure() -> None:
    """Mixed legacy/current implementation evidence must remain parseable and honest."""
    prior = _identity("prior-run", "prior-profile", [_provider(_HYPE, "HYPE")])
    prior["payload"].pop("prestart_backup")
    current = _identity("current-run", "current-profile", [_provider(_HYPE, "HYPE")])

    report = build_provider_contract_history(
        [prior, current],
        current,
        [
            _trade("prior-run", "prior-profile", _HYPE, "HYPE", 1.0),
            _trade("current-run", "current-profile", _HYPE, "HYPE", 0.5),
        ],
    )

    identity = report["by_provider_symbol"][f"{_HYPE}|HYPE"]["implementation_identity"]
    assert identity["source_sha256s"] == ["implementation-current-run"]
    assert identity["missing_source_run_ids"] == ["prior-run"]
    assert identity["equivalence_established"] is False


def test_empty_observer_history_is_not_applicable_instead_of_an_audit_failure() -> None:
    """No live outcomes means there is no execution contract to compare."""
    observer = _identity("observer-run", "observer-profile", [_provider(_HYPE, "HYPE")])
    observer.update(
        {
            "execution_mode": "observe",
            "effective_mode": "OBSERVE ONLY",
            "live_armed": False,
            "execution_authority": "none",
        }
    )

    report = build_provider_contract_history([observer], observer, [])

    assert report["evidence_state"] == "not_applicable_no_live_trades"
    assert report["compatible_trades"] == 0
    assert report["performance"]["total"]["closed_trades"] == 0


def _identity(
    run_id: str,
    profile_fingerprint: str,
    providers: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "event_type": "configuration_identity",
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "run_id": run_id,
        "profile_id": f"profile-{run_id}",
        "profile_fingerprint": profile_fingerprint,
        "run_fingerprint": f"fingerprint-{run_id}",
        "payload": {
            "symbol": "MULTI",
            "assets": [
                _asset("BTC", 25.0),
                _asset("ETH", 25.0),
                _asset("SOL", 75.0),
                _asset("HYPE", 75.0),
            ],
            "providers": deepcopy(providers),
            "position_policy": {
                "max_positions_per_symbol": 1,
                "maximum_concurrent_positions": 4,
            },
            "routing_policy": {
                "mode": "same_symbol_conflict_preference_v1",
                "standalone_intents_ungated": True,
                "forced_regime_exit": False,
            },
            "runtime": {"poll_seconds": 15.0, "lookback_days": 14},
            "prestart_backup": {
                "status": "verified",
                "implementation_sha256": f"implementation-{run_id}",
            },
        },
    }


def _asset(symbol: str, max_notional_usd: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "sides": ["long", "short"],
        "leverage": 5.0,
        "venue_max_leverage": 10.0 if symbol == "HYPE" else 25.0,
        "margin_fraction": 0.03,
        "max_notional_usd": max_notional_usd,
        "stop_bps": 80.0,
        "maximum_hold_seconds": 28_800,
    }


def _provider(
    strategy_id: str,
    symbol: str,
    *,
    executable: bool = True,
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbols": [symbol],
        "sides": ["long", "short"],
        "priority": 40,
        "position_policy": "enter_and_close",
        "timeframe": "1m",
        "maximum_entry_delay_seconds": 60,
        "execution_symbols": [symbol] if executable else [],
        "execution_side_overrides": {},
        "entry_context_overrides": {},
        "sizing_overrides": {},
        "execution": {
            "entry_liquidity": "taker_ioc",
            "stop_policy": "fixed_bps",
            "target_policy": "none",
            "maximum_hold_seconds": 28_800,
            "stop_bps": 80.0,
            "minimum_stop_bps": None,
            "maximum_stop_bps": None,
            "target_bps": None,
            "target_r_multiple": None,
            "safety_stop_overlay": False,
            "maximum_hold_policy": "extend_while_regime_supported",
            "hard_maximum_hold_seconds": 86_400,
        },
        "source_profile": None,
    }


def _trade(
    run_id: str,
    profile_fingerprint: str,
    strategy_id: str,
    symbol: str,
    net_pnl_usd: float,
) -> dict[str, object]:
    entry_ms = 1_000 if run_id == "prior-run" else 3_000
    return {
        "source_run_id": run_id,
        "source_profile_fingerprint": profile_fingerprint,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": "long",
        "net_pnl_usd": net_pnl_usd,
        "entry_margin_used_usd": 5.0,
        "net_return_on_margin_pct": net_pnl_usd / 5.0 * 100.0,
        "fees_usd": 0.02,
        "funding_usd": 0.001,
        "entry": {"venue_timestamp_ms": entry_ms},
        "exit": {"venue_timestamp_ms": entry_ms + 1_000},
    }
