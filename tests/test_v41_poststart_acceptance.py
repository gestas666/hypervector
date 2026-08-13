"""Exact technical acceptance contract for a future live v41 run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
import hypervector.research.v41_poststart_acceptance as acceptance

_V39 = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_"
    "current_canary_v39.toml"
)
_V41 = Path(
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_NOW = datetime(2026, 8, 11, 18, 0, tzinfo=UTC)


def test_exact_v41_binds_flat_boundary_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A technically clean run still requires exact transition evidence."""
    config = _config(_V41)
    monkeypatch.setattr(acceptance, "_shared_acceptance_checks", _passing_checks)

    report = acceptance.build_v41_poststart_acceptance(
        {"audit": {"run": {"run_id": "v41-live"}}},
        config,
        _readiness(config, transition_ready=True),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["decision"] == "accepted"
    assert report["run"] == {"run_id": "v41-live"}
    assert report["contract"]["execution_authority"] == "none"
    assert report["readiness_identity"]["material_state_sha256"] == "frozen"


def test_rejects_a_non_v41_config_or_nonready_boundary() -> None:
    """Neither a similar roster nor a blocked preflight can alias v41."""
    v39 = _config(_V39)
    with pytest.raises(ValueError, match="exact v41"):
        acceptance.build_v41_poststart_acceptance(
            {"audit": {}},
            v39,
            _readiness(v39, transition_ready=True),
            now_utc=_NOW,
        )

    v41 = _config(_V41)
    with pytest.raises(ValueError, match="transition-ready"):
        acceptance.build_v41_poststart_acceptance(
            {"audit": {}},
            v41,
            _readiness(v41, transition_ready=False),
            now_utc=_NOW,
        )


def test_shared_technical_failure_remains_a_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper cannot success-shape a failed runtime check."""
    config = _config(_V41)
    monkeypatch.setattr(
        acceptance,
        "_shared_acceptance_checks",
        lambda *args, **kwargs: {
            "runtime_identity": {
                "passed": False,
                "reasons": ["runtime_profile_fingerprint_mismatch"],
            }
        },
    )

    report = acceptance.build_v41_poststart_acceptance(
        {"audit": {"run": {"run_id": "v41-live"}}},
        config,
        _readiness(config, transition_ready=True),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert report["reasons"] == ["runtime_profile_fingerprint_mismatch"]


def _config(path: Path) -> object:
    return load_multi_asset_live_config(path, mode="observe")


def _readiness(config: object, *, transition_ready: bool) -> dict[str, object]:
    return {
        "schema_version": "v41_successor_readiness_v1",
        "material_state_sha256": "frozen",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "performance_gate": False,
        },
        "candidate": {
            "profile_id": getattr(config, "profile_id"),
            "profile_fingerprint": getattr(config, "profile_fingerprint"),
        },
        "assessment": {
            "sizing_technically_coherent": True,
            "profit_optimality_proven": False,
            "transition_ready_now": transition_ready,
        },
    }


def _passing_checks(*args: object, **kwargs: object) -> dict[str, object]:
    assert kwargs["checkpoint_age"] == 90.0
    assert kwargs["pressure_age"] == 30.0
    return {
        "runtime_identity": {"passed": True, "reasons": []},
        "open_position_protection": {"passed": True, "reasons": []},
    }
