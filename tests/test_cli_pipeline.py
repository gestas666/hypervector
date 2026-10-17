"""``pipeline run/show/list`` with fake loaders and engines (offline, tmp data roots).

The fakes live in this module (``Fakes``/``install``) so the fresh-process
allowlist test can install exactly the same doubles before calling the CLI.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
import importlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

import hypervector
from hypervector.cli import main
from hypervector.commands import pipeline
from hypervector.commands.registry import ACTIONS, GROUP_ORDER, build_parser

BARS = 400
FORBIDDEN_MODULES = (
    "hyperliquid.exchange",
    "hypervector.live.multi_asset_live_runner",
    "hypervector.live.bidirectional_cohort_factory",
    "hypervector.live.cohort_routing_execution",
    "hypervector.live.exec_client",
    "hypervector.live.runner",
    "hypervector.live.session",
    "hypervector.live.engine",
)
PAPER_RUNNER = "hypervector.paper.runner"
HEAVY_MODULES = (
    "pandas",
    "numpy",
    "vectorbt",
    "nautilus_trader",
    "duckdb",
    "hyperliquid",
    "talib",
    "optuna",
    "lightgbm",
    "plotly",
    "requests",
)
EXITS = {
    "mode": "fixed_rr",
    "sl_pct": 0.01,
    "rr": 2.0,
    "atr_length": 14,
    "sl_atr_mult": 1.5,
    "trail_atr_mult": 2.0,
}
SOURCE_ROOT = Path(hypervector.__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent


# --- fakes (shared with the fresh-process test) ----------------------------------------


def strict_bundle(
    exports: Path,
    name: str,
    *,
    strategy: str = "crown_stack_long",
    symbol: str = "BTC",
    timeframe: str = "1m",
    lookback_days: int = 30,
    bar_count: int = BARS,
    strict: bool = True,
) -> Path:
    """A strategy bundle as the search engines publish it."""
    from hypervector.export.phase2 import export_candidate

    track = "downtrend" if "short" in strategy else "uptrend"
    meta: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "track": track,
        "lookback_days": lookback_days,
        "data_provenance": {"bar_count": bar_count, "sources": {"hl": bar_count}},
    }
    if strict:
        meta.update(
            init_cash=10_000.0,
            tp_sl_mode="fixed_rr",
            exits=EXITS,
            costs={"taker_fee": 0.00045, "slippage_bps": 2.0},
            risk={"risk_pct_min": 0.01, "risk_pct_max": 0.05},
        )
    return export_candidate(
        exports,
        run_id=f"run-{name}",
        meta=meta,
        params={"strategy": strategy, "role": track},
        metrics={"net_pnl": -5.0, "trade_count": 2},
        candidate_id=name,
        strict=strict,
    )


class Fakes:
    """Offline doubles for every engine entry point; records each call."""

    def __init__(self) -> None:
        self.calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.fail: set[str] = set()
        self.nautilus_bars: int = BARS
        self.loose_export = False

    def load(self, data_root: object, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
        from hypervector.data.provenance import summarize_provenance
        from hypervector.data.sources import fixture_ohlcv

        self.calls["load"].append({"data_root": data_root, **kwargs})
        frame = fixture_ohlcv(n_bars=BARS, drift=20.0, wave_period=30, source="hl")
        return frame, summarize_provenance(frame)

    def tune(self, **kwargs: Any) -> Any:
        from hypervector.sweep.autotune_models import AutotuneResult

        self.calls["tune"].append(kwargs)
        if "search" in self.fail:
            raise RuntimeError("every trial failed")
        root = Path(kwargs["data_root"])
        bundle = strict_bundle(
            root / "exports",
            f"exp_{kwargs['strategy_name']}_{kwargs['timeframe']}_fake",
            strategy=kwargs["strategy_name"],
            symbol=kwargs["symbol"],
            timeframe=kwargs["timeframe"],
            lookback_days=kwargs["lookback_days"],
            strict=not self.loose_export,
        )
        board = root / "logs" / "research" / "autotune_fake.json"
        board.parent.mkdir(parents=True, exist_ok=True)
        board.write_text("{}", encoding="utf-8")
        return AutotuneResult(
            kwargs["strategy_name"],
            kwargs["symbol"],
            kwargs["timeframe"],
            kwargs["lookback_days"],
            kwargs["n_trials"],
            "karpathy_random_adaptive",
            {"fast": 5},
            {"mode": "fixed_rr"},
            {"net_pnl": -5.0, "trade_count": 2},
            bundle,
            board,
        )

    def check(self, export_dir: object, **kwargs: Any) -> dict[str, Any]:
        self.calls["check"].append({"export_dir": export_dir, **kwargs})
        return {"ok": True}

    def nautilus(self, **kwargs: Any) -> Any:
        self.calls["nautilus"].append(kwargs)
        if "nautilus" in self.fail:
            raise RuntimeError("engine exploded")
        report = Path(kwargs["data_root"]) / "nautilus" / "backtest" / "n1"
        report.mkdir(parents=True, exist_ok=True)
        summary = report / "summary.json"
        summary.write_text(
            json.dumps({"run_id": "n1", "bars": self.nautilus_bars}), encoding="utf-8"
        )
        return SimpleNamespace(
            export_dir=Path(kwargs["export_dir"]),
            orders_count=4,
            pnl=-1.25,
            report_path=summary.resolve(),
            loadout_summary={},
        )

    def model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls["model"].append(kwargs)
        out = Path(kwargs["out_dir"])
        out.mkdir(parents=True)
        (out / "metalabel_lgbm.txt").write_text("booster", encoding="utf-8")
        (out / "metalabel_metadata.json").write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "n_labels": 12,
            "oos_auc_mean": 0.51,
            "beat_baseline": False,
            "bundle_dir": str(out.resolve()),
        }

    def paper(self, **kwargs: Any) -> Any:
        self.calls["paper"].append(kwargs)
        decisions = Path(kwargs["data_root"]) / "paper" / "decisions" / "d.jsonl"
        return SimpleNamespace(
            run_id="paper-1",
            decisions_path=decisions,
            export_dir=Path(kwargs["export_dir"]),
            warm_bars=10,
            live_bars=kwargs["max_live_bars"],
            bars_processed=10 + kwargs["max_live_bars"],
            fills_count=0,
            stop_reason="max_live_bars",
            execution_mode=kwargs["execution_mode"],
        )


def install(
    patch: Callable[[str, object], None], fakes: Fakes, *, paper: bool = False
) -> None:
    """Replace every engine entry point the pipeline may call."""
    patch("hypervector.data.pipeline.load_research_history", fakes.load)
    patch("hypervector.sweep.autotune.run_autotune", fakes.tune)
    patch("hypervector.nautilus.config_stub.phase2_check_report", fakes.check)
    patch("hypervector.nautilus.runner.run_phase2_backtest", fakes.nautilus)
    patch("hypervector.commands.model.train_metalabel_bundle", fakes.model)
    if paper:
        patch("hypervector.paper.runner.start_paper_daemon", fakes.paper)


def forbidden_modules(*, paper_bars: bool) -> list[str]:
    """Execution modules present in this process that the pipeline must never load."""
    names = set(FORBIDDEN_MODULES) | (set() if paper_bars else {PAPER_RUNNER})
    return sorted(
        name
        for name in sys.modules
        if name in names
        or name == "hypervector.operations"
        or name.startswith("hypervector.operations.")
    )


# --- helpers ---------------------------------------------------------------------------


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    doubles = Fakes()
    install(monkeypatch.setattr, doubles)
    return doubles


def _run(data: Path, *extra: str) -> list[str]:
    return ["--data-root", str(data), "pipeline", "run", *extra]


def _stages(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["stage"]: stage for stage in manifest["stages"]}


def _statuses(manifest: dict[str, Any]) -> dict[str, str]:
    return {name: stage["status"] for name, stage in _stages(manifest).items()}


def _manifest_on_disk(data: Path) -> dict[str, Any]:
    [path] = sorted((data / "runs" / "pipeline").glob("*/pipeline.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def _tree(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def _subprocess_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(SOURCE_ROOT)}


# --- registration ----------------------------------------------------------------------


def test_pipeline_group_is_registered_in_spec_order() -> None:
    assert ACTIONS["pipeline"] == ("list", "run", "show")
    assert GROUP_ORDER.index("db") < GROUP_ORDER.index("pipeline")
    assert GROUP_ORDER.index("pipeline") + 1 == GROUP_ORDER.index("system")
    assert "pipeline" in build_parser().format_help()


# --- stage 0 and the plan ----------------------------------------------------------------


def test_dry_run_prints_the_plan_and_writes_nothing(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    argv = _run(data, "--strategy", "crown_stack_long", "--timeframe", "5m")
    assert main([*argv, "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert not data.exists()
    assert fakes.calls == {}
    assert plan["status"] == "planned" and plan["dry_run"] is True
    assert plan["pipeline_id"].startswith("pl-")
    assert plan["pipeline_id"].endswith("-crown_stack_long-BTC-5m")
    assert plan["out_dir"] == str(
        data.resolve() / "runs" / "pipeline" / plan["pipeline_id"]
    )
    stages = _stages(plan)
    assert list(stages) == list(pipeline.STAGES)
    assert stages["validate"]["status"] == "ok"
    assert stages["model"]["status"] == "skipped"
    assert stages["model"]["reason"] == "not_requested"
    words = {name: " ".join(stage["argv"]) for name, stage in stages.items()}
    assert (
        "data history --symbol BTC --timeframe 5m --lookback-days 90" in words["data"]
    )
    assert "tune strategy --strategy crown_stack_long" in words["search"]
    assert "export validate --export <export>" in words["export"]
    assert words["nautilus"].endswith("--lookback-days 90 --no-network")
    assert words["paper"].endswith("paper run --export <export> --mode shadow")
    assert pipeline.EVIDENCE_NOTE in plan["notes"]
    assert plan["request"]["search"] == "tune"


def test_dry_run_from_an_export_writes_nothing(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand", lookback_days=45, timeframe="5m")
    before = _tree(data)
    argv = _run(data, "--strategy", "crown_stack_long", "--export", "cand")
    assert main([*argv, "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert _tree(data) == before
    assert fakes.calls == {}
    statuses = _statuses(plan)
    assert statuses["data"] == statuses["search"] == "skipped"
    assert _stages(plan)["data"]["reason"] == "started_from_export"
    request = plan["request"]
    assert (request["symbol"], request["timeframe"], request["lookback_days"]) == (
        "BTC",
        "5m",
        45,
    )
    assert "--export cand" in " ".join(_stages(plan)["nautilus"]["argv"])
    assert pipeline.EXPORT_START_NOTE in plan["notes"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--paper-bars", "0"],
        ["--paper-bars", "1441"],
        ["--no-network", "--paper-bars", "5"],
        ["--refresh", "--no-network"],
        ["--n-trials", "0"],
        ["--conviction", "1.5"],
    ],
)
def test_stage_zero_refusals_exit_two_without_writes(
    tmp_path: Path,
    fakes: Fakes,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    data = tmp_path / "data"
    assert main([*_run(data, "--strategy", "crown_stack_long"), *extra]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and error["command"] == "pipeline run"
    assert not data.exists()
    assert fakes.calls == {}


def test_bundle_and_strategy_refusals_exit_two(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand", strategy="crown_stack_long")
    before = _tree(data)
    refused = [
        ["--strategy", "no_such_strategy"],
        ["--strategy", "impulse_1m_range_long", "--search", "sweep"],
        ["--strategy", "crown_stack_long", "--export", "missing"],
        ["--strategy", "crown_stack_short", "--export", "cand"],
        ["--strategy", "crown_stack_long", "--export", "cand", "--symbol", "ETH"],
        ["--strategy", "crown_stack_long", "--export", "cand", "--refresh"],
        ["--strategy", "crown_stack_long", "--out-dir", str(data / "exports")],
    ]
    for extra in refused:
        assert main(_run(data, *extra)) == 2, extra
        assert json.loads(capsys.readouterr().err)["ok"] is False
    assert _tree(data) == before
    assert fakes.calls == {}


# --- a full run --------------------------------------------------------------------------


def test_full_run_pins_the_window_and_reports_parity(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    argv = _run(data, "--strategy", "crown_stack_long", "--lookback-days", "30")
    assert main([*argv, "--train-model"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest == _manifest_on_disk(data)
    assert manifest["schema"] == 1 and manifest["status"] == "ok"
    assert set(_statuses(manifest).values()) == {"ok"}

    window = manifest["window"]
    assert window["bars"] == BARS and window["lookback_days"] == 30
    assert window["start"] and window["end"] and window["cache_key"] == "BTC_1m_30d"
    assert window["cache_path"] == str(
        (data / "cache" / "BTC_1m_30d.parquet").resolve()
    )
    [load] = fakes.calls["load"]
    assert load["force_refresh"] is False and load["allow_network"] is True
    [tune] = fakes.calls["tune"]
    assert tune["export_best"] is True and tune["force_refresh"] is False
    # Only the data stage may refresh: the search serves the pinned window.
    assert tune["pin_cache"] is True
    # The engine probe imports Nautilus's execution-client module: never run it.
    [check] = fakes.calls["check"]
    assert check["probe_nautilus"] is False and check["strict"] is True
    [replay] = fakes.calls["nautilus"]
    assert replay["allow_network"] is False and replay["lookback_days"] == 30

    stages = _stages(manifest)
    export_dir = Path(manifest["export_dir"])
    assert export_dir.parent == (data / "exports").resolve()
    assert stages["search"]["artifacts"]["export"] == str(export_dir)
    assert stages["export"]["metrics"]["strict_valid"] is True
    assert "<export>" not in json.dumps(manifest["stages"])
    assert stages["nautilus"]["argv"][-5:] == [
        "--export",
        export_dir.name,
        "--lookback-days",
        "30",
        "--no-network",
    ]
    assert stages["nautilus"]["artifacts"]["validation"].endswith("summary.json")

    parity = manifest["parity"]
    assert parity["report_only"] is True
    assert parity["window_mismatch"] is False
    assert parity["vectorbt"]["net_pnl"] == -5.0 and parity["vectorbt"]["trades"] == 2
    assert parity["nautilus"]["pnl"] == -1.25 and parity["nautilus"]["orders"] == 4
    assert parity["reference_window"] == "pinned"

    model_dir = Path(stages["model"]["artifacts"]["model"])
    assert model_dir == Path(manifest["out_dir"]) / "model"
    assert stages["model"]["metrics"]["installed"] is False
    assert not (data / "models" / "metalabel").exists()
    paper = stages["paper"]
    assert paper["metrics"]["mode"] == "handoff"
    identity = paper["metrics"]["identity"]
    assert identity["execution_mode"] == "shadow" and identity["no_submit"] is True
    assert identity["metalabel_mode"] == "observe"
    assert manifest["next"] == [
        shlex.join(
            [
                "hypervector",
                "--data-root",
                str(data),
                "paper",
                "run",
                "--export",
                export_dir.name,
                "--mode",
                "shadow",
                "--metalabel-bundle",
                str(model_dir),
                "--metalabel-mode",
                "observe",
            ]
        )
    ]
    assert pipeline.EVIDENCE_NOTE in manifest["notes"]


def test_manifest_is_replaced_atomically_after_every_stage(
    tmp_path: Path, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    snapshots: list[dict[str, Any]] = []
    real_replace = os.replace

    def recording_replace(source: str | Path, target: str | Path) -> None:
        source, target = Path(source), Path(target)
        # os is shared: bundle exports also stage-and-replace their own files.
        if target.name == pipeline.MANIFEST:
            assert source.parent == target.parent and source.name != target.name
            snapshots.append(json.loads(source.read_text(encoding="utf-8")))
        real_replace(source, target)

    monkeypatch.setattr(pipeline.os, "replace", recording_replace)
    assert main(_run(data, "--strategy", "crown_stack_long", "--no-nautilus")) == 0
    # initial + data, search, export, paper + final status
    assert len(snapshots) == 6
    assert snapshots[0]["status"] == "running"
    assert _statuses(snapshots[0])["data"] == "not_started"
    assert snapshots[1]["window"]["bars"] == BARS
    done = [sum(s == "ok" for s in _statuses(m).values()) for m in snapshots]
    assert done == sorted(done)
    assert snapshots[-1]["status"] == "ok"
    out_dir = Path(snapshots[-1]["out_dir"])
    assert sorted(path.name for path in out_dir.iterdir()) == [pipeline.MANIFEST]
    assert _stages(snapshots[-1])["nautilus"]["reason"] == "no_nautilus_flag"


@pytest.mark.parametrize("failing", ["search", "nautilus"])
def test_stage_failure_exits_one_with_a_partial_manifest(
    tmp_path: Path,
    fakes: Fakes,
    capsys: pytest.CaptureFixture[str],
    failing: str,
) -> None:
    data = tmp_path / "data"
    fakes.fail = {failing}
    assert main(_run(data, "--strategy", "crown_stack_long")) == 1
    captured = capsys.readouterr()
    manifest = _manifest_on_disk(data)
    assert json.loads(captured.out) == manifest
    assert manifest["status"] == "failed"
    stages = _stages(manifest)
    assert stages[failing]["status"] == "failed"
    assert stages[failing]["exit_code"] == 1
    assert stages[failing]["error_type"] == "RuntimeError"
    order = list(pipeline.STAGES)
    for name in order[order.index(failing) + 1 :]:
        assert stages[name]["status"] in ("not_started", "skipped"), name
    assert stages["paper"]["status"] == "not_started"
    assert stages["data"]["status"] == "ok" and manifest["window"]["bars"] == BARS
    assert manifest["next"] == []
    error = json.loads(captured.err.strip().splitlines()[-1])
    assert error["stage"] == failing and error["command"] == "pipeline run"


def test_an_interrupt_records_the_stage_and_exits_130(
    tmp_path: Path, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(**_kwargs: Any) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr("hypervector.sweep.autotune.run_autotune", interrupted)
    data = tmp_path / "data"
    assert main(_run(data, "--strategy", "crown_stack_long")) == 130
    manifest = _manifest_on_disk(data)
    assert manifest["status"] == "failed"
    search = _stages(manifest)["search"]
    assert (search["status"], search["reason"], search["exit_code"]) == (
        "failed",
        "interrupted",
        130,
    )
    assert _stages(manifest)["export"]["status"] == "not_started"


def test_a_stage_calling_sys_exit_is_a_technical_failure(
    tmp_path: Path,
    fakes: Fakes,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A library sys.exit(0) mid-stage must not leave the run 'running' or exit 0."""

    def exits(**_kwargs: Any) -> Any:
        raise SystemExit(0)

    monkeypatch.delenv("HYPERVECTOR_DEBUG", raising=False)
    monkeypatch.setattr("hypervector.sweep.autotune.run_autotune", exits)
    data = tmp_path / "data"
    assert main(_run(data, "--strategy", "crown_stack_long")) == 1
    manifest = _manifest_on_disk(data)
    assert json.loads(capsys.readouterr().out) == manifest
    assert manifest["status"] == "failed"
    search = _stages(manifest)["search"]
    assert (search["status"], search["error_type"], search["exit_code"]) == (
        "failed",
        "SystemExit",
        1,
    )
    assert _stages(manifest)["export"]["status"] == "not_started"


