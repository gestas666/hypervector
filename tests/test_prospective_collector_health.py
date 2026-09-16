"""Offline contracts for passive frozen-collector health observation."""

from datetime import UTC, datetime
from collections.abc import Callable
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess

import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research import prospective_collector_health as health
from hypervector.research import prospective_collector_watch as watch

NOW = 1_789_520_000_000
START = NOW - 86_400_000
END = NOW + 86_400_000
Sample = tuple[health.CollectorPin, dict[str, object]]


def utc(value: int) -> str:
    """Format synthetic collector timestamps."""
    return datetime.fromtimestamp(value / 1000, UTC).isoformat()


@pytest.fixture
def sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[health.CollectorPin, dict[str, object]]:
    """Create a fully local pinned source and healthy collector observation."""
    source = tmp_path / "source.py"
    source.write_text("# frozen research source\n")
    evidence = {"path": str(source), **file_evidence(source)}
    manifest = {"schema_version": 2, "execution_authority": "none",
                "automatic_promotion": False, "collector_sources": [evidence],
                "protocol": evidence, "contract": {"start_ms": START, "end_ms": END}}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    pin = health.CollectorPin("test", tmp_path, 42, "birth command", str(file_evidence(manifest_path)["sha256"]), 60_000)
    payload = {"schema_version": 2, "execution_authority": "none",
               "automatic_promotion": False, "outcomes_evaluated": False,
               "pid": 42, "state": "waiting", "heartbeat_ms": NOW,
               "generated_at_utc": utc(NOW), "next_due_ms": NOW + 5000,
               "study_start_utc": utc(START), "study_end_exclusive_utc": utc(END),
               "study_phase": "collecting", "error": None,
               "last_cycle": {"completed_boundary_ms": NOW - 5000, "incomplete_queries": 0}}
    (tmp_path / "latest.json").write_text(json.dumps(payload))
    monkeypatch.setattr(health, "process_identity", lambda pid: "birth command")
    monkeypatch.setattr(health, "lock_owners", lambda path: {42})
    monkeypatch.setattr(health, "cohort_checkpoint_writer_active", lambda path: True)
    return pin, payload


def observe(sample: tuple[health.CollectorPin, dict[str, object]], now: int = NOW) -> dict[str, object]:
    """Publish one fixture health file and observe it at a fixed clock."""
    pin, payload = sample
    (pin.root / "latest.json").write_text(json.dumps(payload))
    return health.observe_collector(pin, now_ms=now)


@pytest.mark.parametrize("state", ["waiting", "capturing"])
def test_live_waiting_and_capturing_are_healthy(sample: Sample, state: str) -> None:
    sample[1]["state"] = state
    result = observe(sample)
    assert result["status"] == "healthy"
    assert result["execution_authority"] == "none"
    assert result["outcomes_evaluated"] is False


@pytest.mark.parametrize("state", ["stopped", "faulted", "mystery", "finished"])
def test_unexpected_terminal_or_unknown_state_alerts(sample: Sample, state: str) -> None:
    sample[1]["state"] = state
    assert observe(sample)["status"] == "alert"


@pytest.mark.parametrize("identity", [None, "new birth same command", "birth wrong command"])
def test_absent_reused_or_changed_process_alerts(sample: Sample, monkeypatch: pytest.MonkeyPatch, identity: str | None) -> None:
    monkeypatch.setattr(health, "process_identity", lambda pid: identity)
    assert observe(sample)["status"] == "alert"


@pytest.mark.parametrize("owners,busy", [(set(), False), ({9}, True), ({42}, False), ({42, 9}, True)])
def test_absent_or_ambiguous_lock_alerts(sample: Sample, monkeypatch: pytest.MonkeyPatch, owners: set[int], busy: bool) -> None:
    monkeypatch.setattr(health, "lock_owners", lambda path: owners)
    monkeypatch.setattr(health, "cohort_checkpoint_writer_active", lambda path: busy)
    assert observe(sample)["status"] == "alert"


@pytest.mark.parametrize("field,value", [
    ("pid", 9), ("pid", True), ("schema_version", 9),
    ("execution_authority", "live"), ("automatic_promotion", True),
    ("outcomes_evaluated", True), ("error", "known fault"),
    ("heartbeat_ms", "bad"), ("heartbeat_ms", True),
    ("generated_at_utc", "bad"), ("generated_at_utc", utc(NOW - 1000)),
    ("study_phase", "before_start"), ("study_start_utc", utc(START - 1)),
    ("study_end_exclusive_utc", utc(END + 1)),
    ("next_due_ms", NOW - 1), ("next_due_ms", NOW + 600_000),
])
def test_invalid_health_evidence_alerts(sample: Sample, field: str, value: object) -> None:
    sample[1][field] = value
    assert observe(sample)["status"] == "alert"


