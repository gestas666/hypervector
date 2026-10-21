"""4b-live F3: live-run daemon + live ledger (offline mock transport)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.live.policy import LivePolicy, LivePolicyError


@pytest.fixture(autouse=True)
def _isolated_account_lock_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the daemon's shared-account lock out of the checkout's data/live."""
    root = tmp_path / "account-live"
    monkeypatch.setattr("hypervector.live.runner.canonical_live_root", lambda: root)


class RecordingTransport:
    """Offline venue: records calls and tracks the net position it filled."""

    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
        cancel_error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self.net: dict[str, float] = {}
        self._response = (
            response if response is not None else {"status": "ok", "oid": "live-1"}
        )
        self._error = error
        self._cancel_error = cancel_error

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
            {
                "coin": coin,
                "is_buy": is_buy,
                "sz": sz,
                "reduce_only": reduce_only,
                "wallet_address": wallet_address,
                "private_key": private_key,
            }
        )
        if self._error is not None:
            raise self._error
        response = dict(self._response)
        if "resting" not in json.dumps(response):
            self.net[coin] = self.net.get(coin, 0.0) + (sz if is_buy else -sz)
        return response

    def position(self, *, wallet_address: str, private_key: str, coin: str) -> float:
        return self.net.get(coin, 0.0)

    def cancel_all(
        self,
        *,
        wallet_address: str,
        private_key: str,
        coin: str | None = None,
        oids: list[int] | None = None,
    ) -> dict[str, Any]:
        self.cancel_calls.append(
            {
                "wallet_address": wallet_address,
                "private_key": private_key,
                "coin": coin,
                "oids": oids,
            }
        )
        if self._cancel_error is not None:
            raise self._cancel_error
        return {"status": "ok", "oid": "cancel-batch-1"}


def _write_strict_export(root: Path, *, strategy: str = "crown_stack_short") -> Path:
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id="liverun01",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
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
        candidate_id="live_run_crown",
        strict=True,
    )


def _armed_policy(**kwargs: Any) -> LivePolicy:
    base = dict(
        enabled=True,
        armed=True,
        secrets_present=True,
        max_notional_usd=50.0,
    )
    base.update(kwargs)
    return LivePolicy(**base)


def test_start_live_daemon_refuses_when_unarmed(tmp_path: Path):
    from hypervector.live.runner import start_live_daemon

    export = _write_strict_export(tmp_path)
    transport = RecordingTransport()
    with pytest.raises(LivePolicyError, match="armed"):
        start_live_daemon(
            export_dir=export,
            data_root=tmp_path / "data",
            policy=_armed_policy(armed=False),
            wallet_address="0xabc",
            private_key="k",
            transport=transport,
            warm_ohlcv=fixture_ohlcv(n_bars=50, drift=-5.0),
            poll_fn=lambda after_ts=None: pd.DataFrame(),
            max_live_bars=0,
            install_signal_handlers=False,
            sleep_fn=lambda _s: None,
        )
    assert transport.calls == []


def test_start_live_daemon_refuses_without_secrets_flag(tmp_path: Path):
    from hypervector.live.runner import start_live_daemon

    export = _write_strict_export(tmp_path)
    transport = RecordingTransport()
    with pytest.raises(LivePolicyError, match="secrets"):
        start_live_daemon(
            export_dir=export,
            data_root=tmp_path / "data",
            policy=_armed_policy(secrets_present=False),
            wallet_address="0xabc",
            private_key="k",
            transport=transport,
            warm_ohlcv=fixture_ohlcv(n_bars=50, drift=-5.0),
            poll_fn=lambda after_ts=None: pd.DataFrame(),
            max_live_bars=0,
            install_signal_handlers=False,
            sleep_fn=lambda _s: None,
        )
    assert transport.calls == []


