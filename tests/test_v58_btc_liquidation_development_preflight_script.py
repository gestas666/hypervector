"""Command contract for V58 BTC liquidation development timing preflight."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.btc_liquidation_covariate_models import BookTimingCoverage

_SCRIPT = Path("scripts/v58_btc_liquidation_development_preflight.py")


def _load() -> ModuleType:
    """Load the command script without making scripts a package."""
    spec = spec_from_file_location("v58_btc_liquidation_development_preflight", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load development preflight command")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _timing() -> tuple[BookTimingCoverage, ...]:
    """Build one complete and one incomplete timestamp-only result."""
    return (
        BookTimingCoverage(
            "a",
            1_000,
            1_002,
            2,
            (
                (30_000, 31_002),
                (120_000, 121_002),
                (300_000, 301_002),
                (900_000, 901_002),
            ),
            True,
        ),
        BookTimingCoverage(
            "b",
            2_000,
            2_003,
            3,
            (
                (30_000, None),
                (120_000, None),
                (300_000, None),
                (900_000, None),
            ),
            False,
        ),
    )


def test_defaults_bind_revision_eight_and_development_only_output() -> None:
    """Default command inputs must bind the last outcome-unopened revision."""
    assert _SCRIPT.is_file()
    module = _load()

    args = module.build_parser().parse_args([])

    assert args.journal.name.endswith("20260822-v8.json")
    assert args.plan.name.endswith("acquisition_plan_20260822_v1.json")
    assert args.partition == "development"
    assert args.out.name.endswith("book_timing_preflight_20260822_v1")


def test_report_is_timestamp_only_report_only_and_reconciled() -> None:
    """Preflight output must not calculate market returns or execution economics."""
    module = _load()

    report = module.build_preflight_report(
        _timing(),
        evidence={"journal": {"path": "journal", "sha256": "a" * 64, "bytes": 1}},
    )

    assert report["partition"] == "development"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["market_returns_computed"] is False
    assert report["summary"] == {
        "episodes": 2,
        "technical_complete": 1,
        "technical_incomplete": 1,
        "maximum_entry_delay_ms": 3,
    }
    encoded = json.dumps(report, sort_keys=True).lower()
    assert "net_pnl" not in encoded
    assert "market_return" in encoded


def test_publication_is_immutable_and_hash_binds_timing_rows(tmp_path: Path) -> None:
    """Publish timestamp rows once and reject accidental replacement."""
    module = _load()
    output = tmp_path / "preflight"
    report = module.build_preflight_report(_timing(), evidence={})

    module.publish_preflight(output, report, _timing())

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"report.json", "timing.jsonl.gz"}
    with pytest.raises(FileExistsError):
        module.publish_preflight(output, report, _timing())
