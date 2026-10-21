"""Final review fixes: pinned research windows, paper warm-up, book and archive data.

Everything is offline: the HL/Binance/Bybit fetchers are replaced with
recorders, sockets are refused by ``conftest`` and every data root lives under
``tmp_path``. The pipeline tests leave ``run_autotune``, the sweep, the model
trainer and the history loader real, so the cache policy each stage applies is
what is measured.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from paper_fix_fixtures import write_strict_export
from test_cli_pipeline import Fakes, strict_bundle

import hypervector.data.pipeline as history
from hypervector.cli import main
from hypervector.data.sources import fixture_ohlcv

LOOKBACK = 30
HOURLY_BARS = LOOKBACK * 24 + 1
CORE_KEY = "BTC_1h_30d"
STRICT_KEY = "BTC_1h_30d_hlonly"


def _hourly(end: pd.Timestamp, *, source: str = "hl", n: int = HOURLY_BARS):
    start = (end - pd.Timedelta(hours=n - 1)).tz_localize(None)
    return fixture_ohlcv(
        n_bars=n, start=str(start), freq="1h", drift=5.0, wave_period=12, source=source
    )


def _mixed(end: pd.Timestamp) -> pd.DataFrame:
    """A backfilled window: Binance bars first, the HL tail last."""
    frame = _hourly(end)
    frame.loc[: HOURLY_BARS - 101, "source"] = "binance"
    return frame


class Venues:
    """Recording doubles for every venue fetcher the history loader may call."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, hl: pd.DataFrame) -> None:
        self.calls: list[str] = []
        self.hl = hl
        self.binance: pd.DataFrame | Exception | None = None
        monkeypatch.setattr(history, "live_hl_fetcher", self._hl)
        monkeypatch.setattr(history, "live_binance_fetcher", self._binance)
        monkeypatch.setattr(history, "live_bybit_fetcher", self._bybit)

    def _hl(self, *_args: object) -> pd.DataFrame:
        self.calls.append("hl")
        return self.hl.copy()

    def _binance(self, *_args: object) -> pd.DataFrame | None:
        self.calls.append("binance")
        if isinstance(self.binance, Exception):
            raise self.binance
        return None if self.binance is None else self.binance.copy()

    def _bybit(self, *_args: object) -> None:
        self.calls.append("bybit")
        return None


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("h")


def _seed(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    frame: pd.DataFrame,
    *,
    at: pd.Timestamp,
    strict: bool = False,
) -> Path:
    """Write ``frame`` through the real loader as if fetched at ``at``."""
    seeder = Venues(monkeypatch, frame)
    history.load_research_history(
        root,
        symbol="BTC",
        timeframe="1h",
        lookback_days=LOOKBACK,
        strict_hl_only=strict,
        now=at,
    )
    del seeder
    return root / "cache" / f"{STRICT_KEY if strict else CORE_KEY}.parquet"


def _pipeline(root: Path, *flags: str) -> list[str]:
    market = ["--symbol", "BTC", "--timeframe", "1h", "--lookback-days", str(LOOKBACK)]
    return [
        "--data-root",
        str(root),
        "pipeline",
        "run",
        "--strategy",
        "test_sma_cross_long",
        *market,
        "--n-trials",
        "2",
        *flags,
    ]