def test_no_network_model_training_never_fetches_a_missing_window(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    """From a bundle the data stage is skipped, so only the cache may feed training."""
    data = tmp_path / "data"
    strict_bundle(data / "exports", "cand", lookback_days=30)
    flags = ["--strategy", "crown_stack_long", "--export", "cand", "--no-network"]
    flags += ["--train-model", "--no-nautilus"]

    missing = tmp_path / "missing"
    assert main([*_run(data, *flags), "--out-dir", str(missing)]) == 1
    manifest = json.loads((missing / pipeline.MANIFEST).read_text(encoding="utf-8"))
    model = _stages(manifest)["model"]
    assert (model["status"], model["error_type"]) == ("failed", "FileNotFoundError")
    assert "BTC_1m_30d.parquet" in model["reason"]
    assert fakes.calls["model"] == []
    assert _stages(manifest)["paper"]["status"] == "not_started"
    capsys.readouterr()

    (data / "cache").mkdir(parents=True, exist_ok=True)
    (data / "cache" / "BTC_1m_30d.parquet").write_bytes(b"")
    cached = tmp_path / "cached"
    assert main([*_run(data, *flags), "--out-dir", str(cached)]) == 0
    assert _stages(json.loads(capsys.readouterr().out))["model"]["status"] == "ok"
    assert len(fakes.calls["model"]) == 1


def test_too_few_model_labels_is_a_result_not_a_failure(
    tmp_path: Path,
    fakes: Fakes,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A best trial that rarely fires (often 0 trades) must not abort the run."""
    from hypervector.ml.walk_forward import InsufficientLabelsError

    def too_few(**kwargs: Any) -> dict[str, Any]:
        fakes.calls["model"].append(kwargs)
        raise InsufficientLabelsError(3)

    monkeypatch.setattr("hypervector.commands.model.train_metalabel_bundle", too_few)
    data = tmp_path / "data"
    argv = _run(data, "--strategy", "crown_stack_long", "--no-nautilus")
    assert main([*argv, "--train-model"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["status"] == "ok"
    model = _stages(manifest)["model"]
    assert (model["status"], model["reason"]) == ("skipped", "insufficient_labels")
    assert model["metrics"]["n_labels"] == 3 and "need ≥25" in model["detail"]
    assert not (Path(manifest["out_dir"]) / "model").exists()
    paper = _stages(manifest)["paper"]
    assert paper["status"] == "ok"
    assert paper["metrics"]["identity"]["metalabel_mode"] == "off"
    assert "--metalabel-bundle" not in manifest["next"][0]


def test_an_invalid_export_fails_the_export_stage(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    fakes.loose_export = True
    assert main(_run(data, "--strategy", "crown_stack_long")) == 1
    manifest = _manifest_on_disk(data)
    assert _stages(manifest)["export"]["status"] == "failed"
    assert _stages(manifest)["export"]["error_type"] == "ExportSchemaError"
    assert fakes.calls["nautilus"] == []


# --- nautilus ------------------------------------------------------------------------------


@pytest.mark.parametrize("from_export", [True, False])
def test_unsupported_symbol_skips_nautilus_and_continues(
    tmp_path: Path,
    fakes: Fakes,
    capsys: pytest.CaptureFixture[str],
    from_export: bool,
) -> None:
    data = tmp_path / "data"
    if from_export:
        strict_bundle(data / "exports", "doge-cand", symbol="DOGE")
        extra = ["--export", "doge-cand"]
    else:
        extra = ["--symbol", "DOGE", "--lookback-days", "30"]
    assert main(_run(data, "--strategy", "crown_stack_long", *extra)) == 0
    manifest = json.loads(capsys.readouterr().out)
    nautilus_stage = _stages(manifest)["nautilus"]
    assert nautilus_stage["status"] == "skipped"
    assert nautilus_stage["reason"] == "unsupported_symbol"
    assert "no venue metadata" in nautilus_stage["detail"]
    assert fakes.calls["nautilus"] == [] and fakes.calls["check"] == []
    assert manifest["parity"] is None
    assert _stages(manifest)["paper"]["status"] == "ok"
    assert f"--export {manifest['candidate_id']}" in manifest["next"][0]
    if from_export:
        assert fakes.calls["load"] == [] and fakes.calls["tune"] == []
        assert manifest["window"] is None


def test_nautilus_skip_follows_the_engine_symbol_predicate(
    tmp_path: Path,
    fakes: Fakes,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A symbol the engine resolves (built-in ETH venue geometry) runs Nautilus."""
    data = tmp_path / "data"
    strict_bundle(data / "exports", "eth-cand", symbol="ETH")
    argv = _run(data, "--strategy", "crown_stack_long", "--export", "eth-cand")
    assert main(argv) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert _stages(manifest)["nautilus"]["status"] == "ok"
    assert len(fakes.calls["nautilus"]) == 1
    # Started from a bundle: parity compares against the bundle's recorded window.
    assert manifest["parity"]["reference_window"] == "export"
    assert manifest["parity"]["window_mismatch"] is False


def test_window_mismatch_is_reported_not_gated(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    fakes.nautilus_bars = BARS - 1
    argv = _run(data, "--strategy", "crown_stack_long", "--lookback-days", "30")
    assert main(argv) == 0
    parity = json.loads(capsys.readouterr().out)["parity"]
    assert parity["window_mismatch"] is True
    assert parity["window_mismatch_fields"] == ["bars"]


# --- paper ---------------------------------------------------------------------------------


def test_start_paper_daemon_runs_only_with_paper_bars(
    tmp_path: Path,
    fakes: Fakes,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch.setattr, fakes, paper=True)
    first = tmp_path / "first"
    assert main(_run(first, "--strategy", "crown_stack_long", "--no-nautilus")) == 0
    handoff = json.loads(capsys.readouterr().out)
    assert fakes.calls["paper"] == []
    assert _stages(handoff)["paper"]["metrics"]["mode"] == "handoff"

    second = tmp_path / "second"
    argv = _run(second, "--strategy", "crown_stack_long", "--no-nautilus")
    assert main([*argv, "--paper-bars", "3"]) == 0
    session = json.loads(capsys.readouterr().out)
    [call] = fakes.calls["paper"]
    assert call["execution_mode"] == "shadow"
    assert call["max_live_bars"] == 3
    assert call["sandbox_enabled"] is False
    paper = _stages(session)["paper"]
    assert paper["metrics"]["mode"] == "foreground_shadow"
    assert paper["artifacts"]["paper"].endswith("d.jsonl")
    assert "--max-live-bars 3" in " ".join(paper["argv"])
    assert "--max-live-bars" not in session["next"][0]
    assert "paper report --decisions" in session["next"][1]


def test_paper_session_is_refused_unless_bounded_by_paper_bars(
    tmp_path: Path,
    fakes: Fakes,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unbounded session would be a daemon: fail before start_paper_daemon."""
    from hypervector.commands import paper as paper_commands

    install(monkeypatch.setattr, fakes, paper=True)
    real = paper_commands._paper_options

    def unbounded(*args: Any, **kwargs: Any) -> dict[str, object]:
        return {**real(*args, **kwargs), "max_live_bars": None}

    monkeypatch.setattr(paper_commands, "_paper_options", unbounded)
    data = tmp_path / "data"
    argv = _run(data, "--strategy", "crown_stack_long", "--no-nautilus")
    assert main([*argv, "--paper-bars", "3"]) == 1
    paper = _stages(_manifest_on_disk(data))["paper"]
    assert (paper["status"], paper["error_type"]) == ("failed", "RuntimeError")
    assert fakes.calls["paper"] == []


# --- sweep search -------------------------------------------------------------------------


def test_sweep_search_reads_the_pinned_window_offline(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the data stage may refresh; the sweep re-reads the same key offline."""
    data = tmp_path / "data"
    argv = _run(
        data,
        "--strategy",
        "crown_stack_short",
        "--search",
        "sweep",
        "--lookback-days",
        "30",
        "--refresh",
        "--no-nautilus",
    )
    assert main(argv) == 0
    manifest = json.loads(capsys.readouterr().out)
    first, second = fakes.calls["load"]
    assert first["force_refresh"] is True and first["allow_network"] is True
    assert second["force_refresh"] is False and second["allow_network"] is False
    assert (second["symbol"], second["timeframe"], second["lookback_days"]) == (
        "BTC",
        "1m",
        30,
    )
    search = _stages(manifest)["search"]
    assert search["argv"][3:7] == ["backtest", "sweep", "--track", "downtrend"]
    assert search["artifacts"]["run_id"] == search["metrics"]["run_id"]
    assert Path(search["artifacts"]["export"]).is_dir()
    assert _stages(manifest)["export"]["status"] == "ok"


# --- allowlist ------------------------------------------------------------------------------


@pytest.mark.parametrize("paper_bars", [False, True])
def test_pipeline_never_imports_execution_modules(
    tmp_path: Path, paper_bars: bool
) -> None:
    """A fresh process records sys.modules around a fake-engine run."""
    data = tmp_path / "data"
    argv = _run(data, "--strategy", "crown_stack_long", "--train-model")
    if paper_bars:
        argv += ["--paper-bars", "2"]
    result = tmp_path / "result.json"
    program = (
        "import importlib, json, sys\n"
        f"sys.path.insert(0, {str(TESTS_DIR)!r})\n"
        "import test_cli_pipeline as t\n"
        "def patch(target, value):\n"
        "    module, name = target.rsplit('.', 1)\n"
        "    setattr(importlib.import_module(module), name, value)\n"
        "fakes = t.Fakes()\n"
        f"t.install(patch, fakes, paper={paper_bars!r})\n"
        "before = t.forbidden_modules(paper_bars=True)\n"
        "from hypervector.cli import main\n"
        f"code = main({argv!r})\n"
        f"after = t.forbidden_modules(paper_bars={paper_bars!r})\n"
        f"open({str(result)!r}, 'w').write(json.dumps(\n"
        "    {'code': code, 'before': before, 'after': after,\n"
        "     'paper_calls': len(fakes.calls['paper']),\n"
        f"     'runner': {PAPER_RUNNER!r} in sys.modules}}))\n"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=180,
        cwd=tmp_path,
        env=_subprocess_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    report = json.loads(result.read_text(encoding="utf-8"))
    assert report["code"] == 0
    assert report["before"] == []
    assert report["after"] == []
    assert report["runner"] is paper_bars
    assert report["paper_calls"] == (1 if paper_bars else 0)


# --- show / list --------------------------------------------------------------------------


def _write_run(
    data: Path,
    pipeline_id: str,
    *,
    created: str,
    strategy: str = "crown_stack_long",
    symbol: str = "BTC",
    timeframe: str = "5m",
    status: str = "ok",
) -> Path:
    out = data / "runs" / "pipeline" / pipeline_id
    out.mkdir(parents=True)
    manifest = {
        "schema": 1,
        "pipeline_id": pipeline_id,
        "created_at_utc": created,
        "out_dir": str(out),
        "request": {
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "search": "tune",
            "export": None,
        },
        "candidate_id": f"exp_{strategy}",
        "export_dir": None,
        "stages": [{"stage": "data", "status": "ok"}],
        "status": status,
        "notes": [pipeline.EVIDENCE_NOTE],
    }
    (out / pipeline.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return out


def _fixture_runs(data: Path) -> None:
    _write_run(data, "pl-a", created="2026-10-01T00:00:00Z")
    _write_run(
        data,
        "pl-b",
        created="2026-10-03T00:00:00Z",
        strategy="crown_stack_short",
        status="failed",
    )
    _write_run(data, "pl-c", created="2026-10-02T00:00:00Z", symbol="ETH")
    broken = data / "runs" / "pipeline" / "pl-broken"
    broken.mkdir()
    (broken / pipeline.MANIFEST).write_text("{", encoding="utf-8")


def test_list_is_newest_first_filters_and_flags_broken_manifests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _fixture_runs(data)
    assert main(["--data-root", str(data), "pipeline", "list"]) == 0
    report = json.loads(capsys.readouterr().out)
    ids = [entry["pipeline_id"] for entry in report["pipelines"]]
    # An unreadable manifest has no created time, so its file time (now) ranks it.
    assert ids == ["pl-broken", "pl-b", "pl-c", "pl-a"]
    assert report["count"] == 4 and report["invalid_count"] == 1
    broken = next(e for e in report["pipelines"] if e["pipeline_id"] == "pl-broken")
    assert broken["valid"] is False and broken["errors"]
    assert report["pipelines"][1]["stages"] == {"data": "ok"}

    base = ["--data-root", str(data), "pipeline", "list"]
    assert main([*base, "--symbol", "ETH"]) == 0
    assert [
        e["pipeline_id"] for e in json.loads(capsys.readouterr().out)["pipelines"]
    ] == ["pl-c"]
    assert main([*base, "--strategy", "crown_stack_short", "--timeframe", "5m"]) == 0
    assert [
        e["pipeline_id"] for e in json.loads(capsys.readouterr().out)["pipelines"]
    ] == ["pl-b"]


def test_list_without_runs_is_empty_and_creates_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "pipeline", "list"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0
    assert not data.exists()


def test_show_resolves_latest_ids_and_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    _fixture_runs(data)
    base = ["--data-root", str(data), "pipeline", "show"]
    assert main(base) == 0
    assert json.loads(capsys.readouterr().out)["pipeline_id"] == "pl-b"
    assert main([*base, "pl-a"]) == 0
    assert json.loads(capsys.readouterr().out)["pipeline_id"] == "pl-a"
    assert main([*base, str(data / "runs" / "pipeline" / "pl-c")]) == 0
    assert json.loads(capsys.readouterr().out)["pipeline_id"] == "pl-c"
    assert main([*base, "pl-missing"]) == 2
    assert "pl-missing" in json.loads(capsys.readouterr().err)["error"]
    assert main([*base, "pl-broken"]) == 1
    assert json.loads(capsys.readouterr().err)["error_type"] == "ValueError"


def test_show_latest_without_runs_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert main(["--data-root", str(data), "pipeline", "show"]) == 2
    assert "latest" in json.loads(capsys.readouterr().err)["error"]
    assert not data.exists()


def test_show_reads_a_real_run(
    tmp_path: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    assert main(_run(data, "--strategy", "crown_stack_long", "--no-nautilus")) == 0
    produced = json.loads(capsys.readouterr().out)
    assert main(["--data-root", str(data), "pipeline", "show"]) == 0
    assert json.loads(capsys.readouterr().out) == produced
    assert main(["--data-root", str(data), "pipeline", "list"]) == 0
    [entry] = json.loads(capsys.readouterr().out)["pipelines"]
    assert entry["pipeline_id"] == produced["pipeline_id"]
    assert entry["candidate_id"] == produced["candidate_id"]
    assert entry["status"] == "ok" and entry["search"] == "tune"


@pytest.mark.parametrize(
    "argv",
    [
        ["pipeline", "list"],
        ["pipeline", "show"],
        ["pipeline", "show", "pl-a"],
        ["pipeline", "--help"],
        ["pipeline", "run", "--help"],
    ],
)
def test_show_list_and_help_do_not_import_engines(
    tmp_path: Path, argv: list[str]
) -> None:
    data = tmp_path / "data"
    _write_run(data, "pl-a", created="2026-10-01T00:00:00Z")
    program = (
        "import sys\n"
        "from hypervector.cli import main\n"
        "try:\n"
        f"    code = main(['--data-root', {str(data)!r}, *{argv!r}])\n"
        "except SystemExit as exc:\n"
        "    code = exc.code\n"
        f"heavy = sorted(set({HEAVY_MODULES!r}) & set(sys.modules))\n"
        "assert code == 0, code\n"
        "assert not heavy, heavy\n"
    )
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        timeout=60,
        cwd=tmp_path,
        env=_subprocess_env(),
        stdout=subprocess.DEVNULL,
    )


def test_patch_helper_matches_monkeypatch_targets() -> None:
    """Every faked target exists, so a renamed engine entry point fails loudly here."""
    seen: list[str] = []
    install(lambda target, _value: seen.append(target), Fakes(), paper=True)
    for target in seen:
        module, name = target.rsplit(".", 1)
        assert hasattr(importlib.import_module(module), name), target
