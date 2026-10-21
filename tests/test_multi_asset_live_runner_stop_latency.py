"""A stop reaches the clean shutdown path within about one read timeout.

The supervisor gives the backend 30 s after SIGTERM. Before this bound the stop
was only read between polls: the inter-poll sleep resumed after the handler
(PEP 475) and a public candle read on a dead network could hold the poll for
minutes. These tests pin the three halves of the fix: a hung candle read is
abandoned at its timeout, an idle wait ends within a second, and an order that
is already in flight is never interrupted. The loopback tests send a real
SIGTERM to a real socket read; nothing here contacts Hyperliquid.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import threading
import time
from types import ModuleType
from unittest.mock import Mock

import pytest
import requests

from multi_asset_live_runner_fixtures import execution_contract
from test_cohort_candle_session import PROFILE, _boundary, _retain_fetcher
from test_multi_asset_bidirectional_live_script import _args, _load_module
from test_multi_asset_live_runner import (
    _SYMBOLS,
    _Engine,
    _intent,
    _Poller,
    _Telemetry,
)

from hypervector.data.hl import hl_coin
from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    StrategyCapability,
)
from hypervector.live.multi_asset_intent_poller import (
    ConfiguredMultiAssetIntentPoller,
)
from hypervector.live.multi_asset_live_protocols import MultiAssetIntentPollerProtocol
from hypervector.live.multi_asset_live_runner import MultiAssetLiveRunner
from hypervector.live.process_signal_stop import (
    STOP_CHECK_SECONDS,
    ProcessSignalStop,
    ProcessStopRequested,
    install_process_signal_stop,
    stop_aware_sleep,
)
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState

_PROFILE_A = Path("tests/fixtures/cohort_chain/profile_a.toml")
_NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)
_END_MS = 1_785_585_600_000
_LIVE_READ_TIMEOUT_SECONDS = 10.0
# The loopback tests shorten the live (connect, read) timeout to keep them fast.
_LOOPBACK_TIMEOUT_SECONDS = (1.0, 1.0)
_HANDLED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class _Clock:
    """A monotonic clock that moves only when a read or a wait spends it."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.sleeps: list[float] = []
        self.on_sleep: Callable[[], None] = lambda: None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        self.on_sleep()


@pytest.fixture
def restored_signal_handlers() -> Iterator[None]:
    """Let one test install the real latch without leaking it into the session."""
    saved = {signum: signal.getsignal(signum) for signum in _HANDLED}
    try:
        yield
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)


def _router(symbols: tuple[str, ...]) -> BidirectionalIntentRouter:
    return BidirectionalIntentRouter(
        tuple(
            StrategyCapability("hulk", symbol, frozenset({"long", "short"}), 10)
            for symbol in symbols
        ),
        maximum_positions=2,
    )


def _runner(
    tmp_path: Path,
    script: ModuleType,
    *,
    symbols: tuple[str, ...],
    engines: dict[str, _Engine],
    poller: MultiAssetIntentPollerProtocol,
    telemetry: _Telemetry,
    clock: _Clock,
    latch: ProcessSignalStop,
) -> MultiAssetLiveRunner:
    """Build the runner with the launcher's own stop test and stop-aware wait."""
    stop_file = tmp_path / "STOP"
    pairs = frozenset(("hulk", symbol) for symbol in symbols)
    return MultiAssetLiveRunner(
        symbols=symbols,
        engines=engines,
        router=_router(symbols),
        intent_poller=poller,
        telemetry=telemetry,
        stop_file=stop_file,
        now_fn=lambda: _NOW,
        sleep_fn=partial(
            stop_aware_sleep,
            stop_requested=partial(script._backend_stop_requested, stop_file, latch),
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
        ),
        monotonic_fn=clock.monotonic,
        poll_seconds=15.0,
        signal_stop_requested=lambda: latch.requested,
        maximum_hold_seconds_by_symbol={symbol: 28_800 for symbol in symbols},
        execution_contracts={"hulk": execution_contract()},
        maximum_entry_delay_ms_by_provider_symbol={pair: 60_000 for pair in pairs},
        executable_provider_symbols=pairs,
    )


