"""Paper CLI: paper-check identity + paper-run daemon offline path."""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.paper.maker_execution import PostOnlyLimitFillModel
from hypervector.paper.runner import PaperDaemonResult, start_paper_daemon
from hypervector.paper.session import PaperSession
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


def _write_strict_export(root: Path, *, strategy: str = "crown_stack_short") -> Path:
    track = "downtrend" if "short" in strategy else "uptrend"
    return export_candidate(
        root / "exports",
        run_id="papercli1",
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
            "data_provenance": {"sources": {"fixture": 100}},
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
        candidate_id="paper_cli_crown",
        strict=True,
    )


def _venue_bar(timestamp: str, *, high: float) -> dict[str, object]:
    """Build one Hyperliquid candle for daemon restart tests."""
    return {
        "timestamp": pd.Timestamp(timestamp),
        "open": 100.0,
        "high": high,
        "low": 99.9,
        "close": 100.0,
        "volume": 1.0,
        "source": "hl",
    }


class _EventPump:
    """Deterministic no-network event pump for daemon activation tests."""

    def __init__(self) -> None:
        self.started = False
        self.pumps = 0
        self.closed = False

    def start(self) -> None:
        self.started = True

    def pump(self, _consumer: object) -> int:
        self.pumps += 1
        return 0

    def close(self) -> None:
        self.closed = True


class _FailingStartEventPump(_EventPump):
    """Pump whose startup fails before it can accept a consumer."""

    def start(self) -> None:
        raise RuntimeError("public event stream unavailable")


def test_daemon_activates_authoritative_event_stream_without_rest_book_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile_text = Path("configs/hypervelocity_faithful.toml").read_text()
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        profile_text.replace(
            "data/exports/uptrend_hypervelocity_1m_scalper_long_784548f1",
            str(export),
        ),
        encoding="utf-8",
    )
    profile = replace(load_hypervelocity_profile(profile_path), metalabel_mode="off")
    warm = fixture_ohlcv(n_bars=5)
    pump = _EventPump()
    monkeypatch.setattr(
        PaperSession,
        "initialize_hypervelocity_venue",
        lambda _self: 0.0,
    )
    monkeypatch.setattr(
        "hypervector.paper.runner.make_rest_poll_fn",
        lambda _symbol, _timeframe: (lambda **_kwargs: warm.iloc[0:0].copy()),
    )

    def reject_rest_book(_self: object) -> None:
        raise AssertionError("event authority must not poll the REST book")

    monkeypatch.setattr("hypervector.paper.book.BookFeed.poll", reject_rest_book)

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=None,
        max_live_bars=0,
        install_signal_handlers=False,
        enable_funding_refresh=False,
        hypervelocity_profile=profile,
        event_stream_pump=pump,
        now_fn=lambda: pd.Timestamp("2026-07-26T20:00:00Z"),
    )

    assert result.stop_reason == "max_live_bars"
    assert pump.started and pump.closed
    assert pump.pumps == 2


def test_event_authority_defaults_to_websocket_context_not_rest_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile_text = Path("configs/hypervelocity_faithful.toml").read_text()
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        profile_text.replace(
            "data/exports/uptrend_hypervelocity_1m_scalper_long_784548f1",
            str(export),
        ),
        encoding="utf-8",
    )
    profile = replace(load_hypervelocity_profile(profile_path), metalabel_mode="off")
    warm = fixture_ohlcv(n_bars=5)
    live = warm.iloc[-1:].copy()
    live.loc[:, "timestamp"] = pd.Timestamp("2026-07-26T20:00:00Z")
    returned = False

    def feed(**_kwargs: object) -> pd.DataFrame:
        nonlocal returned
        if returned:
            return live.iloc[0:0].copy()
        returned = True
        return live

    refresh_checks: list[bool] = []

    def assert_ws_authority(session: PaperSession) -> None:
        refresh_checks.append(session.enable_funding_refresh)

    monkeypatch.setattr(
        PaperSession,
        "initialize_hypervelocity_venue",
        lambda _self: 0.0,
    )
    monkeypatch.setattr(PaperSession, "maybe_refresh_funding", assert_ws_authority)
    monkeypatch.setattr(
        "hypervector.paper.runner.make_rest_poll_fn",
        lambda _symbol, _timeframe: feed,
    )

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=None,
        max_live_bars=1,
        install_signal_handlers=False,
        hypervelocity_profile=profile,
        event_stream_pump=_EventPump(),
        enforce_live_boundary=False,
        now_fn=lambda: pd.Timestamp("2026-07-26T20:00:00Z"),
    )

    assert result.live_bars == 1
    assert refresh_checks == [False]


