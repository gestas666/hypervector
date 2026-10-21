"""Final CLI review findings, one regression test (or more) each (offline, tmp roots).

1. ``pipeline run --no-network``: the tune search and the model stage never
   refresh a stale cache over the network; later stages reuse the pinned window.
2. ``--strict-hl-only`` reaches every pipeline stage and the ``data history``
   artifact names the cache the loader served.
3. Usage refusals exit 2 (``live run`` without authority, ``tune strategy
   --n-trials 0``).
4. Handler error paths emit ``{"ok": false, "command", "error_type", "error"}``.
5. ``latest``/``export list`` skip ``.staging-*`` dirs; a trailing slash on a
   candidate id resolves.
6. ``paper report``/``live report`` on a missing decisions file exit 1.
7. Help shows the data-relative defaults.
8. ``artifacts.validation`` is one object shape across stage commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.data import pipeline as data_pipeline
from hypervector.data.cache import ParquetCache
from hypervector.data.sources import fixture_ohlcv
from tests.test_cli_pipeline import Fakes, strict_bundle

TF = "1h"
LOOKBACK = 30
BARS_1H = LOOKBACK * 24


# --- shared helpers --------------------------------------------------------------------


def _seed_cache(
    root: Path, *, days_old: float, strict: bool = False, source: str = "hl"
) -> Path:
    """A research-history cache whose last bar is ``days_old`` days old."""
    end = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(days=days_old)
    start = end - pd.Timedelta(hours=BARS_1H - 1)
    frame = fixture_ohlcv(
        n_bars=BARS_1H,
        start=start.isoformat(),
        freq="1h",
        drift=20.0,
        wave_period=30,
        source=source,
    )
    metadata = {
        "origin": data_pipeline.CACHE_ORIGIN,
        "fetched_at": end.isoformat(),
        "symbol": "BTC",
        "timeframe": TF,
        "lookback_days": LOOKBACK,
        "strict_hl_only": strict,
        "backfill": {},
    }
    key = data_pipeline.cache_key("BTC", TF, LOOKBACK, strict_hl_only=strict)
    return ParquetCache(root / "cache").save(key, frame, metadata=metadata)


@pytest.fixture
def fetches(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    """Every network fetch the history loader attempts (each one fails)."""
    calls: list[tuple[str, str, int]] = []

    def refuse(_cache: object, request: Any) -> None:
        calls.append((request.symbol, request.timeframe, request.lookback_days))
        raise RuntimeError("NETWORK FETCH ATTEMPTED")

    monkeypatch.setattr(data_pipeline, "_fetch", refuse)
    return calls


@pytest.fixture
def engines(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Fake Nautilus and model engines; the real history loader stays in place."""
    doubles = Fakes()
    monkeypatch.setattr(
        "hypervector.nautilus.config_stub.phase2_check_report", doubles.check
    )
    monkeypatch.setattr(
        "hypervector.nautilus.runner.run_phase2_backtest", doubles.nautilus
    )
    monkeypatch.setattr(
        "hypervector.commands.model.train_metalabel_bundle", doubles.model
    )
    return doubles


def _pipeline(data: Path, *extra: str) -> list[str]:
    return [
        "--data-root",
        str(data),
        "pipeline",
        "run",
        "--strategy",
        "test_sma_cross_long",
        "--timeframe",
        TF,
        "--lookback-days",
        str(LOOKBACK),
        *extra,
    ]


def _stages(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["stage"]: stage for stage in manifest["stages"]}


