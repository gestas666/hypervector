"""Report-only provider allocation challenger derived from live evidence."""

import pytest

from hypervector.research.cohort_allocation_challenger import (
    allocation_challenger_applicable,
    build_allocation_challenger,
)

_TARGET = "hype_breakout_onset_bidirectional_v1|HYPE"


def test_compares_selective_hype_cap_without_execution_authority() -> None:
    """The candidate isolates HYPE breakout while preserving other HYPE caps."""
    challenger = build_allocation_challenger(_risk(500.0), _scorecard())

    assert challenger["status"] == "candidate_not_active"
    assert challenger["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
    }
    assert challenger["target_provider_symbol"] == _TARGET
    assert challenger["current"]["planned_notional_usd"] == pytest.approx(25.0)
    assert challenger["candidate"]["planned_notional_usd"] == pytest.approx(75.0)
    assert challenger["candidate"]["planned_margin_usd"] == pytest.approx(15.0)
    assert challenger["candidate"]["effective_change"] is True
    portfolio = challenger["portfolio"]
    assert portfolio["current_maximum_margin_fraction"] == pytest.approx(0.06)
    assert portfolio["candidate_maximum_margin_fraction"] == pytest.approx(0.08)
    assert challenger["required_profile_changes"]["pinned_provider_symbols"] == [
        "hulk_expansion_bidirectional_tuned_v2|HYPE",
        "range_onset_bidirectional_v1|HYPE",
    ]
    assert challenger["execution_sample"]["closed_trades"] == 4
    assert challenger["execution_sample"]["net_pnl_usd"] == pytest.approx(1.004659)
    assert challenger["profit_forecast"] is None


def test_account_value_changes_projection_but_never_candidate_eligibility() -> None:
    """A smaller balance can make the cap inert without becoming a gate."""
    challenger = build_allocation_challenger(_risk(50.0), _scorecard())

    assert challenger["account_value_usd"] == pytest.approx(50.0)
    assert challenger["status"] == "candidate_not_active"
    assert challenger["contract"]["balance_gate"] is False
    assert challenger["current"]["planned_notional_usd"] == pytest.approx(7.5)
    assert challenger["candidate"]["planned_notional_usd"] == pytest.approx(7.5)
    assert challenger["candidate"]["effective_change"] is False


def test_excludes_observe_only_assets_from_portfolio_margin() -> None:
    """Displayed assets without executable routes cannot inflate live risk."""
    risk = _risk(500.0)
    risk["summary"]["executable_assets"] = 2
    risk["summary"]["maximum_simultaneous_effective_margin_fraction"] = 0.04

    challenger = build_allocation_challenger(risk, _scorecard())

    assert challenger["portfolio"]["current_maximum_margin_fraction"] == pytest.approx(
        0.04
    )
    assert challenger["portfolio"][
        "candidate_maximum_margin_fraction"
    ] == pytest.approx(0.06)


def test_inert_cap_lift_is_not_published_as_an_active_challenger() -> None:
    """An already-loaded $75 target cannot masquerade as a future change."""
    risk = _risk(500.0)
    risk["by_asset"]["HYPE"] = _projection(500.0, 75.0)
    for key in (
        "hulk_expansion_bidirectional_tuned_v2|HYPE",
        _TARGET,
        "range_onset_bidirectional_v1|HYPE",
    ):
        risk["by_provider_symbol"][key] = _provider(
            500.0,
            75.0,
            "asset_default",
        )

    assert allocation_challenger_applicable(risk) is False


def test_accepts_target_without_resolved_execution_sample() -> None:
    """Missing outcomes are disclosed rather than converted into a trial gate."""
    scorecard = _scorecard()
    del scorecard["by_provider_symbol"][_TARGET]["execution_performance"]
    del scorecard["by_provider_symbol"][_TARGET]["execution_performance_by_side"]

    challenger = build_allocation_challenger(_risk(500.0), scorecard)

    assert challenger["execution_sample"] == {"status": "no_resolved_execution_sample"}
    assert challenger["status"] == "candidate_not_active"


