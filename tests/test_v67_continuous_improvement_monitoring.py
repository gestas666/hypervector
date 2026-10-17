"""V67 forward lifecycle monitoring must cover every executable route exactly."""

from __future__ import annotations

import pytest

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ROOT = Path(__file__).parents[1]
_CONFIG = _ROOT / (
    "configs/"
    "multi_asset_growth_first_5000_three_asset_evidence_scope_repaired_candidate_v67.toml"
)
_OVERRIDES = _ROOT / "configs/research/cohort_improvement_decision_overrides_v67.json"
_PROFILE_ID = (
    "multi_asset_growth_first_5000_three_asset_evidence_scope_repaired_candidate_v67"
)
_PROFILE_FINGERPRINT = (
    "42afff8bd0dc871db2f6ef6321a6aacd14ec39c033105b6708a3208b96cfc12e"
)
_RUN_ID = "bidirectional-live-1788260371688"
_IMPLEMENTATION_PATHS = (
    "src/hypervector/research/cohort_route_lifecycle_scope.py",
    "src/hypervector/research/cohort_route_lifecycle_evidence.py",
    "src/hypervector/research/cohort_route_lifecycle_values.py",
    "scripts/cohort_route_lifecycle_watch.py",
)

JsonRecord = Mapping[str, object]


def _load_json(path: Path) -> JsonRecord:
    """Load one test-owned JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _file_evidence(path: Path) -> dict[str, object]:
    """Return exact repository-relative evidence for one file."""
    raw = path.read_bytes()
    return {
        "path": str(path.relative_to(_ROOT)),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def test_v67_improvement_overrides_cover_exact_execution_scope() -> None:
    """Every executable V67 provider-symbol must have one exact collector."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    overrides = _load_json(_OVERRIDES)
    assert overrides["source_profile_id"] == _PROFILE_ID
    assert overrides["source_profile_fingerprint"] == _PROFILE_FINGERPRINT
    assert overrides["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    routes = overrides["routes"]
    hypotheses = overrides["active_hypotheses"]
    assert isinstance(routes, dict)
    assert isinstance(hypotheses, list)
    expected = {
        f"{provider_id}|{symbol}"
        for provider_id, symbol in config.executable_provider_symbols
    }
    assert set(routes) == expected
    assert {row["route"] for row in hypotheses} == expected
    assert len(hypotheses) == len(expected)
    expected_directions = {
        route: sorted(
            side
            for provider_id, symbol, side in config.executable_provider_directions
            if f"{provider_id}|{symbol}" == route
        )
        for route in expected
    }
    for row in hypotheses:
        route = str(row["route"])
        assert sorted(row["required_sides"]) == expected_directions[route]
        assert row["execution_effect"] == "report_only"
        assert row["automatic_live_change"] is False
        assert str(row["lifecycle_status_path"]).startswith(
            "data/runtime/bidirectional_cohort/v67_"
        )


def test_v67_preregistrations_are_run_bound_and_source_frozen() -> None:
    """Each route collector must freeze the current run and generator bytes."""
    overrides = _load_json(_OVERRIDES)
    expected_generators = [
        _file_evidence(_ROOT / relative) for relative in _IMPLEMENTATION_PATHS
    ]
    hypotheses = overrides["active_hypotheses"]
    assert isinstance(hypotheses, list)
    for row in hypotheses:
        preregistration = _load_json(
            (_OVERRIDES.parent / str(row["decision_source"])).resolve()
        )
        identity = preregistration["live_identity"]
        assert isinstance(identity, dict)
        route = str(row["route"])
        provider_id, symbol = route.split("|", 1)
        assert identity == {
            "run_id": _RUN_ID,
            "profile_id": _PROFILE_ID,
            "profile_fingerprint": _PROFILE_FINGERPRINT,
            "provider_id": provider_id,
            "signal_strategy_id": provider_id,
            "symbol": symbol,
            "route": route,
            "required_sides": row["required_sides"],
        }
        assert preregistration["implementation_evidence"] == expected_generators
        contract = preregistration["contract"]
        assert isinstance(contract, dict)
        assert contract["report_only"] is True
        assert contract["execution_authority"] == "none"
        assert contract["automatic_live_change"] is False
        assert contract["runtime_strategy_changed"] is False
        boundary = preregistration["prospective_boundary"]
        assert isinstance(boundary, dict)
        assert int(boundary["capture_start_ms"]) == 1788261260000
        assert int(boundary["baseline_eligible_evaluations"]) == 0
        outputs = preregistration["outputs"]
        assert isinstance(outputs, dict)
        assert outputs["mutable_status"] == row["lifecycle_status_path"]
        assert str(outputs["immutable_final"]).startswith(
            "data/logs/research/bidirectional_cohort/v67_"
        )


@pytest.mark.evidence
def test_v67_monitor_evidence_is_hash_bound() -> None:
    """The monitor decision file must reject drift in its source evidence."""
    overrides = _load_json(_OVERRIDES)
    evidence = overrides["evidence"]
    assert isinstance(evidence, list)
    for row in evidence:
        assert isinstance(row, dict)
        source = (_OVERRIDES.parent / str(row["path"])).resolve()
        raw = source.read_bytes()
        assert row["sha256"] == sha256(raw).hexdigest()
        assert row["bytes"] == len(raw)