def test_event_stream_start_failure_is_not_masked_by_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    profile_text = Path("configs/hypervelocity_faithful.toml").read_text()
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        profile_text.replace(
            "data/exports/uptrend_hypervelocity_1m_scalper_long_784548f1",
            str(export),
        ),
        encoding="utf-8",
    )
    profile = replace(load_hypervelocity_profile(profile_path), metalabel_mode="off")
    pump = _FailingStartEventPump()
    monkeypatch.setattr(
        PaperSession,
        "initialize_hypervelocity_venue",
        lambda _self: 0.0,
    )

    with pytest.raises(RuntimeError, match="public event stream unavailable"):
        start_paper_daemon(
            export_dir=export,
            data_root=tmp_path / "data",
            warm_ohlcv=fixture_ohlcv(n_bars=5),
            poll_fn=lambda **_kwargs: fixture_ohlcv(n_bars=0),
            max_live_bars=0,
            install_signal_handlers=False,
            enable_funding_refresh=False,
            hypervelocity_profile=profile,
            event_stream_pump=pump,
            now_fn=lambda: pd.Timestamp("2026-07-26T20:00:00Z"),
        )

    assert pump.closed
    assert pump.pumps == 0


def test_paper_check_reports_mode(tmp_path: Path, capsys, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["--data-root", str(data), "paper", "check"])
    assert rc == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    # Phase 4b default surface is shadow (mainnet-honest, no venue submit).
    assert report["paper"]["execution_mode"] == "shadow"
    assert report["paper"]["mode"] == "shadow"
    assert report["paper"]["live_feed_loop"] is True
    assert report["paper"]["sandbox_enabled"] is False
    assert report["paper"]["secrets_present"] is False
    assert "decisions" in report["paper"]
    assert "ledger" in report["paper"]
    # Env *names* may be listed; never print secret *values* (none set here).
    assert "secret_env_names" in report["paper"]


def test_paper_check_reports_shadow_surface(tmp_path: Path, capsys, monkeypatch):
    """Phase 4b: paper-check exposes shadow/mainnet/no-submit surface (no secrets)."""
    data = tmp_path / "data"
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["--data-root", str(data), "paper", "check"])
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    paper = report["paper"]
    assert paper["mode"] in ("shadow", "paper")
    assert paper["mode"] == "shadow"  # 4b default
    assert paper["network"] == "mainnet"
    assert paper["no_submit"] is True
    assert paper["submitted_default"] is False
    assert paper["order_intent_schema"] == "hv_order_intent_v1"
    assert report["live"]["enabled"] is False
    # Booleans/strings only for shadow keys; never secret values.
    assert "sekrit" not in out
    assert paper["secrets_present"] is False
    assert "testnet" not in out.lower()


def test_paper_check_secrets_present_true(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    rc = main(["--data-root", str(tmp_path / "data"), "paper", "check"])
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["paper"]["secrets_present"] is True
    assert "sekrit" not in out
    assert "0xabc" not in out


def test_paper_check_reports_fill_and_book_surface(tmp_path: Path, capsys, monkeypatch):
    """Phase 4a: paper-check exposes book/fill/metalabel surface (no secrets)."""
    data = tmp_path / "data"
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["--data-root", str(data), "paper", "check"])
    assert rc == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    paper = report["paper"]
    assert paper["preferred_fill_model"] == "l2_walk_v1"
    assert paper["max_book_age_ms"] == 3000
    assert paper["book_feed"] is True
    assert paper["l2_walk_available"] is True
    assert paper["metalabel_enabled"] is False
    assert paper["metalabel_default_off"] is True
    assert paper["metalabel_modes"] == ["off", "observe", "scale", "filter"]
    assert paper["recommended_annotation_flag"] == "--metalabel-mode observe"
    assert "metalabel_ready" in paper
    assert "metalabel_bundle_root" in paper
    assert report["live"]["enabled"] is False
    # No secret material in the payload
    assert "sekrit" not in out
    assert (
        "private" not in out.lower()
        or "private_key" in str(paper.get("secret_env_names", [])).lower()
    )


