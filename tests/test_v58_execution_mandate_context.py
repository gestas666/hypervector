"""Checkpoint-bound execution evidence for the V58 research loop."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
import json
from pathlib import Path

import pytest

from test_cohort_mandate_evidence import _audit

_OBSERVED = datetime(2026, 8, 20, 15, 10, tzinfo=UTC)


def test_v58_mandate_context_loads_exact_report_only_execution(tmp_path: Path) -> None:
    """The V58 consolidator must project the authoritative checkpoint audit."""
    module = import_module("hypervector.research.v58_execution_mandate_context")
    source = _write_checkpoint(tmp_path, _checkpoint())

    context = module.load_v58_execution_mandate_context(source)
    payload = module.execution_mandate_context_payload(context)

    assert payload["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }
    assert payload["execution"]["status"] == "measured_zero_fills"
    assert context.execution_authority == "none"
    assert context.evidence["checkpoint"]["path"] == str(source.resolve())


def test_v58_mandate_context_rejects_live_authority(tmp_path: Path) -> None:
    """A success-shaped checkpoint cannot grant the research context authority."""
    module = import_module("hypervector.research.v58_execution_mandate_context")
    payload = _checkpoint()
    payload["checkpoint_contract"]["execution_authority"] = "hyperliquid_mainnet"
    source = _write_checkpoint(tmp_path, payload)

    with pytest.raises(ValueError, match="report-only contract"):
        module.load_v58_execution_mandate_context(source)


def test_v58_generator_identity_covers_mandate_builder() -> None:
    """Published execution evidence must freeze its transitive builder."""
    paths = import_module(
        "hypervector.research.v58_continuous_generator_paths"
    ).v58_continuous_generator_paths("script.py")

    assert Path("src/hypervector/research/cohort_mandate_evidence.py") in paths
    assert Path("src/hypervector/research/v58_execution_mandate_context.py") in paths
    assert Path("src/hypervector/research/v58_continuous_live_attachment.py") in paths


def _checkpoint() -> dict[str, object]:
    return {
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_pause": False,
            "automatic_retuning": False,
        },
        "audit": _audit(),
    }


def _write_checkpoint(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
