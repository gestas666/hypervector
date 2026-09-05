"""CLI contracts for the report-only external-opportunity monitor."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.research.cohort_external_opportunity_pipeline import (
    ExternalOpportunityPaths,
)
from test_cohort_external_opportunity_pipeline import _write_sources

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "cohort_external_opportunity_monitor.py"
)


def test_once_publishes_exact_report_only_candidate(tmp_path: Path) -> None:
    module = _load()
    sources = _write_sources(tmp_path)
    output = tmp_path / "latest.json"
    args = _args(module, sources, output)

    assert module.run_monitor(args, now_fn=_now, sleep_fn=_unexpected_sleep) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["candidates"][0]["symbol"] == "xyz:BRENTOIL"
    assert payload["candidates"][0]["live_canary"]["closed_lifecycles"] == 3
    assert payload["evidence"]["observer"]["path"] == str(sources.observer.resolve())
    assert payload["generated_at_utc"] == _now().isoformat()
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "available"
    assert status["contract"]["execution_authority"] == "none"
    assert status["last_valid_report_preserved"] is True
    assert status["report"]["path"] == str(output.resolve())
    assert status["report"]["bytes"] == output.stat().st_size


def test_once_fails_closed_without_overwriting_last_valid_output(
    tmp_path: Path,
) -> None:
    module = _load()
    sources = _write_sources(tmp_path)
    observer = json.loads(sources.observer.read_text(encoding="utf-8"))
    observer["execution_authority"] = "live"
    sources.observer.write_text(json.dumps(observer), encoding="utf-8")
    output = tmp_path / "latest.json"
    output.write_text('{"last":"valid"}', encoding="utf-8")

    assert (
        module.run_monitor(
            _args(module, sources, output),
            now_fn=_now,
            sleep_fn=_unexpected_sleep,
        )
        == 2
    )
    assert json.loads(output.read_text(encoding="utf-8")) == {"last": "valid"}
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "unavailable"
    assert status["last_valid_report_preserved"] is True
    assert status["technical_issue"] == (
        "ValueError: BRENTOIL observer contract is invalid"
    )
    assert status["report"]["path"] == str(output.resolve())
    assert status["report"]["bytes"] == output.stat().st_size


def test_status_cannot_alias_last_valid_report(tmp_path: Path) -> None:
    """A malformed status path cannot overwrite the preserved report."""
    module = _load()
    sources = _write_sources(tmp_path)
    output = tmp_path / "latest.json"
    output.write_text('{"last":"valid"}', encoding="utf-8")
    args = _args(module, sources, output)
    args.status = output

    with pytest.raises(ValueError, match="paths must be distinct"):
        module.run_monitor(args, now_fn=_now, sleep_fn=_unexpected_sleep)

    assert json.loads(output.read_text(encoding="utf-8")) == {"last": "valid"}


def test_latest_parity_uses_observation_time_not_a_pinned_filename(
    tmp_path: Path,
) -> None:
    module = _load()
    older = tmp_path / "xyz_brentoil_oil_shock_candle_parity_z.json"
    newer = tmp_path / "xyz_brentoil_oil_shock_candle_parity_a.json"
    older.write_text(json.dumps(_parity_artifact(100)), encoding="utf-8")
    newer.write_text(json.dumps(_parity_artifact(200)), encoding="utf-8")

    assert module.latest_brentoil_parity_path(tmp_path) == newer


def test_default_observer_uses_active_source_revision_recovery_epoch() -> None:
    """The monitor must read the same BRENTOIL status the active observer writes."""
    args = _load().build_parser().parse_args([])

    assert args.observer == Path(
        "data/runtime/research/brentoil_oil_shock_shadow_v2_latest.json"
    )


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_interval_fails_before_reading_sources(
    tmp_path: Path,
    value: float,
) -> None:
    module = _load()
    sources = _write_sources(tmp_path)
    args = _args(module, sources, tmp_path / "latest.json")
    args.interval_seconds = value

    with pytest.raises(ValueError, match="interval must be positive and finite"):
        module.run_monitor(args, now_fn=_now, sleep_fn=_unexpected_sleep)


def _args(
    module: ModuleType,
    paths: ExternalOpportunityPaths,
    output: Path,
) -> object:
    return module.build_parser().parse_args(
        [
            "--canary",
            str(paths.canary),
            "--development",
            str(paths.development),
            "--parity",
            str(paths.parity),
            "--observer",
            str(paths.observer),
            "--out",
            str(output),
            "--status",
            str(output.parent / "status.json"),
            "--once",
        ]
    )


def _load() -> ModuleType:
    spec = spec_from_file_location("cohort_external_opportunity_monitor_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load external-opportunity monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now() -> datetime:
    return datetime(2026, 8, 15, 20, 0, tzinfo=UTC)


def _parity_artifact(observed_at_ms: int) -> dict[str, object]:
    return {
        "schema_version": "hip3_prospective_candle_parity_v1",
        "scope": {
            "symbol": "xyz:BRENTOIL",
            "observed_at_ms": observed_at_ms,
        },
        "contract": {"report_only": True, "execution_authority": "none"},
    }


def _unexpected_sleep(_: float) -> None:
    raise AssertionError("one-shot monitor must not sleep")