def _stopped_by_operator(snapshot: SolLiveSnapshot) -> bool:
    return (
        snapshot.state is SolLiveState.STOPPED
        and snapshot.stop_reason == "operator_stop"
    )


def _healthy_candles() -> Mock:
    response = Mock(status_code=200, headers={})
    response.json.return_value = []
    return response


def test_stop_during_a_hung_candle_read_exits_within_the_read_timeout(
    tmp_path: Path,
) -> None:
    """SIGTERM mid-read on a dead network: one 10 s timeout, then the clean stop.

    The real poller and the launcher's live candle fetcher are used, so the stop
    must pass through both unchanged. Before the fix this read alone could take
    4 x 30 s + 7 s, and every later symbol could do the same.
    """
    script = _load_module()
    config = script.load_multi_asset_live_config(_PROFILE_A, mode="observe")
    symbols = config.symbols
    clock = _Clock()
    latch = ProcessSignalStop()
    reads: list[tuple[str, object]] = []
    signalled_at: list[float] = []

    def post(_url: str, *, json: dict[str, dict[str, str]], timeout: object) -> Mock:
        reads.append((json["req"]["coin"], timeout))
        if len(reads) == 1:
            return _healthy_candles()
        # The supervisor's SIGTERM lands while this read hangs; it then times out.
        latch.requested = True
        signalled_at.append(clock.now)
        clock.now += _LIVE_READ_TIMEOUT_SECONDS
        raise requests.ReadTimeout("read timed out")

    session = Mock(spec=requests.Session)
    session.post.side_effect = post
    poller = ConfiguredMultiAssetIntentPoller(
        config=config,
        fetch_bars=script._live_candle_fetcher(
            session, partial(script._backend_stop_requested, tmp_path / "STOP", latch)
        ),
        collectors={provider.strategy_id: Mock() for provider in config.providers},
        canonical_regime_collector=Mock(),
    )
    engines = {symbol: _Engine(symbol) for symbol in symbols}
    telemetry = _Telemetry()
    runner = _runner(
        tmp_path,
        script,
        symbols=symbols,
        engines=engines,
        poller=poller,
        telemetry=telemetry,
        clock=clock,
        latch=latch,
    )

    assert runner.run(max_polls=5) == 0

    # No retry of the hung read, and no read for any later symbol.
    assert [coin for coin, _ in reads] == [hl_coin(symbol) for symbol in symbols[:2]]
    assert {timeout for _, timeout in reads} == {(5.0, 10.0)}
    # The fake read spends its own timeout; nothing after it may spend more (no
    # retry wait, no later read, no poll wait). The loopback tests below pin
    # that a real socket read ends at that timeout despite the signal.
    assert clock.now - signalled_at[0] == _LIVE_READ_TIMEOUT_SECONDS
    assert clock.sleeps == []
    # Abandoned for a stop, not degraded; no deadline reconciliation was added.
    assert telemetry.degraded_polls == []
    assert all(len(engine.reconciliations) == 1 for engine in engines.values())
    assert all(_stopped_by_operator(engine.snapshot) for engine in engines.values())


class _HangingInfoServer:
    """A loopback info endpoint: the first ``healthy`` reads get ``[]``, the rest hang."""

    def __init__(self, healthy: int) -> None:
        self.requests = 0
        self.hanging = threading.Event()
        self._release = threading.Event()
        server = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802 - the http.server hook name
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                server.requests += 1
                if server.requests > healthy:
                    server.hanging.set()
                    server._release.wait(30.0)
                    return
                body = b"[]"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host!s}:{port}/info"

    def __enter__(self) -> _HangingInfoServer:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._release.set()
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()


@contextmanager
def _sigterm_while_hanging(server: _HangingInfoServer) -> Iterator[None]:
    """Send the main thread one SIGTERM 0.2 s into the hung read.

    The signal is never sent after the block exits, so it cannot outlive the
    test's latch and reach the default handler.
    """
    main_thread = threading.main_thread().ident
    assert main_thread is not None
    guard = threading.Lock()
    armed = [True]

    def fire() -> None:
        if not server.hanging.wait(5.0):
            return
        time.sleep(0.2)
        with guard:
            if armed[0]:
                signal.pthread_kill(main_thread, signal.SIGTERM)

    thread = threading.Thread(target=fire, daemon=True)
    thread.start()
    try:
        yield
    finally:
        with guard:
            armed[0] = False
        thread.join()


