"""Offline identity and provenance checks for HIP-3 candle acquisition."""

from __future__ import annotations

import json
import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hypervector.data.oxa_api import API_ROOT, MarketFamily, OxaHistoryError
from hypervector.data.oxa_candles import (
    OxaCandleClient,
    OxaCandleRequest,
    acquire_and_store_candles,
    candle_output_directory,
    fetch_candle_history,
    read_complete_candle_evidence,
    store_candle_history,
)
from test_oxa_candles import FakeSession, VALID_PAGE

START = datetime(2026, 7, 26, tzinfo=UTC)
END = START + timedelta(minutes=1)


def _request(family: MarketFamily = "hip3") -> OxaCandleRequest:
    return OxaCandleRequest(
        "xyz:AAA" if family == "hip3" else "BTC",
        START,
        END,
        max_pages=1,
        market_family=family,
    )


@pytest.mark.parametrize("family", ["core", "hip3"])
def test_route_keeps_exact_family_symbol_and_request_bounds(
    family: MarketFamily, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the explicitly selected namespace receives the request."""
    calls: list[tuple[str, dict[str, int | str], float]] = []

    def get(
        _self: object, path: str, *, params: dict[str, int | str], timeout: float
    ) -> object:
        calls.append((path, params, timeout))
        return VALID_PAGE

    monkeypatch.setattr("hypervector.data.oxa_api.OxaRestClient.get", get)
    request = _request(family)
    page = OxaCandleClient(api_key="private-test-value").fetch_page(
        request, cursor="next-page"
    )
    prefix = "/hip3" if family == "hip3" else ""
    assert calls == [
        (f"{prefix}/candles/{request.symbol}", request.params("next-page"), 30.0)
    ]
    assert len(page.candles) == 1


@pytest.mark.parametrize(
    ("symbol", "family"),
    [
        ("xyz:AAA", "core"),
        ("AAA", "hip3"),
        ("XYZ:AAA", "hip3"),
        ("xyz:aaa", "hip3"),
        ("xyz:../AAA", "hip3"),
        ("BTC", "invalid"),
    ],
)
def test_request_rejects_wrong_family_and_malformed_identity(
    symbol: str, family: MarketFamily
) -> None:
    """An identifier is rejected instead of normalized or silently rerouted."""
    with pytest.raises(ValueError):
        OxaCandleRequest(symbol, START, END, market_family=family)


def test_core_positional_request_and_cache_path_remain_compatible(
    tmp_path: Path,
) -> None:
    """Appending family preserves all seven historical positional fields."""
    request = OxaCandleRequest("BTC", START, END, "1m", 100, 2, 9.0)
    assert request.market_family == "core"
    assert request.params() == {
        "start": int(START.timestamp() * 1000),
        "end": int(END.timestamp() * 1000),
        "interval": "1m",
        "limit": 100,
    }
    assert candle_output_directory(tmp_path, request).parent == (
        tmp_path / "cache/vendor/0xarchive/hyperliquid/BTC"
    )


@pytest.mark.parametrize("family", ["core", "hip3"])
def test_bundle_round_trip_retains_explicit_provenance(
    tmp_path: Path, family: MarketFamily
) -> None:
    """Raw reproduction and exact cadence bind the explicit source identity."""
    request = _request(family)
    result = fetch_candle_history(
        OxaCandleClient(api_key="test", session=FakeSession([VALID_PAGE])), request
    )
    stored = store_candle_history(tmp_path, request, result)
    manifest = json.loads(stored.manifest_path.read_text())
    prefix = "/hip3" if family == "hip3" else ""
    source = (
        "0xarchive_hyperliquid_hip3_candles"
        if family == "hip3"
        else ("0xarchive_hyperliquid_candles")
    )
    assert manifest["source"] == source
    assert manifest["market_family"] == family
    assert manifest["source_api"] == f"{API_ROOT}{prefix}/candles/{{symbol}}"
    assert stored.directory.parent == (
        tmp_path / f"cache/vendor/0xarchive/hyperliquid{prefix}" / request.symbol
    )
    frame, evidence = read_complete_candle_evidence(
        stored.directory, request, require_complete_cadence=True
    )
    assert len(frame) == 1
    assert evidence["raw_reproduction_matches"] is True


@pytest.mark.parametrize("family", ["core", "hip3"])
@pytest.mark.parametrize("field", ["market_family", "source", "source_api", "symbol"])
def test_reader_rejects_tampered_manifest_identity(
    tmp_path: Path, family: MarketFamily, field: str
) -> None:
    """Valid file hashes do not override contradictory provenance fields."""
    request = _request(family)
    result = fetch_candle_history(
        OxaCandleClient(api_key="test", session=FakeSession([VALID_PAGE])), request
    )
    stored = store_candle_history(tmp_path, request, result)
    manifest = json.loads(stored.manifest_path.read_text())
    manifest[field] = "wrong-identity"
    stored.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest differs"):
        read_complete_candle_evidence(stored.directory, request)


@pytest.mark.parametrize("family", ["core", "hip3"])
def test_omitted_family_is_accepted_only_for_legacy_core_bundles(
    tmp_path: Path, family: MarketFamily
) -> None:
    """Only legacy core evidence can lack a family field."""
    request = _request(family)
    result = fetch_candle_history(
        OxaCandleClient(api_key="test", session=FakeSession([VALID_PAGE])), request
    )
    stored = store_candle_history(tmp_path, request, result)
    manifest = json.loads(stored.manifest_path.read_text())
    manifest.pop("market_family", None)
    stored.manifest_path.write_text(json.dumps(manifest))
    if family == "hip3":
        with pytest.raises(ValueError, match="manifest differs"):
            read_complete_candle_evidence(stored.directory, request)
    else:
        frame, _ = read_complete_candle_evidence(stored.directory, request)
        assert len(frame) == 1


def test_acquisition_report_exposes_family_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stored HIP-3 bundle is reported with its exact family identity."""
    monkeypatch.setattr(
        "hypervector.data.oxa_api.requests.Session",
        lambda: FakeSession([VALID_PAGE]),
    )
    report = acquire_and_store_candles(
        data_root=tmp_path, api_key="private-test-value", request=_request()
    )
    assert report["market_family"] == "hip3"
    assert report["source"] == "0xarchive_hyperliquid_hip3_candles"
    assert report["symbol"] == "xyz:AAA"
    assert "private-test-value" not in json.dumps(report)


@pytest.mark.parametrize(
    "overrides",
    [
        {"interval": "2m"},
        {"limit": 0},
        {"limit": 10001},
        {"max_pages": 0},
        {"timeout_seconds": 0},
        {"end": START},
        {"start": START.replace(tzinfo=None)},
    ],
)
def test_extracted_request_preserves_invalid_bound_rejection(
    overrides: dict[str, object],
) -> None:
    """Moving the request model preserves its established bound failures."""
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(_request(), **overrides)


@pytest.mark.parametrize("field", ["quote_volume", "trade_count", "timestamp"])
def test_hip3_missing_required_evidence_is_not_fabricated(field: str) -> None:
    """Unsupported vendor omissions remain explicit parser failures."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["data"][0].pop(field)  # type: ignore[index]
    with pytest.raises(ValueError, match=field):
        fetch_candle_history(
            OxaCandleClient(api_key="test", session=FakeSession([payload])), _request()
        )


def test_hip3_page_requires_vendor_request_identifier() -> None:
    """A successful body cannot silently omit its evidence identifier."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["meta"].pop("request_id")  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="request_id"):
        fetch_candle_history(
            OxaCandleClient(api_key="test", session=FakeSession([payload])), _request()
        )


def test_incomplete_hip3_acquisition_does_not_publish_a_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page cap is a technical incomplete result, not a successful archive."""
    payload = copy.deepcopy(VALID_PAGE)
    payload["meta"]["next_cursor"] = "next"  # type: ignore[index]
    monkeypatch.setattr(
        "hypervector.data.oxa_api.requests.Session", lambda: FakeSession([payload])
    )
    with pytest.raises(ValueError, match="max-pages exhausted"):
        acquire_and_store_candles(
            data_root=tmp_path, api_key="test", request=_request()
        )
    assert not candle_output_directory(tmp_path, _request()).exists()


def test_hip3_http_failure_does_not_fall_back_to_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed family endpoint cannot be retried with a different identity."""
    calls: list[str] = []

    def get(
        _self: object, path: str, *, params: dict[str, int | str], timeout: float
    ) -> object:
        calls.append(path)
        raise OxaHistoryError("0xArchive request failed with HTTP 404", status_code=404)

    monkeypatch.setattr("hypervector.data.oxa_api.OxaRestClient.get", get)
    with pytest.raises(OxaHistoryError, match="HTTP 404"):
        fetch_candle_history(OxaCandleClient(api_key="test"), _request())
    assert calls == ["/hip3/candles/xyz:AAA"]
