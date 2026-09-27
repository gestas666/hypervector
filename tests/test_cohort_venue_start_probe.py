"""The armed start waits for a reachable venue and refuses a broken market contract."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
import logging
from pathlib import Path

import pytest
import requests

from test_hyperliquid_hip3_reader import _ADDRESS, _SYMBOL, _Info

from hypervector.live.cohort_venue_start_probe import (
    VENUE_WAIT_MARKER,
    await_venue_start,
    backoff_seconds,
    http_meta_fetcher,
    require_market_contract,
    requested_market_leverage,
)
from hypervector.live.hyperliquid_perp_reader import (
    VENUE_MAX_LEVERAGE_CHANGED,
    HyperliquidPerpReader,
    VenueMetadataMismatchError,
)
from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

_EXPECTED = {"BTC": 40, "ETH": 25, "xyz:SNDK": 10, "xyz:BRENTOIL": 20}
# The leverage each market's engine requests, rounded up (V94's values).
_REQUESTED = {"BTC": 10, "ETH": 15, "xyz:SNDK": 8, "xyz:BRENTOIL": 8}
_V94 = Path("configs/multi_asset_growth_first_5000_review_actions_v94.toml")
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


def _probe(
    tmp_path: Path,
    venue: _Venue,
    clock: _Clock,
    lines: list[str] | None = None,
    **kwargs: object,
) -> int:
    lines = [] if lines is None else lines
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


def _meta_with(**max_leverage: int) -> dict[str, object]:
    """Return the fixture metadata with some markets' maximum leverage changed."""
    meta = json.loads(json.dumps(_META))
    for universe in (meta[""]["universe"], meta["xyz"]["universe"]):
        for market in universe:
            key = market["name"].replace("xyz:", "xyz_")
            if key in max_leverage:
                market["maxLeverage"] = max_leverage[key]
    return meta


def test_without_requested_leverage_any_mismatch_is_refused_naming_every_market(
    tmp_path: Path,
) -> None:
    """The exact pin stays in force until the caller passes requested leverage."""
    meta = _meta_with(BTC=50, xyz_BRENTOIL=10)

    with pytest.raises(VenueMetadataMismatchError) as raised:
        _probe(tmp_path, _Venue(meta=meta), _Clock())

    message = str(raised.value)
    assert "BTC max leverage mismatch: expected 40, observed 50" in message
    assert "xyz:BRENTOIL max leverage mismatch: expected 20, observed 10" in message
    assert isinstance(raised.value, HyperliquidAdapterError)


def test_a_venue_increase_warns_and_the_start_continues(tmp_path: Path) -> None:
    """An increase never lets the engine request more than the venue allows."""
    lines: list[str] = []

    assert (
        _probe(
            tmp_path,
            _Venue(meta=_meta_with(BTC=50)),
            _Clock(),
            lines,
            requested_leverage=_REQUESTED,
        )
        == 1
    )

    assert lines == [
        f"{VENUE_MAX_LEVERAGE_CHANGED}: BTC venue max leverage 50 differs from the "
        "profile's 40; the requested leverage 10 is still allowed, so the start "
        "continues",
        "venue start probe passed: markets=4 attempts=1",
    ]


def test_a_decrease_that_still_allows_the_requested_leverage_warns(
    tmp_path: Path,
) -> None:
    """A cut to exactly the requested leverage is still allowed."""
    lines: list[str] = []

    _probe(
        tmp_path,
        _Venue(meta=_meta_with(xyz_BRENTOIL=8, ETH=20)),
        _Clock(),
        lines,
        requested_leverage=_REQUESTED,
    )

    warnings = [line for line in lines if line.startswith(VENUE_MAX_LEVERAGE_CHANGED)]
    assert len(warnings) == 2
    assert "ETH venue max leverage 20 differs from the profile's 25" in warnings[0]
    assert (
        "xyz:BRENTOIL venue max leverage 8 differs from the profile's 20" in warnings[1]
    )
    assert lines[-1] == "venue start probe passed: markets=4 attempts=1"


def test_a_decrease_below_the_requested_leverage_is_refused_naming_every_market(
    tmp_path: Path,
) -> None:
    """Only a venue maximum below the requested leverage refuses; others still warn."""
    lines: list[str] = []
    meta = _meta_with(BTC=50, ETH=10, xyz_SNDK=5)

    with pytest.raises(VenueMetadataMismatchError) as raised:
        _probe(
            tmp_path,
            _Venue(meta=meta),
            _Clock(),
            lines,
            requested_leverage=_REQUESTED,
        )

    assert str(raised.value) == (
        "ETH venue max leverage 10 is below the requested leverage 15 (profile venue "
        "maximum 25); xyz:SNDK venue max leverage 5 is below the requested leverage "
        "8 (profile venue maximum 10)"
    )
    assert [line.split(":")[0] for line in lines] == [VENUE_MAX_LEVERAGE_CHANGED]
    assert not any("probe passed" in line for line in lines)


def test_an_unchanged_venue_with_requested_leverage_emits_no_warning(
    tmp_path: Path,
) -> None:
    lines: list[str] = []

    _probe(tmp_path, _Venue(), _Clock(), lines, requested_leverage=_REQUESTED)

    assert lines == ["venue start probe passed: markets=4 attempts=1"]