def test_rejects_an_input_contract_that_claims_a_balance_gate() -> None:
    """Research evidence with balance authority cannot enter the checkpoint."""
    risk = _risk(500.0)
    risk["contract"]["balance_gate"] = True

    with pytest.raises(ValueError, match="risk contract is not report-only"):
        build_allocation_challenger(risk, _scorecard())


def _risk(account_value: float) -> dict[str, object]:
    by_asset = {
        symbol: _projection(account_value, cap)
        for symbol, cap in {"BTC": 25.0, "ETH": 25.0, "SOL": 75.0, "HYPE": 25.0}.items()
    }
    providers = {
        "hulk_expansion_bidirectional_tuned_v2|HYPE": _provider(
            account_value, 25.0, "asset_default"
        ),
        _TARGET: _provider(account_value, 25.0, "asset_default"),
        "range_onset_bidirectional_v1|HYPE": _provider(
            account_value, 25.0, "asset_default"
        ),
        "range_onset_bidirectional_v1|SOL": _provider(
            account_value, 75.0, "provider_override", margin_fraction=0.10
        ),
    }
    maximum = _maximum_margin_fraction(by_asset, providers, account_value)
    return {
        "schema_version": 1,
        "mode": "cohort_runtime_risk_utilization_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "performance_gate": False,
            "balance_gate": False,
            "automatic_sizing_change": False,
        },
        "account_value_usd": account_value,
        "summary": {
            "configured_assets": 4,
            "cap_bound_assets": sum(row["cap_binding"] for row in by_asset.values()),
            "configured_maximum_positions": 4,
            "provider_symbols": len(providers),
            "provider_symbol_overrides": 1,
            "maximum_simultaneous_effective_margin_fraction": maximum,
        },
        "by_asset": by_asset,
        "by_provider_symbol": providers,
    }


def _provider(
    account_value: float,
    cap: float,
    source: str,
    *,
    margin_fraction: float = 0.03,
) -> dict[str, object]:
    return {
        **_projection(account_value, cap, margin_fraction=margin_fraction),
        "sizing_source": source,
    }


def _maximum_margin_fraction(
    assets: dict[str, dict[str, object]],
    providers: dict[str, dict[str, object]],
    account_value: float,
) -> float:
    margins = {
        symbol: float(row["planned_margin_usd"]) for symbol, row in assets.items()
    }
    for key, row in providers.items():
        symbol = key.split("|", 1)[1]
        margins[symbol] = max(margins[symbol], float(row["planned_margin_usd"]))
    return sum(margins.values()) / account_value


def _projection(
    account_value: float,
    cap: float,
    *,
    margin_fraction: float = 0.03,
) -> dict[str, object]:
    leverage = 5.0
    uncapped = account_value * margin_fraction * leverage
    planned = min(uncapped, cap)
    return {
        "configured_leverage": leverage,
        "configured_margin_fraction": margin_fraction,
        "configured_max_notional_usd": cap,
        "uncapped_notional_usd": uncapped,
        "planned_notional_usd": planned,
        "planned_margin_usd": planned / leverage,
        "effective_margin_fraction": planned / leverage / account_value,
        "notional_fraction_of_equity": planned / account_value,
        "cap_utilization_ratio": planned / uncapped,
        "cap_binding": uncapped > cap,
    }


def _scorecard() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_pause": False,
            "automatic_retuning": False,
            "performance_gate": False,
            "balance_gate": False,
        },
        "by_provider_symbol": {
            _TARGET: {
                "strategy_id": "hype_breakout_onset_bidirectional_v1",
                "symbol": "HYPE",
                "execution_performance": {
                    "closed_trades": 4,
                    "wins": 3,
                    "losses": 1,
                    "breakeven": 0,
                    "net_pnl_usd": 1.004659,
                    "fees_usd": 0.086187,
                    "funding_usd": -0.001594,
                    "profit_factor": 5.486747,
                },
                "execution_performance_by_side": {
                    "long": {"closed_trades": 3, "net_pnl_usd": 0.772171},
                    "short": {"closed_trades": 1, "net_pnl_usd": 0.232488},
                },
            }
        },
    }
