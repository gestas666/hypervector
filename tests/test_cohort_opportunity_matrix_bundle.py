"""Durable report-only opportunity-matrix bundle tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.cohort_opportunity_matrix_bundle import (
    publish_opportunity_matrix_bundle,
)


def test_bundle_publishes_two_strict_supplemental_challengers(
    tmp_path: Path,
) -> None:
    """The rolling primary carries both observers without execution authority."""
    primary = _write(tmp_path / "primary.json", _matrix())
    hype = _write(tmp_path / "hype.json", _observer("hype-candidate"))
    sol = _write(tmp_path / "sol.json", _observer("sol-candidate"))
    output = tmp_path / "latest.json"

    result = publish_opportunity_matrix_bundle(
        primary,
        (hype, sol),
        output,
    )

    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored == result
    assert stored["contract"]["execution_authority"] == "none"
    assert [
        row["portfolio_journal"]["contract"]["candidate_strategy_id"]
        for row in stored["supplemental_forward_challengers"]
    ] == ["hype-candidate", "sol-candidate"]


def test_bundle_fails_closed_without_replacing_last_good_output(
    tmp_path: Path,
) -> None:
    """Duplicate identity cannot corrupt the last complete display bundle."""
    primary = _write(tmp_path / "primary.json", _matrix())
    first = _write(tmp_path / "first.json", _observer("duplicate"))
    second = _write(tmp_path / "second.json", _observer("duplicate"))
    output = _write(tmp_path / "latest.json", {"last_good": True})

    with pytest.raises(ValueError, match="duplicate candidate strategy"):
        publish_opportunity_matrix_bundle(primary, (first, second), output)

    assert json.loads(output.read_text(encoding="utf-8")) == {"last_good": True}


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _matrix() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_execution_opportunity_matrix",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
        },
        "hypotheses": 0,
        "comparisons": 0,
        "results": [],
    }


def _observer(candidate: str) -> dict[str, object]:
    value = _matrix()
    value["forward_challenger"] = {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "live_strategy_changed": False,
            "automatic_promotion": False,
            "portfolio_pnl_claimed": False,
        },
        "portfolio_journal": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "portfolio_pnl_claimed": False,
                "candidate_strategy_id": candidate,
            }
        },
    }
    return value