@pytest.mark.parametrize("age,status", [(120_000, "healthy"), (120_001, "alert"), (-5000, "healthy"), (-5001, "alert")])
def test_heartbeat_thresholds_are_explicit(sample: Sample, age: int, status: str) -> None:
    assert observe(sample, NOW + age)["status"] == status


def test_correct_finished_window_may_have_no_live_process(sample: Sample, monkeypatch: pytest.MonkeyPatch) -> None:
    sample[1].update(state="finished", heartbeat_ms=END + 5000,
                     generated_at_utc=utc(END + 5000), study_phase="collection_window_ended",
                     last_cycle={"completed_boundary_ms": END})
    monkeypatch.setattr(health, "process_identity", lambda pid: None)
    monkeypatch.setattr(health, "lock_owners", lambda path: set())
    monkeypatch.setattr(health, "cohort_checkpoint_writer_active", lambda path: False)
    assert observe(sample, END + 1_000_000)["status"] == "finished"
    sample[1]["last_cycle"] = {"completed_boundary_ms": END - 1}
    assert observe(sample, END + 1_000_000)["status"] == "alert"


@pytest.mark.parametrize("target", ["manifest.json", "source.py"])
def test_manifest_or_source_mutation_alerts(sample: Sample, target: str) -> None:
    path = sample[0].root / target
    path.write_text(path.read_text() + " ")
    assert observe(sample)["status"] == "alert"


@pytest.mark.parametrize("content", [None, "{broken", "[]"])
def test_missing_malformed_or_wrong_shape_health_alerts(sample: Sample, content: str | None) -> None:
    path = sample[0].root / "latest.json"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    result = health.observe_collector(sample[0], now_ms=NOW)
    assert result["status"] == "alert"
    assert result["reason"]


def test_source_failure_is_not_silently_healthy(sample: Sample) -> None:
    (sample[0].root / "source.py").unlink()
    assert observe(sample)["status"] == "alert"


def test_bound_loop_reads_after_final_sleep_and_retains_fault(tmp_path: Path) -> None:
    elapsed = [0.0]
    seen = []

    def inspect() -> list[dict[str, object]]:
        seen.append(elapsed[0])
        return [{"status": "alert" if elapsed[0] >= 16 else "healthy"}]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    result = watch.run_health_watch(inspect, tmp_path, duration_seconds=16,
                                    interval_seconds=15, monotonic=lambda: elapsed[0], sleep=sleep)
    assert seen == [0, 15, 16]
    assert result["status"] == "alert"
    assert json.loads((tmp_path / "result.json").read_text())["status"] == "alert"
    assert (tmp_path / "start.json").exists()


def test_deadline_is_observed_and_immutable_receipts_prevent_duplicate_launch(tmp_path: Path) -> None:
    elapsed = [0.0]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    result = watch.run_health_watch(lambda: [{"status": "healthy"}], tmp_path,
                                    duration_seconds=2, interval_seconds=15,
                                    monotonic=lambda: elapsed[0], sleep=sleep)
    assert result["status"] == "observation_deadline"
    before = (tmp_path / "start.json").read_bytes()
    with pytest.raises(FileExistsError):
        watch.run_health_watch(lambda: [], tmp_path, duration_seconds=2)
    assert (tmp_path / "start.json").read_bytes() == before


@pytest.mark.parametrize("duration,interval", [(0, 1), (-1, 1), (float("nan"), 1), (1, 0), (1, float("inf"))])
def test_invalid_watch_budget_rejected(tmp_path: Path, duration: float, interval: float) -> None:
    with pytest.raises(ValueError):
        watch.run_health_watch(lambda: [], tmp_path, duration_seconds=duration, interval_seconds=interval)


def test_absent_error_field_is_not_a_success_shaped_default(sample: Sample) -> None:
    del sample[1]["error"]
    assert observe(sample)["status"] == "alert"


def test_initial_inspection_is_preserved_even_when_later_health_changes(tmp_path: Path) -> None:
    elapsed = [0.0]

    def sleep(seconds: float) -> None:
        elapsed[0] += seconds

    watch.run_health_watch(lambda: [{"status": "healthy", "time": elapsed[0]}], tmp_path,
                           duration_seconds=2, monotonic=lambda: elapsed[0], sleep=sleep)
    initial = json.loads((tmp_path / "initial.json").read_text())
    assert initial["collectors"][0]["time"] == 0


