"""Continuous BRENTOIL lifecycle watcher command tests."""

from argparse import Namespace
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

from pytest import MonkeyPatch


def test_watcher_command_exists() -> None:
    """The clean prospective epoch must have durable lifecycle automation."""
    assert Path("scripts/brentoil_oil_shock_lifecycle_watch.py").is_file()


def test_parser_requires_exact_sources_and_watch_destinations(tmp_path: Path) -> None:
    """The watcher CLI names every causal source and durable destination."""
    args = _script().build_parser().parse_args(_cli_args(tmp_path))

    assert args.journal == tmp_path / "decisions.jsonl"
    assert args.status == tmp_path / "latest.json"
    assert args.snapshot_dir == tmp_path / "snapshots"
    assert args.interval_seconds == 60.0
    assert args.max_cycles == 0


def test_watch_once_publishes_safe_waiting_status(tmp_path: Path) -> None:
    """A quiet prefix refreshes atomic status without immutable snapshots."""
    args = _args(tmp_path)

    status = _script().watch_once(args, report_builder=_waiting_report)

    observed = json.loads(args.status.read_text())
    assert observed == status
    assert status["execution_authority"] == "none"
    assert status["watch_state"] == "WAITING_ELIGIBLE_ONSET"
    assert status["snapshot"] is None
    assert list(args.snapshot_dir.iterdir()) == []


def test_watch_status_freezes_watcher_generator_identity(tmp_path: Path) -> None:
    """Every status must identify the watcher and lifecycle command bytes."""
    args = _args(tmp_path)

    status = _script().watch_once(args, report_builder=_waiting_report)

    identity = status["watcher_generator_identity"]
    paths = {row["path"] for row in identity["files"]}
    assert any(path.endswith("brentoil_oil_shock_lifecycle_watch.py") for path in paths)
    assert any(path.endswith("brentoil_oil_shock_lifecycle.py") for path in paths)
    assert all(
        row["bytes"] > 0 and len(row["sha256"]) == 64 for row in identity["files"]
    )


def test_watch_once_snapshots_eligible_state_once(tmp_path: Path) -> None:
    """An eligible onset creates one immutable, idempotent state snapshot."""
    args = _args(tmp_path)

    first = _script().watch_once(args, report_builder=_eligible_report)
    second = _script().watch_once(args, report_builder=_eligible_report)

    snapshots = list(args.snapshot_dir.iterdir())
    assert first["snapshot"] == second["snapshot"]
    assert len(snapshots) == 1
    observed = json.loads(snapshots[0].read_text())
    assert observed["watch_state_id"] == first["watch_state_id"]
    assert observed["source"]["eligible_decisions"] == 1


def test_watch_once_uses_exact_lifecycle_builder_by_default(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Production refresh delegates to the frozen lifecycle report builder."""
    module = _script()
    args = _args(tmp_path)

    def build(_args: Namespace, *, destination: Path) -> dict[str, object]:
        return _waiting_report(_args, destination)

    monkeypatch.setattr(module, "build_report", build)

    status = module.watch_once(args)

    assert status["watch_state"] == "WAITING_ELIGIBLE_ONSET"


def test_watcher_runs_bounded_cycles_with_fresh_observation_times(
    tmp_path: Path,
) -> None:
    """Each bounded cycle freezes a new causal observation timestamp."""
    args = _args(tmp_path)
    args.interval_seconds = 2.0
    args.max_cycles = 2
    observed: list[int] = []
    sleeps: list[float] = []

    def build(cycle: Namespace, destination: Path) -> dict[str, object]:
        assert destination == args.status
        observed.append(cycle.observed_at_ms)
        return _waiting_report(cycle, destination)

    timestamps = iter((1_800_000_000_001, 1_800_000_000_002))
    result = _script().run_watcher(
        args,
        report_builder=build,
        sleep_fn=sleeps.append,
        clock_ms=lambda: next(timestamps),
    )

    assert result == 0
    assert observed == [1_800_000_000_001, 1_800_000_000_002]
    assert sleeps == [2.0]


def test_main_runs_one_locked_report_only_cycle(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """The real command creates durable destinations and exits when bounded."""
    module = _script()

    def build(args: Namespace, *, destination: Path) -> dict[str, object]:
        return _waiting_report(args, destination)

    monkeypatch.setattr(module, "build_report", build)
    argv = [*_cli_args(tmp_path), "--max-cycles", "1"]

    result = module.main(argv)

    assert result == 0
    assert (tmp_path / "latest.json").is_file()
    assert (tmp_path / "snapshots").is_dir()


def _script() -> ModuleType:
    path = Path("scripts/brentoil_oil_shock_lifecycle_watch.py")
    spec = importlib.util.spec_from_file_location("brentoil_lifecycle_watcher", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("BRENTOIL lifecycle watcher is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _args(root: Path) -> Namespace:
    snapshot_dir = root / "snapshots"
    snapshot_dir.mkdir()
    return Namespace(status=root / "latest.json", snapshot_dir=snapshot_dir)


def _cli_args(root: Path) -> list[str]:
    return [
        "--journal",
        str(root / "decisions.jsonl"),
        "--candle-ledger",
        str(root / "candles.jsonl"),
        "--book-ledger",
        str(root / "books.jsonl"),
        "--mark-data-root",
        str(root / "marks"),
        "--development",
        str(root / "development.json"),
        "--live-canary",
        str(root / "canary.json"),
        "--status",
        str(root / "latest.json"),
        "--snapshot-dir",
        str(root / "snapshots"),
    ]


def _waiting_report(_args: Namespace, destination: Path) -> dict[str, object]:
    assert destination.name == "latest.json"
    return {
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "technical_assessment": {
            "status": "WAITING_ELIGIBLE_ONSET",
            "live_change_supported": False,
        },
        "source": {"eligible_decisions": 0, "observed_decisions": 2},
        "nominal": {"summary": {"resolved": 0, "censored": 0}},
        "stress": {"summary": {"resolved": 0, "censored": 0}},
    }


def _eligible_report(args: Namespace, destination: Path) -> dict[str, object]:
    report = _waiting_report(args, destination)
    report["technical_assessment"] = {
        "status": "TECHNICALLY_UNRESOLVED",
        "live_change_supported": False,
    }
    report["source"] = {"eligible_decisions": 1, "observed_decisions": 3}
    report["nominal"] = {"summary": {"resolved": 0, "censored": 1}}
    report["stress"] = {"summary": {"resolved": 0, "censored": 1}}
    return report
