"""Regression tests for the generic single-export ``live run`` daemon.

Every venue interaction uses an in-process fake (a simulated venue transport or
fake official-SDK ``Info``/``Exchange`` objects). Nothing here opens a socket,
loads a real key or constructs an authenticated exchange client.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.live.policy import LivePolicy, LivePolicyError
from hypervector.nautilus.signals import SignalIntent


@pytest.fixture(autouse=True)
def _isolated_account_lock_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the daemon's shared-account lock out of the checkout's data/live."""
    root = tmp_path / "account-live"
    monkeypatch.setattr("hypervector.live.runner.canonical_live_root", lambda: root)

WALLET = "0x" + "1" * 40
OTHER_WALLET = "0x" + "2" * 40
KEY = "test-signing-key"

HOLD = SignalIntent(direction="flat", enter=False, exit=False, bar_index=0)
ENTER_SHORT = SignalIntent(direction="short", enter=True, exit=False, bar_index=0)
ENTER_LONG = SignalIntent(direction="long", enter=True, exit=False, bar_index=0)
EXIT = SignalIntent(direction="short", enter=False, exit=True, bar_index=0)
# Enter when flat, close when in a position: fires on every bar.
TOGGLE = SignalIntent(direction="short", enter=True, exit=True, bar_index=0)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class SimVenueTransport:
    """In-memory venue: fills every accepted order, tracks the net position."""

    def __init__(
        self,
        *,
        initial: dict[str, float] | None = None,
        place_error: Exception | None = None,
        fill_before_error: bool = False,
        position_offset: float = 0.0,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self.position_reads = 0
        self.net: dict[str, float] = dict(initial or {})
        self._place_error = place_error
        self._fill_before_error = fill_before_error
        self._position_offset = position_offset

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {"coin": coin, "is_buy": is_buy, "sz": sz, "reduce_only": reduce_only}
        )
        signed = sz if is_buy else -sz
        current = self.net.get(coin, 0.0)
        if reduce_only and (
            current == 0.0
            or (current > 0) == (signed > 0)
            or abs(signed) > abs(current) + 1e-12
        ):
            return _statuses({"error": "Reduce only order would increase position."})
        if self._place_error is not None:
            if self._fill_before_error:
                self.net[coin] = current + signed
            raise self._place_error
        self.net[coin] = current + signed
        return _statuses(
            {"filled": {"totalSz": repr(sz), "avgPx": "40000.0", "oid": len(self.calls)}}
        )

    def position(self, *, wallet_address: str, private_key: str, coin: str) -> float:
        self.position_reads += 1
        return self.net.get(coin, 0.0) + self._position_offset

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
        oids: list[int] | None = None,
    ) -> dict[str, Any]:
        self.cancel_calls.append({"coin": coin, "oids": oids})
        count = len(oids or [])
        return {
            "status": "ok",
            "response": {"type": "cancel", "data": {"statuses": ["success"] * count}},
        }


def _statuses(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "response": {"type": "order", "data": {"statuses": [status]}},
    }


class LegacyTransport:
    """Transport with the pre-fix signature (no reduce_only, no oids, no position)."""

    def __init__(self, response: Any = None, cancel_response: Any = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self._response = (
            response if response is not None else {"status": "ok", "oid": "x-1"}
        )
        self._cancel_response = cancel_response

    def place_market(
        self,
        *,
        coin: str,
        is_buy: bool,
        sz: float,
        wallet_address: str,
        private_key: str,
    ) -> Any:
        self.calls.append({"coin": coin, "is_buy": is_buy, "sz": sz})
        return self._response

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
    ) -> Any:
        self.cancel_calls.append({"coin": coin})
        return self._cancel_response


class ScriptedIntents:
    """Signal-agnostic ``last_bar_intent`` replacement keyed by the last bar."""

    def __init__(
        self,
        *,
        default: SignalIntent = HOLD,
        by_ts: dict[pd.Timestamp, SignalIntent] | None = None,
    ) -> None:
        self.default = default
        self.by_ts = {pd.Timestamp(k): v for k, v in (by_ts or {}).items()}
        self.calls = 0
        self.seen: list[tuple[pd.Timestamp, float]] = []

    def __call__(
        self, df: pd.DataFrame, strategy_name: str, params: dict[str, Any]
    ) -> SignalIntent:
        self.calls += 1
        ts = pd.Timestamp(df.index[-1])
        self.seen.append((ts, float(df["close"].iloc[-1])))
        return self.by_ts.get(ts, self.default)


class SequenceClock:
    def __init__(self, *values: str) -> None:
        self._values = [pd.Timestamp(v, tz="UTC") for v in values]
        self.calls = 0

    def __call__(self) -> pd.Timestamp:
        index = min(self.calls, len(self._values) - 1)
        self.calls += 1
        return self._values[index]


class ScriptedFeed:
    def __init__(self, *frames: pd.DataFrame | None) -> None:
        self._frames = list(frames)
        self.after: list[pd.Timestamp | None] = []

    def __call__(self, *, after_ts: pd.Timestamp | None = None, **_: Any) -> Any:
        self.after.append(after_ts)
        if not self._frames:
            return pd.DataFrame()
        frame = self._frames.pop(0)
        return pd.DataFrame() if frame is None else frame


