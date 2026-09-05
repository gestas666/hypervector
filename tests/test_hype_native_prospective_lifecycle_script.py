"""Publication tests for prospective HYPE-native lifecycle evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_prospective_lifecycle.py")


def test_publish_binds_ledger_config_and_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publication freezes every identity-bearing input before writing."""
    module = _load_script()
    args = _args(tmp_path, module)

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        assert path == args.decisions and run_id == "run-v54"
        yield ([{"event_type": "configuration_identity"}], _source("a"))

    def build(records: object, spec: object) -> dict[str, object]:
        assert records == [{"event_type": "configuration_identity"}]
        assert getattr(spec, "strategy_id") == "hype-native-v3"
        return {"status": "waiting_for_first_eligible_long"}

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(module, "build_hype_native_prospective_report", build)

    report = module.publish_report(args)

    assert report["evidence"]["decision_ledger"]["sha256"] == "a" * 64
    assert report["evidence"]["config"]["sha256"] == _config_sha(args.config)
    assert len(report["generator_identity"]["files"]) >= 6
    generator_paths = {
        Path(row["path"]).name for row in report["generator_identity"]["files"]
    }
    assert "hype_native_baseline_comparison.py" in generator_paths
    assert json.loads(args.out.read_text(encoding="utf-8")) == report


def test_failed_ledger_recheck_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changing append-only prefix aborts before immutable publication."""
    module = _load_script()
    args = _args(tmp_path, module)

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        del path, run_id
        yield ([{}], _source("c"))
        raise RuntimeError("ledger changed")

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(
        module,
        "build_hype_native_prospective_report",
        lambda *_args: {"status": "waiting_for_first_eligible_long"},
    )

    with pytest.raises(RuntimeError, match="ledger changed"):
        module.publish_report(args)

    assert not args.out.exists()


def test_watch_once_atomically_publishes_waiting_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A quiet observer prefix updates status without inventing a snapshot."""
    module = _load_script()
    args = _args(tmp_path, module)
    args.status = tmp_path / "latest.json"
    args.snapshot_dir = tmp_path / "snapshots"

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        del path, run_id
        yield ([{}], _source("d"))

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(module.time, "time", lambda: 123.456)
    monkeypatch.setattr(
        module,
        "build_hype_native_prospective_report",
        lambda *_args: {
            "status": "waiting_for_first_eligible_long",
            "signal_counts": {"eligible_long_entries": 0},
            "lifecycles": [],
            "resolved_proxy_summary": {"trades": 0},
            "contract": {"execution_authority": "none"},
        },
    )

    status = module.watch_once(args)

    assert status["observed_at_ms"] == 123_456
    assert status["watch_state"] == "waiting_for_first_eligible_long"
    assert status["snapshot"] is None
    assert json.loads(args.status.read_text(encoding="utf-8")) == status
    assert not args.snapshot_dir.exists()


def test_watch_once_publishes_each_closed_state_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolved lifecycle receives an immutable, idempotent state snapshot."""
    module = _load_script()
    args = _args(tmp_path, module)
    args.status = tmp_path / "latest.json"
    args.snapshot_dir = tmp_path / "snapshots"

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        del path, run_id
        yield ([{}], _source("e"))

    report = {
        "status": "resolved_proxy_lifecycle_evidence_available",
        "signal_counts": {"eligible_long_entries": 1},
        "attempts": [{"status": "resolved_opposite_native_onset_proxy"}],
        "lifecycles": [{"decision_time_ms": 60_000, "exit_book_time_ms": 130_000}],
        "resolved_proxy_summary": {"trades": 1},
        "contract": {"execution_authority": "none"},
    }
    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(
        module, "build_hype_native_prospective_report", lambda *_args: dict(report)
    )

    first = module.watch_once(args)
    second = module.watch_once(args)

    snapshot_path = Path(first["snapshot"])
    assert snapshot_path.is_file()
    assert second["snapshot"] == first["snapshot"]
    assert len(tuple(args.snapshot_dir.glob("*.json"))) == 1
    frozen = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert frozen["watch_state_id"] == first["watch_state_id"]


def test_unchanged_closed_state_accepts_a_larger_ledger_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ledger growth alone must refresh status without killing the watcher."""
    module = _load_script()
    args = _args(tmp_path, module)
    args.status = tmp_path / "latest.json"
    args.snapshot_dir = tmp_path / "snapshots"
    sources = iter((_source("e"), _source("f")))

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        del path, run_id
        yield ([{}], next(sources))

    report = {
        "status": "resolved_proxy_lifecycle_evidence_available",
        "signal_counts": {"eligible_long_entries": 1},
        "attempts": [{"status": "resolved_opposite_native_onset_proxy"}],
        "lifecycles": [{"decision_time_ms": 60_000, "exit_book_time_ms": 130_000}],
        "resolved_proxy_summary": {"trades": 1},
        "contract": {"execution_authority": "none"},
    }
    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(
        module, "build_hype_native_prospective_report", lambda *_args: dict(report)
    )

    first = module.watch_once(args)
    second = module.watch_once(args)

    assert second["snapshot"] == first["snapshot"]
    assert second["evidence"]["decision_ledger"]["sha256"] == "f" * 64
    assert len(tuple(args.snapshot_dir.glob("*.json"))) == 1


