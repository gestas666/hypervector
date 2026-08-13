"""Contract tests for the bounded Apex cohort research command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/apex_cohort_screen.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("apex_cohort_screen", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Apex cohort script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _argv(database: Path, output: Path, funding: Path | None = None) -> list[str]:
    funding_path = funding or Path("funding.parquet")
    return [
        "--candidate",
        "apex_mean_reversion_v2",
        "--segment",
        "development",
        "--symbol",
        "BTC",
        "--start",
        "2025-07-28T00:00:00Z",
        "--end",
        "2026-01-28T00:00:00Z",
        "--database",
        str(database),
        "--funding",
        str(funding_path),
        "--out",
        str(output),
    ]


def test_parser_requires_candidate_segment_window_database_and_output() -> None:
    module = _module()

    with pytest.raises(SystemExit):
        module._parser().parse_args([])

    args = module._parser().parse_args(_argv(Path("market.duckdb"), Path("out.json")))
    assert args.candidate == "apex_mean_reversion_v2"
    assert args.segment == "development"


def test_request_refuses_window_that_differs_from_frozen_segment() -> None:
    module = _module()
    argv = _argv(Path("market.duckdb"), Path("out.json"))
    argv[argv.index("--end") + 1] = "2026-01-27T00:00:00Z"
    args = module._parser().parse_args(argv)

    with pytest.raises(ValueError, match="frozen development window"):
        module._validated_request(args)


def test_command_refuses_to_overwrite_immutable_output(tmp_path: Path) -> None:
    database = tmp_path / "market.duckdb"
    database.touch()
    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Apex cohort output exists"):
        _module().main(_argv(database, output))


def test_report_retains_authority_provenance_and_negative_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    database = tmp_path / "market.duckdb"
    database.write_bytes(b"immutable input")
    funding = tmp_path / "funding.parquet"
    funding.write_bytes(b"immutable funding")
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        module,
        "run_apex_candidate",
        lambda request: {
            "status": "completed_negative",
            "metrics": {"net_pnl_usd": -12.5},
            "limitations": ["synthetic test payload"],
        },
    )

    assert module.main(_argv(database, output, funding)) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["report_only"] is True
    assert payload["execution_authority"] == "none"
    assert payload["place_attempted"] is False
    assert payload["candidate"] == "apex_mean_reversion_v2"
    assert payload["result"]["metrics"]["net_pnl_usd"] == -12.5
    assert payload["input_identity"]["database_metadata_sha256"]
    assert payload["input_identity"]["funding_sha256"]
    assert payload["assumptions"]["taker_fee_rate"] == 0.00045


def test_command_surface_has_no_live_execution_authority() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
