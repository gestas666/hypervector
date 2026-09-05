"""Contracts for outcome-blind BTC OI-expansion input registration."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/v58_btc_oi_expansion_register_inputs.py")


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "v58_btc_oi_expansion_register_inputs_script", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("BTC OI-expansion input-registration script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_registration_payload_is_count_blind_and_exactly_bound() -> None:
    """Registration binds frozen evidence without inspecting cadence or outcomes."""
    module = _module()
    preregistration = {"path": "/evidence/prereg.json", "sha256": "1" * 64, "bytes": 10}
    generators = {"aggregate_sha256": "2" * 64, "files": {}}
    sources = {
        "aggregate_sha256": "3" * 64,
        "files": [{"file_id": "source-1"}],
        "execution_authority": "none",
    }

    payload = module.build_registration_payload(
        preregistration,
        generators,
        sources,
        generated_at=datetime(2026, 8, 21, 22, 0, tzinfo=UTC),
    )

    assert payload["preregistration"] == preregistration
    assert payload["generator_identity"] == generators
    assert payload["source_evidence"] == sources
    assert payload["authority"] == {
        "report_only": True,
        "execution_authority": "none",
        "outcomes_computed": False,
        "live_change": False,
    }
    assert payload["change_scope"]["candidate_counts_inspected"] is False
    encoded = json.dumps(payload).lower()
    assert "forward_prices" not in encoded
    assert "returns" not in encoded
    assert "pnl" not in encoded


def test_registration_publication_is_immutable(tmp_path: Path) -> None:
    """Publish one deterministic JSON record and refuse replacement."""
    module = _module()
    output = tmp_path / "registration.json"
    payload = {"schema_version": "test", "execution_authority": "none"}

    module.publish_registration(output, payload)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError):
        module.publish_registration(output, payload)
