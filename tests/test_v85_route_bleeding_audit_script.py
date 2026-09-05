"""CLI publication tests for the immutable V85 route audit."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/v85_route_bleeding_audit.py")


def test_publish_loads_every_frozen_prefix_and_writes_once(tmp_path: Path) -> None:
    """The command must rebuild from all eight frozen ledgers before publishing."""
    module = _module()
    preregistration = tmp_path / "prereg.json"
    output = tmp_path / "audit.json"
    preregistration.write_text(json.dumps(_preregistration()), encoding="utf-8")
    calls: list[str] = []

    def load_prefix(
        evidence: dict[str, object],
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        calls.append(str(evidence["path"]))
        return ([{"sequence": 1}], {"sha256": "a" * 64})

    module.load_frozen_jsonl_prefix = load_prefix
    module.audit_multi_asset_live_run = lambda *_args, **_kwargs: {"run": {}}
    module.build_route_bleeding_audit = lambda _audit, _prereg: {
        "contract": {"execution_authority": "none"}
    }
    args = argparse.Namespace(preregistration=preregistration, out=output)

    report, published = module.publish(args)

    assert calls == [
        "cohort.jsonl",
        "btc.jsonl",
        "eth.jsonl",
        "sol.jsonl",
        "hype.jsonl",
        "zec.jsonl",
        "spcx.jsonl",
        "sndk.jsonl",
    ]
    assert report["evidence"]["frozen_prefixes_verified"] is True
    assert published == output
    with pytest.raises(FileExistsError, match="immutable"):
        module.publish(args)


def test_parser_requires_preregistration_and_output() -> None:
    """The audit command has no mutable or live-arming mode."""
    module = _module()
    args = module.build_parser().parse_args(
        ["--preregistration", "frozen.json", "--out", "audit.json"]
    )

    assert args.preregistration == Path("frozen.json")
    assert args.out == Path("audit.json")
    assert not hasattr(args, "enabled")


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("V85 route bleeding audit script is missing")
    spec = spec_from_file_location("v85_route_bleeding_audit_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V85 route bleeding audit script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _preregistration() -> dict[str, object]:
    assets = {
        "BTC": {"path": "btc.jsonl"},
        "ETH": {"path": "eth.jsonl"},
        "SOL": {"path": "sol.jsonl"},
        "HYPE": {"path": "hype.jsonl"},
        "ZEC": {"path": "zec.jsonl"},
        "xyz:SPCX": {"path": "spcx.jsonl"},
        "xyz:SNDK": {"path": "sndk.jsonl"},
    }
    return {
        "execution_authority": "none",
        "automatic_strategy_mutation": False,
        "frozen_runtime_identity": {"run_id": "run-v85"},
        "frozen_cohort_ledger_prefix": {"path": "cohort.jsonl"},
        "frozen_asset_ledger_prefixes": assets,
    }
