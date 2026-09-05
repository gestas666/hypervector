"""Live-backend health context for the report-only V58 loop."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
import json
from pathlib import Path

import pytest

import v58_live_lifecycle_fixtures as lifecycle_fixtures

_OBSERVED = datetime(2026, 8, 19, 14, 36, tzinfo=UTC)


def test_faulted_backend_is_distinct_from_healthy_observer(tmp_path: Path) -> None:
    """A fresh checkpoint must expose that live execution is not running."""
    source = _source(tmp_path)
    module = import_module("hypervector.research.v58_live_backend_context")

    context = module.load_v58_live_backend_context(
        source,
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
    )
    payload = module.live_backend_context_payload(context)

    assert payload["live_execution_running"] is False
    assert payload["lifecycle_state"] == "backend_runtime_fault"
    assert payload["runtime_fault_exception_type"] == "ValueError"
    assert payload["operator_attention_required"] is True
    assert payload["ledger_last_snapshot_flat_order_free"] is True
    assert "ledger_terminal_snapshot_flat_order_free" not in payload
    assert payload["current_venue_position_order_state_verified"] is False
    assert payload["measurement_scope"] == "active_live_checkpoint"
    assert payload["live_runtime"]["poll_cycles"] == 12
    timing = payload["live_entry_submission_timing"]
    assert timing["status"] == "submission_contract_enforced"
    assert timing["eligible_evaluations"] == 1
    assert timing["submitted_entries"] == 1
    assert timing["minimum_submission_headroom_ms"] == 42_000
    assert timing["executed_late_entries_proven"] is False
    assert payload["automatic_live_change"] is False
    assert payload["execution_authority"] == "none"


def test_stale_backend_checkpoint_is_rejected(tmp_path: Path) -> None:
    """A historical fault snapshot cannot masquerade as current diagnosis."""
    source = _source(tmp_path, generated_at="2026-08-19T14:30:00+00:00")
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="checkpoint is stale"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_lifecycle_and_ledger_asset_state_must_reconcile(tmp_path: Path) -> None:
    """Contradictory backend and ledger state must fail instead of being merged."""
    payload = _payload()
    payload["audit"]["health"]["assets"]["BTC"]["final_state"] = "OPEN"
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="asset state is inconsistent"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_backend_context_rejects_execution_authority(tmp_path: Path) -> None:
    """The continuous research context must remain incapable of execution."""
    payload = _payload()
    payload["checkpoint_contract"]["execution_authority"] = "hyperliquid_mainnet"
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="report-only contract"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_backend_context_distinguishes_unavailable_report_only_venue(
    tmp_path: Path,
) -> None:
    """A public valuation outage is retryable, not an unsafe contract."""
    payload = _payload()
    payload["venue_portfolio"] = {
        "status": "unavailable",
        "technical_issue": "venue portfolio query failed: ReadTimeout",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "execution_collateral_unchanged": True,
        },
    }
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="venue portfolio is temporarily unavailable"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_live_backend_exposes_actual_open_fill_and_protection(tmp_path: Path) -> None:
    """The improvement loop must distinguish live fills from observer marks."""
    source = _write(tmp_path, _payload_with_open_eth())
    module = import_module("hypervector.research.v58_live_backend_context")
    context = module.load_v58_live_backend_context(
        source,
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
    )
    evidence = module.live_backend_context_payload(context)["open_lifecycles"]
    trade = evidence["trades"][0]
    assert evidence["open_lifecycles"] == 1
    assert trade["lifecycle_id"] == "ETH:520161109446"
    assert trade["actual_entry_fill_claim"] and not trade["actual_exit_fill_claim"]
    assert trade["entry_price"] == 2198.9
    assert trade["entry_execution_quality"] == {
        "trade_id": 741233744669590,
        "expected_price": 2204.5,
        "slippage_bps": -25.40258562032216,
        "acknowledgement_latency_ms": 1265,
        "markout_bps": -2.5012506253119238,
        "markout_horizon_ms": 5169,
        "measurement_scope": "actual_venue_entry_fill",
    }
    assert trade["actual_completed_path"] == {
        "completed_bars": 146,
        "price_source": "completed_1m_candle_high_low",
        "maximum_favorable_excursion_bps": 672.6090317886224,
        "maximum_adverse_excursion_bps": 0.0,
        "current_directional_return_bps": 227.386420482969,
        "peak_giveback_bps": 445.22261130565334,
        "continuous_path_claim": False,
        "measurement_scope": "actual_fill_completed_candle_path",
    }
    assert trade["profit_protection_estimate"] == {
        "status": "open_profit_unprotected",
        "estimated_exit_now_net_usd": 15.908896281277002,
        "estimated_stop_net_usd": -5.043299240000036,
        "marked_to_stop_giveback_usd": 20.952195521277037,
        "protected_profit_fraction": 0.0,
        "method": "measured_entry_fee_rate_no_future_funding_or_slippage",
        "actual_exit_fill_claim": False,
    }
    assert trade["marked_net_pnl_usd"] == 16.231151
    assert trade["protective_stop_oid"] == 520161149035
    assert trade["protective_stop_trigger_price"] == 2185.7066
    assert trade["maximum_hold_seconds"] == 43_200
    assert trade["profit_lock_policy"] == "none"
    assert trade["marked_pnl_is_provisional"] is True
    assert evidence["execution_authority"] == "none"


def test_live_backend_reconciles_compact_health_with_execution_positions(
    tmp_path: Path,
) -> None:
    """Compact health rows must derive state only from exact execution evidence."""
    payload = _payload_with_open_eth()
    for row in payload["audit"]["health"]["assets"].values():
        row["position_size_signed"] = None
        row["open_order_ids"] = None
    payload["audit"]["health"]["assets"]["ETH"]["stop_oid"] = 520161149035
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    context = module.load_v58_live_backend_context(
        source,
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
    )
    evidence = module.live_backend_context_payload(context)

    assert evidence["ledger_asset_states"]["ETH"] == "OPEN"
    assert evidence["ledger_last_snapshot_flat_order_free"] is False
    assert evidence["open_lifecycles"]["trades"][0]["protective_stop_oid"] == (
        520161149035
    )


def test_live_backend_preserves_adopted_entry_and_runtime_run_identities(
    tmp_path: Path,
) -> None:
    """A restarted runtime must retain the exact predecessor entry provenance."""
    payload = _payload_with_open_eth()
    source_run = "bidirectional-live-1787000000000"
    payload["audit"]["open_trade_reflections"]["trades"][0]["source_run_id"] = (
        source_run
    )
    payload["audit"]["execution"]["fill_details"][0]["origin_run_id"] = source_run
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    context = module.load_v58_live_backend_context(
        source,
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
    )
    trade = module.live_backend_context_payload(context)["open_lifecycles"]["trades"][0]

    assert trade["runtime_run_id"] == "bidirectional-live-1787065473571"
    assert trade["source_run_id"] == source_run


def test_live_backend_rejects_adopted_entry_without_matching_source_fill(
    tmp_path: Path,
) -> None:
    """Cross-run provenance cannot be accepted without the exact entry fill."""
    payload = _payload_with_open_eth()
    payload["audit"]["open_trade_reflections"]["trades"][0]["source_run_id"] = (
        "bidirectional-live-1787000000000"
    )
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="entry-fill coverage is inconsistent"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_live_backend_preserves_undefined_fraction_without_open_profit(
    tmp_path: Path,
) -> None:
    """No-open-profit protection must remain unavailable rather than zero."""
    payload = _payload_with_open_eth()
    protection = payload["audit"]["open_trade_reflections"]["trades"][0][
        "profit_protection"
    ]
    protection["status"] = "no_open_profit"
    protection["protected_profit_fraction"] = None
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    context = module.load_v58_live_backend_context(
        source, observed_at=_OBSERVED, maximum_age_seconds=180.0
    )
    trade = module.live_backend_context_payload(context)["open_lifecycles"]["trades"][0]

    assert trade["profit_protection_estimate"]["protected_profit_fraction"] is None


def test_live_backend_rejects_missing_open_protective_stop(tmp_path: Path) -> None:
    """An actual open fill cannot be reported without its owned stop."""
    payload = _payload_with_open_eth()
    payload["audit"]["health"]["assets"]["ETH"]["open_order_ids"] = []
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="protective stop is absent"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_live_backend_rejects_unreconciled_open_marked_pnl(tmp_path: Path) -> None:
    """Marked live PnL must equal unrealized PnL less costs plus funding."""
    payload = _payload_with_open_eth()
    trade = payload["audit"]["open_trade_reflections"]["trades"][0]
    trade["marked_economics"]["active_lifecycle_marked_net_pnl_usd"] = 99.0
    trade["profit_protection"]["reported_marked_net_pnl_usd"] = 99.0
    payload["audit"]["execution"]["open_positions"][0][
        "active_lifecycle_marked_net_pnl_usd"
    ] = 99.0
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="marked PnL components do not reconcile"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def test_live_backend_rejects_open_lifecycle_count_mismatch(tmp_path: Path) -> None:
    """Execution and reflection open counts cannot contradict their rows."""
    payload = _payload_with_open_eth()
    payload["audit"]["execution"]["open_lifecycles"] = 2
    source = _write(tmp_path, payload)
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="counts are inconsistent"):
        module.load_v58_live_backend_context(
            source,
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
        )


def _source(tmp_path: Path, *, generated_at: str = "2026-08-19T14:35:25+00:00") -> Path:
    payload = _payload()
    payload["generated_at_utc"] = generated_at
    return _write(tmp_path, payload)


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload() -> dict[str, object]:
    assets = _flat_assets()
    return {
        "schema_version": 1,
        "generated_at_utc": "2026-08-19T14:35:25+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_pause": False,
            "automatic_retuning": False,
        },
        "lifecycle": _faulted_lifecycle(assets),
        "audit": _audit(assets),
        "venue_portfolio": {
            "status": "observed",
            "observed_at_utc": "2026-08-19T14:35:25+00:00",
            "contract": {"report_only": True, "execution_authority": "none"},
        },
    }


def _flat_assets() -> dict[str, dict[str, object]]:
    return {
        symbol: {
            "final_state": "FLAT",
            "position_size_signed": 0.0,
            "open_order_ids": [],
        }
        for symbol in ("BTC", "HYPE", "xyz:SPCX")
    }


def _faulted_lifecycle(assets: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "state": "backend_runtime_fault",
        "backend_process_health": "faulted",
        "cohort_heartbeat_status": "degraded",
        "cohort_heartbeat_age_seconds": 24_053.0,
        "cohort_last_event_type": "runtime_fault",
        "cohort_last_observed_at_utc": "2026-08-19T07:54:57+00:00",
        "runtime_fault_exception_type": "ValueError",
        "asset_states": {symbol: "FLAT" for symbol in assets},
    }


def _audit(assets: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "run": {
            "profile_id": "multi_asset_growth_first_5000_spcx_short_containment_v57",
            "profile_fingerprint": "7" * 64,
            "run_id": "bidirectional-live-1787065473571",
            "symbols": list(assets),
            "executable_provider_symbols": ["provider_v1|BTC"],
        },
        "coverage": {"complete": True, "technical_gaps": []},
        "health": {"assets": assets},
        "runtime": _runtime(),
        "routing": _routing(),
        "execution": {
            "open_lifecycles": 0,
            "open_positions": [],
            "fill_details": [],
        },
        "open_trade_reflections": _empty_open_reflections(),
        "trade_reflections": lifecycle_fixtures.empty_trade_reflections(),
    }


def _runtime() -> dict[str, object]:
    return {
        "poll_cycles": 12,
        "poll_interval_seconds": {
            "count": 11,
            "minimum": 14.0,
            "median": 15.0,
            "mean": 15.0,
            "maximum": 16.0,
        },
        "stop_reasons": {},
    }


def _routing() -> dict[str, object]:
    return {
        "entry_age_diagnostics": {
            "eligible_evaluations": 1,
            "enter_actions": 1,
            "submitted_entries": 1,
            "stale_entries_withheld": 0,
            "executed_late_entries_proven": False,
            "submission_timestamp_observed": True,
            "entry_submission_enforcement_observed": True,
            "by_provider_symbol": {
                "provider_v1|BTC": {
                    "submitted_entries": 1,
                    "submitted_entries_over_limit": 0,
                    "minimum_submission_headroom_ms": 42_000,
                }
            },
        }
    }


def _empty_open_reflections() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_open_trade_reflections",
        "scope": "compatible_profile_history",
        "open_lifecycles": 0,
        "trades": [],
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_strategy_changes": False,
        },
    }


def _payload_with_open_eth() -> dict[str, object]:
    """Return a checkpoint with one reconciled, protected ETH lifecycle."""
    payload = _payload()
    payload["audit"]["run"]["symbols"].append("ETH")
    payload["lifecycle"]["asset_states"]["ETH"] = "OPEN"
    payload["audit"]["health"]["assets"]["ETH"] = {
        "final_state": "OPEN",
        "position_size_signed": 0.3317,
        "open_order_ids": [520161149035],
    }
    payload["audit"]["execution"] = _open_execution()
    payload["audit"]["open_trade_reflections"] = _open_reflections()
    return payload


def _open_execution() -> dict[str, object]:
    """Return one internally reconciled open-position execution row."""
    return {
        "open_lifecycles": 1,
        "fill_details": [
            {
                "trade_id": 741233744669590,
                "oid": 520161109446,
                "origin_run_id": "bidirectional-live-1787065473571",
                "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
                "symbol": "ETH",
                "operation": "entry",
                "side": "B",
                "direction": "Open Long",
                "venue_timestamp_ms": 1787172919582,
                "price": 2198.9,
                "size": 0.3317,
                "fee_usd": 0.31509,
                "expected_price": 2204.5,
                "slippage_bps": -25.40258562032216,
                "acknowledgement_latency_ms": 1265,
                "markout_bps": -2.5012506253119238,
                "markout_horizon_ms": 5169,
            }
        ],
        "open_positions": [
            {
                "status": "provisional_open",
                "symbol": "ETH",
                "side": "long",
                "size_signed": 0.3317,
                "entry_price": 2198.9,
                "mark_price": 2248.9,
                "mark_price_source": "venue_position_value_div_size",
                "position_value_usd": 745.96013,
                "margin_used_usd": 150.0,
                "leverage": 5,
                "unrealized_pnl_usd": 16.585,
                "fees_usd": 0.31509,
                "funding_usd": -0.038759,
                "active_lifecycle_marked_net_pnl_usd": 16.231151,
            }
        ],
    }


def _open_reflections() -> dict[str, object]:
    """Return the exact open-trade reflection paired with `_open_execution`."""
    position = _open_execution()["open_positions"][0]
    return {
        "schema_version": 1,
        "mode": "cohort_open_trade_reflections",
        "scope": "compatible_profile_history",
        "open_lifecycles": 1,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_strategy_changes": False,
        },
        "trades": [_open_reflection(position)],
    }


def _open_reflection(position: dict[str, object]) -> dict[str, object]:
    return {
        "lifecycle_id": "ETH:520161109446",
        "source_run_id": "bidirectional-live-1787065473571",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "side": "long",
        "entry": {
            "price": 2198.9,
            "size": 0.3317,
            "venue_timestamp_ms": 1787172919582,
        },
        "marked_economics": position,
        "protective_stop": {"oid": 520161149035, "trigger_price": 2185.7066},
        "exit_plan": {
            "source": "bound_execution_plan",
            "maximum_hold_seconds": 43_200,
            "deadline_timestamp_ms": 1787216100000,
            "profit_lock_policy": "none",
            "opposite_intent_exit_scope": (
                "selected_opposite_from_any_executable_provider_same_symbol"
            ),
        },
        "path_since_entry": {
            "status": "observed",
            "completed_bars": 146,
            "first_timestamp_ms": 1787172960000,
            "last_timestamp_ms": 1787181660000,
            "highest_price": 2346.8,
            "lowest_price": 2202.3,
            "maximum_favorable_excursion_bps": 672.6090317886224,
            "maximum_adverse_excursion_bps": 0.0,
            "current_directional_return_bps": 227.386420482969,
            "peak_giveback_bps": 445.22261130565334,
            "excursion_price_source": "completed_1m_candle_high_low",
        },
        "profit_protection": {
            "status": "open_profit_unprotected",
            "reported_marked_net_pnl_usd": 16.231151,
            "estimated_exit_now_net_usd": 15.908896281277002,
            "estimated_stop_net_usd": -5.043299240000036,
            "marked_to_stop_giveback_usd": 20.952195521277037,
            "protected_profit_fraction": 0.0,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage",
        },
    }
