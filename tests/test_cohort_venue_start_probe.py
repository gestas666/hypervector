"""The armed start waits for a reachable venue and refuses a changed market contract."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
import requests

from test_hyperliquid_hip3_reader import _ADDRESS, _SYMBOL, _Info

from hypervector.live.cohort_venue_start_probe import (
    VENUE_WAIT_MARKER,
    await_venue_start,
    backoff_seconds,
    http_meta_fetcher,
)
from hypervector.live.hyperliquid_perp_reader import (
    HyperliquidPerpReader,
    VenueMetadataMismatchError,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfigError

_EXPECTED = {"BTC": 40, "ETH": 25, "xyz:SNDK": 10, "xyz:BRENTOIL": 20}
_META = {
    "": {
        "universe": [
            {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
            {"name": "ETH", "szDecimals": 4, "maxLeverage": 25},
            {"name": "SOL", "szDecimals": 2, "maxLeverage": 20},
        ]
    },
    "xyz": {
        "universe": [
            {"name": "xyz:SNDK", "szDecimals": 3, "maxLeverage": 10},
            {"name": "xyz:BRENTOIL", "szDecimals": 2, "maxLeverage": 20},
        ]
    },
}


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


class _Venue:
    """Answer each dex read from a script of failures, then from fixed metadata."""

    def __init__(
        self,
        failures: list[Exception] | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        self.failures = list(failures or [])
        self.meta = meta or _META
        self.reads: list[str] = []

    def __call__(self, dex: str) -> object:
        self.reads.append(dex)
        if self.failures:
            raise self.failures.pop(0)
        return self.meta[dex]


class _Clock:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def _probe(tmp_path: Path, venue: _Venue, clock: _Clock, **kwargs: object) -> int:
    lines: list[str] = []
    attempts = await_venue_start(
        kwargs.pop("expected", _EXPECTED),  # type: ignore[arg-type]
        fetch_meta=venue,
        stop_file=tmp_path / "STOP",
        marker=tmp_path / VENUE_WAIT_MARKER,
        sleep_fn=clock.sleep,
        now_fn=lambda: datetime(2026, 9, 24, 16, tzinfo=UTC),
        emit=lines.append,
        **kwargs,  # type: ignore[arg-type]
    )
    return attempts


def test_reachable_matching_venue_passes_on_the_first_attempt(tmp_path: Path) -> None:
    venue, clock = _Venue(), _Clock()

    assert _probe(tmp_path, venue, clock) == 1

    assert venue.reads == ["", "xyz"]
    assert clock.slept == []
    assert not (tmp_path / VENUE_WAIT_MARKER).exists()


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError("no route to host"),
        requests.Timeout("read timed out"),
        _http_error(503),
        _http_error(429),
    ],
)
def test_transient_failures_wait_with_capped_backoff(
    tmp_path: Path, failure: Exception
) -> None:
    """Seven failed attempts wait 15, 30, 60, 120, 240, 300 and 300 seconds."""
    venue, clock = _Venue([failure] * 7), _Clock()

    assert _probe(tmp_path, venue, clock) == 8

    assert sum(clock.slept) == 15 + 30 + 60 + 120 + 240 + 300 + 300
    assert max(clock.slept) <= 5.0
    assert [backoff_seconds(n) for n in range(1, 8)] == [
        15.0,
        30.0,
        60.0,
        120.0,
        240.0,
        300.0,
        300.0,
    ]


def test_the_wait_publishes_a_marker_and_removes_it_when_reachable(
    tmp_path: Path,
) -> None:
    marker = tmp_path / VENUE_WAIT_MARKER
    observed: list[dict[str, object]] = []
    venue = _Venue([requests.ConnectionError("down")] * 2)

    class _Watching(_Clock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            observed.append(json.loads(marker.read_text()))

    assert _probe(tmp_path, venue, _Watching()) == 3

    assert not marker.exists()
    assert observed[0]["attempts"] == 1
    assert observed[-1]["attempts"] == 2
    assert observed[-1]["reason"] == "transport_connection_retry_exhausted"
    assert observed[-1]["waiting_since_utc"] == "2026-09-24T16:00:00+00:00"
    assert isinstance(observed[-1]["pid"], int)


def test_a_stop_file_during_the_wait_refuses_the_start(tmp_path: Path) -> None:
    venue = _Venue([requests.ConnectionError("down")] * 100)
    stop = tmp_path / "STOP"

    class _Operator(_Clock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if len(self.slept) == 7:
                stop.write_text("operator stop")

    with pytest.raises(MultiAssetLiveConfigError, match="operator stop file"):
        _probe(tmp_path, venue, _Operator())

    assert len(venue.reads) <= 2
    assert not (tmp_path / VENUE_WAIT_MARKER).exists()


@pytest.mark.parametrize(
    "failure",
    [_http_error(400), _http_error(404), ValueError("malformed")],
)
def test_non_transient_failures_propagate_without_waiting(
    tmp_path: Path, failure: Exception
) -> None:
    venue, clock = _Venue([failure]), _Clock()

    with pytest.raises(type(failure)):
        _probe(tmp_path, venue, clock)

    assert clock.slept == []


def test_leverage_mismatch_is_refused_naming_every_market(tmp_path: Path) -> None:
    meta = json.loads(json.dumps(_META))
    meta["xyz"]["universe"][1]["maxLeverage"] = 10
    meta[""]["universe"][0]["maxLeverage"] = 50

    with pytest.raises(VenueMetadataMismatchError) as raised:
        _probe(tmp_path, _Venue(meta=meta), _Clock())

    message = str(raised.value)
    assert "BTC max leverage mismatch: expected 40, observed 50" in message
    assert "xyz:BRENTOIL max leverage mismatch: expected 20, observed 10" in message
    assert isinstance(raised.value, HyperliquidAdapterError)


def test_core_only_cohort_reads_only_the_core_dex(tmp_path: Path) -> None:
    venue = _Venue()

    _probe(tmp_path, venue, _Clock(), expected={"BTC": 40, "ETH": 25})

    assert venue.reads == [""]


def test_http_fetcher_posts_public_meta_with_a_timeout() -> None:
    calls: list[tuple[str, object, float]] = []

    class _Session:
        def post(self, url: str, *, json: object, timeout: float) -> object:
            calls.append((url, json, timeout))
            response = requests.Response()
            response.status_code = 200
            response._content = b'{"universe": []}'
            return response

    fetch = http_meta_fetcher(_Session())  # type: ignore[arg-type]

    assert fetch("xyz") == {"universe": []}
    assert calls == [
        ("https://api.hyperliquid.xyz/info", {"type": "meta", "dex": "xyz"}, 10.0)
    ]


def test_http_fetcher_raises_a_classifiable_status() -> None:
    class _Session:
        def post(self, *_args: object, **_kwargs: object) -> object:
            response = requests.Response()
            response.status_code = 502
            return response

    with pytest.raises(requests.HTTPError):
        http_meta_fetcher(_Session())("")  # type: ignore[arg-type]


def test_reader_preflight_mismatch_is_the_refusable_type() -> None:
    """Engine-start preflight raises the same type the live boundary refuses on."""
    reader = HyperliquidPerpReader(
        info=_Info(), account_address=_ADDRESS, symbol=_SYMBOL, perp_dex="xyz"
    )

    with pytest.raises(VenueMetadataMismatchError, match="expected 20, observed 50"):
        reader.preflight(expected_max_leverage=20)
