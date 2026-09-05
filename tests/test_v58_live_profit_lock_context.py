"""Prospective profit-lock context for open V58 live lifecycles."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
import json
from pathlib import Path

import pytest
import test_v58_live_backend_context as fixtures
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)


def test_live_context_projects_predeclared_profit_lock_without_exit_claim(
    tmp_path: Path,
) -> None:
    """The consolidator must retain exact counterfactual exit evidence."""
    payload = fixtures._payload_with_open_eth()
    trade = payload["audit"]["open_trade_reflections"]["trades"][0]
    trade["open_profit_lock_challenger"] = _challenger()
    source = tmp_path / "checkpoint.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    module = import_module("hypervector.research.v58_live_backend_context")

    context = module.load_v58_live_backend_context(
        source,
        observed_at=datetime(2026, 8, 19, 14, 36, tzinfo=UTC),
        maximum_age_seconds=180.0,
    )
    trade = module.live_backend_context_payload(context)["open_lifecycles"]["trades"][0]

    challenger = trade["profit_lock_challenger"]
    assert challenger["policy_origin"] == "existing_predeclared_hype_profit_research_v1"
    assert challenger["actual_exit_fill_claim"] is False
    assert challenger["execution_authority"] == "none"
    policy = challenger["policies"]["a25_floor15_trail10"]
    assert policy == {
        "activation_bps": 25.0,
        "floor_bps": 15.0,
        "trailing_giveback_bps": 10.0,
        "status": "triggered_before_current_boundary",
        "trigger_timestamp_ms": 1787181000000,
        "estimated_net_pnl_excluding_funding_usd": 12.5,
        "estimated_minus_current_exit_net_excluding_funding_usd": -3.4,
        "funding_included": False,
        "additional_slippage_included": False,
    }


def test_live_context_rejects_success_shaped_incomplete_profit_lock(
    tmp_path: Path,
) -> None:
    """Observed status cannot conceal missing completed path evidence."""
    payload = fixtures._payload_with_open_eth()
    challenger = _challenger()
    challenger["completed_bars_observed"] = 145
    payload["audit"]["open_trade_reflections"]["trades"][0][
        "open_profit_lock_challenger"
    ] = challenger
    source = tmp_path / "checkpoint.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    module = import_module("hypervector.research.v58_live_backend_context")

    with pytest.raises(ValueError, match="status and coverage disagree"):
        module.load_v58_live_backend_context(
            source,
            observed_at=datetime(2026, 8, 19, 14, 36, tzinfo=UTC),
            maximum_age_seconds=180.0,
        )


def test_continuous_generator_identity_covers_profit_lock_projection() -> None:
    """A changed exit diagnostic must change the continuous report identity."""
    paths = {str(path) for path in v58_continuous_generator_paths("script.py")}

    assert "src/hypervector/research/v58_live_profit_lock_context.py" in paths


def _challenger() -> dict[str, object]:
    return {
        "schema_version": 2,
        "mode": "cohort_open_profit_lock_challenger_v2",
        "status": "observed",
        "policy_origin": "existing_predeclared_hype_profit_research_v1",
        "as_of_timestamp_ms": 1787181660000,
        "completed_bars_expected": 146,
        "completed_bars_observed": 146,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_strategy_changes": False,
            "automatic_promotion": False,
        },
        "policies": {
            "a25_floor15_trail10": _policy(25.0, 15.0, 10.0, triggered=True),
            "a40_floor15_trail20": _policy(40.0, 15.0, 20.0),
            "a60_floor15_trail30": _policy(60.0, 15.0, 30.0),
        },
    }


def _policy(
    activation: float, floor: float, giveback: float, *, triggered: bool = False
) -> dict[str, object]:
    status = "triggered_before_current_boundary" if triggered else "not_activated"
    economics: dict[str, object] = {
        "status": "unavailable",
        "reason": "policy_state_not_activated",
    }
    if triggered:
        economics = {
            "status": "estimated_trigger_exit",
            "estimated_net_pnl_excluding_funding_usd": 12.5,
            "estimated_minus_current_exit_net_excluding_funding_usd": -3.4,
            "funding_included": False,
            "additional_slippage_included": False,
        }
    return {
        "policy_id": _policy_id(activation, floor, giveback),
        "activation_bps": activation,
        "floor_bps": floor,
        "trailing_giveback_bps": giveback,
        "status": status,
        "trigger_timestamp_ms": 1787181000000 if triggered else None,
        "counterfactual_economics": economics,
    }


def _policy_id(activation: float, floor: float, giveback: float) -> str:
    return f"a{activation:g}_floor{floor:g}_trail{giveback:g}"
