"""Exact V58 ETH R-normalized exit-policy context tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.v58_eth_risk_normalized_lock_context import (
    eth_risk_normalized_lock_context_payload,
    load_v58_eth_risk_normalized_lock_context,
)
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)

_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_RUN = "bidirectional-live-1787166474078"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_ROUTE = f"{_STRATEGY}|ETH"


def test_open_context_reports_both_frozen_policies_without_authority(
    tmp_path: Path,
) -> None:
    """An open ETH path must preserve exact policy state and no authority."""
    checkpoint = _write(tmp_path, _checkpoint())

    context = eth_risk_normalized_lock_context_payload(
        load_v58_eth_risk_normalized_lock_context(checkpoint)
    )

    assert context["route"] == _ROUTE
    assert context["lifecycle_state"] == "open"
    assert context["lifecycle_id"] == "ETH:1"
    assert set(context["policies"]) == {
        "r2_floor1_trail1",
        "r5_floor2_trail2",
    }
    assert context["policies"]["r5_floor2_trail2"]["status"] == (
        "triggered_before_current_boundary"
    )
    assert context["historical_eth_lifecycles"] == 3
    assert context["current_path_is_first_eth_activation"] is True
    assert any("counterfactual fills reuse" in item for item in context["limitations"])
    assert any(
        "not current-profile portfolio PnL" in item for item in context["limitations"]
    )
    economics = context["policies"]["r5_floor2_trail2"]["counterfactual_economics"]
    assert economics["funding_included"] is False
    assert economics["additional_slippage_included"] is False
    assert context["strategy_change_supported"] is False
    assert context["execution_authority"] == "none"
    _assert_minimum_evidence(context, current_resolved=False)


def test_closed_context_uses_current_run_result(tmp_path: Path) -> None:
    """After closure, the exact current-run result must replace open state."""
    payload = _checkpoint()
    payload["audit"]["open_trade_reflections"]["trades"] = []
    payload["audit"]["trade_reflections"] = {"trades": [_closed_trade()]}
    payload["audit"]["health"] = {"assets": {"ETH": _flat_eth_health()}}
    mechanism = payload["audit"]["profit_lock_challenger"][
        "risk_normalized_all_time_live_mechanism"
    ]
    mechanism["latest_results"].append(_closed_result())

    context = eth_risk_normalized_lock_context_payload(
        load_v58_eth_risk_normalized_lock_context(_write(tmp_path, payload))
    )

    assert context["lifecycle_state"] == "closed"
    assert context["lifecycle_id"] == "ETH:1"
    assert context["actual_net_pnl_usd"] == 20.0
    close = context["actual_close_reconciliation"]
    assert close["entry"]["price"] == 2198.9
    assert close["exit"]["price"] == 2261.1
    assert close["exit_reason"] == "maximum_hold"
    assert close["holding_time_ms"] == 43_200_000
    assert close["gross_market_pnl_usd"] == pytest.approx(20.63174)
    assert close["fees_usd"] == 0.73174
    assert close["funding_usd"] == 0.1
    assert close["net_pnl_usd"] == 20.0
    assert close["accounting_reconciled"] is True
    assert close["ledger_flat_order_free"] is True
    assert (
        context["policies"]["r5_floor2_trail2"]["estimated_minus_actual_net_usd"]
        == 18.0
    )
    assert "resolved long lifecycle" in context["interpretation"]
    assert "unresolved" not in context["interpretation"]
    assert context["strategy_change_supported"] is False
    _assert_minimum_evidence(context, current_resolved=True)


def test_empty_restarted_run_reports_no_current_eth_lifecycle(tmp_path: Path) -> None:
    """A fresh run with no ETH event is valid empty evidence, not an error."""
    payload = _checkpoint()
    payload["audit"]["open_trade_reflections"]["trades"] = []

    context = eth_risk_normalized_lock_context_payload(
        load_v58_eth_risk_normalized_lock_context(_write(tmp_path, payload))
    )

    assert context["lifecycle_state"] == "not_observed_current_run"
    assert context["lifecycle_id"] is None
    assert context["side"] is None
    assert context["policies"] == {}
    assert context["current_path_is_first_eth_activation"] is False
    assert "no ETH lifecycle has been observed" in context["interpretation"]
    assert context["strategy_change_supported"] is False
    _assert_minimum_evidence(context, current_resolved=False)


@pytest.mark.parametrize(
    ("defect", "message"),
    (
        ("price_accounting", "price and cash accounting disagree"),
        ("policy_accounting", "policy and reflected net PnL disagree"),
        ("owned_order", "not flat and order-free"),
    ),
)
def test_closed_context_rejects_accounting_or_cleanup_drift(
    tmp_path: Path, defect: str, message: str
) -> None:
    """A close cannot report success with inconsistent cash or owned orders."""
    payload = _checkpoint()
    payload["audit"]["open_trade_reflections"]["trades"] = []
    trade = _closed_trade()
    health = _flat_eth_health()
    result = _closed_result()
    if defect == "price_accounting":
        trade["exit"]["price"] = 2260.0
    elif defect == "policy_accounting":
        result["actual_net_pnl_usd"] = 19.0
    else:
        health["open_order_ids"] = [520161149035]
    payload["audit"]["trade_reflections"] = {"trades": [trade]}
    payload["audit"]["health"] = {"assets": {"ETH": health}}
    mechanism = payload["audit"]["profit_lock_challenger"][
        "risk_normalized_all_time_live_mechanism"
    ]
    mechanism["latest_results"].append(result)

    with pytest.raises(ValueError, match=message):
        load_v58_eth_risk_normalized_lock_context(_write(tmp_path, payload))


def test_context_rejects_policy_or_profile_drift(tmp_path: Path) -> None:
    """Policy and runtime identity drift must fail closed."""
    payload = _checkpoint()
    payload["audit"]["run"]["profile_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="runtime identity"):
        load_v58_eth_risk_normalized_lock_context(_write(tmp_path, payload))

    payload = _checkpoint()
    mechanism = payload["audit"]["profit_lock_challenger"][
        "risk_normalized_all_time_live_mechanism"
    ]
    mechanism["policies"][0]["activation_r"] = 3.0
    with pytest.raises(ValueError, match="policy contract"):
        load_v58_eth_risk_normalized_lock_context(_write(tmp_path, payload))


def test_historical_disposition_is_source_bound_and_report_only(
    tmp_path: Path,
) -> None:
    """The current context must reject drift in its historical source artifact."""
    checkpoint = _write(tmp_path, _checkpoint())
    source = tmp_path / "historical.json"
    source.write_text('{"result":"frozen"}', encoding="utf-8")
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps(_historical_disposition(source)), encoding="utf-8")

    context = eth_risk_normalized_lock_context_payload(
        load_v58_eth_risk_normalized_lock_context(checkpoint, journal)
    )

    historical = context["historical_disposition"]
    assert historical["disposition"] == "reject_global_eth_exit_replacement"
    assert historical["live_change_proposed"] is False
    assert historical["current_live_lifecycle_changes_decision"] is False
    source.write_text('{"result":"changed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="historical source artifact changed"):
        load_v58_eth_risk_normalized_lock_context(checkpoint, journal)


def test_continuous_report_freezes_minimum_evidence_logic() -> None:
    """Generator identity must cover the ETH evidence requirement."""
    paths = {str(path) for path in v58_continuous_generator_paths("script.py")}

    assert "src/hypervector/research/v58_eth_risk_lock_evidence.py" in paths
    assert "src/hypervector/research/v58_eth_historical_disposition.py" in paths


def _assert_minimum_evidence(
    context: dict[str, object], *, current_resolved: bool
) -> None:
    minimum = context["minimum_additional_evidence"]
    assert minimum["current_lifecycle_resolved"] is current_resolved
    assert minimum["new_resolved_lifecycles_per_side"] == 1
    assert minimum["required_sides"] == ["long", "short"]
    assert minimum["not_an_automatic_performance_gate"] is True
    assert minimum["live_change_requires_explicit_human_approval"] is True
    assert set(minimum["exact_reconciliation_required"]) == {
        "fills",
        "fees",
        "funding",
        "slippage",
        "exit_reason",
        "flat_order_free",
    }
    assert set(minimum["change_reconsideration_requirements"]) == {
        "preregistered_same_mechanism",
        "exact_cost_and_gap_sensitivity",
        "positive_after_largest_winner_removal",
        "independent_resolved_long_and_short_lifecycles",
    }


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _checkpoint() -> dict[str, object]:
    mechanism = {
        "schema_version": 1,
        "mode": "cohort_risk_normalized_profit_lock_mechanism_v1",
        "scope": "all_live_history_normalized_mechanism",
        "policy_origin": "post_hoc_large_winner_giveback_hypothesis_20260813",
        "policies": [
            _policy("r2_floor1_trail1", 2.0, 1.0, 1.0),
            _policy("r5_floor2_trail2", 5.0, 2.0, 2.0),
        ],
        "by_provider_symbol": {_ROUTE: _history()},
        "latest_results": [],
        "limitations": [
            "counterfactual fills reuse actual exit reference ratios and fee rates",
            "normalized mechanism evidence is not current-profile portfolio PnL",
        ],
    }
    return {
        "lifecycle": {"state": "running_consistent"},
        "audit": {
            "run": {
                "profile_id": _PROFILE,
                "profile_fingerprint": _FINGERPRINT,
                "run_id": _RUN,
                "executable_provider_symbols": [_ROUTE],
            },
            "open_trade_reflections": {"trades": [_open_trade()]},
            "profit_lock_challenger": {
                "risk_normalized_all_time_live_mechanism": mechanism
            },
        },
    }


def _policy(
    policy_id: str, activation_r: float, floor_r: float, giveback_r: float
) -> dict[str, object]:
    return {
        "policy_id": policy_id,
        "activation_r": activation_r,
        "floor_r": floor_r,
        "peak_giveback_r": giveback_r,
    }


def _history() -> dict[str, object]:
    summary = {
        "lifecycles": 3,
        "eligible_lifecycles": 3,
        "triggered": 0,
        "wins": 2,
        "losses": 1,
        "mean_actual_net_return_bps": 26.5,
        "mean_estimated_net_return_bps": 26.5,
        "mean_delta_net_return_bps": 0.0,
    }
    return {"summary_by_policy": {key: summary for key in _policy_ids()}}


def _open_trade() -> dict[str, object]:
    return {
        "lifecycle_id": "ETH:1",
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
        "source_run_id": _RUN,
        "open_risk_normalized_profit_lock_challenger": {
            "schema_version": 2,
            "mode": "cohort_open_risk_normalized_profit_lock_challenger_v1",
            "status": "observed",
            "policy_origin": ("post_hoc_large_winner_giveback_hypothesis_20260813"),
            "contract": {"report_only": True, "execution_authority": "none"},
            "policies": {
                key: {
                    "policy_id": key,
                    "status": "triggered_before_current_boundary",
                    "counterfactual_economics": {
                        "estimated_net_pnl_excluding_funding_usd": value,
                        "funding_included": False,
                        "additional_slippage_included": False,
                    },
                }
                for key, value in zip(_policy_ids(), (5.0, 38.0), strict=True)
            },
        },
    }


def _closed_result() -> dict[str, object]:
    return {
        "lifecycle_id": "ETH:1",
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
        "source_run_id": _RUN,
        "exit_timestamp_ms": 200,
        "actual_net_pnl_usd": 20.0,
        "status": "eligible",
        "policies": {
            key: {
                "policy_id": key,
                "status": "triggered",
                "estimated_net_pnl_usd": value,
                "estimated_minus_actual_net_usd": value - 20.0,
            }
            for key, value in zip(_policy_ids(), (5.0, 38.0), strict=True)
        },
    }


def _closed_trade() -> dict[str, object]:
    return {
        "lifecycle_id": "ETH:1",
        "source_run_id": _RUN,
        "source_profile_fingerprint": _FINGERPRINT,
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
        "entry": {
            "oid": 520161109446,
            "price": 2198.9,
            "size": 0.3317,
            "venue_timestamp_ms": 100,
            "slippage_bps": -25.4,
        },
        "exit": {
            "oid": 520161200000,
            "price": 2261.1,
            "size": 0.3317,
            "venue_timestamp_ms": 43_200_100,
            "slippage_bps": 1.25,
        },
        "protective_stop": {"oid": 520161149035, "trigger_price": 2185.7},
        "exit_reason": "maximum_hold",
        "holding_time_ms": 43_200_000,
        "fees_usd": 0.73174,
        "funding_usd": 0.1,
        "net_pnl_usd": 20.0,
    }


def _flat_eth_health() -> dict[str, object]:
    return {
        "final_state": "FLAT",
        "position_size_signed": 0.0,
        "open_order_ids": [],
        "protected_if_open": True,
    }


def _policy_ids() -> tuple[str, str]:
    return "r2_floor1_trail1", "r5_floor2_trail2"


def _historical_disposition(source: Path) -> dict[str, object]:
    raw = source.read_bytes()
    from hashlib import sha256

    return {
        "symbol": "ETH",
        "strategy_id": _STRATEGY,
        "contract": {"report_only": True, "execution_authority": "none"},
        "source_artifact": {
            "path": str(source),
            "sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "decision": {
            "disposition": "reject_global_eth_exit_replacement",
            "retain_current_native_12h_exit_contract": True,
            "current_live_lifecycle_changes_decision": False,
            "live_change_proposed": False,
        },
    }
