"""Tests for immutable, outcome-blind Deribit DVOL acquisition."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest

import hypervector.research.deribit_dvol_acquisition as acquisition


class PageFetcher:
    """Return deterministic Deribit pages and record exact requests."""

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.requests: list[dict[str, str | int]] = []

    def __call__(
        self,
        url: str,
        params: Mapping[str, str | int],
    ) -> bytes:
        """Return the next response for one exact official endpoint request."""
        assert url == acquisition.DERIBIT_DVOL_URL
        self.requests.append(dict(params))
        return self._responses[len(self.requests) - 1]


def test_acquisition_publishes_exact_pages_and_hourly_frame(tmp_path: Path) -> None:
    """The source bundle must bind every raw page and normalized row."""
    responses = _responses(_valid_rows())
    fetcher = PageFetcher(responses)
    output = tmp_path / "dvol"

    published = acquisition.acquire_deribit_dvol_bundle(
        output,
        fetcher,
        context=_context(),
    )

    assert published == output
    assert len(fetcher.requests) == 9
    assert fetcher.requests[0] == {
        "currency": "BTC",
        "start_timestamp": acquisition.START_TIMESTAMP_MS,
        "end_timestamp": acquisition.END_TIMESTAMP_MS,
        "resolution": "3600",
    }
    for index, content in enumerate(responses, start=1):
        assert (output / f"raw/page_{index:04d}.json").read_bytes() == content
    frame = pd.read_parquet(output / "dvol.parquet")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(frame) == acquisition.EXPECTED_ROWS
    assert frame.iloc[0]["timestamp"] == pd.Timestamp("2025-07-28T00:00:00Z")
    assert frame.iloc[-1]["timestamp"] == pd.Timestamp("2026-07-28T00:00:00Z")
    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close"]
    assert manifest["schema_version"] == "deribit_btc_dvol_hourly_bundle_v1"
    assert manifest["coverage"]["rows"] == acquisition.EXPECTED_ROWS
    assert manifest["coverage"]["hourly_gaps"] == 0
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["execution_authority"] == "none"
    assert set(manifest["files"]) == {
        "dvol.parquet",
        *(f"raw/page_{index:04d}.json" for index in range(1, 10)),
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"jsonrpc": "2.0", "error": {"code": 1}}, "JSON-RPC error"),
        ({"jsonrpc": "1.0", "result": {"data": [], "continuation": None}}, "version"),
        ({"jsonrpc": "2.0", "result": {"data": "bad", "continuation": None}}, "data"),
    ],
)
def test_acquisition_rejects_rpc_or_result_errors(
    tmp_path: Path,
    payload: dict[str, object],
    message: str,
) -> None:
    """API-shaped failures must not publish a success-shaped bundle."""
    output = tmp_path / "dvol"
    fetcher = PageFetcher([_encoded(payload)])

    with pytest.raises(ValueError, match=message):
        acquisition.acquire_deribit_dvol_bundle(output, fetcher, context=_context())

    assert not output.exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("short_row", "five values"),
        ("non_hour", "hour-aligned"),
        ("nonpositive", "finite and positive"),
        ("bad_ohlc", "OHLC bounds"),
        ("duplicate", "duplicate"),
        ("gap", "hourly continuity"),
        ("incomplete", "exact bounds"),
    ],
)
def test_acquisition_rejects_malformed_or_incomplete_history(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    """Malformed values and incomplete point-in-time coverage fail closed."""
    rows = _mutated_rows(mutation)
    output = tmp_path / "dvol"

    with pytest.raises(ValueError, match=message):
        acquisition.acquire_deribit_dvol_bundle(
            output,
            PageFetcher(_responses(rows)),
            context=_context(),
        )

    assert not output.exists()


def test_acquisition_rejects_non_decreasing_continuation(tmp_path: Path) -> None:
    """Only the documented backward continuation direction is supported."""
    payload = json.loads(_responses(_valid_rows())[0])
    payload["result"]["continuation"] = acquisition.END_TIMESTAMP_MS
    output = tmp_path / "dvol"

    with pytest.raises(ValueError, match="backward"):
        acquisition.acquire_deribit_dvol_bundle(
            output,
            PageFetcher([_encoded(payload)]),
            context=_context(),
        )

    assert not output.exists()


@pytest.mark.parametrize(
    ("context_change", "message"),
    [
        ({"hypothesis_id": "changed"}, "identity"),
        ({"execution_authority": "live"}, "execution authority"),
        ({"candidate_results_inspected_before_acquisition": True}, "candidate results"),
        ({"preregistration": {}}, "preregistration"),
    ],
)
def test_acquisition_rejects_context_drift_before_fetch(
    tmp_path: Path,
    context_change: dict[str, object],
    message: str,
) -> None:
    """Identity and authority drift must prevent all network access."""
    fetcher = PageFetcher(_responses(_valid_rows()))
    context = {**_context(), **context_change}

    with pytest.raises(ValueError, match=message):
        acquisition.acquire_deribit_dvol_bundle(
            tmp_path / "dvol",
            fetcher,
            context=context,
        )

    assert fetcher.requests == []


def test_acquisition_rejects_existing_output_before_fetch(tmp_path: Path) -> None:
    """Immutable bundle reuse must not issue another request."""
    output = tmp_path / "dvol"
    output.mkdir()
    fetcher = PageFetcher(_responses(_valid_rows()))

    with pytest.raises(FileExistsError, match="already exists"):
        acquisition.acquire_deribit_dvol_bundle(output, fetcher, context=_context())

    assert fetcher.requests == []


def _context() -> dict[str, object]:
    return {
        "hypothesis_id": "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1",
        "execution_authority": "none",
        "candidate_results_inspected_before_acquisition": False,
        "preregistration": {"bytes": 10, "sha256": "abc"},
    }


def _valid_rows() -> list[list[int | float]]:
    return [
        [
            acquisition.START_TIMESTAMP_MS + index * acquisition.HOUR_MS,
            50.0,
            51.0,
            49.0,
            50.5,
        ]
        for index in range(acquisition.EXPECTED_ROWS)
    ]


def _mutated_rows(mutation: str) -> list[list[int | float]]:
    rows = _valid_rows()
    if mutation == "short_row":
        rows[100] = rows[100][:-1]
    elif mutation == "non_hour":
        rows[100][0] += 1
    elif mutation == "nonpositive":
        rows[100][4] = 0.0
    elif mutation == "bad_ohlc":
        rows[100][1:] = [50.0, 49.0, 48.0, 51.0]
    elif mutation == "duplicate":
        rows[100][0] = rows[99][0]
    elif mutation == "gap":
        del rows[100]
    elif mutation == "incomplete":
        del rows[0]
    else:
        raise AssertionError(f"unknown mutation: {mutation}")
    return rows


def _responses(rows: list[list[int | float]]) -> list[bytes]:
    chunks = [rows[max(0, end - 1000) : end] for end in range(len(rows), 0, -1000)]
    responses: list[bytes] = []
    for index, chunk in enumerate(chunks):
        continuation = chunk[0][0] - 1 if index < len(chunks) - 1 else None
        responses.append(
            _encoded(
                {
                    "jsonrpc": "2.0",
                    "result": {"data": chunk, "continuation": continuation},
                }
            )
        )
    return responses


def _encoded(payload: object) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