@pytest.mark.parametrize("code,stdout,stderr,expected", [
    (0, "birth command\n", "", "birth command"), (1, "", "", None),
])
def test_process_probe_uses_birth_and_handles_absence(monkeypatch: pytest.MonkeyPatch, code: int,
                                                     stdout: str, stderr: str, expected: str | None) -> None:
    monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], code, stdout, stderr))
    assert health.process_identity(42) == expected


@pytest.mark.parametrize("stdout,expected", [("p42\n", {42}), ("p42\np43\n", {42, 43}), ("", set())])
def test_lock_probe_preserves_all_open_owners(monkeypatch: pytest.MonkeyPatch, stdout: str, expected: set[int]) -> None:
    monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0 if stdout else 1, stdout, ""))
    assert health.lock_owners(Path("/synthetic/lock")) == expected


@pytest.mark.parametrize("probe", ["process_identity", "lock_owners"])
@pytest.mark.parametrize("error", [subprocess.CalledProcessError(2, "probe"), subprocess.TimeoutExpired("probe", 5)])
def test_probe_errors_remain_explicit_alerts(sample: Sample, monkeypatch: pytest.MonkeyPatch,
                                            probe: str, error: Exception) -> None:
    def fail(value: object) -> object:
        raise error

    monkeypatch.setattr(health, probe, fail)
    assert observe(sample)["status"] == "alert"


@pytest.mark.parametrize("content", ["[]", '{"collectors": []}', '{"collectors": [{}]}'])
def test_pin_file_rejects_missing_identity(tmp_path: Path, content: str) -> None:
    path = tmp_path / "pins.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        health.load_pins(path)


@pytest.mark.parametrize("change", [{"label": ""}, {"root": Path("relative")}, {"pid": 0},
                                    {"pid": True}, {"cadence_ms": 0}, {"manifest_sha256": "bad"}])
def test_invalid_pin_cannot_be_constructed(sample: Sample, change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(sample[0], **change)


def test_pin_file_roundtrip_and_duplicate_rejection(sample: Sample) -> None:
    pin, _ = sample
    record = {**asdict(pin), "root": str(pin.root)}
    path = pin.root / "pins.json"
    path.write_text(json.dumps({"collectors": [record]}))
    assert health.load_pins(path) == (pin,)
    path.write_text(json.dumps({"collectors": [record, record]}))
    with pytest.raises(ValueError, match="duplicate"):
        health.load_pins(path)
    record["label"] = 42
    path.write_text(json.dumps({"collectors": [record]}))
    with pytest.raises(ValueError, match="strings"):
        health.load_pins(path)


@pytest.mark.parametrize("field,value", [("schema_version", 9), ("collector_sources", []),
                                        ("collector_sources", [{}]), ("contract", None)])
def test_pinned_but_invalid_manifest_is_rejected(sample: Sample, field: str, value: object) -> None:
    pin, payload = sample
    path = pin.root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    updated = replace(pin, manifest_sha256=str(file_evidence(path)["sha256"]))
    assert observe((updated, payload))["status"] == "alert"


@pytest.mark.parametrize("value", [None, "2026-09-16T00:00:00"])
def test_missing_or_naive_timestamp_alerts(sample: Sample, value: object) -> None:
    sample[1]["generated_at_utc"] = value
    assert observe(sample)["status"] == "alert"


def test_oversized_health_is_an_explicit_alert(sample: Sample) -> None:
    (sample[0].root / "latest.json").write_bytes(b" " * (2 * 1024 * 1024 + 1))
    assert health.observe_collector(sample[0], now_ms=NOW)["status"] == "alert"


def test_all_finished_collectors_end_watch_without_sleep(tmp_path: Path) -> None:
    result = watch.run_health_watch(lambda: [{"status": "finished"}], tmp_path, duration_seconds=20)
    assert result["status"] == "collection_finished"


@pytest.mark.parametrize("probe,arg", [(health.process_identity, 42), (health.lock_owners, Path("/lock"))])
def test_probe_command_failures_are_not_absence(monkeypatch: pytest.MonkeyPatch, probe: Callable[[object], object], arg: object) -> None:
    monkeypatch.setattr(health.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "permission denied"))
    with pytest.raises(subprocess.CalledProcessError):
        probe(arg)
