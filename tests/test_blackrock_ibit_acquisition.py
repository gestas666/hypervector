"""Tests for immutable outcome-blind BlackRock IBIT acquisition."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import hypervector.research.blackrock_ibit_acquisition as acquisition


def test_acquisition_publishes_source_bound_normalized_bundle(tmp_path: Path) -> None:
    """Raw issuer bytes and normalized history must have exact evidence."""
    content = _valid_workbook()
    requested: list[str] = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return content

    output = tmp_path / "bundle"
    published = acquisition.acquire_blackrock_ibit_history_bundle(
        output,
        fetch,
        context=_context(),
    )

    assert published == output
    assert requested == [acquisition.BLACKROCK_IBIT_HISTORY_URL]
    assert (output / "fund_data.xml").read_bytes() == content
    history = pd.read_parquet(output / "history.parquet")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert history["as_of_date"].tolist() == list(
        pd.to_datetime(["2026-08-19", "2026-08-20"])
    )
    assert history["shares_outstanding"].tolist() == [1100, 1200]
    assert manifest["schema_version"] == "blackrock_ibit_historical_bundle_v1"
    assert manifest["source_url"] == acquisition.BLACKROCK_IBIT_HISTORY_URL
    assert manifest["execution_authority"] == "none"
    assert manifest["report_only"] is True
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["context"] == _context()
    assert manifest["coverage"] == {
        "rows": 2,
        "raw_historical_rows": 2,
        "normalized_valid_observation_rows": 2,
        "first_as_of_date": "2026-08-19",
        "last_as_of_date": "2026-08-20",
        "duplicate_as_of_dates": 0,
        "split_like_discontinuities": 0,
        "excluded_share_placeholder_rows": 0,
        "excluded_share_placeholder_dates": [],
        "candidate_outcomes_computed": False,
    }
    for name in ("fund_data.xml", "history.parquet"):
        assert manifest["files"][name]["bytes"] == (output / name).stat().st_size
        assert len(manifest["files"][name]["sha256"]) == 64


@pytest.mark.parametrize("content", [b"", b"not a BlackRock workbook"])
def test_acquisition_rejects_empty_or_unparseable_source(
    tmp_path: Path,
    content: bytes,
) -> None:
    """Invalid issuer responses must leave no published directory."""
    output = tmp_path / "bundle"

    with pytest.raises(ValueError):
        acquisition.acquire_blackrock_ibit_history_bundle(
            output,
            lambda _: content,
            context=_context(),
        )

    assert not output.exists()


def test_acquisition_rejects_authority_drift_before_fetch(tmp_path: Path) -> None:
    """Source acquisition cannot inherit order or live authority."""
    output = tmp_path / "bundle"
    fetched = False

    def fetch(_: str) -> bytes:
        nonlocal fetched
        fetched = True
        return _valid_workbook()

    context = {**_context(), "execution_authority": "live"}
    with pytest.raises(ValueError, match="execution authority"):
        acquisition.acquire_blackrock_ibit_history_bundle(
            output, fetch, context=context
        )

    assert fetched is False
    assert not output.exists()


def test_acquisition_requires_bound_source_integrity_addendum(tmp_path: Path) -> None:
    """The post-failure placeholder rule must be immutable acquisition context."""
    context = _context()
    del context["source_integrity_addendum"]

    with pytest.raises(ValueError, match="source-integrity addendum"):
        acquisition.acquire_blackrock_ibit_history_bundle(
            tmp_path / "bundle",
            lambda _: _valid_workbook(),
            context=context,
        )


def test_acquisition_records_excluded_pre_window_placeholder(tmp_path: Path) -> None:
    """The manifest must expose every excluded non-observation and raw row."""
    content = _valid_workbook().replace(
        b"</Table>",
        (
            b"<Row><Cell><Data>Mar 31, 2024</Data></Cell>"
            b"<Cell><Data>20</Data></Cell><Cell><Data>-</Data></Cell>"
            b"<Cell><Data>--</Data></Cell></Row></Table>"
        ),
        1,
    )
    output = tmp_path / "bundle"

    acquisition.acquire_blackrock_ibit_history_bundle(
        output,
        lambda _: content,
        context=_context(),
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["coverage"]["raw_historical_rows"] == 3
    assert manifest["coverage"]["normalized_valid_observation_rows"] == 2
    assert manifest["coverage"]["excluded_share_placeholder_dates"] == ["2024-03-31"]


def test_acquisition_rejects_existing_output_before_fetch(tmp_path: Path) -> None:
    """Immutable output reuse must fail without issuing a network request."""
    output = tmp_path / "bundle"
    output.mkdir()
    fetched = False

    def fetch(_: str) -> bytes:
        nonlocal fetched
        fetched = True
        return _valid_workbook()

    with pytest.raises(FileExistsError, match="already exists"):
        acquisition.acquire_blackrock_ibit_history_bundle(
            output,
            fetch,
            context=_context(),
        )

    assert fetched is False


def _context() -> dict[str, object]:
    return {
        "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
        "execution_authority": "none",
        "candidate_results_inspected_before_acquisition": False,
        "preregistration": {"bytes": 10, "sha256": "abc"},
        "source_integrity_addendum": {"bytes": 20, "sha256": "def"},
    }


def _valid_workbook() -> bytes:
    headers = ("As Of", "NAV per Share", "Ex-Dividends", "Shares Outstanding")
    rows = (
        ("Aug 20, 2026", "38.25", "-", "1,200"),
        ("Aug 19, 2026", "37.50", "-", "1,100"),
    )
    rendered = "".join(_row(row) for row in (headers, *rows))
    return (
        '<Workbook xmlns:ss="urn:test"><Worksheet ss:Name="Historical"><Table>'
        f"{rendered}</Table></Worksheet></Workbook>"
    ).encode()


def _row(values: tuple[str, str, str, str]) -> str:
    cells = "".join(f"<Cell><Data>{value}</Data></Cell>" for value in values)
    return f"<Row>{cells}</Row>"