def test_paper_run_requires_export_path():
    with pytest.raises(SystemExit) as exc:
        main(["paper", "run"])
    assert exc.value.code != 0


def test_paper_run_help():
    with pytest.raises(SystemExit) as exc:
        main(["paper", "run", "--help"])
    assert exc.value.code == 0


def test_paper_run_help_lists_phase4a_flags(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["paper", "run", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--preferred-fill-model" in help_text
    assert "--max-book-age-ms" in help_text
    assert "--metalabel-mode" in help_text
    assert "--no-metalabel" not in help_text


def test_paper_run_help_lists_mode_and_shadow_surface(capsys):
    """Phase 4b: --mode flag + help states no venue orders / mainnet shadow."""
    with pytest.raises(SystemExit) as exc:
        main(["paper", "run", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out.lower()
    assert "--mode" in help_text
    assert "shadow" in help_text
    assert "no venue" in help_text or "no venue orders" in help_text
    assert "mainnet" in help_text


def test_daemon_default_shadow_mode_on_offline_path(tmp_path: Path):
    """Daemon default execution_mode is shadow (live REST default; offline path same kwargs)."""
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=20, drift=-3.0, wave_period=15)

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=lambda **_: warm.iloc[0:0].copy(),
        max_live_bars=0,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
    )
    assert isinstance(result, PaperDaemonResult)
    assert result.execution_mode == "shadow"
    assert result.warm_bars == 20


def test_hypervelocity_daemon_warmup_seeds_without_historical_orders(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Historical indicator seed data must not become fresh shadow orders."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    warm = fixture_ohlcv(n_bars=20, drift=5.0, wave_period=10)
    monkeypatch.setattr(
        "hypervector.paper.session.PaperSession._hypervelocity_allowed",
        lambda _self, _direction: True,
    )

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=lambda **_: warm.iloc[0:0].copy(),
        max_live_bars=0,
        poll_interval_secs=0.0,
        sleep_fn=lambda _seconds: None,
        install_signal_handlers=False,
    )

    rows = [json.loads(line) for line in result.decisions_path.read_text().splitlines()]
    assert [row["action"] for row in rows] == ["session_start"]
    assert result.fills_count == 0


def test_start_paper_daemon_offline_injected_bars(tmp_path: Path, capsys):
    """Daemon warm-up + live poll mock; no network; stop after max live bars."""
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=50, drift=-5.0, wave_period=20)
    live = fixture_ohlcv(n_bars=10, drift=-5.0, wave_period=20)
    # Shift live timestamps after warm so they count as new bars
    live = live.copy()
    live["timestamp"] = (
        warm["timestamp"].iloc[-1]
        + (live["timestamp"] - live["timestamp"].iloc[0])
        + (warm["timestamp"].iloc[1] - warm["timestamp"].iloc[0])
    )

    calls = {"n": 0}

    def poll_fn(*, after_ts=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return live
        return live.iloc[0:0].copy()  # empty thereafter

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        conviction=0.5,
        fee_tier=0,
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        max_live_bars=10,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
        execution_mode="paper",  # offline stable paper assertions
    )
    assert isinstance(result, PaperDaemonResult)
    assert result.warm_bars == 50
    assert result.live_bars == 10
    assert result.bars_processed == 60
    assert result.decisions_path.is_file()
    assert result.stop_reason in ("max_live_bars", "poll_exhausted", "stop")
    assert result.execution_mode == "paper"
    text = result.decisions_path.read_text(encoding="utf-8")
    assert "execution_mode" in text
    assert "paper" in text
    # Banner on stderr
    err = capsys.readouterr().err
    assert "PAPER MODE" in err
    assert "no venue orders" in err.lower() or "no venue" in err.lower()


def test_daemon_warmup_does_not_poll_book(tmp_path: Path, monkeypatch):
    """Highest-+EV lock: historical warm-up never hits live L2 REST."""
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=30, drift=-5.0, wave_period=20)
    live = fixture_ohlcv(n_bars=3, drift=-5.0, wave_period=20)
    live = live.copy()
    live["timestamp"] = (
        warm["timestamp"].iloc[-1]
        + (live["timestamp"] - live["timestamp"].iloc[0])
        + (warm["timestamp"].iloc[1] - warm["timestamp"].iloc[0])
    )

    book_polls = {"n": 0}

    def fake_poll(self, *, session=None):
        book_polls["n"] += 1
        return None

    monkeypatch.setattr("hypervector.paper.book.BookFeed.poll", fake_poll)

    calls = {"n": 0}

    def poll_fn(*, after_ts=None, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return live
        return live.iloc[0:0].copy()

    # Injected poll_fn ⇒ offline path; book stays off entirely.
    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        max_live_bars=3,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
    )
    assert result.warm_bars == 30
    assert result.live_bars == 3
    assert book_polls["n"] == 0

    # Simulate live REST path (poll_fn is None → live_book_enabled): warm-up
    # still no poll; one arm poll after warm, then live bars may poll.
    book_polls["n"] = 0
    # Avoid real network for bars: still inject warm; use a stub feed via
    # monkeypatching make_rest_poll_fn and process only warm by max_live_bars=0.
    from hypervector.paper import runner as runner_mod

    def fake_rest_poll_fn(symbol, timeframe):
        def _feed(*, after_ts=None, **_kwargs):
            return live.iloc[0:0].copy()

        return _feed

    monkeypatch.setattr(runner_mod, "make_rest_poll_fn", fake_rest_poll_fn)
    result2 = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data2",
        warm_ohlcv=warm,
        poll_fn=None,  # live REST path ⇒ book armed after warm
        max_live_bars=0,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
    )
    assert result2.warm_bars == 30
    # Exactly one arm poll after warm-up (max_live_bars=0 → no live on_bar polls)
    assert book_polls["n"] == 1


