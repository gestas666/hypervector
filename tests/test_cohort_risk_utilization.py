"""Runtime sizing utilization derived from authoritative cohort telemetry."""

import pytest

from hypervector.research.cohort_risk_utilization import cohort_risk_utilization


def test_reports_when_the_notional_cap_overrides_fractional_sizing() -> None:
    """A binding cap remains visible rather than masquerading as 3% margin."""
    evidence = cohort_risk_utilization(_records(), run_id="live-a")

    assert evidence["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "automatic_sizing_change": False,
    }
    assert evidence["account_value_usd"] == pytest.approx(500.0)
    assert evidence["summary"]["cap_bound_assets"] == 2
    assert evidence["summary"]["configured_assets"] == 2
    assert evidence["summary"]["configured_maximum_positions"] == 2
    assert evidence["summary"][
        "maximum_simultaneous_effective_margin_fraction"
    ] == pytest.approx(0.02)
    btc = evidence["by_asset"]["BTC"]
    assert btc["configured_margin_fraction"] == pytest.approx(0.03)
    assert btc["uncapped_notional_usd"] == pytest.approx(75.0)
    assert btc["configured_max_notional_usd"] == pytest.approx(25.0)
    assert btc["planned_notional_usd"] == pytest.approx(25.0)
    assert btc["effective_margin_fraction"] == pytest.approx(0.01)
    assert btc["cap_binding"] is True


def test_reports_fractional_sizing_when_the_cap_does_not_bind() -> None:
    """A high guardrail cap leaves equity-proportional sizing authoritative."""
    records = _records(max_notional_usd=1_000.0)

    evidence = cohort_risk_utilization(records, run_id="live-a")

    assert evidence["summary"]["cap_bound_assets"] == 0
    assert evidence["by_asset"]["BTC"]["planned_notional_usd"] == pytest.approx(75.0)
    assert evidence["by_asset"]["BTC"]["effective_margin_fraction"] == pytest.approx(
        0.03
    )


def test_accepts_capacity_above_the_configured_asset_count() -> None:
    """An unused capacity slot must not invalidate read-only risk telemetry."""
    records = _records()
    records[0]["payload"]["position_policy"]["maximum_concurrent_positions"] = 3

    evidence = cohort_risk_utilization(records, run_id="live-a")

    assert evidence["summary"]["configured_assets"] == 2
    assert evidence["summary"]["configured_maximum_positions"] == 3
    assert evidence["summary"][
        "maximum_simultaneous_effective_margin_fraction"
    ] == pytest.approx(0.02)


def test_rejects_capacity_below_the_configured_asset_count() -> None:
    """Every configured asset must retain one possible portfolio slot."""
    records = _records()
    records[0]["payload"]["position_policy"]["maximum_concurrent_positions"] = 1

    with pytest.raises(ValueError, match="must cover configured assets"):
        cohort_risk_utilization(records, run_id="live-a")


def test_rejects_duplicate_asset_symbols_in_runtime_identity() -> None:
    """A duplicate must fail rather than silently overwrite sizing evidence."""
    records = _records()
    assets = records[0]["payload"]["assets"]
    assets[1]["symbol"] = "BTC"

    with pytest.raises(ValueError, match="duplicate configured asset"):
        cohort_risk_utilization(records, run_id="live-a")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("leverage", True, "BTC leverage must be numeric"),
        ("margin_fraction", 1.01, "BTC margin fraction must not exceed one"),
        ("max_notional_usd", 0.0, "BTC maximum notional must be finite and positive"),
    ],
)
def test_rejects_invalid_asset_sizing_values(
    field: str,
    value: object,
    message: str,
) -> None:
    """Invalid runtime sizing inputs fail explicitly at the checkpoint boundary."""
    records = _records()
    records[0]["payload"]["assets"][0][field] = value

    with pytest.raises(ValueError, match=message):
        cohort_risk_utilization(records, run_id="live-a")


