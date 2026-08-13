"""Standalone checksum-bound HIP-3 path-repair command tests."""

from __future__ import annotations

from argparse import Namespace
import gzip
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hip3_prospective_path_repair.py"
_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_SYMBOL = "xyz:SKHX"


def test_command_publishes_repaired_report_without_authority(tmp_path: Path) -> None:
    module = _module()
    base, archive, output = _files(tmp_path)
    supplemental = module.SupplementalPathEvidence(
        mark_timestamps_ms=_timestamps(3_000),
        l2_timestamps_ms=_timestamps(1_000),
        evidence={"complete": True, "market_family": "hip3", "symbol": _SYMBOL},
        protected_files=(archive,),
    )

    report = module.run_command(_args(base, archive, output), supplemental=supplemental)

    assert report["technical_assessment"]["unresolved_bars"] == 0
    assert report["technical_assessment"]["repaired_bars"] == 1
    assert report["contract"]["execution_authority"] == "none"
    assert report["base_path_audit_evidence"]["path"] == str(base.resolve())
    assert json.loads(output.read_text()) == report
    with pytest.raises(FileExistsError):
        module.run_command(_args(base, archive, output), supplemental=supplemental)


def test_command_rejects_changed_protected_evidence(tmp_path: Path) -> None:
    module = _module()
    base, archive, output = _files(tmp_path)
    supplemental = module.SupplementalPathEvidence(
        mark_timestamps_ms=_timestamps(3_000),
        l2_timestamps_ms=_timestamps(1_000),
        evidence={"complete": True, "market_family": "hip3", "symbol": _SYMBOL},
        protected_files=(archive,),
    )
    original = module._require_unchanged_files

    def mutate(
        paths: tuple[Path, ...], expected: tuple[dict[str, object], ...]
    ) -> None:
        archive.write_text("changed")
        original(paths, expected)

    module._require_unchanged_files = mutate
    with pytest.raises(ValueError, match="changed during path repair"):
        module.run_command(_args(base, archive, output), supplemental=supplemental)
    assert not output.exists()


def test_command_rejects_archive_bounds_that_miss_unresolved_bar(
    tmp_path: Path,
) -> None:
    module = _module()
    base, archive, output = _files(tmp_path)
    payload = json.loads(archive.read_text())
    payload["requested_start_utc"] = "2027-01-01T00:00:00+00:00"
    payload["requested_end_utc"] = "2027-01-01T01:00:00+00:00"
    archive.write_text(json.dumps(payload))
    supplemental = module.SupplementalPathEvidence(
        mark_timestamps_ms=(),
        l2_timestamps_ms=(),
        evidence={"complete": True, "market_family": "hip3", "symbol": _SYMBOL},
        protected_files=(archive,),
    )

    with pytest.raises(ValueError, match="does not cover unresolved bars"):
        module.run_command(_args(base, archive, output), supplemental=supplemental)


def test_book_loader_excludes_exact_end_boundary_but_rejects_later_rows(
    tmp_path: Path,
) -> None:
    module = _module()
    path = tmp_path / "books.jsonl.gz"
    rows = [
        _book_row(_START_MS),
        _book_row(_START_MS + _BAR_MS - 1),
        _book_row(_START_MS + _BAR_MS),
    ]
    with gzip.open(path, "wt") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    config = module.Hip3ProspectivePathRepairConfig(
        _SYMBOL, _START_MS, _START_MS + _BAR_MS
    )

    assert module._load_book_timestamps((path,), config) == (
        _START_MS,
        _START_MS + _BAR_MS - 1,
    )

    rows[-1] = _book_row(_START_MS + _BAR_MS + 1)
    with gzip.open(path, "wt") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="exceeds repair bounds"):
        module._load_book_timestamps((path,), config)


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_prospective_path_repair_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(base: Path, archive: Path, output: Path) -> Namespace:
    return Namespace(
        symbol=_SYMBOL,
        data_root=Path("data"),
        path_audit=base,
        archive_audit=archive,
        output=output,
    )


def _files(tmp_path: Path) -> tuple[Path, Path, Path]:
    base = tmp_path / "base.json"
    archive = tmp_path / "archive.json"
    output = tmp_path / "repaired.json"
    base.write_text(json.dumps(_base_audit()))
    archive.write_text(
        json.dumps(
            {
                "symbol": _SYMBOL,
                "market_family": "hip3",
                "requested_start_utc": "2027-01-15T08:15:00+00:00",
                "requested_end_utc": "2027-01-15T08:30:00+00:00",
                "chunk_seconds": 900,
                "book_only": False,
                "complete": True,
            }
        )
    )
    return base, archive, output


def _timestamps(cadence: int) -> tuple[int, ...]:
    return tuple(range(_START_MS + _BAR_MS, _START_MS + 2 * _BAR_MS, cadence))


def _base_audit() -> dict[str, object]:
    return {
        "schema_version": "hip3_prospective_path_audit_v1",
        "mode": "prospective_public_venue_path_coverage",
        "contract": {"report_only": True, "execution_authority": "none"},
        "source": {"symbol": _SYMBOL, "observed_at_ms": _START_MS + 3 * _BAR_MS},
        "coverage": {
            "first_full_bar_open_ms": _START_MS,
            "completed_bar_end_ms": _START_MS + 2 * _BAR_MS,
            "completed_bars": 2,
            "timeframe_minutes": 15,
        },
        "evidence_identity": {"completed_bar_trades": {"rows": 2, "sha256": "b" * 64}},
        "channels": {},
        "bar_diagnostics": [_bar(_START_MS, True), _bar(_START_MS + _BAR_MS, False)],
        "technical_assessment": {
            "prospective_bar_path_coverage_resolved": False,
            "unresolved_bars": 1,
            "candle_ohlc_parity_resolved": False,
        },
        "limitations": [],
    }


def _book_row(timestamp: int) -> dict[str, object]:
    return {
        "symbol": _SYMBOL,
        "source": "0xarchive_hyperliquid_hip3_l2",
        "ts_exchange_ms": timestamp,
    }


def _bar(start: int, resolved: bool) -> dict[str, object]:
    quality = {"observations": 2, "maximum_gap_ms": 1_000, "complete": resolved}
    return {
        "bar_open_ms": start,
        "bar_close_ms": start + _BAR_MS,
        "mark": dict(quality),
        "l2": dict(quality),
        "resolved": resolved,
    }