def test_capped_live_rest_waits_for_next_completed_bar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Normal empty REST polls between candles must not mimic mock exhaustion."""
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=20, drift=-1.0)
    live = warm.iloc[[-1]].copy()
    live["timestamp"] = warm["timestamp"].iloc[-1] + pd.Timedelta(minutes=1)
    calls = {"count": 0}

    def fake_rest_poll_fn(symbol: str, timeframe: str):
        del symbol, timeframe

        def poll(*, after_ts=None):
            del after_ts
            calls["count"] += 1
            if calls["count"] <= 3:
                return live.iloc[0:0].copy()
            return live

        return poll

    monkeypatch.setattr(
        "hypervector.paper.runner.make_rest_poll_fn",
        fake_rest_poll_fn,
    )
    monkeypatch.setattr(
        "hypervector.paper.book.BookFeed.poll",
        lambda _self: None,
    )

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=None,
        max_live_bars=1,
        poll_interval_secs=0.0,
        sleep_fn=lambda _seconds: None,
        install_signal_handlers=False,
        enable_funding_refresh=False,
        enforce_live_boundary=False,
    )

    assert calls["count"] == 4
    assert result.live_bars == 1
    assert result.stop_reason == "max_live_bars"


def test_live_rest_seeds_stale_catchup_without_calling_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale cache tails seed indicators; only post-activation closes execute."""
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=20, drift=-1.0)
    returned = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-07-25T14:58:00Z",
                    "2026-07-25T14:59:00Z",
                    "2026-07-25T15:00:00Z",
                    "2026-07-25T15:01:00Z",
                ],
                utc=True,
            ),
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.0] * 4,
            "volume": [1.0] * 4,
        }
    )
    monkeypatch.setattr(
        "hypervector.paper.runner.make_rest_poll_fn",
        lambda _symbol, _timeframe: (lambda **_kwargs: returned),
    )
    monkeypatch.setattr("hypervector.paper.book.BookFeed.poll", lambda _self: None)
    observed: list[pd.Timestamp] = []
    from hypervector.paper.session import PaperSession

    original = PaperSession.on_bar

    def record_live(self: PaperSession, row: pd.Series) -> str | None:
        observed.append(pd.Timestamp(row["timestamp"]))
        return original(self, row)

    monkeypatch.setattr(PaperSession, "on_bar", record_live)
    times = iter(
        [
            pd.Timestamp("2026-07-25T15:00:30Z"),
            pd.Timestamp("2026-07-25T15:01:05Z"),
        ]
    )

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=None,
        max_live_bars=1,
        poll_interval_secs=0.0,
        sleep_fn=lambda _seconds: None,
        install_signal_handlers=False,
        enable_funding_refresh=False,
        now_fn=lambda: next(times),
    )

    assert result.live_bars == 1
    assert observed == [pd.Timestamp("2026-07-25T15:00:00Z")]
    rows = [json.loads(line) for line in result.decisions_path.read_text().splitlines()]
    identity = next(row for row in rows if row["action"] == "session_start")
    assert identity["runtime"]["live_activated_at"] == "2026-07-25T15:00:30+00:00"