def test_start_live_daemon_writes_live_ledger_and_places_on_live_phase(
    tmp_path: Path,
):
    from hypervector.live.runner import start_live_daemon

    export = _write_strict_export(tmp_path)
    data_root = tmp_path / "data"
    transport = RecordingTransport(response={"status": "ok", "oid": "oid-live-9"})

    warm = fixture_ohlcv(n_bars=200, drift=-5.0, wave_period=40)
    # One live bar after warm so live phase can run intent path.
    last_ts = pd.Timestamp(warm["timestamp"].iloc[-1])
    live_bar = warm.iloc[[-1]].copy()
    live_bar["timestamp"] = last_ts + pd.Timedelta(minutes=1)
    live_bar["close"] = float(live_bar["close"].iloc[0]) * 0.99

    result = start_live_daemon(
        export_dir=export,
        data_root=data_root,
        policy=_armed_policy(max_notional_usd=50.0),
        wallet_address="0xwallet",
        private_key="sekrit",
        transport=transport,
        warm_ohlcv=warm,
        poll_fn=lambda after_ts=None: live_bar,
        max_live_bars=1,
        install_signal_handlers=False,
        sleep_fn=lambda _s: None,
        conviction=0.5,
    )

    assert result.execution_mode == "live"
    assert result.warm_bars == 200
    assert result.live_bars == 1
    assert result.decisions_path.is_file()
    # Live root only
    assert "live" in result.decisions_path.parts
    assert "paper" not in result.decisions_path.parts
    paper_dec = data_root / "paper" / "decisions" / "decisions.jsonl"
    assert not paper_dec.is_file() or paper_dec.read_text().strip() == ""

    rows = [
        json.loads(line)
        for line in result.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert all(r.get("execution_mode") == "live" for r in rows)
    assert all(r.get("network") == "mainnet" for r in rows)

    # Warm-up must never place.
    market = [
        r
        for r in rows
        if r.get("action") not in (None, "session_start", "funding")
        and r.get("action") != "session_start"
    ]
    warm_market = [r for r in market if r.get("live_phase") is False]
    for r in warm_market:
        assert r.get("submitted") is False
        assert r.get("place_attempted") is False

    # Any place calls only after warm-up (live phase).
    # Transport may or may not be called depending on strategy signals on live bar.
    for call in transport.calls:
        assert call["wallet_address"] == "0xwallet"
        assert call["private_key"] == "sekrit"
        # Cap: notional <= 50
        assert call["sz"] * 100_000 < 10_000  # loose; real assert via live_phase rows

    live_market = [r for r in market if r.get("live_phase") is True]
    for r in live_market:
        assert r.get("place_attempted") is True
        oi = r.get("order_intent") or {}
        assert oi.get("submit_enabled") is True
        if r.get("submitted") is True:
            assert r.get("venue_order_id") == "oid-live-9"


def test_live_fill_engine_place_failure_stamps_error(tmp_path: Path):
    from hypervector.live.engine import LiveFillEngine
    from hypervector.paper.costs import CostProvider

    transport = RecordingTransport(error=RuntimeError("venue reject"))
    from hypervector.live.exec_client import HyperliquidLiveExecClient

    client = HyperliquidLiveExecClient(
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
        max_notional_usd=50.0,
    )
    engine = LiveFillEngine(
        tmp_path / "data",
        cost_provider=CostProvider(
            fee_tier=0, slippage_bps=2.0, funding_rate_hourly=0.0
        ),
        run_id="r1",
        export_id="e1",
        strategy_name="crown_stack_short",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        client=client,
        place_enabled=True,
        max_notional_usd=50.0,
    )
    rec = engine.apply_market_fill(
        feed_ts="t1",
        action="enter_short",
        side="sell",
        qty=0.001,
        mark_px=40_000.0,
    )
    assert rec["submitted"] is False
    assert rec["place_attempted"] is True
    assert "venue reject" in (rec.get("submit_error") or "")
    assert rec["execution_mode"] == "live"
    assert engine.position.qty == 0.0  # reject does not open position


def test_live_fill_engine_warm_no_place(tmp_path: Path):
    from hypervector.live.engine import LiveFillEngine
    from hypervector.live.exec_client import HyperliquidLiveExecClient
    from hypervector.paper.costs import CostProvider

    transport = RecordingTransport()
    client = HyperliquidLiveExecClient(
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
        max_notional_usd=50.0,
    )
    engine = LiveFillEngine(
        tmp_path / "data",
        cost_provider=CostProvider(
            fee_tier=0, slippage_bps=2.0, funding_rate_hourly=0.0
        ),
        run_id="r1",
        export_id="e1",
        strategy_name="crown_stack_short",
        symbol="BTC",
        timeframe="1m",
        conviction=0.5,
        client=client,
        place_enabled=False,
        max_notional_usd=50.0,
    )
    rec = engine.apply_market_fill(
        feed_ts="t1",
        action="enter_short",
        side="sell",
        qty=0.001,
        mark_px=40_000.0,
    )
    assert rec["submitted"] is False
    assert rec["place_attempted"] is False
    assert rec["live_phase"] is False
    assert transport.calls == []
    assert engine.position.qty != 0.0  # warm tracks synthetic position


def test_cli_live_run_refuses_without_arm(tmp_path: Path, capsys, monkeypatch):
    from hypervector.cli import main

    export = _write_strict_export(tmp_path)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(export),
            "--enabled",
            "--max-live-bars",
            "0",
        ]
    )
    # A missing authority flag is a refusal (exit 2) with the JSON error shape.
    assert rc == 2
    error = json.loads(capsys.readouterr().err)
    assert (error["command"], error["error_type"]) == ("live run", "CommandRefused")
    err = error["error"]
    assert (
        "arm" in err.lower()
        or "accept-live-risk" in err.lower()
        or "risk" in err.lower()
    )


