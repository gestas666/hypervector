"""Comparison-evidence provenance for the first V58 ETH live close."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence
import hypervector.research.v58_eth_live_close_reconciliation_io as close_io
from hypervector.research.v58_eth_live_close_reconciliation_io import (
    load_v58_eth_live_close_reconciliation,
)
from test_v58_eth_live_close_reconciliation import _source_files

Record = Mapping[str, object]


def test_loader_rejects_changed_preregistered_comparison_evidence(
    tmp_path: Path,
) -> None:
    """A changed frozen exit comparison must invalidate close publication."""
    paths = _source_files(tmp_path)
    preregistration = Path(paths["preregistration"])
    payload = json.loads(preregistration.read_text(encoding="utf-8"))
    historical = _write_source(tmp_path / "historical.json", {"decision": "retain"})
    component = _write_source(tmp_path / "component.json", {"status": "rejected"})
    payload["comparison_evidence"] = {
        "native_exit_disposition": _evidence(historical),
        "component_decay_result": _evidence(component),
    }
    preregistration.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    historical.write_text('{"decision":"changed"}', encoding="utf-8")

    with pytest.raises(ValueError, match="comparison evidence changed"):
        load_v58_eth_live_close_reconciliation(
            preregistration,
            expected_preregistration_sha256=file_evidence(preregistration)["sha256"],
            continuous_path=Path(paths["continuous"]),
            venue_path=Path(paths["venue"]),
            observer_status_path=Path(paths["observer_status"]),
            observer_provenance_path=Path(paths["observer_provenance"]),
            expected_observer_provenance_sha256=str(
                paths["observer_provenance_sha256"]
            ),
            generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        )


def test_loader_rechecks_comparison_evidence_after_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A comparison mutation during report construction must abort publication."""
    paths = _source_files(tmp_path)
    preregistration = Path(paths["preregistration"])
    payload = json.loads(preregistration.read_text(encoding="utf-8"))
    historical = _write_source(tmp_path / "historical.json", {"decision": "retain"})
    component = _write_source(tmp_path / "component.json", {"status": "rejected"})
    payload["comparison_evidence"] = {
        "native_exit_disposition": _evidence(historical),
        "component_decay_result": _evidence(component),
    }
    preregistration.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    original = close_io.build_v58_eth_live_close_reconciliation

    def mutating_build(
        preregistration_payload: Record,
        closed_context: Record,
        ledger_rows: Sequence[Record],
        venue_preflight: Record,
        observer_resolution: Record,
    ) -> dict[str, object]:
        report = original(
            preregistration_payload,
            closed_context,
            ledger_rows,
            venue_preflight,
            observer_resolution,
        )
        historical.write_text('{"decision":"changed"}', encoding="utf-8")
        return report

    monkeypatch.setattr(
        close_io, "build_v58_eth_live_close_reconciliation", mutating_build
    )
    with pytest.raises(ValueError, match="changed"):
        load_v58_eth_live_close_reconciliation(
            preregistration,
            expected_preregistration_sha256=file_evidence(preregistration)["sha256"],
            continuous_path=Path(paths["continuous"]),
            venue_path=Path(paths["venue"]),
            observer_status_path=Path(paths["observer_status"]),
            observer_provenance_path=Path(paths["observer_provenance"]),
            expected_observer_provenance_sha256=str(
                paths["observer_provenance_sha256"]
            ),
            generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        )


def _write_source(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), **file_evidence(path)}