def test_daemon_reconciles_resumed_target_with_historical_funding(
    tmp_path: Path,
) -> None:
    """Startup splits seed history from venue-matched missed execution bars."""
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    data_root = tmp_path / "data"
    original = PaperSession(
        export_dir=export,
        data_root=data_root,
        run_id="restart-run",
        execution_mode="shadow",
    )
    original.ensure_session_identity()
    original.engine.apply_market_fill(
        feed_ts="2026-07-25T12:58:00Z",
        action="enter_long",
        side="buy",
        qty=1.0,
        mark_px=100.0,
        fill_model=PostOnlyLimitFillModel(),
    )
    warm = pd.DataFrame(
        [
            _venue_bar("2026-07-25T12:57:00Z", high=100.1),
            _venue_bar("2026-07-25T12:58:00Z", high=100.1),
            _venue_bar("2026-07-25T12:59:00Z", high=100.1),
        ]
    )
    calls: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def funding_history(
        symbol: str,
        *,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.DataFrame:
        assert symbol == "BTC"
        calls.append((start_time, end_time))
        return pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2026-07-25T13:00:00Z")],
                "funding_rate": [0.001],
                "source": ["hl_funding_history"],
            }
        )

    result = start_paper_daemon(
        export_dir=export,
        data_root=data_root,
        warm_ohlcv=warm,
        poll_fn=lambda **_kwargs: warm.iloc[0:0].copy(),
        funding_history_fn=funding_history,
        max_live_bars=0,
        poll_interval_secs=0.0,
        sleep_fn=lambda _seconds: None,
        install_signal_handlers=False,
        execution_mode="shadow",
        now_fn=lambda: pd.Timestamp("2026-07-25T13:00:30Z"),
    )

    assert result.run_id == "restart-run"
    assert result.warm_bars == 3
    assert calls == [
        (
            pd.Timestamp("2026-07-25T13:00:00Z"),
            pd.Timestamp("2026-07-25T13:01:00Z"),
        )
    ]
    rows = [json.loads(line) for line in result.decisions_path.read_text().splitlines()]
    funding = [row for row in rows if row.get("action") == "funding"]
    assert funding[-1]["funding_rate_hourly"] == 0.001


def test_start_paper_daemon_stop_file(tmp_path: Path):
    export = _write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=5, drift=-1.0)
    stop = tmp_path / "STOP"
    poll_count = {"n": 0}

    def poll_fn(*, after_ts=None, **_kwargs):
        poll_count["n"] += 1
        if poll_count["n"] >= 2:
            stop.write_text("stop", encoding="utf-8")
        return warm.iloc[0:0].copy()

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=poll_fn,
        stop_file=stop,
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
    )
    assert result.stop_reason == "stop_file"
    assert result.warm_bars == 5