def _loopback_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False  # a proxy from the environment must not see loopback
    return session


@pytest.mark.integration
@pytest.mark.usefixtures("restored_signal_handlers")
def test_a_real_sigterm_neither_cuts_short_nor_extends_a_hung_socket_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The launcher's fetcher on a real socket: one read timeout, then the stop.

    PEP 475 resumes the interrupted receive for only the time that remained, so
    the read ends at its timeout; the stop check then abandons the ladder.
    """
    script = _load_module()
    monkeypatch.setattr(
        script, "_PUBLIC_CANDLE_TIMEOUT_SECONDS", _LOOPBACK_TIMEOUT_SECONDS
    )
    latch = install_process_signal_stop(ProcessSignalStop())
    with _HangingInfoServer(healthy=0) as server, _loopback_session() as session:
        monkeypatch.setattr("hypervector.data.hl.HL_INFO_URL", server.url)
        fetch = script._live_candle_fetcher(
            session, partial(script._backend_stop_requested, tmp_path / "STOP", latch)
        )
        started = time.monotonic()
        with (
            _sigterm_while_hanging(server),
            pytest.raises(ProcessStopRequested) as caught,
        ):
            fetch("BTC", "1m", 5 / 1440, end_ms=_END_MS)
        elapsed = time.monotonic() - started

    assert latch.requested is True
    assert server.requests == 1
    assert isinstance(caught.value.__context__, requests.ReadTimeout)
    # A retry would add a 1 s back-off and a second 1 s read.
    assert 0.9 <= elapsed < 2.0


@pytest.mark.integration
@pytest.mark.usefixtures("restored_signal_handlers")
def test_a_real_sigterm_mid_poll_reaches_the_clean_stop_within_one_read_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Real poller, launcher fetcher, runner and socket: the whole stop path."""
    script = _load_module()
    config = script.load_multi_asset_live_config(_PROFILE_A, mode="observe")
    monkeypatch.setattr(
        script, "_PUBLIC_CANDLE_TIMEOUT_SECONDS", _LOOPBACK_TIMEOUT_SECONDS
    )
    latch = install_process_signal_stop(ProcessSignalStop())
    engines = {symbol: _Engine(symbol) for symbol in config.symbols}
    telemetry = _Telemetry()
    with _HangingInfoServer(healthy=1) as server, _loopback_session() as session:
        monkeypatch.setattr("hypervector.data.hl.HL_INFO_URL", server.url)
        poller = ConfiguredMultiAssetIntentPoller(
            config=config,
            fetch_bars=script._live_candle_fetcher(
                session,
                partial(script._backend_stop_requested, tmp_path / "STOP", latch),
            ),
            collectors={provider.strategy_id: Mock() for provider in config.providers},
            canonical_regime_collector=Mock(),
        )
        runner = _runner(
            tmp_path,
            script,
            symbols=config.symbols,
            engines=engines,
            poller=poller,
            telemetry=telemetry,
            clock=_Clock(),
            latch=latch,
        )
        started = time.monotonic()
        with _sigterm_while_hanging(server):
            polls = runner.run(max_polls=5)
        elapsed = time.monotonic() - started

    assert polls == 0
    # The first symbol's read, then the hung one; no retry and no later symbol.
    assert server.requests == 2
    assert telemetry.degraded_polls == []
    assert all(_stopped_by_operator(engine.snapshot) for engine in engines.values())
    assert elapsed < 2.0


