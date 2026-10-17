"""k-prefixed HL coins keep their case; HIP-3 / unlisted symbols keep fetched HL data.

Regressions:
- ``hl_coin('kPEPE')`` returned ``KPEPE`` (HL rejects it with HTTP 500).
- ``binance_symbol('xyz:TSLA')`` produced ``XYZ:TSLAUSDT``; every endpoint
  rejected it, ``load_research_history`` raised, and the HL candles it had
  already fetched were discarded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests

import hypervector.data.backfill as backfill
from hypervector.data.cache import ParquetCache
from hypervector.data.hl import hl_coin
from hypervector.data.pipeline import cache_key, load_research_history
from hypervector.data.sources import fixture_ohlcv

_NOW = pd.Timestamp("2026-10-17T00:00:00Z")


@pytest.mark.parametrize(
    ("symbol", "coin"),
    [
        ("kPEPE", "kPEPE"),
        ("kPEPE-PERP", "kPEPE"),
        ("kPEPEUSDT", "kPEPE"),
        (" kBONK ", "kBONK"),
        ("kSHIB", "kSHIB"),
        ("KAS", "KAS"),  # real uppercase coins starting with K stay as-is
        ("KAITO", "KAITO"),
        ("kas", "KAS"),  # lowercase input is not a 1000x contract
        ("btc-perp", "BTC"),
        ("xyz:TSLA", "xyz:TSLA"),
    ],
)
def test_hl_coin_preserves_case_sensitive_thousand_contracts(symbol: str, coin: str) -> None:
    assert hl_coin(symbol) == coin


def test_candle_request_sends_exact_k_coin() -> None:
    from hypervector.data.hl import fetch_hl_ohlcv

    seen: list[str] = []

    class _Resp:
        status_code = 200
        headers: dict[str, str] = {}

        def json(self) -> list[Any]:
            return []

        def raise_for_status(self) -> None:
            return None

    class _Sess:
        def post(self, url: str, json: dict[str, Any], timeout: Any = None) -> _Resp:
            del url, timeout
            seen.append(json["req"]["coin"])
            return _Resp()

    fetch_hl_ohlcv("kPEPE", "1h", 2, session=_Sess(), end_ms=1_792_195_200_000)  # type: ignore[arg-type]

    assert seen and set(seen) == {"kPEPE"}


def test_cex_symbol_maps_thousand_contracts_and_refuses_hip3() -> None:
    assert backfill.binance_symbol("kPEPE") == "1000PEPEUSDT"
    assert backfill.bybit_symbol("kBONK-PERP") == "1000BONKUSDT"
    assert backfill.binance_symbol("BTC") == "BTCUSDT"
    assert backfill.binance_symbol("ETHUSDT") == "ETHUSDT"
    with pytest.raises(backfill.BackfillUnavailable):
        backfill.binance_symbol("xyz:TSLA")


def _hl_tail(n_bars: int = 300) -> pd.DataFrame:
    start = _NOW - pd.Timedelta(minutes=n_bars - 1)
    return fixture_ohlcv(n_bars=n_bars, start=str(start.tz_localize(None)), source="hl")


def test_hip3_history_skips_cex_backfill_and_keeps_hl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hl = _hl_tail()
    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", lambda *_a: hl)
    monkeypatch.setattr(
        "hypervector.data.pipeline.live_binance_fetcher",
        lambda *_a: pytest.fail("Binance has no HIP-3 instrument"),
    )
    monkeypatch.setattr(
        "hypervector.data.pipeline.live_bybit_fetcher",
        lambda *_a: pytest.fail("Bybit has no HIP-3 instrument"),
    )

    frame, prov = load_research_history(
        tmp_path, symbol="xyz:TSLA", timeframe="1m", lookback_days=30, now=_NOW
    )

    assert len(frame) == len(hl)
    assert frame["source"].eq("hl").all()
    assert prov["backfill"]["binance"].startswith("not_applicable")
    assert prov["partial"] is True


def test_unlisted_cex_symbol_keeps_hl_history_and_reports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    hl = _hl_tail()

    def unlisted(*_a: Any) -> pd.DataFrame:
        raise backfill.BackfillUnavailable("venue does not list 1000NEIROUSDT")

    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", lambda *_a: hl)
    monkeypatch.setattr("hypervector.data.pipeline.live_binance_fetcher", unlisted)
    monkeypatch.setattr("hypervector.data.pipeline.live_bybit_fetcher", unlisted)

    with caplog.at_level("WARNING", logger="hypervector.data.pipeline"):
        frame, prov = load_research_history(
            tmp_path, symbol="kNEIRO", timeframe="1m", lookback_days=30, now=_NOW
        )

    assert len(frame) == len(hl)
    assert prov["backfill"]["binance"].startswith("unavailable")
    assert prov["backfill"]["bybit"].startswith("unavailable")
    assert any("unavailable" in r.getMessage() for r in caplog.records)


def test_transient_backfill_failure_is_loud_but_hl_data_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hl = _hl_tail()

    def binance_down(*_a: Any) -> pd.DataFrame:
        raise requests.ConnectionError("binance reset")

    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", lambda *_a: hl)
    monkeypatch.setattr("hypervector.data.pipeline.live_binance_fetcher", binance_down)

    with pytest.raises(requests.ConnectionError) as caught:
        load_research_history(tmp_path, symbol="BTC", timeframe="1m", lookback_days=30, now=_NOW)

    assert any("--strict-hl-only" in note for note in getattr(caught.value, "__notes__", []))
    cache = ParquetCache(tmp_path / "cache")
    assert not cache.exists(cache_key("BTC", "1m", 30))
    assert cache.exists(cache_key("BTC", "1m", 30, strict_hl_only=True))

    frame, prov = load_research_history(
        tmp_path,
        symbol="BTC",
        timeframe="1m",
        lookback_days=30,
        strict_hl_only=True,
        allow_network=False,
        now=_NOW,
    )
    assert len(frame) == len(hl)
    assert prov["cache_hit"] is True


class _ProbeSession:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)

    def get(self, url: str, params: dict[str, Any], timeout: Any = None) -> Any:
        del url, params, timeout
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        response = requests.Response()
        response.status_code = item
        response._content = b'{"code":-1121,"msg":"Invalid symbol."}' if item >= 400 else b"[]"
        return response


def test_endpoint_probe_classifies_unlisted_symbol() -> None:
    with pytest.raises(backfill.BackfillUnavailable):
        backfill._pick_binance_endpoint(_ProbeSession([400, 400, 451, 400]), "1000NEIROUSDT", "1m", 0)  # type: ignore[arg-type]


def test_endpoint_probe_transport_failure_stays_a_runtime_error() -> None:
    session = _ProbeSession([requests.ConnectionError("reset"), 400, 400, 400])
    with pytest.raises(RuntimeError) as caught:
        backfill._pick_binance_endpoint(session, "BTCUSDT", "1m", 0)  # type: ignore[arg-type]
    assert not isinstance(caught.value, backfill.BackfillUnavailable)


@pytest.mark.parametrize(
    ("symbol", "pair"),
    [
        ("BTC-Perp", "BTCUSDT"),  # suffixes are case-insensitive, as before
        ("kPEPE-Perp", "1000PEPEUSDT"),
        ("kPEPEusdt", "1000PEPEUSDT"),  # same coin hl_coin resolves to kPEPE
        ("kpepe", "KPEPEUSDT"),  # lowercase input is not a 1000x contract
    ],
)
def test_cex_symbol_suffixes_are_case_insensitive(symbol: str, pair: str) -> None:
    assert backfill.binance_symbol(symbol) == pair


def test_failure_keeping_hl_history_never_masks_the_backfill_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hl = _hl_tail()

    def binance_down(*_a: Any) -> pd.DataFrame:
        raise requests.ConnectionError("binance reset")

    def broken_save(*_a: Any, **_k: Any) -> Path:
        raise ValueError("parquet writer rejected the frame")

    monkeypatch.setattr("hypervector.data.pipeline.live_hl_fetcher", lambda *_a: hl)
    monkeypatch.setattr("hypervector.data.pipeline.live_binance_fetcher", binance_down)
    monkeypatch.setattr(ParquetCache, "save", broken_save)

    with pytest.raises(requests.ConnectionError) as caught:
        load_research_history(tmp_path, symbol="BTC", timeframe="1m", lookback_days=30, now=_NOW)

    assert any("could not keep" in note for note in getattr(caught.value, "__notes__", []))