def test_cli_paper_run_offline_via_monkeypatch(tmp_path: Path, capsys, monkeypatch):
    """CLI paper-run calls daemon; inject offline path so no network."""
    export = _write_strict_export(tmp_path)
    data = tmp_path / "data"
    warm = fixture_ohlcv(n_bars=20, drift=-3.0, wave_period=15)

    def fake_daemon(**kwargs):
        return start_paper_daemon(
            export_dir=kwargs["export_dir"],
            data_root=kwargs["data_root"],
            conviction=kwargs.get("conviction", 0.5),
            fee_tier=kwargs.get("fee_tier", 0),
            sandbox_enabled=kwargs.get("sandbox_enabled", False),
            preferred_fill_model=kwargs.get("preferred_fill_model", "l2_walk_v1"),
            max_book_age_ms=kwargs.get("max_book_age_ms", 3000),
            metalabel_enabled=kwargs.get("metalabel_enabled", False),
            stop_file=kwargs.get("stop_file"),
            execution_mode=kwargs.get("execution_mode", "shadow"),
            warm_ohlcv=warm,
            poll_fn=lambda **_: warm.iloc[0:0].copy(),
            max_live_bars=0,
            poll_interval_secs=0.0,
            sleep_fn=lambda _s: None,
            install_signal_handlers=False,
        )

    monkeypatch.setattr("hypervector.commands.paper.start_paper_daemon", fake_daemon)
    rc = main(
        [
            "--data-root",
            str(data),
            "paper",
            "run",
            "--export",
            str(export),
        ]
    )
    assert rc == 0
    out = capsys.readouterr()
    # Default daemon mode is shadow — banner must match (not lie as paper-only).
    assert "SHADOW MODE" in out.err
    assert "no venue orders" in out.err.lower()
    payload = json.loads(out.out)
    assert payload["ok"] is True
    # Daemon default is shadow; CLI Task 5 may wire flags later
    assert payload["execution_mode"] == "shadow"
    assert payload["warm_bars"] == 20


@pytest.mark.usefixtures("annotation_model")
def test_cli_paper_run_passes_fill_and_metalabel_flags(tmp_path: Path, monkeypatch):
    """CLI flags for preferred fill model, book age, metalabel flow into daemon."""
    export = _write_strict_export(tmp_path)
    data = tmp_path / "data"
    captured: dict = {}

    def fake_daemon(**kwargs):
        captured.update(kwargs)
        warm = fixture_ohlcv(n_bars=5, drift=-1.0)
        return start_paper_daemon(
            export_dir=kwargs["export_dir"],
            data_root=kwargs["data_root"],
            conviction=kwargs.get("conviction", 0.5),
            preferred_fill_model=kwargs.get("preferred_fill_model"),
            max_book_age_ms=kwargs.get("max_book_age_ms"),
            metalabel_enabled=kwargs.get("metalabel_enabled", False),
            execution_mode=kwargs.get("execution_mode", "shadow"),
            warm_ohlcv=warm,
            poll_fn=lambda **_: warm.iloc[0:0].copy(),
            max_live_bars=0,
            poll_interval_secs=0.0,
            sleep_fn=lambda _s: None,
            install_signal_handlers=False,
        )

    monkeypatch.setattr("hypervector.commands.paper.start_paper_daemon", fake_daemon)
    rc = main(
        [
            "--data-root",
            str(data),
            "paper",
            "run",
            "--export",
            str(export),
            "--preferred-fill-model",
            "top_bps_v1",
            "--max-book-age-ms",
            "1500",
            "--metalabel-mode",
            "filter",
        ]
    )
    assert rc == 0
    assert captured["preferred_fill_model"] == "top_bps_v1"
    assert captured["max_book_age_ms"] == 1500.0
    assert captured["metalabel_enabled"] is True
    assert captured["execution_mode"] == "shadow"  # CLI default


@pytest.mark.usefixtures("annotation_model")
def test_cli_paper_run_observe_mode_reaches_daemon(tmp_path: Path, monkeypatch):
    """Observe mode is explicit and reaches the backend without enabling a gate."""
    export = _write_strict_export(tmp_path)
    data = tmp_path / "data"
    captured: dict = {}

    def fake_daemon(**kwargs):
        captured.update(kwargs)
        warm = fixture_ohlcv(n_bars=5, drift=-1.0)
        return start_paper_daemon(
            export_dir=kwargs["export_dir"],
            data_root=kwargs["data_root"],
            metalabel_enabled=kwargs.get("metalabel_enabled", False),
            metalabel_mode=kwargs.get("metalabel_mode"),
            execution_mode=kwargs.get("execution_mode", "shadow"),
            warm_ohlcv=warm,
            poll_fn=lambda **_: warm.iloc[0:0].copy(),
            max_live_bars=0,
            poll_interval_secs=0.0,
            sleep_fn=lambda _s: None,
            install_signal_handlers=False,
        )

    monkeypatch.setattr("hypervector.commands.paper.start_paper_daemon", fake_daemon)

    rc = main(
        [
            "--data-root",
            str(data),
            "paper",
            "run",
            "--export",
            str(export),
            "--metalabel-mode",
            "observe",
        ]
    )

    assert rc == 0
    assert captured["metalabel_enabled"] is True
    assert captured["metalabel_mode"] == "observe"


