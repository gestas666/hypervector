"""Publication tests for immutable HYPE-native exact-depth paths."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_counterfactual_path.py")


def test_publish_binds_stable_sources_and_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Publication must freeze both active-ledger prefixes and its generator."""
    module = _load_script()
    args = _args(tmp_path)
    sources = {
        args.decisions: ([{"event_type": "configuration_identity"}], _source("a")),
        args.asset_ledger: ([{"event_type": "configuration_identity"}], _source("b")),
    }

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        assert run_id == "run-v53"
        yield sources[path]

    def build(cohort: object, asset: object, spec: object) -> dict[str, object]:
        assert cohort == sources[args.decisions][0]
        assert asset == sources[args.asset_ledger][0]
        assert getattr(spec, "candidate_strategy_id") == "native-v2"
        return {"status": "open_counterfactual_path"}

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(module, "build_hype_native_counterfactual_path", build)

    report = module.publish_path(args)

    assert report["evidence"]["cohort_ledger"]["sha256"] == "a" * 64
    assert report["evidence"]["asset_ledger"]["sha256"] == "b" * 64
    assert len(report["generator_identity"]["files"]) >= 4
    assert json.loads(args.out.read_text(encoding="utf-8")) == report


def test_failed_source_recheck_leaves_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changing append-only prefix must abort before immutable publication."""
    module = _load_script()
    args = _args(tmp_path)

    @contextmanager
    def snapshot(path: Path, *, run_id: str) -> Iterator[tuple[object, object]]:
        del path, run_id
        yield ([{}], _source("c"))
        raise RuntimeError("source changed")

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(
        module,
        "build_hype_native_counterfactual_path",
        lambda *_args: {"status": "open_counterfactual_path"},
    )

    with pytest.raises(RuntimeError, match="source changed"):
        module.publish_path(args)

    assert not args.out.exists()


def _args(tmp_path: Path) -> object:
    module = _load_script()
    return module.build_parser().parse_args(
        [
            "--decisions",
            str(tmp_path / "decisions.jsonl"),
            "--asset-ledger",
            str(tmp_path / "hype.jsonl"),
            "--run-id",
            "run-v53",
            "--profile-id",
            "profile-v53",
            "--profile-fingerprint",
            "c" * 64,
            "--source-strategy-id",
            "source-v53",
            "--candidate-strategy-id",
            "native-v2",
            "--side",
            "long",
            "--decision-time-ms",
            "60000",
            "--notional-usd",
            "1250",
            "--stop-bps",
            "80",
            "--maximum-entry-delay-ms",
            "60000",
            "--maximum-exit-delay-ms",
            "60000",
            "--soft-hold-seconds",
            "28800",
            "--hard-hold-seconds",
            "86400",
            "--fee-bps-per-side",
            "4.32",
            "--residual-slippage-bps-per-side",
            "2",
            "--maximum-clock-skew-ms",
            "2000",
            "--horizons-minutes",
            "5,15,60,240,480",
            "--out",
            str(tmp_path / "report.json"),
        ]
    )


def _source(fill: str) -> dict[str, object]:
    return {"bytes": 12, "sha256": fill * 64}


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_counterfactual_path_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
