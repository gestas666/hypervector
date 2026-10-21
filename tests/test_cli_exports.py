"""Bundle references, export inventory and stored-trial selection (commands/exports.py)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import hypervector
from hypervector.cli import main
from hypervector.commands.common import CommandRefused
from hypervector.commands.exports import (
    explain_no_export_trial,
    resolve_export,
    resolve_metalabel_bundle,
    select_export_trial,
)
from hypervector.runs.db import RunsDB, TrialRow

HEAVY = ("pandas", "numpy", "vectorbt", "nautilus_trader", "duckdb", "talib")
EXITS = {
    "mode": "atr",
    "sl_pct": 0.01,
    "rr": 2.0,
    "atr_length": 14,
    "sl_atr_mult": 1.5,
    "trail_atr_mult": 2.0,
}
COSTS = {"taker_fee": 0.00045, "slippage_bps": 2.0}
RISK = {"risk_pct_min": 0.01, "risk_pct_max": 0.05}


def _bundle(
    exports: Path,
    name: str,
    *,
    created: str | None = "2026-10-01T00:00:00+00:00",
    strict: bool = True,
    strategy: str = "test_sma_cross_long",
    symbol: str = "BTC",
    timeframe: str = "1m",
) -> Path:
    """A strategy bundle written with the standard library only."""
    path = exports / name
    path.mkdir(parents=True)
    meta: dict[str, object] = {
        "schema_version": "1",
        "run_id": f"run-{name}",
        "package_version": "test",
        "symbol": symbol,
        "timeframe": timeframe,
        "track": "uptrend",
        "strategy": strategy,
    }
    if created is not None:
        meta["created_at_utc"] = created
    if strict:
        meta.update(
            init_cash=10_000.0, costs=COSTS, risk=RISK, tp_sl_mode="atr", exits=EXITS
        )
    (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (path / "params.json").write_text(
        json.dumps({"strategy": strategy, "fast": 5}), encoding="utf-8"
    )
    (path / "metrics.json").write_text(
        json.dumps({"net_pnl": -12.5, "trade_count": 4}), encoding="utf-8"
    )
    return path


def _model_bundle(path: Path, *, mtime: float | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "metalabel_lgbm.txt").write_text("tree\n", encoding="utf-8")
    (path / "metalabel_metadata.json").write_text(
        json.dumps({"feature_names": ["close"]}), encoding="utf-8"
    )
    if mtime is not None:
        os.utime(path / "metalabel_lgbm.txt", (mtime, mtime))
    return path


# --- resolve_export ---------------------------------------------------------------


def test_resolve_export_accepts_absolute_and_cwd_relative_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(tmp_path / "elsewhere", "b1")
    assert resolve_export(bundle, tmp_path / "data") == bundle.resolve()
    monkeypatch.chdir(tmp_path)
    assert resolve_export("elsewhere/b1", "data") == bundle.resolve()


def test_resolve_export_accepts_a_candidate_id_under_the_data_root(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    bundle = _bundle(data / "exports", "uptrend_test_sma_cross_long_abc")
    assert resolve_export("uptrend_test_sma_cross_long_abc", data) == bundle.resolve()


def test_latest_is_the_newest_strictly_valid_bundle(tmp_path: Path) -> None:
    exports = tmp_path / "data" / "exports"
    _bundle(exports, "old", created="2026-01-01T00:00:00Z")
    chosen = _bundle(exports, "mid", created="2026-06-01T00:00:00Z")
    _bundle(exports, "new_but_loose", created="2026-09-01T00:00:00Z", strict=False)
    assert resolve_export("latest", tmp_path / "data") == chosen.resolve()


def test_latest_falls_back_to_mtime_and_breaks_ties_by_name(tmp_path: Path) -> None:
    exports = tmp_path / "data" / "exports"
    first = _bundle(exports, "a_bundle", created=None)
    second = _bundle(exports, "b_bundle", created=None)
    for path in (first, second):
        os.utime(path, (1_700_000_000, 1_700_000_000))
    assert resolve_export("latest", tmp_path / "data") == second.resolve()
    os.utime(first, (1_800_000_000, 1_800_000_000))
    assert resolve_export("latest", tmp_path / "data") == first.resolve()


def test_unknown_reference_is_refused_naming_where_it_looked(tmp_path: Path) -> None:
    with pytest.raises(CommandRefused) as exc:
        resolve_export("nope", tmp_path / "data")
    message = str(exc.value)
    assert "'nope' not found" in message
    assert str(tmp_path / "data" / "exports" / "nope") in message
    with pytest.raises(CommandRefused, match="'latest'"):
        resolve_export("latest", tmp_path / "data")
    with pytest.raises(CommandRefused):
        resolve_export("../escape", tmp_path / "data")


def test_a_missing_reference_exits_two_through_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "export", "show", "--export", "x"]) == 2
    report = json.loads(capsys.readouterr().err)
    assert report["command"] == "export show"
    assert report["error_type"] == "CommandRefused"
    assert not data.exists()


# --- resolve_metalabel_bundle -----------------------------------------------------


def test_metalabel_bundle_resolves_directories_names_and_latest(tmp_path: Path) -> None:
    data = tmp_path / "data"
    models = data / "models" / "metalabel"
    older = _model_bundle(models / "wf_a_1", mtime=1_700_000_000)
    newer = _model_bundle(models / "wf_b_2", mtime=1_800_000_000)
    assert resolve_metalabel_bundle(older, data) == older.resolve()
    assert resolve_metalabel_bundle("wf_a_1", data) == older.resolve()
    assert resolve_metalabel_bundle("latest", data) == newer.resolve()


def test_installed_metalabel_root_counts_for_latest(tmp_path: Path) -> None:
    data = tmp_path / "data"
    installed = _model_bundle(data / "models" / "metalabel", mtime=1_900_000_000)
    _model_bundle(installed / "wf_old", mtime=1_700_000_000)
    assert resolve_metalabel_bundle("latest", data) == installed.resolve()


def test_metalabel_bundle_without_loader_files_is_refused(tmp_path: Path) -> None:
    incomplete = tmp_path / "model"
    incomplete.mkdir()
    (incomplete / "metalabel_lgbm.txt").write_text("tree\n", encoding="utf-8")
    with pytest.raises(CommandRefused, match="metalabel_metadata.json"):
        resolve_metalabel_bundle(incomplete, tmp_path / "data")
    with pytest.raises(CommandRefused, match="'latest'"):
        resolve_metalabel_bundle("latest", tmp_path / "data")


# --- export list / show -----------------------------------------------------------


def test_export_list_flags_invalid_bundles_newest_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _bundle(data / "exports", "valid_old", created="2026-01-01T00:00:00Z")
    _bundle(data / "exports", "loose_new", created="2026-05-01T00:00:00Z", strict=False)
    broken = data / "exports" / "broken"
    broken.mkdir()
    (broken / "meta.json").write_text("{not json", encoding="utf-8")
    os.utime(broken, (1_000_000_000, 1_000_000_000))

    assert main(["--data-root", str(data), "export", "list"]) == 0
    report = json.loads(capsys.readouterr().out)
    names = [entry["candidate_id"] for entry in report["exports"]]
    assert names == ["loose_new", "valid_old", "broken"]
    by_name = {entry["candidate_id"]: entry for entry in report["exports"]}
    assert by_name["valid_old"]["strict_valid"] is True
    assert by_name["valid_old"]["errors"] == []
    assert by_name["loose_new"]["strict_valid"] is False
    assert any("strict" in error for error in by_name["loose_new"]["errors"])
    assert by_name["broken"]["strict_valid"] is False and by_name["broken"]["errors"]
    assert report["invalid_count"] == 2
    assert set(by_name["valid_old"]) >= {
        "candidate_id",
        "export_dir",
        "strategy",
        "symbol",
        "timeframe",
        "created_at_utc",
        "strict_valid",
        "errors",
    }


def test_export_list_filters_and_never_creates_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    assert main(["--data-root", str(empty), "export", "list"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0
    assert not empty.exists()

    data = tmp_path / "data"
    _bundle(data / "exports", "btc", symbol="BTC", timeframe="5m")
    _bundle(data / "exports", "eth", symbol="ETH", timeframe="5m")
    _bundle(data / "exports", "short", strategy="test_sma_cross_short", symbol="ETH")
    argv = ["--data-root", str(data), "export", "list", "--symbol", "ETH"]
    assert main([*argv, "--timeframe", "5m"]) == 0
    assert [
        e["candidate_id"] for e in json.loads(capsys.readouterr().out)["exports"]
    ] == ["eth"]
    assert main([*argv, "--strategy", "test_sma_cross_short"]) == 0
    assert [
        e["candidate_id"] for e in json.loads(capsys.readouterr().out)["exports"]
    ] == ["short"]


def test_export_show_reports_contents_and_strict_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _bundle(data / "exports", "good")
    _bundle(data / "exports", "loose", strict=False)
    assert main(["--data-root", str(data), "export", "show", "--export", "good"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["export_dir"] == str((data / "exports" / "good").resolve())
    assert report["strict_valid"] is True
    assert report["meta"]["symbol"] == "BTC"
    assert report["params"]["strategy"] == "test_sma_cross_long"
    assert report["metrics"]["net_pnl"] == -12.5
    # Showing an invalid bundle still works; validity is reported, not gated.
    assert main(["--data-root", str(data), "export", "show", "--export", "loose"]) == 0
    loose = json.loads(capsys.readouterr().out)
    assert loose["strict_valid"] is False
    assert loose["validation"]["errors"]


@pytest.mark.parametrize(
    "argv", [["export", "list"], ["export", "show", "--export", "latest"]]
)
def test_inventory_commands_do_not_import_engines(
    tmp_path: Path, argv: list[str]
) -> None:
    data = tmp_path / "data"
    _bundle(data / "exports", "fixture")
    program = (
        "import sys\n"
        "from hypervector.cli import main\n"
        f"code = main(['--data-root', {str(data)!r}, *{argv!r}])\n"
        f"heavy = sorted(set({HEAVY!r}) & set(sys.modules))\n"
        "assert code == 0, code\n"
        "assert not heavy, heavy\n"
    )
    source_root = Path(hypervector.__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=60,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(source_root)},
        stdout=subprocess.DEVNULL,
    )


# --- export validate --------------------------------------------------------------


def test_export_validate_is_strict_by_default_and_loose_on_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _bundle(data / "exports", "loose", strict=False)
    base = ["--data-root", str(data), "export", "validate", "--export", "loose"]
    assert main(base) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and error["strict"] is True
    assert any("strict" in line for line in error["errors"])
    assert main([*base, "--loose"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["strict"] is False
    assert report["artifacts"]["validation"] == {"strict": False, "valid": True}


def test_export_validate_resolves_latest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    bundle = _bundle(data / "exports", "only")
    argv = ["--data-root", str(data), "export", "validate", "--export", "latest"]
    assert main(argv) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["export_dir"] == str(bundle.resolve())
    assert report["artifacts"]["export"] == str(bundle.resolve())


# --- select_export_trial ----------------------------------------------------------


def _row(
    trial_id: int,
    net_pnl: float,
    *,
    run_id: str = "r1",
    track: str = "uptrend",
    strategy: str = "test_sma_cross_long",
    symbol: str = "BTC",
    timeframe: str = "1m",
    apply_costs: bool = True,
    status: str = "ok",
    meta: bool = True,
) -> dict[str, object]:
    return {
        "id": trial_id,
        "run_id": run_id,
        "track": track,
        "strategy": strategy,
        "status": status,
        "net_pnl": net_pnl,
        "total_return_pct": net_pnl / 100,
        "research_meta": (
            {"symbol": symbol, "timeframe": timeframe, "apply_costs": apply_costs}
            if meta
            else None
        ),
    }


def test_selection_ranks_by_net_pnl_and_keeps_negative_results() -> None:
    rows = [_row(1, -50.0), _row(2, -10.0), _row(3, -30.0)]
    assert select_export_trial(rows)["id"] == 2


def test_selection_filters_by_every_given_field() -> None:
    rows = [
        _row(1, 90.0, symbol="ETH"),
        _row(2, 80.0, timeframe="5m"),
        _row(3, 70.0, run_id="r2"),
        _row(4, 60.0, track="downtrend", strategy="test_sma_cross_short"),
        _row(5, 50.0),
    ]
    assert select_export_trial(rows)["id"] == 1
    assert select_export_trial(rows, symbol="BTC")["id"] == 2
    assert select_export_trial(rows, symbol="BTC", timeframe="1m")["id"] == 3
    assert (
        select_export_trial(rows, run_id="r1", timeframe="1m", symbol="BTC")["id"] == 4
    )
    assert (
        select_export_trial(
            rows, track="uptrend", run_id="r1", timeframe="1m", symbol="BTC"
        )["id"]
        == 5
    )
    assert select_export_trial(rows, strategy="test_sma_cross_short")["id"] == 4
    assert select_export_trial(rows, symbol="SOL") is None


def test_selection_prefers_costed_trials_and_requires_research_meta() -> None:
    rows = [
        _row(1, 500.0, apply_costs=False),
        _row(2, 900.0, meta=False),
        _row(3, 999.0, status="error"),
        _row(4, 10.0),
    ]
    assert select_export_trial(rows)["id"] == 4
    assert select_export_trial(rows[:3])["id"] == 1


def test_no_selection_is_explained() -> None:
    assert "run 'backtest sweep'" in explain_no_export_trial([], {"track": "uptrend"})
    rows = [_row(1, 1.0, symbol="ETH")]
    assert "matches the filters (symbol=BTC)" in explain_no_export_trial(
        rows, {"symbol": "BTC", "track": None}
    )
    assert "research_meta" in explain_no_export_trial(
        [_row(1, 1.0, meta=False)], {"track": "uptrend"}
    )


# --- export create ----------------------------------------------------------------


def _store_trials(data: Path) -> None:
    def trial(run_id: str, symbol: str, pnl: float, timeframe: str = "1m") -> TrialRow:
        return TrialRow(
            run_id=run_id,
            track="uptrend",
            strategy="test_sma_cross_long",
            params={"fast": 5, "slow": 20},
            net_pnl=pnl,
            total_return_pct=pnl / 100,
            sharpe=0.1,
            trade_count=3,
            wins=1,
            losses=2,
            win_pct=33.3,
            max_drawdown=5.0,
            research_meta={
                "symbol": symbol,
                "timeframe": timeframe,
                "lookback_days": 30,
                "init_cash": 10_000.0,
                "tp_sl_mode": "atr",
                "exits": EXITS,
                "risk": RISK,
                "costs": COSTS,
                "apply_costs": True,
                "fee_model": "hl_base_taker",
            },
        )

    database = RunsDB(data / "runs" / "hypervector.db")
    try:
        database.insert_trials(
            [
                trial("btc-run", "BTC", 120.0),
                trial("btc-run", "BTC", -40.0),
                trial("eth-run", "ETH", 300.0, timeframe="15m"),
            ]
        )
    finally:
        database.close()


def test_export_create_filters_select_the_trial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _store_trials(data)
    base = ["--data-root", str(data), "export", "create", "--track", "uptrend"]

    assert main([*base, "--symbol", "BTC"]) == 0
    btc = json.loads(capsys.readouterr().out)
    meta = json.loads((Path(btc["export_dir"]) / "meta.json").read_text())
    assert btc["ok"] is True and btc["symbol"] == "BTC" and meta["symbol"] == "BTC"
    assert btc["metrics"]["net_pnl"] == 120.0
    assert btc["artifacts"] == {"export": btc["export_dir"]}
    assert btc["candidate_id"] == Path(btc["export_dir"]).name

    assert main([*base, "--timeframe", "15m"]) == 0
    eth = json.loads(capsys.readouterr().out)
    assert eth["symbol"] == "ETH" and eth["timeframe"] == "15m"

    assert (
        main(["--data-root", str(data), "export", "create", "--run-id", "btc-run"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["run_id"] == "btc-run"


def test_export_create_refusals_and_empty_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "export", "create"]) == 2
    assert "--track or --run-id" in json.loads(capsys.readouterr().err)["error"]
    assert (
        main(["--data-root", str(data), "export", "create", "--track", "uptrend"]) == 1
    )
    error = json.loads(capsys.readouterr().err)
    assert error["error_type"] == "NoExportableTrial"
    assert not data.exists()

    _store_trials(data)
    argv = ["--data-root", str(data), "export", "create", "--run-id", "btc-run"]
    assert main([*argv, "--symbol", "SOL"]) == 1
    assert "symbol=SOL" in json.loads(capsys.readouterr().err)["error"]
    assert not (data / "exports").exists()
