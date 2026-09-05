"""Immutable command tests for the V86 ZEC UT-Bot transfer."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "zec_utbot_peak_harvest_transfer.py"
_SPEC = spec_from_file_location("zec_utbot_peak_harvest_transfer_script", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("ZEC UT-Bot transfer script is unavailable")
MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(MODULE)


def test_parser_requires_exact_partition_and_sources() -> None:
    """The command must make chronology and immutable evidence explicit."""
    parser = MODULE.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    args = parser.parse_args(
        [
            "--partition",
            "development",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--source-start",
            "2025-10-02T14:00:00Z",
            "--score-start",
            "2025-10-15T00:00:00Z",
            "--end",
            "2026-01-28T00:00:00Z",
            "--output",
            "report.json",
        ]
    )
    assert args.partition == "development"
    assert args.bars == Path("bars.parquet")
    assert args.output == Path("report.json")


def test_main_publishes_report_only_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command must pass exact inputs and never mutate live authority."""
    report = {"execution_authority": "none", "automatic_live_change": False}
    captured: dict[str, object] = {}
    monkeypatch.setattr(MODULE, "run_partition_screen", lambda **kwargs: report)
    monkeypatch.setattr(
        MODULE,
        "write_immutable_json",
        lambda path, value: captured.update(path=path, value=value),
    )
    result = MODULE.main(
        [
            "--partition",
            "validation",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--source-start",
            "2026-01-28T00:00:00Z",
            "--score-start",
            "2026-02-01T00:00:00Z",
            "--end",
            "2026-05-01T00:00:00Z",
            "--output",
            "report.json",
        ]
    )
    assert result == 0
    assert captured == {"path": Path("report.json"), "value": report}


def test_short_only_dispatches_selected_sleeve(monkeypatch: pytest.MonkeyPatch) -> None:
    """The disclosed second-stage candidate must use the short-only evaluator."""
    report = {"execution_authority": "none", "automatic_live_change": False}
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        MODULE,
        "run_partition_screen",
        lambda **_kwargs: pytest.fail("bidirectional evaluator was called"),
    )
    monkeypatch.setattr(
        MODULE,
        "run_short_partition_screen",
        lambda **kwargs: captured.update(kwargs) or report,
    )
    monkeypatch.setattr(MODULE, "write_immutable_json", lambda *_args: None)
    result = MODULE.main(
        [
            "--short-only",
            "--partition",
            "development",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--source-start",
            "2025-10-02T14:00:00Z",
            "--score-start",
            "2025-10-15T00:00:00Z",
            "--end",
            "2026-01-28T00:00:00Z",
            "--output",
            "report.json",
        ]
    )
    assert result == 0
    assert captured["partition"] == "development"
