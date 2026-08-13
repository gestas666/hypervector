"""CLI contracts for immutable v31 raw-ledger acceptance evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v31_raw_ledger_acceptance.py")


def test_script_persists_raw_rejection_and_returns_two(tmp_path: Path) -> None:
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    out = tmp_path / "raw.json"
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(out)]
    )
    module.build_v31_route_forward_snapshot = lambda *unused: {"phase": "candidate"}
    module.build_v31_poststart_acceptance = lambda *unused, **options: _aggregate()
    module.build_v31_raw_ledger_acceptance = lambda *unused, **options: _rejection()
    module._snapshot_inputs = _snapshots

    report = module.run(args)

    assert report["accepted"] is False
    assert module.exit_code(report) == 2
    assert json.loads(out.read_text(encoding="utf-8")) == report
    assert report["evidence"]["cohort_ledger_prefix"]["sha256"] == "cohort-hash"


def test_script_refuses_existing_immutable_output(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "raw.json"
    out.write_text("{}\n", encoding="utf-8")
    args = module.build_parser().parse_args(["--out", str(out)])

    with pytest.raises(FileExistsError, match="already exists"):
        module.run(args)


def _module() -> object:
    spec = spec_from_file_location("v31_raw_ledger_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v31 raw-ledger acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _aggregate() -> dict[str, object]:
    return {
        "accepted": True,
        "run": {
            "run_id": "v31-live-run",
            "profile_id": "multi_asset_bidirectional_swing_pruned_candidate_v31",
            "profile_fingerprint": "candidate-fingerprint",
        },
    }


def _rejection() -> dict[str, object]:
    return {
        "accepted": False,
        "decision": "rejected",
        "reasons": ["pressure_cutoff_mismatch"],
        "contract": {"execution_authority": "none"},
    }


@contextmanager
def _snapshots(
    unused_args: object, unused_run_id: str
) -> Iterator[
    tuple[
        list[dict[str, object]], dict[str, list[dict[str, object]]], dict[str, object]
    ]
]:
    del unused_args, unused_run_id
    yield (
        [],
        {},
        {
            "cohort_ledger_prefix": {"sha256": "cohort-hash"},
            "asset_ledger_prefixes": {},
        },
    )
