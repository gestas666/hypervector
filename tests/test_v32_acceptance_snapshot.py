"""Identity contracts for the exact v32 post-start acceptance snapshot."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v32_acceptance_snapshot import (
    build_v32_acceptance_snapshot,
)

_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
)
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v3.json")


def test_snapshot_binds_exact_v32_config_journal_and_route_authority() -> None:
    snapshot = build_v32_acceptance_snapshot(_checkpoint(), _journal(), _CANDIDATE)

    assert snapshot["phase"] == "candidate_v32_forward"
    assert snapshot["source_run"]["profile_id"] == snapshot["candidate"]["profile_id"]
    assert snapshot["candidate"]["both_directions"] is True
    assert snapshot["candidate"]["maximum_positions"] == 9
    assert len(snapshot["candidate"]["execution_scope"]) == 21
    assert len(snapshot["candidate"]["observe_only_scope"]) == 3
    assert snapshot["live_state"]["all_open_positions_protected"] is True


def test_snapshot_rejects_run_identity_or_authority_drift() -> None:
    checkpoint = _checkpoint()
    checkpoint["audit"]["run"]["profile_fingerprint"] = "drifted"
    with pytest.raises(ValueError, match="profile identity"):
        build_v32_acceptance_snapshot(checkpoint, _journal(), _CANDIDATE)

    checkpoint = _checkpoint()
    checkpoint["audit"]["run"]["observe_only_provider_symbols"].clear()
    with pytest.raises(ValueError, match="observe-only route scope"):
        build_v32_acceptance_snapshot(checkpoint, _journal(), _CANDIDATE)


def test_snapshot_rejects_journal_candidate_hash_drift() -> None:
    journal = _journal()
    evidence = next(
        row
        for row in journal["evidence"]
        if row["role"] == "inactive_exact_delta_v32_candidate"
    )
    evidence["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="candidate config SHA-256"):
        build_v32_acceptance_snapshot(_checkpoint(), journal, _CANDIDATE)


def _checkpoint() -> dict[str, object]:
    config = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    observed = {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
    executable = config.executable_provider_symbols
    return {
        "generated_at_utc": "2026-08-09T23:00:00+00:00",
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "transition_drain": {"status": "inactive"},
        "audit": {
            "run": {
                "run_id": "v32-live-run",
                "profile_id": config.profile_id,
                "profile_fingerprint": config.profile_fingerprint,
                "executable_provider_symbols": _routes(executable),
                "observe_only_provider_symbols": _routes(observed - executable),
            },
            "health": {"faults": 0, "assets": {"HYPE": _open_asset()}},
            "execution": {"closed_trades": 0},
            "portfolio": {"final_equity_usd": 500.0},
        },
    }


def _open_asset() -> dict[str, object]:
    return {
        "final_state": "OPEN",
        "position_size_signed": -1.0,
        "protected_if_open": True,
        "stop_oid": 123,
        "open_order_ids": [123],
    }


def _journal() -> dict[str, object]:
    return deepcopy(json.loads(_JOURNAL.read_text(encoding="utf-8")))


def _routes(routes: object) -> list[str]:
    return sorted(f"{provider}|{symbol}" for provider, symbol in routes)