def test_cli_forces_hypervelocity_model_policy_to_annotation_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _write_strict_export(
        tmp_path,
        strategy="hypervelocity_1m_scalper_long",
    )
    captured: dict = {}

    def fake_daemon(**kwargs):
        captured.update(kwargs)
        return PaperDaemonResult(
            run_id="hv",
            export_dir=Path(kwargs["export_dir"]),
            decisions_path=tmp_path / "decisions.jsonl",
            warm_bars=0,
            live_bars=0,
            bars_processed=0,
            fills_count=0,
            stop_reason="bounded",
            execution_mode="shadow",
        )

    monkeypatch.setattr("hypervector.commands.paper.start_paper_daemon", fake_daemon)
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "paper",
            "run",
            "--export",
            str(export),
            "--metalabel-mode",
            "filter",
        ]
    )

    assert rc == 0
    assert captured["metalabel_enabled"] is True
    assert captured["metalabel_mode"] == "observe"
    assert captured["metalabel_filter"] is False


def test_hypervelocity_shadow_cli_uses_websocket_funding_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def fake_daemon(**kwargs: object) -> PaperDaemonResult:
        captured.update(kwargs)
        return PaperDaemonResult(
            run_id="hv",
            export_dir=Path("data/exports"),
            decisions_path=tmp_path / "decisions.jsonl",
            warm_bars=0,
            live_bars=0,
            bars_processed=0,
            fills_count=0,
            stop_reason="bounded",
            execution_mode="shadow",
        )

    monkeypatch.setattr("hypervector.commands.shadow.start_paper_daemon", fake_daemon)

    result = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "paper",
            "shadow",
            "--config",
            "configs/hypervelocity_faithful.toml",
            "--max-live-bars",
            "0",
        ]
    )

    assert result == 0
    assert captured["enable_funding_refresh"] is False
    output = json.loads(capsys.readouterr().out)
    assert output["funding_authority"] == "hyperliquid_ws_activeAssetCtx"
    assert output["rest_funding_refresh_enabled"] is False


def test_cli_paper_run_mode_flag_wires_execution_mode(tmp_path: Path, monkeypatch):
    """paper run --mode paper|shadow is forwarded to start_paper_daemon."""
    export = _write_strict_export(tmp_path)
    data = tmp_path / "data"
    captured: dict = {}

    def fake_daemon(**kwargs):
        captured.update(kwargs)
        warm = fixture_ohlcv(n_bars=5, drift=-1.0)
        return start_paper_daemon(
            export_dir=kwargs["export_dir"],
            data_root=kwargs["data_root"],
            execution_mode=kwargs.get("execution_mode", "shadow"),
            warm_ohlcv=warm,
            poll_fn=lambda **_: warm.iloc[0:0].copy(),
            max_live_bars=0,
            poll_interval_secs=0.0,
            sleep_fn=lambda _s: None,
            install_signal_handlers=False,
        )

    monkeypatch.setattr("hypervector.commands.paper.start_paper_daemon", fake_daemon)
    rc = main(
        [
            "--data-root",
            str(data),
            "paper",
            "run",
            "--export",
            str(export),
            "--mode",
            "paper",
        ]
    )
    assert rc == 0
    assert captured["execution_mode"] == "paper"


@pytest.fixture
def annotation_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Model-option forwarding is exercised with a deterministic local model."""
    class Model:
        root = tmp_path / "fixture-model"
        feature_names = ["close"]

        def predict_probability(self, _features: dict[str, float]) -> float:
            return 0.73

    monkeypatch.setattr("hypervector.ml.metalabel.Metalabeler.from_env", lambda **_kwargs: Model())