def _manifest(root: Path) -> dict[str, Any]:
    [path] = sorted((root / "runs" / "pipeline").glob("*/pipeline.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["stage"] == name)


# --- pipeline run --no-network: later stages never refresh ------------------------------


@pytest.mark.parametrize(
    "flags",
    [
        ("--no-nautilus",),
        ("--no-nautilus", "--train-model"),
        ("--no-nautilus", "--search", "sweep", "--train-model"),
    ],
    ids=["tune", "tune-model", "sweep-model"],
)
def test_no_network_stages_read_the_pinned_stale_window_without_fetching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
) -> None:
    """A cache older than a day is served as is; no stage reaches a venue."""
    root = tmp_path / "data"
    old = _now() - pd.Timedelta(days=2)
    cache = _seed(monkeypatch, root, _hourly(old), at=old)
    before = cache.read_bytes()
    venues = Venues(monkeypatch, _hourly(_now()))

    assert main(_pipeline(root, "--no-network", *flags)) == 0
    capsys.readouterr()
    assert venues.calls == []
    assert cache.read_bytes() == before
    manifest = _manifest(root)
    window = manifest["window"]
    assert pd.Timestamp(window["end"]) == old
    search = _stage(manifest, "search")["metrics"]["window"]
    assert search["matches_pinned"] is True, search
    assert search["mismatched_fields"] == []
    if "--train-model" in flags:
        assert _stage(manifest, "model")["status"] in ("ok", "skipped")


def test_tune_board_reports_the_window_the_manifest_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "data"
    old = _now() - pd.Timedelta(days=2)
    _seed(monkeypatch, root, _hourly(old), at=old)
    Venues(monkeypatch, _hourly(_now()))

    assert main(_pipeline(root, "--no-network", "--no-nautilus")) == 0
    capsys.readouterr()
    manifest = _manifest(root)
    board = json.loads(
        Path(_stage(manifest, "search")["artifacts"]["board"]).read_text("utf-8")
    )
    assert board["data_provenance"]["cache_hit"] is True
    assert board["data_provenance"]["refreshed"] is False
    assert pd.Timestamp(board["data_window"]["last_bar_utc"]) == pd.Timestamp(
        manifest["window"]["end"]
    )


def test_export_start_model_training_stays_offline_with_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """From a bundle the data stage is skipped; the model reads only the cache."""
    root = tmp_path / "data"
    strict_bundle(root / "exports", "cand", timeframe="1h", lookback_days=LOOKBACK)
    venues = Venues(monkeypatch, _hourly(_now()))
    flags = ["--strategy", "test_sma_cross_long", "--export", "cand", "--no-network"]
    flags += ["--train-model", "--no-nautilus"]
    base = ["--data-root", str(root), "pipeline", "run", *flags]

    missing = tmp_path / "missing"
    assert main([*base, "--out-dir", str(missing)]) == 1
    capsys.readouterr()
    manifest = json.loads((missing / "pipeline.json").read_text(encoding="utf-8"))
    model = _stage(manifest, "model")
    assert (model["status"], model["error_type"]) == ("failed", "FileNotFoundError")
    assert f"{CORE_KEY}.parquet" in model["reason"]
    assert venues.calls == []

    old = _now() - pd.Timedelta(days=2)
    cache = _seed(monkeypatch, root, _hourly(old), at=old)
    before = cache.read_bytes()
    venues = Venues(monkeypatch, _hourly(_now()))
    cached = tmp_path / "cached"
    assert main([*base, "--out-dir", str(cached)]) == 0
    capsys.readouterr()
    assert venues.calls == []
    assert cache.read_bytes() == before


# --- pipeline run --strict-hl-only: every stage uses the HL-only window ------------------


def test_strict_pipeline_on_a_clean_root_never_backfills_or_writes_the_default_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "data"
    venues = Venues(monkeypatch, _hourly(_now()))
    fakes = Fakes()
    monkeypatch.setattr(
        "hypervector.nautilus.config_stub.phase2_check_report", fakes.check
    )
    monkeypatch.setattr(
        "hypervector.nautilus.runner.run_phase2_backtest", fakes.nautilus
    )
    fakes.nautilus_bars = HOURLY_BARS

    assert main(_pipeline(root, "--strict-hl-only", "--train-model")) == 0
    capsys.readouterr()
    assert venues.calls == ["hl"]
    assert not (root / "cache" / f"{CORE_KEY}.parquet").exists()
    manifest = _manifest(root)
    window = manifest["window"]
    assert window["cache_key"] == STRICT_KEY
    assert Path(window["cache_path"]).is_file()
    assert Path(window["cache_path"]).name == f"{STRICT_KEY}.parquet"
    [replay] = fakes.calls["nautilus"]
    assert set(replay["ohlcv"]["source"]) == {"hl"}
    assert len(replay["ohlcv"]) == window["bars"]
    parity = manifest["parity"]
    assert {"start", "end"} <= set(parity["compared_fields"])
    assert parity["window_mismatch"] is False
    assert _stage(manifest, "model")["status"] in ("ok", "skipped")


def test_strict_pipeline_ignores_an_older_mixed_default_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fresh backfilled default entry must never feed the Nautilus or model stage."""
    root = tmp_path / "data"
    _seed(monkeypatch, root, _mixed(_now()), at=_now())
    Venues(monkeypatch, _hourly(_now()))
    fakes = Fakes()
    fakes.nautilus_bars = HOURLY_BARS
    monkeypatch.setattr(
        "hypervector.nautilus.config_stub.phase2_check_report", fakes.check
    )
    monkeypatch.setattr(
        "hypervector.nautilus.runner.run_phase2_backtest", fakes.nautilus
    )
    seen: list[dict[str, Any]] = []
    from hypervector.commands import model as model_commands

    real_train = model_commands.train_metalabel_bundle

    def spy_train(**kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs)
        return real_train(**kwargs)

    monkeypatch.setattr(model_commands, "train_metalabel_bundle", spy_train)

    assert main(_pipeline(root, "--strict-hl-only", "--train-model")) == 0
    capsys.readouterr()
    manifest = _manifest(root)
    assert manifest["window"]["sources"] == {"hl": HOURLY_BARS}
    assert manifest["window"]["cache_key"] == STRICT_KEY
    [replay] = fakes.calls["nautilus"]
    assert set(replay["ohlcv"]["source"]) == {"hl"}
    [train] = seen
    assert set(train["ohlcv"]["source"]) == {"hl"}


def test_nautilus_replay_defaults_to_the_bundles_strict_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A strict bundle replayed alone reads the _hlonly key, never the mixed default."""
    from hypervector.nautilus.runner import _resolve_ohlcv

    root = tmp_path / "data"
    _seed(monkeypatch, root, _mixed(_now()), at=_now())
    Venues(monkeypatch, _hourly(_now()))
    strict = SimpleNamespace(
        symbol="BTC",
        timeframe="1h",
        meta={"data_provenance": {"strict_hl_only": True}},
    )
    with pytest.raises(FileNotFoundError, match=STRICT_KEY):
        _resolve_ohlcv(
            ohlcv=None,
            data_root=root,
            loadout=strict,
            lookback_days=LOOKBACK,
            allow_network=False,
        )
    _seed(monkeypatch, root, _hourly(_now()), at=_now(), strict=True)
    frame = _resolve_ohlcv(
        ohlcv=None, data_root=root, loadout=strict, lookback_days=LOOKBACK,
        allow_network=False,
    )
    assert set(frame["source"]) == {"hl"}
    loose = SimpleNamespace(symbol="BTC", timeframe="1h", meta={})
    frame = _resolve_ohlcv(
        ohlcv=None, data_root=root, loadout=loose, lookback_days=LOOKBACK,
        allow_network=False,
    )
    assert "binance" in set(frame["source"])


def test_model_training_forwards_the_cache_policy_and_the_bundles_strict_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hypervector.commands.model import train_metalabel_bundle
    from hypervector.export.phase2 import export_candidate
    import hypervector.ml.walk_forward as walk_forward

    root = tmp_path / "data"
    bundle = strict_bundle(root / "exports", "loose", timeframe="1h")
    meta_path = bundle / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["data_provenance"]["strict_hl_only"] = True
    strict = export_candidate(
        root / "exports",
        run_id="run-strict",
        meta=meta,
        params={"strategy": "test_sma_cross_long", "role": "uptrend"},
        metrics={"net_pnl": -5.0, "trade_count": 2},
        candidate_id="strict",
        strict=True,
    )
    loads: list[dict[str, Any]] = []

    class Stop(Exception):
        pass

    def spy(_root: object, **kwargs: Any) -> None:
        loads.append(kwargs)
        raise Stop

    monkeypatch.setattr(walk_forward, "load_research_history", spy)
    for export, allow in ((strict, False), (bundle, True)):
        with pytest.raises(Stop):
            train_metalabel_bundle(
                export_dir=export, data_root=root, allow_network=allow
            )
    assert [(c["strict_hl_only"], c["allow_network"]) for c in loads] == [
        (True, False),
        (False, True),
    ]


# --- paper warm-up: a CEX outage never blocks an HL-only warm-up --------------------------


def _paper_start(tmp_path: Path, root: Path, now: pd.Timestamp) -> Any:
    from hypervector.paper.runner import start_paper_daemon

    export = write_strict_export(tmp_path, timeframe="1h")
    return start_paper_daemon(
        export_dir=export,
        data_root=root,
        execution_mode="paper",
        max_live_bars=0,
        poll_fn=lambda **_kwargs: pd.DataFrame(),
        poll_interval_secs=0.0,
        sleep_fn=lambda _s: None,
        install_signal_handlers=False,
        lookback_days=LOOKBACK,
        enforce_live_boundary=False,
        enable_funding_refresh=False,
        warm_tail_fn=lambda *_a, **_k: _hourly(now, n=5),
        now_fn=lambda: now,
    )


def test_paper_start_survives_a_binance_outage_with_a_stale_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    now = _now()
    old = now - pd.Timedelta(days=2)
    _seed(monkeypatch, root, _hourly(old), at=old)
    venues = Venues(monkeypatch, _hourly(now))
    venues.binance = RuntimeError("no Binance kline endpoint available: HTTP 503")

    result = _paper_start(tmp_path, root, now)
    assert result.warm_bars > 0
    assert "bybit" not in venues.calls
    # The HL bars the failed refresh kept are newer than the stale cache.
    assert pd.Timestamp(result.warmup_provenance["cache_last_open"]) == now


def test_paper_start_survives_a_binance_outage_without_a_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The HL bars the failed load kept are enough to warm up."""
    root = tmp_path / "data"
    now = _now()
    venues = Venues(monkeypatch, _hourly(now))
    venues.binance = RuntimeError("no Binance kline endpoint available: HTTP 503")

    result = _paper_start(tmp_path, root, now)
    assert result.warm_bars > 0
    assert venues.calls == ["hl", "binance"]


def test_kept_hl_only_note_does_not_promise_a_flag_to_every_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venues = Venues(monkeypatch, _hourly(_now()))
    venues.binance = RuntimeError("HTTP 503")
    with pytest.raises(RuntimeError) as caught:
        history.load_research_history(
            tmp_path / "data", symbol="BTC", timeframe="1h", lookback_days=LOOKBACK
        )
    [note] = caught.value.__notes__
    assert STRICT_KEY in note
    assert "pass --strict-hl-only" not in note
    assert "commands that offer --strict-hl-only" in note


def test_warmup_docstring_no_longer_claims_the_cache_is_served_however_old() -> None:
    import hypervector.paper.warmup as warmup

    assert "however old it is" not in (warmup.__doc__ or "")


# --- data history --strict-hl-only: the artifact names the served file --------------------


def test_strict_history_artifact_path_is_the_served_cache_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "data"
    _seed(monkeypatch, root, _hourly(_now()), at=_now(), strict=True)
    venues = Venues(monkeypatch, _hourly(_now()))
    argv = ["--data-root", str(root), "data", "history", "--symbol", "BTC"]
    argv += ["--timeframe", "1h", "--lookback-days", str(LOOKBACK), "--strict-hl-only"]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert venues.calls == []
    dataset = out["artifacts"]["dataset"]
    assert dataset["cache_path"] == str(Path(out["provenance"]["cache_path"]).resolve())
    assert dataset["cache_path"].endswith(f"{STRICT_KEY}.parquet")
    assert Path(dataset["cache_path"]).is_file()


# --- book-align: empty or one-sided snapshots are not invented microstructure -------------


def _book_rows(tmp_path: Path) -> Path:
    from hypervector.data.book_record import snapshot_to_row
    from hypervector.paper.book import BookLevel, BookSnapshot

    base = 1_784_992_000_000.0
    bids = (BookLevel(100.0, 2.0), BookLevel(99.0, 1.0))
    asks = (BookLevel(101.0, 1.0), BookLevel(102.0, 3.0))
    books = [
        (bids, asks),  # full book
        (bids, ()),  # bids only
        ((), ()),  # no levels at all
        ((), asks),  # asks only
    ]
    path = tmp_path / "book.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for index, (bid_levels, ask_levels) in enumerate(books):
            snapshot = BookSnapshot(
                symbol="BTC",
                bids=bid_levels,
                asks=ask_levels,
                ts_recv_ms=base + index * 60_000 + 10,
                ts_exchange_ms=base + index * 60_000,
                source="hl_rest_l2",
            )
            row = snapshot_to_row(snapshot, depth_levels=20, run_id="r")
            handle.write(json.dumps(row) + "\n")
    return path


def test_one_sided_and_empty_snapshots_carry_nan_not_neutral_values(
    tmp_path: Path,
) -> None:
    from hypervector.data.book_align import load_l2_jsonl

    book = load_l2_jsonl(_book_rows(tmp_path))
    # The snapshot with no levels holds no observation and is dropped.
    assert len(book) == 3
    full, bids_only, asks_only = (book.iloc[i] for i in range(3))
    assert full["spread_bps"] > 0 and full["book_depth_ratio"] == pytest.approx(1.5 / 2)
    for row in (bids_only, asks_only):
        assert pd.isna(row["spread_bps"])
        assert pd.isna(row["mid"])
        assert pd.isna(row["micro_price_delta_bps"])
    assert pd.isna(bids_only["book_depth_ratio"])
    assert asks_only["book_depth_ratio"] == 0.0
    assert bids_only["obi_5"] == 1.0 and asks_only["obi_5"] == -1.0


def test_empty_snapshot_bar_is_unmatched_coverage(tmp_path: Path) -> None:
    from hypervector.data.book_align import (
        align_orderbook_to_ohlcv,
        book_coverage_summary,
        load_l2_jsonl,
    )

    book = load_l2_jsonl(_book_rows(tmp_path))
    stamps = pd.to_datetime(
        [1_784_992_000_000 + i * 60_000 for i in range(4)], unit="ms", utc=True
    )
    bars = pd.DataFrame({"timestamp": stamps, "close": [100.0] * 4})
    aligned = align_orderbook_to_ohlcv(bars, book, max_tolerance_ms=30_000)
    assert aligned["book_available"].tolist() == [True, True, False, True]
    assert pd.isna(aligned["spread_bps"].iloc[1])
    summary = book_coverage_summary(aligned, max_tolerance_ms=30_000)
    assert summary["matched_bars"] == 3 and summary["warnings"]


def test_book_gate_cannot_pass_an_unobserved_spread_as_zero(tmp_path: Path) -> None:
    from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl

    book = load_l2_jsonl(_book_rows(tmp_path))
    stamps = pd.to_datetime(
        [1_784_992_000_000 + i * 60_000 for i in range(4)], unit="ms", utc=True
    )
    bars = pd.DataFrame({"timestamp": stamps, "close": [100.0] * 4})
    aligned = align_orderbook_to_ohlcv(bars, book, max_tolerance_ms=30_000)
    assert not (aligned["spread_bps"] == 0.0).any()
    assert not (aligned["book_depth_ratio"] == 1.0).iloc[1:3].any()


# --- archive liquidation-fetch: core markets only ----------------------------------------


def test_liquidation_request_refuses_a_hip3_symbol() -> None:
    from hypervector.data.oxa_liquidations import OxaLiquidationRequest

    start = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    end = datetime(2026, 8, 21, 12, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="uppercase Hyperliquid asset"):
        OxaLiquidationRequest(symbol="xyz:TSLA", start=start, end=end)
    assert OxaLiquidationRequest(symbol="kPEPE", start=start, end=end).symbol == "kPEPE"


def test_liquidation_fetch_help_does_not_advertise_hip3() -> None:
    from hypervector.commands.registry import spec_for

    spec = spec_for("archive liquidation-fetch")
    [symbol] = [arg for arg in spec["arguments"] if arg["flags"] == ["--symbol"]]
    text = symbol["options"]["help"]
    assert "or deployer:asset (HIP-3)" not in text
    assert "core" in text and "not supported" in text


def test_liquidation_fetch_cli_refuses_hip3_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OXA_API_KEY", "test-key-not-real")
    argv = ["--data-root", str(tmp_path), "archive", "liquidation-fetch"]
    argv += ["--symbol", "xyz:TSLA", "--start", "2026-08-21T12:00:00Z"]
    argv += ["--end", "2026-08-21T12:01:00Z"]
    assert main(argv) != 0
    err = capsys.readouterr().err
    assert "uppercase Hyperliquid asset" in err
    assert not (tmp_path / "cache" / "vendor").exists()