def _manifest(data: Path) -> dict[str, Any]:
    [path] = sorted((data / "runs" / "pipeline").glob("*/pipeline.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def _error(text: str) -> dict[str, Any]:
    """The single JSON error document a handler printed on stderr."""
    try:
        document = json.loads(text)
    except ValueError:
        lines = [line for line in text.strip().splitlines() if line.strip()]
        document = json.loads(lines[-1])
    assert document["ok"] is False
    for key in ("command", "error_type", "error"):
        assert document.get(key), (key, document)
    return document


# --- 1. --no-network never refreshes a stale cache ------------------------------------


def test_no_network_tune_search_serves_the_stale_cache_without_fetching(
    tmp_path: Path, fetches: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _seed_cache(data, days_old=3)
    argv = _pipeline(data, "--no-network", "--n-trials", "1", "--no-nautilus")
    assert main(argv) == 0, capsys.readouterr().err
    manifest = json.loads(capsys.readouterr().out)
    assert fetches == []
    assert _stages(manifest)["search"]["status"] == "ok"
    assert manifest["window"]["bars"] == BARS_1H


def test_tune_stage_is_pinned_and_offline_and_records_pin_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tests.test_cli_pipeline import install

    doubles = Fakes()
    install(monkeypatch.setattr, doubles)
    data = tmp_path / "data"
    assert main(_pipeline(data, "--no-nautilus")) == 0
    manifest = json.loads(capsys.readouterr().out)
    [tune] = doubles.calls["tune"]
    assert tune["pin_cache"] is True and tune["allow_network"] is False
    assert tune["force_refresh"] is False
    assert _stages(manifest)["search"]["argv"][-1] == "--pin-cache"


def test_run_autotune_offline_load_serves_stale_and_fails_on_a_miss(
    tmp_path: Path, fetches: list[Any]
) -> None:
    from hypervector.sweep import autotune
    from hypervector.sweep.autotune_models import SearchSettings

    def settings(root: Path) -> SearchSettings:
        return SearchSettings(
            root=root,
            strategy_name="test_sma_cross_long",
            symbol="BTC",
            timeframe=TF,
            lookback_days=LOOKBACK,
            n_trials=1,
            fee_model="hl_base_taker",
            book_data_path=None,
            sampler="karpathy",
            no_export=True,
            strict_hl_only=False,
            force_refresh=False,
            allow_network=False,
        )

    stale = tmp_path / "stale"
    _seed_cache(stale, days_old=3)
    bars, provenance = autotune._load_inputs(settings(stale))
    assert len(bars) == BARS_1H and provenance["stale"] is True
    with pytest.raises(FileNotFoundError, match="offline history cache missing"):
        autotune._load_inputs(settings(tmp_path / "empty"))
    assert fetches == []
    with pytest.raises(ValueError, match="force_refresh"):
        autotune.run_autotune(
            data_root=tmp_path, force_refresh=True, allow_network=False
        )


def test_no_network_model_stage_trains_on_the_pinned_window(
    tmp_path: Path,
    fetches: list[Any],
    engines: Fakes,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    _seed_cache(data, days_old=3)
    argv = _pipeline(
        data, "--no-network", "--search", "sweep", "--train-model", "--no-nautilus"
    )
    assert main(argv) == 0, capsys.readouterr().err
    manifest = json.loads(capsys.readouterr().out)
    assert fetches == []
    assert _stages(manifest)["model"]["status"] == "ok"
    [model] = engines.calls["model"]
    assert len(model["ohlcv"]) == BARS_1H
    assert model["ohlcv_provenance"]["cache_key"] == "BTC_1h_30d"


def test_model_stage_from_an_export_reads_a_stale_cache_offline(
    tmp_path: Path,
    fetches: list[Any],
    engines: Fakes,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand", timeframe=TF, lookback_days=LOOKBACK)
    _seed_cache(data, days_old=3)
    flags = ["--export", "cand", "--no-network", "--train-model", "--no-nautilus"]
    argv = [
        "--data-root",
        str(data),
        "pipeline",
        "run",
        "--strategy",
        "test_sma_cross_long",
        *flags,
    ]
    assert main(argv) == 0, capsys.readouterr().err
    assert fetches == []
    [model] = engines.calls["model"]
    assert len(model["ohlcv"]) == BARS_1H


# --- 2. --strict-hl-only reaches every stage --------------------------------------------


def test_strict_pipeline_uses_the_hl_only_cache_in_every_stage(
    tmp_path: Path,
    fetches: list[Any],
    engines: Fakes,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    served = _seed_cache(data, days_old=0, strict=True)
    argv = _pipeline(
        data, "--strict-hl-only", "--no-network", "--search", "sweep", "--train-model"
    )
    assert main(argv) == 0, capsys.readouterr().err
    manifest = json.loads(capsys.readouterr().out)
    assert fetches == []
    assert sorted(p.name for p in (data / "cache").glob("*.parquet")) == [served.name]
    window = manifest["window"]
    assert window["cache_key"] == "BTC_1h_30d_hlonly"
    assert window["cache_path"] == str(served.resolve())
    [replay] = engines.calls["nautilus"]
    assert len(replay["ohlcv"]) == BARS_1H and replay["allow_network"] is False
    [model] = engines.calls["model"]
    assert len(model["ohlcv"]) == BARS_1H
    assert {s["status"] for s in manifest["stages"]} == {"ok"}


def test_strict_pipeline_from_an_export_reads_the_hl_only_cache(
    tmp_path: Path,
    fetches: list[Any],
    engines: Fakes,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand", timeframe=TF, lookback_days=LOOKBACK)
    _seed_cache(data, days_old=0, strict=True)
    argv = [
        "--data-root",
        str(data),
        "pipeline",
        "run",
        "--strategy",
        "test_sma_cross_long",
        "--export",
        "cand",
        "--strict-hl-only",
        "--no-network",
        "--train-model",
    ]
    assert main(argv) == 0, capsys.readouterr().err
    assert fetches == []
    [replay] = engines.calls["nautilus"]
    assert len(replay["ohlcv"]) == BARS_1H
    [model] = engines.calls["model"]
    assert model["ohlcv_provenance"]["cache_key"] == "BTC_1h_30d_hlonly"


def test_data_history_strict_names_the_cache_the_loader_served(
    tmp_path: Path, fetches: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    served = _seed_cache(data, days_old=0, strict=True)
    argv = ["--data-root", str(data), "data", "history", "--symbol", "BTC"]
    argv += ["--timeframe", TF, "--lookback-days", str(LOOKBACK)]
    assert main([*argv, "--strict-hl-only", "--pin-cache"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert fetches == []
    dataset = out["artifacts"]["dataset"]
    assert dataset["cache_path"] == str(served.resolve())
    assert Path(dataset["cache_path"]).is_file()
    assert Path(out["provenance"]["cache_path"]).resolve() == served.resolve()


# --- 3. usage refusals exit 2 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("flags", "secrets", "needle"),
    [
        ([], True, "--i-accept-live-risk"),
        (["--i-accept-live-risk"], True, "--enabled"),
        (["--enabled", "--i-accept-live-risk"], False, "HYPERVECTOR_HL_WALLET_ADDRESS"),
    ],
)
def test_live_run_without_authority_is_a_json_refusal_exit_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: list[str],
    secrets: bool,
    needle: str,
) -> None:
    def never(**_kwargs: object) -> None:
        raise AssertionError("live daemon started")

    monkeypatch.setattr("hypervector.live.runner.start_live_daemon", never)
    if secrets:
        monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
        monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    else:
        monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
        monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    export = tmp_path / "bundle"
    export.mkdir()
    data = tmp_path / "data"
    argv = ["--data-root", str(data), "live", "run", "--export", str(export), *flags]
    assert main(argv) == 2
    captured = capsys.readouterr()
    error = _error(captured.err)
    assert (error["command"], error["error_type"]) == ("live run", "CommandRefused")
    assert needle in error["error"]
    assert "sekrit" not in captured.err + captured.out
    assert not data.exists()


def test_live_run_missing_export_is_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unresolvable bundle is refused (exit 2) before credentials or clients."""
    argv = ["--data-root", str(tmp_path / "data"), "live", "run"]
    authority = ["--enabled", "--i-accept-live-risk"]
    assert main([*argv, "--export", str(tmp_path / "absent"), *authority]) == 2
    error = _error(capsys.readouterr().err)
    assert error["error_type"] == "CommandRefused"
    assert "absent" in error["error"]


def test_tune_strategy_zero_trials_is_refused_before_any_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "hypervector.sweep.autotune.load_research_history",
        lambda *_a, **_k: pytest.fail("history read before the n-trials check"),
    )
    data = tmp_path / "data"
    argv = ["--data-root", str(data), "tune", "strategy"]
    assert main([*argv, "--strategy", "test_sma_cross_long", "--n-trials", "0"]) == 2
    error = _error(capsys.readouterr().err)
    assert error["error_type"] == "CommandRefused"
    assert "--n-trials" in error["error"]
    assert not data.exists()


# --- 4. one error document shape -----------------------------------------------------------


def _write_garbage(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a database at all" * 64)
    return path


def test_in_process_refusals_and_failures_emit_the_shared_error_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # ./data under tmp_path: 'live request' refuses an explicit --data-root.
    monkeypatch.chdir(tmp_path)
    request = ["live", "request", "--inbox", str(tmp_path / "inbox"), "--run-id", "r1"]
    request += ["--profile-fingerprint", "f" * 8, "--symbol", "BTC"]
    request += ["--action", "manual_close"]
    paper_ledger = tmp_path / "paper" / "d.jsonl"
    live_ledger = tmp_path / "live" / "d.jsonl"
    for ledger in (paper_ledger, live_ledger):
        ledger.parent.mkdir(parents=True)
        ledger.write_text("", encoding="utf-8")
    cases: list[tuple[list[str], int, str]] = [
        (["live", "monitor", "--config", str(tmp_path / "nope.toml")], 2, "live monitor"),
        (
            ["live", "monitor", "--config", "x.toml", "--interval-seconds", "0"],
            2,
            "live monitor",
        ),
        ([*request, "--settings", str(tmp_path / "s.json")], 2, "live request"),
        ([*request, "--submit"], 2, "live request"),
        (["live", "report", "--decisions", str(paper_ledger)], 1, "live report"),
        (["paper", "report", "--decisions", str(live_ledger)], 1, "paper report"),
    ]
    for words, code, command in cases:
        assert main(words) == code, words
        captured = capsys.readouterr()
        error = _error(captured.err)
        assert error["command"] == command, words
        assert captured.out == "", words


def test_paper_run_refusals_are_command_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hypervector.commands import paper

    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand")
    argv = ["--data-root", str(data), "paper", "run", "--export", "cand"]

    def conflicting(*_a: object, **_k: object) -> None:
        raise paper.PaperArgumentsError("conflicting options")

    monkeypatch.setattr(paper, "_paper_options", conflicting)
    assert main(argv) == 2
    error = _error(capsys.readouterr().err)
    assert (error["command"], error["error_type"]) == ("paper run", "CommandRefused")


def test_research_database_failures_name_the_command_and_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    garbage = _write_garbage(data / "research" / "market.duckdb")
    root = ["--data-root", str(data)]
    assert main([*root, "db", "status"]) == 1
    error = _error(capsys.readouterr().err)
    assert error["command"] == "db status"

    assert main([*root, "db", "status", "--database", str(tmp_path / "none.duckdb")]) == 1
    error = _error(capsys.readouterr().err)
    assert error["error_type"] == "FileNotFoundError"

    hip3 = ["db", "hip3-liquidity", "--symbol", "xyz:TSLA", "--database", str(garbage)]
    assert main([*root, *hip3]) == 1
    assert _error(capsys.readouterr().err)["command"] == "db hip3-liquidity"


def test_book_record_failure_names_the_command_and_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def offline(*_a: object, **_k: object) -> None:
        raise ConnectionError("venue unreachable")

    monkeypatch.setattr("hypervector.data.book_record.append_snapshot", offline)
    monkeypatch.setattr("hypervector.data.book_record.run_book_recorder", offline)
    root = ["--data-root", str(tmp_path / "data"), "data", "book-record"]
    assert main([*root, "--once"]) == 1
    error = _error(capsys.readouterr().err)
    assert (error["command"], error["error_type"]) == ("data book-record", "ConnectionError")
    assert main([*root, "--max-snapshots", "1"]) == 1
    assert _error(capsys.readouterr().err)["command"] == "data book-record"


def test_oxa_and_research_failure_helpers_carry_command_and_type(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import argparse

    from hypervector import cli_oxa, cli_research_support

    args = argparse.Namespace(command="archive candle-fetch")
    assert cli_oxa._print_failure(ValueError("bad window"), args, extra=1) == 1
    error = _error(capsys.readouterr().err)
    assert (error["command"], error["error_type"], error["extra"]) == (
        "archive candle-fetch",
        "ValueError",
        1,
    )
    args = argparse.Namespace(command="db paper-trades")
    assert cli_research_support.print_failure(OSError("gone"), args) == 1
    error = _error(capsys.readouterr().err)
    assert (error["command"], error["error_type"]) == ("db paper-trades", "OSError")


def test_paper_audit_missing_ledger_is_one_json_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hypervector.operations import multi_asset_bidirectional_observer_audit as audit

    missing = tmp_path / "paper" / "cohort" / "decisions.jsonl"
    code = audit.main(["--decisions", str(missing), "--out", str(tmp_path / "a.json")])
    assert code == 1
    error = _error(capsys.readouterr().err)
    assert (error["command"], error["error_type"]) == ("paper audit", "FileNotFoundError")
    assert "live" not in error["error"].split(":")[0]
    assert not (tmp_path / "a.json").exists()


# --- 5. bundle resolver edge cases ----------------------------------------------------------


def test_latest_and_list_skip_staging_dirs_and_trailing_slash_resolves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hypervector.commands.exports import list_exports, resolve_export

    data = tmp_path / "data"
    older = strict_bundle(data / "exports", "export_uptrend_1")
    staging = strict_bundle(data / "exports", ".staging-abc123")
    meta = json.loads((staging / "meta.json").read_text(encoding="utf-8"))
    meta["created_at_utc"] = "2999-01-01T00:00:00Z"
    (staging / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    assert resolve_export("latest", data) == older.resolve()
    assert [e["candidate_id"] for e in list_exports(data)] == ["export_uptrend_1"]
    monkeypatch.chdir(tmp_path)
    assert resolve_export("export_uptrend_1/", data) == older.resolve()
    assert main(["--data-root", str(data), "export", "list"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 1


# --- 6. a missing decisions file exits 1 -----------------------------------------------------


@pytest.mark.parametrize("group", ["paper", "live"])
def test_report_on_a_missing_decisions_file_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], group: str
) -> None:
    data = tmp_path / "data"
    typo = tmp_path / group / "typo.jsonl"
    assert main(["--data-root", str(data), group, "report", "--decisions", str(typo)]) == 1
    error = _error(capsys.readouterr().err)
    assert error["command"] == f"{group} report" and str(typo) in error["error"]
    assert main(["--data-root", str(data), group, "report"]) == 1
    error = _error(capsys.readouterr().err)
    assert "decisions.jsonl" in error["error"]

    typo.parent.mkdir(parents=True, exist_ok=True)
    typo.write_text("", encoding="utf-8")
    assert main(["--data-root", str(data), group, "report", "--decisions", str(typo)]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 0


# --- 7. help shows data-relative defaults -----------------------------------------------------


def test_help_states_data_relative_defaults(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as done:
        main(["paper", "checkpoint", "--help"])
    assert done.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "(default: DATA_ROOT/paper/cohort/decisions.jsonl)" in text
    assert "(default: DATA_ROOT/runtime/cohort_observer/latest_checkpoint.json)" in text


def test_every_data_default_argument_names_its_path_in_help() -> None:
    import argparse

    from hypervector.commands.registry import (
        CLI_COMMANDS,
        _argparse_options,
        iter_arguments,
        spec_for,
    )

    seen = 0
    for command in CLI_COMMANDS:
        for argument in iter_arguments(spec_for(command)):
            relative = argument.get("data_default")
            if not relative or argument.get("hidden"):
                continue
            seen += 1
            text = _argparse_options(argument)["help"]
            assert text is not argparse.SUPPRESS
            assert f"DATA_ROOT/{relative}" in text, (command, argument["flags"])
    assert seen >= 20


# --- 8. one artifacts.validation shape ----------------------------------------------------------


def test_nautilus_run_and_export_validate_share_the_validation_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    doubles = Fakes()
    monkeypatch.setattr(
        "hypervector.nautilus.runner.run_phase2_backtest", doubles.nautilus
    )
    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand")
    root = ["--data-root", str(data)]
    assert main([*root, "nautilus", "run", "--export", "cand", "--no-network"]) == 0
    nautilus = json.loads(capsys.readouterr().out)["artifacts"]["validation"]
    assert main([*root, "export", "validate", "--export", "cand"]) == 0
    export = json.loads(capsys.readouterr().out)["artifacts"]["validation"]
    assert isinstance(nautilus, dict) and isinstance(export, dict)
    assert nautilus["valid"] is True and nautilus["strict"] is True
    assert nautilus["report_path"].endswith("summary.json")
    assert export == {"strict": True, "valid": True}
    assert set(export) <= set(nautilus)
