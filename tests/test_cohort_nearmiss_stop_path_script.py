"""Publication-boundary tests for near-miss stop-path evidence."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.research.cohort_nearmiss_stop_path import NearMissPathSpec

_SCRIPT = Path("scripts/cohort_nearmiss_stop_path.py")


def test_publish_binds_both_stable_ledger_prefixes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Published evidence must identify both exact stable source prefixes."""
    module = _load_script()
    args = _args(tmp_path)
    snapshots = {
        args.decisions: ([{"event_type": "market_candles"}], _source("a")),
        args.asset_ledger: ([{"event_type": "book_observation"}], _source("b")),
    }

    @contextmanager
    def snapshot(
        path: Path, *, run_id: str
    ) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
        assert run_id == "run-a"
        yield snapshots[path]

    def build(
        cohort: object, asset: object, spec: NearMissPathSpec
    ) -> dict[str, object]:
        assert cohort == snapshots[args.decisions][0]
        assert asset == snapshots[args.asset_ledger][0]
        assert spec.run_id == "run-a"
        assert spec.target_bps == 60.0
        return {"status": "protective_stop_proxy_crossed"}

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(module, "build_nearmiss_stop_path", build)

    report = module.publish_path(args)

    assert report["evidence"] == {
        "cohort_ledger": {"path": str(args.decisions), **_source("a")},
        "asset_ledger": {"path": str(args.asset_ledger), **_source("b")},
    }
    generator_paths = {
        Path(row["path"]).name for row in report["generator_identity"]["files"]
    }
    assert "cohort_nearmiss_stop_path_reporting.py" in generator_paths
    assert len(report["generator_identity"]["files"]) == 5
    assert json.loads(args.out.read_text(encoding="utf-8")) == report


def test_source_recheck_failure_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source mutation at context exit must preempt immutable publication."""
    module = _load_script()
    args = _args(tmp_path)

    @contextmanager
    def snapshot(
        path: Path, *, run_id: str
    ) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
        del path, run_id
        yield ([{}], _source("c"))
        raise RuntimeError("ledger changed during snapshot")

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)

    def build(
        cohort: object, asset: object, spec: NearMissPathSpec
    ) -> dict[str, object]:
        del cohort, asset, spec
        return {"status": "protective_stop_proxy_crossed"}

    monkeypatch.setattr(module, "build_nearmiss_stop_path", build)

    with pytest.raises(RuntimeError, match="ledger changed"):
        module.publish_path(args)

    assert not args.out.exists()


def _source(fill: str) -> dict[str, object]:
    return {"bytes": 12, "sha256": fill * 64}


def _args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        decisions=tmp_path / "decisions.jsonl",
        asset_ledger=tmp_path / "hype.jsonl",
        run_id="run-a",
        profile_id="profile-a",
        profile_fingerprint="f" * 64,
        strategy_id="strategy-a",
        symbol="HYPE",
        side="long",
        decision_time_ms=1_000,
        available_time_ms=1_000,
        reference_price=100.0,
        stop_bps=80.0,
        target_bps=60.0,
        soft_maximum_hold_seconds=28_800,
        modeled_hurdle_bps=13.0,
        notional_usd=5_000.0,
        out=tmp_path / "report.json",
    )


def _load_script() -> ModuleType:
    spec = spec_from_file_location("cohort_nearmiss_stop_path_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
