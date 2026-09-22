"""A transient public candle server error must use the bounded read retry budget."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from hypervector.data.hl import fetch_hl_ohlcv_snapshot
from hypervector.live.transient_transport import transient_read_failure_reason

_END_MS = 1_785_585_600_000


def _response(status: int, retry_after: str | None = None) -> requests.Response:
    """Construct a real response so production HTTP-error handling is exercised."""
    response = requests.Response()
    response.status_code = status
    response.url = "https://example.invalid/info"
    response._content = (
        Path(__file__).parent / "fixtures/hl_candle_sample.json"
    ).read_bytes()
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return response


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_transient_server_error_recovers_fresh_candles(status: int) -> None:
    """One temporary failure is followed by a fresh successful response."""
    healthy = _response(200)
    session = Mock(spec=requests.Session)
    session.post.side_effect = [_response(status), healthy]
    delays: list[float] = []

    frame = fetch_hl_ohlcv_snapshot(
        "BTC", "1m", 14, session=session, end_ms=_END_MS, sleep_fn=delays.append
    )

    assert session.post.call_count == 2
    assert delays == [1.0]
    assert len(frame) == len(json.loads(healthy.content))


def test_server_error_exhaustion_preserves_final_response() -> None:
    """Repeated gateway failure stops after four requests without stale fallback."""
    responses = [_response(502) for _ in range(4)]
    session = Mock(spec=requests.Session)
    session.post.side_effect = responses
    delays: list[float] = []

    with pytest.raises(requests.HTTPError) as caught:
        fetch_hl_ohlcv_snapshot(
            "BTC", "1m", 14, session=session, end_ms=_END_MS, sleep_fn=delays.append
        )

    assert caught.value.response is responses[-1]
    assert session.post.call_count == 4
    assert delays == [1.0, 2.0, 4.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 501])
def test_permanent_http_error_is_not_retried(status: int) -> None:
    """Invalid requests and unsupported endpoints retain immediate failure."""
    response = _response(status)
    session = Mock(spec=requests.Session)
    session.post.return_value = response
    delays: list[float] = []

    with pytest.raises(requests.HTTPError) as caught:
        fetch_hl_ohlcv_snapshot(
            "BTC", "1m", 14, session=session, end_ms=_END_MS, sleep_fn=delays.append
        )

    assert caught.value.response is response
    assert session.post.call_count == 1
    assert delays == []


def test_server_retry_after_obeys_existing_delay_cap() -> None:
    """A gateway response cannot ask the polling loop to sleep without bounds."""
    session = Mock(spec=requests.Session)
    session.post.side_effect = [_response(503, "600"), _response(200)]
    delays: list[float] = []

    fetch_hl_ohlcv_snapshot(
        "BTC", "1m", 14, session=session, end_ms=_END_MS, sleep_fn=delays.append
    )

    assert delays == [15.0]
    assert session.post.call_count == 2


def test_gateway_degradation_preserves_required_deadline_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exhausted gateway read still permits the existing unconditional close."""
    from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
    from hypervector.live.transient_transport import transient_read_failure_reason
    from test_cohort_degraded_deadlines import (
        FailingPoller,
        REFERENCE_PRICE,
        SOFT_MS,
        runner_fixture,
    )

    error = requests.HTTPError("gateway failure", response=_response(502))
    reason = transient_read_failure_reason(error)
    assert reason == "http_server_retry_exhausted"
    monkeypatch.setattr(
        FailingPoller,
        "failure",
        TransientCohortMarketDataError(source="public_candles", reason=reason),
    )
    runner, engine, telemetry = runner_fixture(
        tmp_path, age_ms=SOFT_MS, side=-0.25, extension=False
    )

    assert runner.run(max_polls=1) == 1
    assert engine.exits == [(REFERENCE_PRICE, "maximum_hold_seconds")]
    assert telemetry.degraded_polls == [("public_candles", reason)]
    assert telemetry.heartbeats == 0
    assert all(not asset.entries for asset in runner._engines.values())


def test_gateway_mutation_failure_remains_ambiguous_without_retry() -> None:
    """A lost signed response must retain identity instead of becoming a read."""
    from hypervector.live.sol_order_transport import (
        SolOrderTransportError,
        call_ambiguous_order_mutation,
    )
    from hypervector.live.transient_transport import transient_read_failure_reason

    error = requests.HTTPError("gateway failure", response=_response(502))
    mutation = Mock(side_effect=error)
    identity = "0x11111111111111111111111111111111"

    with pytest.raises(SolOrderTransportError) as caught:
        call_ambiguous_order_mutation(
            operation="entry", client_order_id=identity, mutation=mutation
        )

    mutation.assert_called_once_with()
    assert caught.value.client_order_id == identity
    assert caught.value.ambiguous is True
    assert caught.value.__cause__ is error
    assert transient_read_failure_reason(caught.value) is None


def test_well_formed_but_unexpected_body_degrades_like_a_gateway_error() -> None:
    """A 200 carrying a non-list body is the same gateway class as a 502.

    A bare RuntimeError escapes the poller's classifier, `poll_with_deadlines`'
    transient handler and both of the run loop's handlers, so it hard-exits the
    backend and skips the unconditional maximum-hold exits that the transient path
    guarantees.
    """
    response = requests.Response()
    response.status_code = 200
    response.url = "https://example.invalid/info"
    response._content = json.dumps({"error": "gateway rewrote the body"}).encode()
    session = Mock()
    session.post.return_value = response

    with pytest.raises(requests.RequestException):
        fetch_hl_ohlcv_snapshot(
            "BTC", "1h", lookback_days=1, end_ms=_END_MS, session=session
        )

    assert (
        transient_read_failure_reason(
            _raised(session, response)
        )
        is not None
    ), "the classifier must treat it as retryable transport degradation"


def _raised(session: Mock, response: requests.Response) -> Exception:
    try:
        fetch_hl_ohlcv_snapshot(
            "BTC", "1h", lookback_days=1, end_ms=_END_MS, session=session
        )
    except requests.RequestException as exc:
        return exc
    raise AssertionError("expected a requests-typed failure")