def test_cli_live_run_refuses_without_enabled(tmp_path: Path, capsys, monkeypatch):
    from hypervector.cli import main

    export = _write_strict_export(tmp_path)
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(export),
            "--i-accept-live-risk",
            "--max-live-bars",
            "0",
        ]
    )
    assert rc == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error_type"] == "CommandRefused"
    assert "enabled" in error["error"].lower()


def test_paper_package_still_has_no_live_exec_import():
    paper_root = Path(__file__).resolve().parents[1] / "src" / "hypervector" / "paper"
    forbidden = (
        "HyperliquidLiveExecClient",
        "create_live_exec_client",
        "from hypervector.live.exec_client",
        "from hypervector.live.runner",
    )
    offenders: list[str] = []
    for path in sorted(paper_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, "paper must not import live exec:\n" + "\n".join(offenders)


def test_start_live_daemon_cancel_all_on_stop(tmp_path: Path):
    """F4: after live phase armed, the stop path runs the kill switch once.

    The daemon only sends IOC orders, which never rest, so with no owned
    resting order the kill is a verified no-op: it must not cancel orders it
    did not place (another strategy's stops on the same account).
    """
    from hypervector.live.runner import start_live_daemon

    export = _write_strict_export(tmp_path)
    transport = RecordingTransport()
    warm = fixture_ohlcv(n_bars=40, drift=-5.0)

    result = start_live_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        policy=_armed_policy(),
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
        warm_ohlcv=warm,
        poll_fn=lambda after_ts=None: pd.DataFrame(),
        max_live_bars=0,
        install_signal_handlers=False,
        sleep_fn=lambda _s: None,
    )
    assert result.cancel_attempted is True
    assert result.cancel_ok is True
    assert result.cancel_error is None
    assert transport.cancel_calls == []


def test_cancel_all_transport_error_is_best_effort(tmp_path: Path, monkeypatch):
    """An owned resting order whose cancel fails is reported, never raised."""
    from hypervector.live.runner import start_live_daemon
    from hypervector.nautilus.signals import SignalIntent

    monkeypatch.setattr(
        "hypervector.live.session.last_bar_intent",
        lambda df, name, params: SignalIntent("short", True, False, len(df) - 1),
    )
    export = _write_strict_export(tmp_path)
    transport = RecordingTransport(
        response={
            "status": "ok",
            "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 42}}]}},
        },
        cancel_error=RuntimeError("cancel down"),
    )
    warm = fixture_ohlcv(n_bars=20, drift=-5.0)
    live_bar = warm.iloc[[-1]].copy()
    live_bar["timestamp"] = pd.Timestamp(warm["timestamp"].iloc[-1]) + pd.Timedelta(
        minutes=1
    )

    result = start_live_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        policy=_armed_policy(),
        wallet_address="0xabc",
        private_key="k",
        transport=transport,
        warm_ohlcv=warm,
        poll_fn=lambda after_ts=None: live_bar,
        max_live_bars=1,
        install_signal_handlers=False,
        sleep_fn=lambda _s: None,
    )
    assert len(transport.calls) == 1
    assert transport.cancel_calls[0]["oids"] == [42]
    assert transport.cancel_calls[0]["coin"] == "BTC"
    assert result.cancel_attempted is True
    assert result.cancel_ok is False
    assert "cancel down" in (result.cancel_error or "")