@pytest.mark.parametrize("request_stop", ["signal", "stop_file"])
def test_stop_during_the_inter_poll_wait_exits_within_one_second(
    tmp_path: Path,
    request_stop: str,
) -> None:
    """A stop 3.4 s into the 15 s wait is honoured at the next one-second slice."""
    script = _load_module()
    clock = _Clock()
    latch = ProcessSignalStop()
    arrives_at = clock.now + 3.4

    def request() -> None:
        if clock.now < arrives_at:
            return
        if request_stop == "signal":
            latch.requested = True
        else:
            (tmp_path / "STOP").write_text("stop\n", encoding="utf-8")

    clock.on_sleep = request
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    poller = _Poller(())
    runner = _runner(
        tmp_path,
        script,
        symbols=_SYMBOLS,
        engines=engines,
        poller=poller,
        telemetry=_Telemetry(),
        clock=clock,
        latch=latch,
    )

    assert runner.run(max_polls=5) == 1

    assert clock.sleeps == [1.0, 1.0, 1.0, 1.0]
    assert clock.now - arrives_at <= STOP_CHECK_SECONDS
    assert len(poller.observed_at) == 1
    assert all(_stopped_by_operator(engine.snapshot) for engine in engines.values())


class _SignalledMidEntry(_Engine):
    """Receive the supervisor's SIGTERM between the entry fill and its stop."""

    def __init__(self, symbol: str) -> None:
        super().__init__(symbol)
        self.steps: list[str] = []

    def enter(self, **kwargs: object) -> SolLiveSnapshot:  # type: ignore[override]
        self.steps.append("entry_filled")
        signal.raise_signal(signal.SIGTERM)
        time.sleep(0.01)  # a handler that raised would surface here at the latest
        self.steps.append("protective_stop_placed")
        return super().enter(**kwargs)  # type: ignore[arg-type]


@pytest.mark.usefixtures("restored_signal_handlers")
def test_a_signal_during_order_submission_never_interrupts_it(
    tmp_path: Path,
) -> None:
    """A real SIGTERM mid-entry: the stop is placed, the cycle ends, then the stop.

    The venue stop is left resting: the clean shutdown path changes only the
    local lifecycle state.
    """
    script = _load_module()
    latch = install_process_signal_stop(ProcessSignalStop())
    clock = _Clock()
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    signalled = _SignalledMidEntry("BTC")
    engines["BTC"] = signalled
    telemetry = _Telemetry()
    poller = _Poller((_intent("BTC", "long"),))
    runner = _runner(
        tmp_path,
        script,
        symbols=_SYMBOLS,
        engines=engines,
        poller=poller,
        telemetry=telemetry,
        clock=clock,
        latch=latch,
    )

    assert runner.run(max_polls=5) == 1

    assert latch.requested is True
    assert signalled.steps == ["entry_filled", "protective_stop_placed"]
    assert len(signalled.entries) == 1
    assert telemetry.funding_windows[0]["post_action_reconciliation"] is True
    assert len(poller.observed_at) == 1
    assert clock.sleeps == []
    stopped = signalled.snapshot
    assert _stopped_by_operator(stopped)
    assert stopped.stop_oid == 2
    assert stopped.position_size_signed == 1.0


class _StopCheckInsideExecution(_Engine):
    """A misplaced stop check inside an order-capable operation."""

    def enter(self, **kwargs: object) -> SolLiveSnapshot:  # type: ignore[override]
        raise ProcessStopRequested("stop check inside an order operation")


def test_a_stop_raised_inside_the_order_phase_is_never_treated_as_clean(
    tmp_path: Path,
) -> None:
    """Fail closed: it propagates, so the relaunch runs startup reconciliation."""
    script = _load_module()
    engines = {symbol: _Engine(symbol) for symbol in _SYMBOLS}
    engines["BTC"] = _StopCheckInsideExecution("BTC")
    runner = _runner(
        tmp_path,
        script,
        symbols=_SYMBOLS,
        engines=engines,
        poller=_Poller((_intent("BTC", "long"),)),
        telemetry=_Telemetry(),
        clock=_Clock(),
        latch=ProcessSignalStop(),
    )

    with pytest.raises(ProcessStopRequested):
        runner.run(max_polls=5)

    assert not any(_stopped_by_operator(engine.snapshot) for engine in engines.values())