def test_parser_supports_bounded_watch_mode(tmp_path: Path) -> None:
    """The same exact contract can drive a bounded report-only watcher."""
    module = _load_script()
    args = _args(tmp_path, module)
    values = [
        value
        for value in _argument_values(args)
        if value not in {"--out", str(args.out)}
    ]
    values.extend(
        [
            "--status",
            str(tmp_path / "latest.json"),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--interval-seconds",
            "15",
            "--max-cycles",
            "2",
        ]
    )

    parsed = module.build_parser().parse_args(values)

    assert parsed.status == tmp_path / "latest.json"
    assert parsed.snapshot_dir == tmp_path / "snapshots"
    assert parsed.interval_seconds == 15.0
    assert parsed.max_cycles == 2


def test_watcher_honors_bounded_cycles_without_busy_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bounded watcher polls exactly and sleeps only between cycles."""
    module = _load_script()
    args = _args(tmp_path, module)
    args.status = tmp_path / "latest.json"
    args.snapshot_dir = tmp_path / "snapshots"
    args.interval_seconds = 2.0
    args.max_cycles = 2
    calls: list[int] = []
    sleeps: list[float] = []
    monkeypatch.setattr(
        module,
        "watch_once",
        lambda _args: calls.append(1) or {"watch_state": "waiting"},
    )

    result = module.run_watcher(args, sleep_fn=sleeps.append)

    assert result == 0
    assert calls == [1, 1]
    assert sleeps == [2.0]


def test_baseline_comparison_changes_material_watch_state() -> None:
    """A changed same-bar baseline verdict must create a distinct state identity."""
    module = _load_script()
    report = {
        "status": "tracking_open_lifecycle",
        "signal_counts": {"eligible_long_entries": 1},
        "attempts": [],
        "lifecycles": [],
        "baseline_comparisons": [{"baseline_eligible": False}],
        "resolved_proxy_summary": {"trades": 0},
    }

    first = module._state_id(report)
    report["baseline_comparisons"] = [{"baseline_eligible": True}]

    assert module._state_id(report) != first


def _args(tmp_path: Path, module: ModuleType) -> object:
    config = tmp_path / "v54.toml"
    config.write_text("profile_id = 'v54'\n", encoding="utf-8")
    return module.build_parser().parse_args(
        _argument_values_for(config, tmp_path / "report.json")
    )


def _argument_values(args: object) -> list[str]:
    return _argument_values_for(args.config, args.out)


def _argument_values_for(config: Path, output: Path) -> list[str]:
    return [
        "--decisions",
        str(config.parent / "decisions.jsonl"),
        "--config",
        str(config),
        "--config-sha256",
        _config_sha(config),
        "--run-id",
        "run-v54",
        "--profile-id",
        "profile-v54",
        "--profile-fingerprint",
        "b" * 64,
        "--run-fingerprint",
        "c" * 64,
        "--strategy-id",
        "hype-native-v3",
        "--notional-usd",
        "1250",
        "--stop-bps",
        "80",
        "--maximum-hold-seconds",
        "28800",
        "--maximum-entry-delay-ms",
        "60000",
        "--maximum-exit-delay-ms",
        "60000",
        "--fee-bps-per-side",
        "4.32",
        "--residual-slippage-bps-per-side",
        "2",
        "--maximum-book-gap-ms",
        "45000",
        "--out",
        str(output),
    ]


def _config_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source(fill: str) -> dict[str, object]:
    return {"bytes": 12, "sha256": fill * 64}


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_prospective_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