@pytest.mark.parametrize(
    "requested",
    [
        {"BTC": 10, "ETH": 15, "xyz:SNDK": 8},
        {**_REQUESTED, "SOL": 8},
        {**_REQUESTED, "ETH": 0},
        {**_REQUESTED, "ETH": True},
        {**_REQUESTED, "ETH": 15.0},
    ],
)
def test_malformed_requested_leverage_is_refused_before_any_venue_read(
    tmp_path: Path, requested: dict[str, object]
) -> None:
    venue = _Venue()

    with pytest.raises(ValueError, match="requested leverage"):
        _probe(tmp_path, venue, _Clock(), requested_leverage=requested)

    assert venue.reads == []


def test_every_configured_market_is_held_to_its_rounded_up_leverage() -> None:
    """Watch-only markets are included: each market's engine sets leverage at start."""
    config = load_multi_asset_live_config(_V94, mode="live")
    watch_only = set(config.symbols) - {
        symbol for _strategy, symbol in config.executable_provider_symbols
    }

    requested = requested_market_leverage(config)

    assert watch_only == {"HYPE", "xyz:SPCX"}
    assert requested == {
        "BTC": 10,
        "ETH": 15,
        "SOL": 8,
        "HYPE": 10,
        "xyz:SPCX": 10,
        "xyz:SNDK": 8,
        "xyz:BRENTOIL": 8,
        "xyz:TSLA": 8,
    }
    fractional = replace(
        config,
        assets=tuple(
            replace(asset, leverage=7.5) if asset.symbol == "SOL" else asset
            for asset in config.assets
        ),
    )
    assert requested_market_leverage(fractional)["SOL"] == 8


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


def _reader() -> HyperliquidPerpReader:
    """Return a reader whose venue reports a maximum leverage of 50."""
    return HyperliquidPerpReader(
        info=_Info(), account_address=_ADDRESS, symbol=_SYMBOL, perp_dex="xyz"
    )


def test_reader_preflight_mismatch_is_the_refusable_type() -> None:
    """Engine-start preflight raises the same type the live boundary refuses on."""
    with pytest.raises(VenueMetadataMismatchError, match="expected 20, observed 50"):
        _reader().preflight(expected_max_leverage=20)


def test_reader_preflight_refuses_only_below_the_requested_leverage() -> None:
    with pytest.raises(VenueMetadataMismatchError) as raised:
        _reader().preflight(expected_max_leverage=60, requested_leverage=51)

    assert str(raised.value) == (
        f"{_SYMBOL} venue max leverage 50 is below the requested leverage 51 "
        "(profile venue maximum 60)"
    )


@pytest.mark.parametrize("expected", [20, 60])
def test_reader_preflight_warns_on_a_tolerated_change_and_continues(
    expected: int, caplog: pytest.LogCaptureFixture
) -> None:
    """An increase (20 -> 50) or a cut that still allows 10x (60 -> 50) warns."""
    with caplog.at_level(
        logging.WARNING, logger="hypervector.live.hyperliquid_perp_reader"
    ):
        preflight = _reader().preflight(
            expected_max_leverage=expected, requested_leverage=10
        )

    assert preflight.market.max_leverage == 50
    assert [record.getMessage() for record in caplog.records] == [
        f"{VENUE_MAX_LEVERAGE_CHANGED}: {_SYMBOL} venue max leverage 50 differs from "
        f"the profile's {expected}; the requested leverage 10 is still allowed, so "
        "the start continues"
    ]


def test_reader_preflight_with_an_unchanged_venue_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        _reader().preflight(expected_max_leverage=50, requested_leverage=50)

    assert caplog.records == []


@pytest.mark.parametrize("requested", [0, -1, True, 10.0])
def test_reader_preflight_refuses_a_malformed_requested_leverage_before_any_read(
    requested: int,
) -> None:
    """The engine preflight refuses bad input like the probe: same type, no read."""
    info = _Info()
    reader = HyperliquidPerpReader(
        info=info, account_address=_ADDRESS, symbol=_SYMBOL, perp_dex="xyz"
    )

    with pytest.raises(
        ValueError, match=f"^{_SYMBOL} requested leverage must be a positive integer$"
    ):
        reader.preflight(expected_max_leverage=50, requested_leverage=requested)

    assert info.calls == []


@pytest.mark.parametrize(
    ("expected", "observed", "requested"),
    [
        (40, 40, 10),
        (40, 50, 10),
        (40, 10, 10),
        (40, 9, 10),
        (10, 5, 10),
        (20, 20, None),
        (20, 25, None),
        (20, 15, None),
    ],
)
def test_probe_and_engine_preflight_apply_one_rule(
    expected: int, observed: int, requested: int | None
) -> None:
    """The start probe and the engine preflight refuse exactly the same venues."""
    meta = {
        "": {"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": observed}]}
    }
    probe_refused = reader_refused = False
    try:
        require_market_contract(
            {"BTC": expected},
            meta,
            requested_leverage=None if requested is None else {"BTC": requested},
            emit=lambda _line: None,
        )
    except VenueMetadataMismatchError:
        probe_refused = True

    class _BtcInfo(_Info):
        def meta(self, dex: str = "") -> object:
            return meta[""]

        def all_mids(self, dex: str = "") -> object:
            return {"BTC": "100000.0"}

    reader = HyperliquidPerpReader(
        info=_BtcInfo(), account_address=_ADDRESS, symbol="BTC"
    )
    try:
        reader.preflight(expected_max_leverage=expected, requested_leverage=requested)
    except VenueMetadataMismatchError:
        reader_refused = True

    assert probe_refused == reader_refused
    assert probe_refused == (
        observed != expected if requested is None else observed < requested
    )