def test_live_candle_retry_wait_ends_within_a_second_of_a_stop(
    tmp_path: Path,
) -> None:
    """A 15 s Retry-After wait in the live wiring ends at the next slice."""
    script = _load_module()
    latch = ProcessSignalStop()
    throttled = Mock(status_code=429, headers={"Retry-After": "15"})
    session = Mock(spec=requests.Session)
    session.post.return_value = throttled
    fetch = script._live_candle_fetcher(
        session, partial(script._backend_stop_requested, tmp_path / "STOP", latch)
    )
    timer = threading.Timer(0.2, setattr, (latch, "requested", True))
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(ProcessStopRequested):
            fetch("BTC", "1m", 5 / 1440, end_ms=_END_MS)
    finally:
        timer.cancel()

    assert session.post.call_count == 1
    assert time.monotonic() - started < 0.2 + STOP_CHECK_SECONDS + 1.0


def test_a_nan_retry_after_in_the_live_wiring_retries_instead_of_failing(
    tmp_path: Path,
) -> None:
    """The live wait rejects NaN, so a NaN delay would have ended the backend."""
    script = _load_module()
    throttled = Mock(status_code=429, headers={"Retry-After": "nan"})
    session = Mock(spec=requests.Session)
    session.post.side_effect = [throttled, _healthy_candles()]
    fetch = script._live_candle_fetcher(
        session,
        partial(script._backend_stop_requested, tmp_path / "STOP", ProcessSignalStop()),
    )
    started = time.monotonic()

    frame = fetch("BTC", "1m", 5 / 1440, end_ms=_END_MS)

    assert frame.empty
    assert session.post.call_count == 2
    # The ladder's own first back-off, not the malformed header.
    assert 1.0 <= time.monotonic() - started < 2.0


def test_live_candle_read_is_not_started_once_the_stop_file_exists(
    tmp_path: Path,
) -> None:
    script = _load_module()
    session = Mock(spec=requests.Session)
    fetch = script._live_candle_fetcher(
        session,
        partial(script._backend_stop_requested, tmp_path / "STOP", ProcessSignalStop()),
    )
    (tmp_path / "STOP").write_text("stop\n", encoding="utf-8")

    with pytest.raises(ProcessStopRequested):
        fetch("BTC", "1m", 5 / 1440, end_ms=_END_MS)

    session.post.assert_not_called()


def test_the_runner_waits_on_the_latch_it_was_handed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The launcher installs the handed latch and makes the poll wait stop-aware."""
    script = _load_module()
    config = script.load_multi_asset_live_config(_PROFILE_A, mode="observe")
    installed: list[object] = []

    def install(stop: ProcessSignalStop | None = None) -> ProcessSignalStop:
        installed.append(stop)
        assert stop is not None
        return stop

    monkeypatch.setattr(script, "install_process_signal_stop", install)
    monkeypatch.setattr(script, "_create_operator_inbox", lambda *_args: None)
    latch = ProcessSignalStop()
    runner = script._create_runner(
        config,
        {symbol: Mock() for symbol in config.symbols},
        Mock(),
        Mock(),
        Mock(),
        "offline-stop-latency",
        signal_stop=latch,
    )
    assert installed == [latch]

    latch.requested = True
    started = time.monotonic()
    runner._sleep_fn(30.0)

    assert time.monotonic() - started < 1.0
    assert runner._signal_stop_requested() is True


def test_run_live_hands_one_latch_to_the_candle_reads_and_the_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The latch the runner installs is the one the public candle reads consult."""
    module, _session = _boundary(monkeypatch, tmp_path)
    seen: dict[str, object] = {}

    def run(
        _args: object,
        _config: object,
        _presence: object,
        fetch_bars: Callable[..., object],
        lock_path: Path | None = None,
        signal_stop: ProcessSignalStop | None = None,
    ) -> int:
        assert isinstance(signal_stop, ProcessSignalStop)
        assert signal_stop.requested is False
        signal_stop.requested = True
        with pytest.raises(ProcessStopRequested):
            fetch_bars("BTC", "1m", 5 / 1440, end_ms=_END_MS)
        seen["signal_stop"] = signal_stop
        return 0

    monkeypatch.setattr(
        module.ConfiguredMultiAssetIntentPoller,
        "with_registered_collectors",
        _retain_fetcher,
    )
    monkeypatch.setattr(module, "_run_locked", run)

    assert (
        module.run_live(_args(config=PROFILE, enabled=True, i_accept_live_risk=True))
        == 0
    )
    assert "signal_stop" in seen