def test_projects_provider_symbol_override_against_asset_default() -> None:
    """Provider allocation remains explicit beside the asset-level fallback."""
    records = _records(max_notional_usd=50.0)
    records[0]["payload"]["providers"] = [
        {
            "strategy_id": "range_onset_bidirectional_v1",
            "execution_symbols": ["BTC", "ETH"],
            "sizing_overrides": {
                "BTC": {"margin_fraction": 0.06, "max_notional_usd": 40.0}
            },
        }
    ]

    evidence = cohort_risk_utilization(records, run_id="live-a")

    assert evidence["summary"]["provider_symbols"] == 2
    assert evidence["summary"]["provider_symbol_overrides"] == 1
    btc = evidence["by_provider_symbol"]["range_onset_bidirectional_v1|BTC"]
    eth = evidence["by_provider_symbol"]["range_onset_bidirectional_v1|ETH"]
    assert btc["sizing_source"] == "provider_override"
    assert btc["planned_notional_usd"] == pytest.approx(40.0)
    assert btc["effective_margin_fraction"] == pytest.approx(0.016)
    assert eth["sizing_source"] == "asset_default"
    assert eth["planned_notional_usd"] == pytest.approx(50.0)


def test_ignores_observe_only_provider_in_execution_risk_projection() -> None:
    """An empty execution scope contributes no live sizing or margin risk."""
    records = _records(max_notional_usd=50.0)
    records[0]["payload"]["providers"] = [
        {
            "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
            "execution_symbols": ["BTC"],
            "sizing_overrides": {},
        },
        {
            "strategy_id": "range_onset_bidirectional_v1",
            "execution_symbols": [],
            "sizing_overrides": {},
        },
    ]

    evidence = cohort_risk_utilization(records, run_id="live-a")

    assert evidence["summary"]["provider_symbols"] == 1
    assert set(evidence["by_provider_symbol"]) == {
        "hulk_expansion_bidirectional_tuned_v2|BTC"
    }


def test_portfolio_margin_uses_largest_provider_policy_per_asset() -> None:
    """A low balance must not hide a provider override behind the asset default."""
    records = _records(max_notional_usd=75.0, account_value_usd=50.0)
    records[0]["payload"]["providers"] = [
        {
            "strategy_id": "range_onset_bidirectional_v1",
            "execution_symbols": ["BTC", "ETH"],
            "sizing_overrides": {
                "BTC": {"margin_fraction": 0.10, "max_notional_usd": 75.0}
            },
        }
    ]

    evidence = cohort_risk_utilization(records, run_id="live-a")

    assert evidence["account_value_usd"] == pytest.approx(50.0)
    assert evidence["summary"][
        "maximum_simultaneous_effective_margin_fraction"
    ] == pytest.approx(0.13)


def test_projects_directional_provider_sizing_without_hiding_either_side() -> None:
    """Risk telemetry preserves long and short policies as separate rows."""
    records = _records(max_notional_usd=75.0)
    records[0]["payload"]["providers"] = [
        {
            "strategy_id": "range_onset_bidirectional_v1",
            "execution_symbols": ["BTC"],
            "sizing_overrides": {
                "BTC": {"margin_fraction": 0.03, "max_notional_usd": 25.0}
            },
            "directional_sizing_overrides": {
                "BTC": {
                    "long": {"margin_fraction": 0.08, "max_notional_usd": 60.0},
                    "short": {"margin_fraction": 0.02, "max_notional_usd": 15.0},
                }
            },
        }
    ]

    evidence = cohort_risk_utilization(records, run_id="live-a")

    sides = evidence["by_provider_symbol_side"]
    long = sides["range_onset_bidirectional_v1|BTC|long"]
    short = sides["range_onset_bidirectional_v1|BTC|short"]
    assert long["sizing_source"] == "provider_direction_override"
    assert long["planned_notional_usd"] == pytest.approx(60.0)
    assert short["sizing_source"] == "provider_direction_override"
    assert short["planned_notional_usd"] == pytest.approx(15.0)
    assert evidence["summary"]["provider_direction_overrides"] == 2


def _records(
    max_notional_usd: float = 25.0,
    account_value_usd: float = 500.0,
) -> list[dict[str, object]]:
    assets = [
        {
            "symbol": symbol,
            "leverage": 5.0,
            "margin_fraction": 0.03,
            "max_notional_usd": max_notional_usd,
        }
        for symbol in ("BTC", "ETH")
    ]
    return [
        _row(
            1,
            "configuration_identity",
            {
                "assets": assets,
                "position_policy": {"maximum_concurrent_positions": 2},
            },
        ),
        _row(2, "cohort_snapshot", {"account_value_usd": account_value_usd}),
    ]


def _row(
    sequence: int, event_type: str, payload: dict[str, object]
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "run_id": "live-a",
        "event_type": event_type,
        "payload": payload,
    }
