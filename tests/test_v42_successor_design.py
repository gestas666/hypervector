"""Tests for the evidence-bound focused v42 successor design."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v42_successor_design import build_v42_successor_design

_ROOT = Path(__file__).parents[1]
_CONFIG = _ROOT / (
    "configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml"
)
_V41 = _ROOT / (
    "data/logs/research/bidirectional_cohort/"
    "v41_successor_readiness_20260811T1730Z_v1.json"
)
_HYPE_EXIT = _ROOT / (
    "data/logs/research/hype_compression_breakout_challenger_20260811_v4/report.json"
)


def test_design_keeps_only_focused_routes_and_unused_risk() -> None:
    """The design cannot silently refill removed routes or capital slots."""
    report = _build()

    assert report["candidate"]["profile_fingerprint"].startswith("c691ee99")
    assert report["capacity"] == {
        "account_position_cap": 10,
        "configured_assets": 3,
        "maximum_simultaneous_positions": 3,
        "unused_account_slots": 7,
    }
    assert report["sizing"]["maximum_margin_fraction"] == pytest.approx(
        0.0967017529620656
    )
    assert report["sizing"]["gross_notional_usd"] == pytest.approx(2417.54382369664)
    assert report["risk"]["p99_stop_wave_loss_usd"] == pytest.approx(21.79766670010579)
    assert report["assessment"]["removed_risk_redistributed"] is False
    assert report["assessment"]["route_edge_established"] is False
    assert report["assessment"]["transition_ready_now"] is False


def test_design_preserves_live_prefix_and_hype_exit_rejection() -> None:
    """Current losses and rejected HYPE exit changes remain visible blockers."""
    report = _build()

    assert report["live_prefix"]["closed_trades"] >= 4
    assert report["live_prefix"]["wins"] == 0
    assert report["live_prefix"]["open_lifecycles"] >= 1
    assert report["route_evidence"]["HYPE"]["exit_disposition"] == (
        "retain_control_exit"
    )
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_restart"] is False


def test_design_rejects_wrong_source_identity_or_hype_disposition() -> None:
    """Aliased risk or exit evidence cannot support the candidate."""
    inputs = _inputs()
    wrong_risk = deepcopy(inputs)
    wrong_risk["v41"]["candidate"]["profile_id"] = "wrong"
    with pytest.raises(ValueError, match="v41 source profile"):
        _call(wrong_risk)

    wrong_exit = deepcopy(inputs)
    wrong_exit["hype"]["compression_exit_challenger"]["disposition"] = "promote"
    with pytest.raises(ValueError, match="HYPE exit disposition"):
        _call(wrong_exit)


def _build() -> dict[str, object]:
    return _call(_inputs())


def _call(inputs: dict[str, object]) -> dict[str, object]:
    config = load_multi_asset_live_config(
        _CONFIG,
        mode="observe",
        enabled=False,
        accepts_live_risk=False,
    )
    return build_v42_successor_design(
        config=config,
        v41_readiness=inputs["v41"],
        current_checkpoint=inputs["checkpoint"],
        hype_exit_evidence=inputs["hype"],
    )


def _inputs() -> dict[str, dict[str, object]]:
    return {
        "v41": _read(_V41),
        "checkpoint": _frozen_checkpoint(),
        "hype": _read(_HYPE_EXIT),
    }


def _frozen_checkpoint() -> dict[str, object]:
    return {
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": (
                "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5"
            ),
        },
        "audit": {
            "trade_reflections": {
                "performance": {
                    "current_run": {
                        "run_id": "bidirectional-live-1786453934555",
                        "total": {
                            "closed_trades": 4,
                            "wins": 0,
                            "losses": 4,
                            "net_pnl_usd": -2.229934,
                        },
                    }
                }
            },
            "open_trade_reflections": {"open_lifecycles": 4},
        },
        "lifecycle": {"all_assets_terminal": False},
    }


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