class FakeInfo:
    def __init__(
        self,
        *,
        metas: dict[str, dict[str, Any]],
        mids: dict[str, dict[str, str]],
        positions: dict[str, list[dict[str, Any]]] | None = None,
        open_orders: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._metas = metas
        self._mids = mids
        self._positions = positions or {}
        self._open = open_orders or {}
        self.calls: list[tuple[str, str]] = []

    def meta(self, dex: str = "") -> dict[str, Any]:
        self.calls.append(("meta", dex))
        return self._metas[dex]

    def all_mids(self, dex: str = "") -> dict[str, str]:
        self.calls.append(("all_mids", dex))
        return self._mids[dex]

    def user_state(self, address: str, dex: str = "") -> dict[str, Any]:
        self.calls.append(("user_state", dex))
        return {
            "assetPositions": [
                {"position": p, "type": "oneWay"} for p in self._positions.get(dex, [])
            ]
        }

    def open_orders(self, address: str, dex: str = "") -> list[dict[str, Any]]:
        self.calls.append(("open_orders", dex))
        return list(self._open.get(dex, []))


class FakeExchange:
    def __init__(self, *, order_response: Any = None, cancel_response: Any = None):
        self.orders: list[dict[str, Any]] = []
        self.cancels: list[list[dict[str, Any]]] = []
        self._order_response = order_response
        self._cancel_response = cancel_response

    def order(
        self,
        name: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Any,
        reduce_only: bool = False,
        cloid: Any = None,
        builder: Any = None,
    ) -> Any:
        self.orders.append(
            {
                "coin": name,
                "is_buy": is_buy,
                "sz": sz,
                "limit_px": limit_px,
                "order_type": order_type,
                "reduce_only": reduce_only,
            }
        )
        if self._order_response is not None:
            return self._order_response
        return _statuses({"filled": {"totalSz": repr(sz), "avgPx": "64000.0", "oid": 7}})

    def bulk_cancel(self, cancel_requests: list[dict[str, Any]]) -> Any:
        self.cancels.append(list(cancel_requests))
        if self._cancel_response is not None:
            return self._cancel_response
        return {
            "status": "ok",
            "response": {
                "type": "cancel",
                "data": {"statuses": ["success"] * len(cancel_requests)},
            },
        }

    def market_open(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("generic transport must not use market_open")


class FakeBuilder:
    def __init__(self, info: FakeInfo, exchange: FakeExchange) -> None:
        self.info = info
        self.exchange = exchange
        self.builds: list[dict[str, Any]] = []

    def build(
        self,
        *,
        account_address: str,
        private_key: str,
        perp_dexes: tuple[str, ...] = (),
    ) -> tuple[FakeInfo, FakeExchange]:
        self.builds.append(
            {"account_address": account_address, "perp_dexes": tuple(perp_dexes)}
        )
        return self.info, self.exchange


def _core_info(**kwargs: Any) -> FakeInfo:
    return FakeInfo(
        metas={
            "": {
                "universe": [
                    {"name": "BTC", "szDecimals": 5, "maxLeverage": 40},
                    {"name": "ETH", "szDecimals": 4, "maxLeverage": 25},
                ]
            }
        },
        mids={"": {"BTC": "64123.456", "ETH": "3000.5"}},
        **kwargs,
    )


def _hip3_info(**kwargs: Any) -> FakeInfo:
    return FakeInfo(
        metas={
            "xyz": {
                "universe": [{"name": "xyz:TSLA", "szDecimals": 3, "maxLeverage": 10}]
            }
        },
        mids={"xyz": {"xyz:TSLA": "251.37"}},
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write_export(
    root: Path, *, timeframe: str = "1m", strategy: str = "test_sma_cross_short"
) -> Path:
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id=f"livefix{timeframe}",
        meta={
            "symbol": "BTC",
            "timeframe": timeframe,
            "track": track,
            "lookback_days": 30,
            "init_cash": 10_000.0,
            "tp_sl_mode": "fixed_rr",
            "exits": {
                "mode": "fixed_rr",
                "sl_pct": 0.01,
                "rr": 2.0,
                "atr_length": 14,
                "sl_atr_mult": 1.5,
                "trail_atr_mult": 2.0,
            },
            "costs": {
                "taker_fee": 0.00035,
                "slippage_bps": 2.0,
                "funding_rate_8h": 0.0001,
                "minutes_per_funding": 480,
            },
            "risk": {
                "risk_pct_min": 0.01,
                "risk_pct_max": 0.05,
                "default_conviction": 0.5,
                "max_size_frac": 1.0,
            },
            "data_provenance": {"sources": {"fixture": 300}},
        },
        params={
            "strategy": strategy,
            "bbwp_lookback": 100,
            "bbwp_threshold": 20.0,
            "exit_mode": "fixed_rr",
            "role": track,
        },
        metrics={
            "net_pnl": 50.0,
            "total_return_pct": 0.5,
            "sharpe": 0.4,
            "trade_count": 3,
        },
        candidate_id=f"live_fix_{timeframe}",
        strict=True,
    )


def _policy(**kwargs: Any) -> LivePolicy:
    base: dict[str, Any] = dict(
        enabled=True, armed=True, secrets_present=True, max_notional_usd=50.0
    )
    base.update(kwargs)
    return LivePolicy(**base)


def _bars(start: str, n: int, *, freq: str = "1min", base: float = 40_000.0):
    return fixture_ohlcv(n_bars=n, start=start, freq=freq, base_price=base, drift=-1.0)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _daemon(
    tmp_path: Path,
    *,
    transport: Any,
    warm: pd.DataFrame | None,
    poll_fn: Callable[..., Any],
    max_live_bars: int | None,
    **extra: Any,
):
    from hypervector.live.runner import start_live_daemon

    return start_live_daemon(
        export_dir=extra.pop("export", None) or _write_export(tmp_path),
        data_root=tmp_path / "data",
        policy=extra.pop("policy", None) or _policy(),
        wallet_address=WALLET,
        private_key=KEY,
        transport=transport,
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        max_live_bars=max_live_bars,
        install_signal_handlers=False,
        sleep_fn=lambda _s: None,
        **extra,
    )


def _patch_intents(monkeypatch: pytest.MonkeyPatch, intents: ScriptedIntents) -> None:
    monkeypatch.setattr("hypervector.live.session.last_bar_intent", intents)


# --------------------------------------------------------------------------- #
# Finding 1: stale catch-up bars and the still-forming candle
# --------------------------------------------------------------------------- #


def test_one_poll_full_of_catchup_bars_places_at_most_one_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-fix: 1440 catch-up bars in one poll replayed as rapid-fire orders."""
    intents = ScriptedIntents(default=TOGGLE)
    _patch_intents(monkeypatch, intents)
    warm = _bars("2026-10-16 00:00", 60)
    catchup = _bars("2026-10-16 01:00", 1440)
    transport = SimVenueTransport()

    result = _daemon(
        tmp_path,
        transport=transport,
        warm=warm,
        poll_fn=ScriptedFeed(catchup),
        max_live_bars=2000,
    )

    assert len(transport.calls) <= 1
    assert result.live_bars == 1
    assert result.catchup_bars == 1439
    newest = pd.Timestamp(catchup["timestamp"].iloc[-1])
    assert intents.seen == [(newest, float(catchup["close"].iloc[-1]))]


def test_clocked_boundary_only_latest_closed_bar_after_activation_trades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intents = ScriptedIntents(default=ENTER_SHORT)
    _patch_intents(monkeypatch, intents)
    warm = _bars("2026-10-17 00:00", 200)  # last close 03:20
    gap = _bars("2026-10-17 03:20", 41)  # 03:20..04:00; 04:00 forming at 04:00:05
    nxt = _bars("2026-10-17 04:00", 2)  # 04:00 closed, 04:01 forming at 04:01:03
    transport = SimVenueTransport()

    result = _daemon(
        tmp_path,
        transport=transport,
        warm=warm,
        poll_fn=ScriptedFeed(gap, nxt),
        max_live_bars=1,
        now_fn=SequenceClock(
            "2026-10-17 04:00:05", "2026-10-17 04:00:06", "2026-10-17 04:01:03"
        ),
        enforce_live_boundary=True,
    )

    assert result.catchup_bars == 40
    assert result.live_bars == 1
    assert [ts for ts, _ in intents.seen] == [pd.Timestamp("2026-10-17 04:00", tz="UTC")]
    assert len(transport.calls) == 1
    assert transport.calls[0]["is_buy"] is False


def test_forming_candle_is_not_processed_and_its_final_close_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intents = ScriptedIntents(default=HOLD)
    _patch_intents(monkeypatch, intents)
    warm = _bars("2026-10-17 12:00", 55)  # last close 12:55
    forming = _bars("2026-10-17 12:55", 1)
    forming["close"] = 40_100.6
    final = _bars("2026-10-17 12:55", 2)
    final.loc[0, "close"] = 40_102.9
    feed = ScriptedFeed(forming, final)

    result = _daemon(
        tmp_path,
        transport=SimVenueTransport(),
        warm=warm,
        poll_fn=feed,
        max_live_bars=1,
        now_fn=SequenceClock(
            "2026-10-17 12:55:30", "2026-10-17 12:55:40", "2026-10-17 12:56:02"
        ),
        enforce_live_boundary=True,
    )

    assert result.live_bars == 1
    assert intents.seen == [(pd.Timestamp("2026-10-17 12:55", tz="UTC"), 40_102.9)]
    last_warm = pd.Timestamp("2026-10-17 12:54", tz="UTC")
    assert feed.after[:2] == [last_warm, last_warm]


def test_lagging_feed_bar_older_than_latest_close_has_no_order_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intents = ScriptedIntents(default=ENTER_SHORT)
    _patch_intents(monkeypatch, intents)
    warm = _bars("2026-10-17 12:00", 55)
    lagging = _bars("2026-10-17 12:55", 2)  # closes 12:56 and 12:57
    transport = SimVenueTransport()

    result = _daemon(
        tmp_path,
        transport=transport,
        warm=warm,
        poll_fn=ScriptedFeed(lagging),
        max_live_bars=1,
        now_fn=SequenceClock("2026-10-17 12:55:30", "2026-10-17 12:58:10"),
        enforce_live_boundary=True,
    )

    assert transport.calls == []
    assert intents.calls == 0
    assert result.live_bars == 0
    assert result.catchup_bars == 2


def test_warmup_drops_forming_candle_at_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents())
    warm = _bars("2026-10-17 12:00", 56)  # 12:55 still forming at 12:55:30

    result = _daemon(
        tmp_path,
        transport=SimVenueTransport(),
        warm=warm,
        poll_fn=ScriptedFeed(),
        max_live_bars=0,
        now_fn=SequenceClock("2026-10-17 12:55:30"),
        enforce_live_boundary=True,
    )

    assert result.warm_bars == 55


def test_warmup_gap_wider_than_poll_window_refuses_before_any_venue_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents())
    warm = _bars("2026-10-14 00:00", 60)
    transport = SimVenueTransport()

    with pytest.raises(RuntimeError, match="poll window"):
        _daemon(
            tmp_path,
            transport=transport,
            warm=warm,
            poll_fn=ScriptedFeed(),
            max_live_bars=0,
            now_fn=SequenceClock("2026-10-17 12:00:00"),
            enforce_live_boundary=True,
        )
    assert transport.calls == []
    assert transport.position_reads == 0


def test_loaded_warmup_history_is_force_refreshed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents())
    captured: dict[str, Any] = {}

    def fake_load(root: Any, **kwargs: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
        captured.update(kwargs)
        return _bars("2026-10-17 00:00", 60), {"sources": {"fixture": 60}}

    monkeypatch.setattr("hypervector.live.runner.load_research_history", fake_load)
    _daemon(
        tmp_path,
        transport=SimVenueTransport(),
        warm=None,
        poll_fn=ScriptedFeed(),
        max_live_bars=0,
    )
    assert captured["force_refresh"] is True


class MutableClock:
    """Wall clock a fake feed or loader can advance while a request is in flight."""

    def __init__(self, value: str) -> None:
        self.now = pd.Timestamp(value, tz="UTC")

    def set(self, value: str) -> None:
        self.now = pd.Timestamp(value, tz="UTC")

    def __call__(self) -> pd.Timestamp:
        return self.now


def test_poll_in_flight_across_a_candle_close_does_not_act_on_the_partial_candle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The snapshot is taken mid-request; a candle that closed after the request
    left is still partial in it and must wait for the next poll's final value."""
    intents = ScriptedIntents(default=HOLD)
    _patch_intents(monkeypatch, intents)
    clock = MutableClock("2026-10-17 12:55:30")  # activation
    warm = _bars("2026-10-17 12:00", 55)  # last close 12:55
    partial = _bars("2026-10-17 12:55", 1)
    partial["close"] = 40_100.6
    final = _bars("2026-10-17 12:55", 2)
    final.loc[0, "close"] = 40_102.9
    polls: list[pd.Timestamp | None] = []

    def feed(*, after_ts: pd.Timestamp | None = None, **_: Any) -> pd.DataFrame:
        polls.append(after_ts)
        if len(polls) == 1:
            clock.set("2026-10-17 12:55:59.8")  # request leaves; 12:55 still forming
            snapshot = partial.copy()
            clock.set("2026-10-17 12:56:00.3")  # response lands after the close
            return snapshot
        clock.set("2026-10-17 12:56:05")
        return final

    result = _daemon(
        tmp_path,
        transport=SimVenueTransport(),
        warm=warm,
        poll_fn=feed,
        max_live_bars=1,
        now_fn=clock,
        enforce_live_boundary=True,
    )

    assert result.live_bars == 1
    assert intents.seen == [(pd.Timestamp("2026-10-17 12:55", tz="UTC"), 40_102.9)]
    last_warm = pd.Timestamp("2026-10-17 12:54", tz="UTC")
    assert polls[:2] == [last_warm, last_warm]


def test_warmup_candle_closing_while_history_loads_is_not_seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Activation is stamped before the warm-up fetch, so a candle that was
    forming in the history snapshot is left for the live feed's final value."""
    _patch_intents(monkeypatch, ScriptedIntents())
    clock = MutableClock("2026-10-17 12:54:50")

    def fake_load(root: Any, **kwargs: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
        bars = _bars("2026-10-17 12:00", 55)  # 12:54 forming (partial) in snapshot
        clock.set("2026-10-17 12:55:10")  # multi-venue load finishes after its close
        return bars, {"sources": {"fixture": len(bars)}}

    monkeypatch.setattr("hypervector.live.runner.load_research_history", fake_load)
    stop = tmp_path / "STOP"
    after: list[pd.Timestamp | None] = []

    def stop_after_first_poll(
        *, after_ts: pd.Timestamp | None = None, **_: Any
    ) -> pd.DataFrame:
        after.append(after_ts)
        stop.write_text("stop", encoding="utf-8")
        return pd.DataFrame()

    result = _daemon(
        tmp_path,
        transport=SimVenueTransport(),
        warm=None,
        poll_fn=stop_after_first_poll,
        max_live_bars=None,
        stop_file=stop,
        now_fn=clock,
        enforce_live_boundary=True,
    )

    assert result.warm_bars == 54
    assert after == [pd.Timestamp("2026-10-17 12:53", tz="UTC")]


# --------------------------------------------------------------------------- #
# Finding 2: synthetic warm-up position must not reach the armed phase
# --------------------------------------------------------------------------- #


def _live_session(tmp_path: Path, transport: Any, **kwargs: Any):
    from hypervector.live.exec_client import HyperliquidLiveExecClient
    from hypervector.live.session import LiveSession

    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=transport,
        max_notional_usd=50.0,
    )
    return LiveSession(
        export_dir=kwargs.pop("export", None) or _write_export(tmp_path),
        data_root=tmp_path / "data",
        client=client,
        max_notional_usd=50.0,
        **kwargs,
    )


def test_enable_live_place_discards_synthetic_warmup_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warm = _bars("2026-10-17 00:00", 60)
    last_warm = pd.Timestamp(warm["timestamp"].iloc[-1])
    live_bar = _bars("2026-10-17 01:00", 1)
    intents = ScriptedIntents(
        by_ts={last_warm: ENTER_SHORT, pd.Timestamp(live_bar["timestamp"].iloc[0]): EXIT}
    )
    _patch_intents(monkeypatch, intents)
    transport = SimVenueTransport()
    session = _live_session(tmp_path, transport)

    session.process_frame(warm)
    assert session.engine.position.qty < 0  # synthetic short at warm-up end

    session.enable_live_place()
    assert session.engine.position.qty == 0.0
    session.on_bar(live_bar.iloc[0])

    assert transport.calls == []  # no phantom close opening a real long
    rows = _rows(session.decisions_path)
    discarded = [r for r in rows if r.get("action") == "warmup_position_discarded"]
    assert len(discarded) == 1
    assert discarded[0]["place_attempted"] is False
    assert discarded[0]["live_phase"] is False
    assert discarded[0]["discarded_qty"] < 0


def test_daemon_warmup_ending_in_synthetic_short_sends_no_live_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warm = _bars("2026-10-17 00:00", 151)
    last_warm = pd.Timestamp(warm["timestamp"].iloc[-1])
    live_bar = _bars("2026-10-17 02:31", 1)
    intents = ScriptedIntents(
        by_ts={last_warm: ENTER_SHORT, pd.Timestamp(live_bar["timestamp"].iloc[0]): EXIT}
    )
    _patch_intents(monkeypatch, intents)
    transport = SimVenueTransport()

    _daemon(
        tmp_path,
        transport=transport,
        warm=warm,
        poll_fn=ScriptedFeed(live_bar),
        max_live_bars=1,
    )
    assert transport.calls == []
    assert transport.net.get("BTC", 0.0) == 0.0


def test_daemon_refuses_to_arm_when_venue_already_holds_the_coin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    transport = SimVenueTransport(initial={"BTC": 0.25})

    with pytest.raises(RuntimeError, match="venue already holds"):
        _daemon(
            tmp_path,
            transport=transport,
            warm=_bars("2026-10-17 00:00", 60),
            poll_fn=ScriptedFeed(_bars("2026-10-17 01:00", 1)),
            max_live_bars=1,
        )
    assert transport.calls == []


def test_daemon_refuses_to_arm_when_venue_position_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    transport = LegacyTransport()

    with pytest.raises(RuntimeError, match="venue position"):
        _daemon(
            tmp_path,
            transport=transport,
            warm=_bars("2026-10-17 00:00", 60),
            poll_fn=ScriptedFeed(_bars("2026-10-17 01:00", 1)),
            max_live_bars=1,
        )
    assert transport.calls == []


def test_live_close_is_reduce_only_full_size_and_not_notional_capped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warm = _bars("2026-10-17 00:00", 60)
    first = _bars("2026-10-17 01:00", 1)
    second = _bars("2026-10-17 01:01", 1)
    second["close"] = 44_000.0  # +10%: close notional now exceeds the $50 cap
    intents = ScriptedIntents(
        by_ts={
            pd.Timestamp(first["timestamp"].iloc[0]): ENTER_LONG,
            pd.Timestamp(second["timestamp"].iloc[0]): EXIT,
        }
    )
    _patch_intents(monkeypatch, intents)
    transport = SimVenueTransport()

    result = _daemon(
        tmp_path,
        transport=transport,
        warm=warm,
        poll_fn=ScriptedFeed(first, second),
        max_live_bars=2,
    )

    assert [c["is_buy"] for c in transport.calls] == [True, False]
    entry, close = transport.calls
    assert entry["reduce_only"] is False
    assert close["reduce_only"] is True
    assert close["sz"] == pytest.approx(entry["sz"], rel=0, abs=0)
    assert transport.net["BTC"] == 0.0
    rows = _rows(result.decisions_path)
    close_rows = [r for r in rows if r.get("action") == "close"]
    assert close_rows and close_rows[-1]["order_intent"]["reduce_only"] is True


def test_venue_position_drift_after_an_order_stops_the_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambiguous transport failure that still filled must not go unnoticed."""
    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    transport = SimVenueTransport(
        place_error=TimeoutError("read timed out"), fill_before_error=True
    )

    with pytest.raises(RuntimeError, match="venue position"):
        _daemon(
            tmp_path,
            transport=transport,
            warm=_bars("2026-10-17 00:00", 60),
            poll_fn=ScriptedFeed(_bars("2026-10-17 01:00", 1), _bars("2026-10-17 01:01", 1)),
            max_live_bars=5,
        )
    assert len(transport.calls) == 1
    rows = _rows(tmp_path / "data" / "live" / "decisions" / "decisions.jsonl")
    failures = [r for r in rows if r.get("action") == "venue_reconciliation_failed"]
    assert len(failures) == 1
    assert failures[0]["venue_position_qty"] == pytest.approx(transport.net["BTC"])
    assert failures[0]["position_qty"] == 0.0


# --------------------------------------------------------------------------- #
# Finding 3: SDK transport builds valid orders, addresses HIP-3, cancels honestly
# --------------------------------------------------------------------------- #


def test_unrounded_size_is_rejected_by_sdk_wire_encoding() -> None:
    """Documents why the pre-fix transport failed every order client-side."""
    from hyperliquid.utils.signing import float_to_wire

    with pytest.raises(ValueError, match="rounding"):
        float_to_wire(0.000744896712621828)


def test_sdk_transport_rounds_size_down_and_price_to_wire_valid_ioc(tmp_path: Path):
    from hyperliquid.utils.signing import order_request_to_order_wire

    from hypervector.live.exec_client import _SdkPlaceTransport

    info, exchange = _core_info(), FakeExchange()
    builder = FakeBuilder(info, exchange)
    transport = _SdkPlaceTransport(sdk_builder=builder)

    raw = transport.place_market(
        coin="BTC",
        is_buy=True,
        sz=0.000744896712621828,
        wallet_address=WALLET,
        private_key=KEY,
    )

    assert raw["status"] == "ok"
    order = exchange.orders[0]
    assert order["coin"] == "BTC"
    assert order["sz"] == 0.00074
    assert order["reduce_only"] is False
    assert order["order_type"] == {"limit": {"tif": "Ioc"}}
    # Buy limit is 5% through the live mid, 5 significant figures.
    assert order["limit_px"] == 67330.0
    wire = order_request_to_order_wire(
        {
            "coin": order["coin"],
            "is_buy": order["is_buy"],
            "sz": order["sz"],
            "limit_px": order["limit_px"],
            "order_type": order["order_type"],
            "reduce_only": order["reduce_only"],
        },
        0,
    )
    assert wire["s"] == "0.00074"
    assert wire["t"] == {"limit": {"tif": "Ioc"}}


def test_sdk_transport_reuses_one_session_and_metadata_per_process() -> None:
    from hypervector.live.exec_client import _SdkPlaceTransport

    info, exchange = _core_info(), FakeExchange()
    builder = FakeBuilder(info, exchange)
    transport = _SdkPlaceTransport(sdk_builder=builder)
    for _ in range(3):
        transport.place_market(
            coin="BTC", is_buy=False, sz=0.001, wallet_address=WALLET, private_key=KEY
        )

    assert len(builder.builds) == 1
    assert builder.builds[0] == {"account_address": WALLET, "perp_dexes": ()}
    assert [c for c in info.calls if c[0] == "meta"] == [("meta", "")]
    sell = exchange.orders[0]
    assert sell["limit_px"] == pytest.approx(60917.0)
    assert sell["is_buy"] is False


def test_sdk_transport_addresses_hip3_namespaced_coin() -> None:
    from hypervector.live.exec_client import _SdkPlaceTransport

    info = _hip3_info(
        positions={"xyz": [{"coin": "xyz:TSLA", "szi": "-1.5"}]},
    )
    exchange = FakeExchange()
    builder = FakeBuilder(info, exchange)
    transport = _SdkPlaceTransport(sdk_builder=builder)

    transport.place_market(
        coin="xyz:TSLA",
        is_buy=True,
        sz=0.123456,
        wallet_address=WALLET,
        private_key=KEY,
        reduce_only=True,
    )
    position = transport.position(wallet_address=WALLET, private_key=KEY, coin="xyz:TSLA")

    assert builder.builds == [{"account_address": WALLET, "perp_dexes": ("xyz",)}]
    assert ("meta", "xyz") in info.calls
    assert ("all_mids", "xyz") in info.calls
    assert ("user_state", "xyz") in info.calls
    order = exchange.orders[0]
    assert order["coin"] == "xyz:TSLA"
    assert order["sz"] == 0.123
    assert order["reduce_only"] is True
    assert position == -1.5


def test_sdk_transport_refuses_size_that_rounds_to_zero_via_client() -> None:
    from hypervector.live.exec_client import (
        HyperliquidLiveExecClient,
        _SdkPlaceTransport,
    )

    info, exchange = _core_info(), FakeExchange()
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=_SdkPlaceTransport(sdk_builder=FakeBuilder(info, exchange)),
        max_notional_usd=50.0,
    )
    result = client.place_market("BTC", "buy", 0.000001, mark_px=64_000.0)

    assert result.submitted is False
    assert "rounds to zero" in (result.error or "")
    assert exchange.orders == []


def test_client_reports_venue_filled_size_and_average_price() -> None:
    from hypervector.live.exec_client import (
        HyperliquidLiveExecClient,
        _SdkPlaceTransport,
    )

    info = _core_info()
    exchange = FakeExchange(
        order_response=_statuses(
            {"filled": {"totalSz": "0.0005", "avgPx": "64010.5", "oid": 91}}
        )
    )
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=_SdkPlaceTransport(sdk_builder=FakeBuilder(info, exchange)),
        max_notional_usd=50.0,
    )
    result = client.place_market("BTC", "sell", 0.00078, mark_px=64_000.0)

    assert result.submitted is True
    assert result.venue_order_id == "91"
    assert result.filled_qty == pytest.approx(0.0005)
    assert result.avg_px == pytest.approx(64010.5)


def test_sdk_transport_ioc_no_match_is_not_submitted() -> None:
    from hypervector.live.exec_client import (
        HyperliquidLiveExecClient,
        _SdkPlaceTransport,
    )

    exchange = FakeExchange(
        order_response=_statuses(
            {"error": "Order could not immediately match against any resting orders."}
        )
    )
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=_SdkPlaceTransport(sdk_builder=FakeBuilder(_core_info(), exchange)),
        max_notional_usd=50.0,
    )
    result = client.place_market("BTC", "buy", 0.0007, mark_px=64_000.0)
    assert result.submitted is False
    assert "could not immediately match" in (result.error or "")


def test_sdk_transport_cancels_only_owned_open_orders() -> None:
    from hypervector.live.exec_client import _SdkPlaceTransport

    info = _core_info(
        open_orders={
            "": [
                {"coin": "BTC", "oid": 11, "sz": "0.001", "side": "B"},
                {"coin": "BTC", "oid": 99, "sz": "0.5", "side": "A"},  # not ours
                {"coin": "ETH", "oid": 12, "sz": "0.1", "side": "B"},
            ]
        }
    )
    exchange = FakeExchange()
    transport = _SdkPlaceTransport(sdk_builder=FakeBuilder(info, exchange))

    raw = transport.cancel_all(
        wallet_address=WALLET, private_key=KEY, coin="BTC", oids=[11, 12]
    )

    assert exchange.cancels == [[{"coin": "BTC", "oid": 11}]]
    assert raw["status"] == "ok"


def test_sdk_transport_never_cancels_unowned_orders_without_ids() -> None:
    from hypervector.live.exec_client import LiveVenueError, _SdkPlaceTransport

    exchange = FakeExchange()
    transport = _SdkPlaceTransport(sdk_builder=FakeBuilder(_core_info(), exchange))
    with pytest.raises(LiveVenueError, match="owned"):
        transport.cancel_all(wallet_address=WALLET, private_key=KEY, coin="BTC")
    assert exchange.cancels == []


def test_client_cancel_all_without_owned_orders_touches_nothing() -> None:
    from hypervector.live.exec_client import HyperliquidLiveExecClient

    transport = SimVenueTransport()
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET, private_key=KEY, transport=transport, max_notional_usd=50.0
    )
    client.place_market("BTC", "buy", 0.001, mark_px=40_000.0)  # IOC: filled
    result = client.cancel_all(symbol="BTC")

    assert result.submitted is True
    assert result.error is None
    assert "no owned resting orders" in (result.detail or "")
    assert transport.cancel_calls == []


def test_client_cancels_owned_resting_order_and_reports_venue_errors() -> None:
    from hypervector.live.exec_client import (
        HyperliquidLiveExecClient,
        _SdkPlaceTransport,
    )

    info = _core_info(
        open_orders={"": [{"coin": "BTC", "oid": 7, "sz": "0.0007", "side": "B"}]}
    )
    exchange = FakeExchange(
        order_response=_statuses({"resting": {"oid": 7}}),
        cancel_response={
            "status": "ok",
            "response": {"type": "cancel", "data": {"statuses": [{"error": "gone"}]}},
        },
    )
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=_SdkPlaceTransport(sdk_builder=FakeBuilder(info, exchange)),
        max_notional_usd=50.0,
    )
    placed = client.place_market("BTC", "buy", 0.0007, mark_px=64_000.0)
    assert placed.submitted is True
    assert placed.filled_qty == 0.0

    result = client.cancel_all(symbol="BTC")
    assert exchange.cancels == [[{"coin": "BTC", "oid": 7}]]
    assert result.submitted is False
    assert "gone" in (result.error or "")


def test_client_treats_noop_cancel_note_as_failure() -> None:
    from hypervector.live.exec_client import HyperliquidLiveExecClient

    class NoteTransport(SimVenueTransport):
        def place_market(self, **kwargs: Any) -> dict[str, Any]:
            super().place_market(**kwargs)
            return _statuses({"resting": {"oid": 5}})

        def cancel_all(self, **kwargs: Any) -> dict[str, Any]:
            self.cancel_calls.append(kwargs)
            return {"status": "ok", "note": "no cancel_all on SDK; open orders untouched"}

    transport = NoteTransport()
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET, private_key=KEY, transport=transport, max_notional_usd=50.0
    )
    client.place_market("BTC", "buy", 0.001, mark_px=40_000.0)
    result = client.cancel_all(symbol="BTC")

    assert len(transport.cancel_calls) == 1
    assert result.submitted is False
    assert "untouched" in (result.error or "")


def test_client_refuses_reduce_only_on_transport_without_support() -> None:
    from hypervector.live.exec_client import HyperliquidLiveExecClient

    transport = LegacyTransport()
    client = HyperliquidLiveExecClient(
        wallet_address=WALLET, private_key=KEY, transport=transport, max_notional_usd=50.0
    )
    result = client.place_market("BTC", "sell", 0.001, mark_px=40_000.0, reduce_only=True)
    assert result.submitted is False
    assert "reduce-only" in (result.error or "")
    assert transport.calls == []


def test_client_treats_non_dict_transport_response_as_not_submitted() -> None:
    from hypervector.live.exec_client import HyperliquidLiveExecClient

    client = HyperliquidLiveExecClient(
        wallet_address=WALLET,
        private_key=KEY,
        transport=LegacyTransport(response="ok"),
        max_notional_usd=50.0,
    )
    result = client.place_market("BTC", "buy", 0.001, mark_px=40_000.0)
    assert result.submitted is False
    assert result.error


def test_daemon_stop_reports_kill_honestly_without_cancelling_foreign_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents())
    transport = SimVenueTransport()
    result = _daemon(
        tmp_path,
        transport=transport,
        warm=_bars("2026-10-17 00:00", 40),
        poll_fn=ScriptedFeed(),
        max_live_bars=0,
    )
    assert result.cancel_attempted is True
    assert result.cancel_ok is True
    assert transport.cancel_calls == []


def test_default_sdk_transport_construction_is_inert() -> None:
    from hypervector.live.exec_client import _SdkPlaceTransport

    transport = _SdkPlaceTransport()
    assert transport.session_count == 0


# --------------------------------------------------------------------------- #
# Finding 4: non-finite / non-positive notional caps fail closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("cap", [math.nan, math.inf, -math.inf, -50.0, 0.0])
def test_policy_require_start_refuses_invalid_cap(cap: float) -> None:
    policy = _policy(max_notional_usd=cap)
    with pytest.raises(LivePolicyError, match="max_notional_usd"):
        policy.require_start()
    assert policy.readiness()["can_start"] is False


def test_policy_require_notional_refuses_nan_cap() -> None:
    with pytest.raises(LivePolicyError, match="max_notional_usd"):
        LivePolicy(max_notional_usd=math.nan).require_notional(
            qty=0.25, mark_px=40_000.0
        )


@pytest.mark.parametrize("cap", [math.nan, math.inf, -1.0])
def test_client_and_engine_refuse_invalid_cap(tmp_path: Path, cap: float) -> None:
    from hypervector.live.engine import LiveFillEngine
    from hypervector.live.exec_client import HyperliquidLiveExecClient
    from hypervector.paper.costs import CostProvider

    with pytest.raises(LivePolicyError, match="max_notional_usd"):
        HyperliquidLiveExecClient(
            wallet_address=WALLET,
            private_key=KEY,
            transport=SimVenueTransport(),
            max_notional_usd=cap,
        )
    with pytest.raises(ValueError, match="max_notional_usd"):
        LiveFillEngine(
            tmp_path / "data",
            cost_provider=CostProvider(
                fee_tier=0, slippage_bps=2.0, funding_rate_hourly=0.0
            ),
            run_id="r",
            export_id="e",
            strategy_name="test_sma_cross_short",
            symbol="BTC",
            timeframe="1m",
            conviction=0.5,
            max_notional_usd=cap,
        )


@pytest.mark.parametrize(("qty", "mark"), [(math.nan, 40_000.0), (0.25, math.nan)])
def test_engine_refuses_non_finite_qty_or_mark_before_placing(
    tmp_path: Path, qty: float, mark: float
) -> None:
    """A NaN mark would otherwise skip cap scaling exactly like a NaN cap."""
    from hypervector.live.engine import LiveFillEngine
    from hypervector.live.exec_client import HyperliquidLiveExecClient
    from hypervector.paper.costs import CostProvider

    transport = SimVenueTransport()
    engine = LiveFillEngine(
        tmp_path / "data",
        cost_provider=CostProvider(fee_tier=0, slippage_bps=2.0, funding_rate_hourly=0.0),
        run_id="r",
        export_id="e",
        strategy_name="test_sma_cross_short",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        client=HyperliquidLiveExecClient(
            wallet_address=WALLET, private_key=KEY, transport=transport, max_notional_usd=50.0
        ),
        place_enabled=True,
        max_notional_usd=50.0,
    )
    with pytest.raises(ValueError, match="must be positive"):
        engine.apply_market_fill(
            feed_ts="t", action="enter_long", side="buy", qty=qty, mark_px=mark
        )
    assert transport.calls == []


def test_daemon_with_nan_cap_never_constructs_client_or_places(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents(default=ENTER_SHORT))
    transport = SimVenueTransport()
    with pytest.raises(LivePolicyError, match="max_notional_usd"):
        _daemon(
            tmp_path,
            transport=transport,
            warm=_bars("2026-10-17 00:00", 60),
            poll_fn=ScriptedFeed(_bars("2026-10-17 01:00", 1)),
            max_live_bars=1,
            policy=_policy(max_notional_usd=math.nan),
        )
    assert transport.calls == []
    assert transport.position_reads == 0


def test_cli_live_run_refuses_nan_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.cli import main

    export = _write_export(tmp_path)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", WALLET)
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", KEY)
    # The CLI refuses a NaN cap at parse time (usage error, exit 2), before any
    # policy, credential or engine code runs.
    with pytest.raises(SystemExit) as refused:
        main(
            [
                "--data-root",
                str(tmp_path / "data"),
                "live",
                "run",
                "--export",
                str(export),
                "--enabled",
                "--i-accept-live-risk",
                "--max-notional-usd",
                "nan",
                "--max-live-bars",
                "0",
            ]
        )
    captured = capsys.readouterr()
    assert refused.value.code == 2
    assert "--max-notional-usd" in captured.err
    assert KEY not in captured.err + captured.out


# --------------------------------------------------------------------------- #
# Finding 5: warm-up seeding is linear and evaluates no synthetic intents
# --------------------------------------------------------------------------- #


def test_seed_history_matches_iterated_buffer_without_intents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intents = ScriptedIntents(default=HOLD)
    _patch_intents(monkeypatch, intents)
    # A small rolling window keeps the O(n * window) reference path fast.
    monkeypatch.setattr("hypervector.live.session.DEFAULT_MAX_LOOKBACK", 50)
    warm = _bars("2026-10-17 00:00", 120)
    export = _write_export(tmp_path)

    iterated = _live_session(tmp_path / "a", SimVenueTransport(), export=export)
    iterated.process_frame(warm)
    calls_iterated = intents.calls

    seeded = _live_session(tmp_path / "b", SimVenueTransport(), export=export)
    n = seeded.seed_history(warm)

    assert n == len(warm)
    assert intents.calls == calls_iterated  # seeding evaluated no intents
    assert seeded.buffer_rows == iterated.buffer_rows
    assert len(seeded.buffer_rows) == 50
    assert seeded.bars_processed == iterated.bars_processed
    assert seeded.last_timestamp == iterated.last_timestamp
    assert seeded.engine.position.qty == 0.0
    assert not seeded.decisions_path.exists()


def test_daemon_warmup_runs_no_per_bar_strategy_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    intents = ScriptedIntents(default=TOGGLE)
    _patch_intents(monkeypatch, intents)
    result = _daemon(
        tmp_path,
        transport=SimVenueTransport(),
        warm=_bars("2026-10-17 00:00", 200),
        poll_fn=ScriptedFeed(),
        max_live_bars=0,
    )
    assert result.warm_bars == 200
    assert result.bars_processed == 200
    assert intents.calls == 0
    rows = _rows(result.decisions_path)
    assert [r["action"] for r in rows] == ["session_start"]


# --------------------------------------------------------------------------- #
# Finding 6: funding accrues over the real bar interval
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("timeframe", "freq", "hours"),
    [("1m", "1min", 1 / 60), ("5m", "5min", 5 / 60), ("15m", "15min", 0.25), ("1h", "1h", 1.0)],
)
def test_funding_accrues_for_actual_bar_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timeframe: str,
    freq: str,
    hours: float,
) -> None:
    _patch_intents(monkeypatch, ScriptedIntents(default=HOLD))
    rate = 0.0001
    session = _live_session(
        tmp_path,
        SimVenueTransport(),
        export=_write_export(tmp_path, timeframe=timeframe),
        funding_rate_hourly=rate,
    )
    session.engine.apply_market_fill(
        feed_ts="seed", action="enter_short", side="sell", qty=0.001, mark_px=40_000.0
    )
    bar = _bars("2026-10-17 00:00", 1, freq=freq).iloc[0]
    session.on_bar(bar)

    funding = [r for r in _rows(session.decisions_path) if r["action"] == "funding"]
    assert len(funding) == 1
    expected = -0.001 * float(bar["close"]) * rate * hours
    assert funding[0]["funding_payment_usd"] == pytest.approx(expected, rel=1e-12)


def test_unsupported_timeframe_refuses_before_any_ledger_write(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported live timeframe"):
        _live_session(
            tmp_path, SimVenueTransport(), export=_write_export(tmp_path, timeframe="4h")
        )
    assert not (tmp_path / "data" / "live" / "decisions" / "decisions.jsonl").exists()
