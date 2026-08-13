"""Operator-command contracts for exact v32 technical acceptance."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/v32_acceptance.py")


def test_script_persists_combined_rejection_without_execution_authority(
    tmp_path: Path,
) -> None:
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("{}\n", encoding="utf-8")
    out = tmp_path / "v32-acceptance.json"
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(out)]
    )
    module.build_v32_acceptance_snapshot = lambda *unused: {"phase": "v32"}
    module.build_v32_poststart_acceptance = lambda *unused, **options: _aggregate()
    module.build_v32_raw_ledger_acceptance = lambda *unused, **options: _raw()
    module._snapshot_inputs = _snapshots

    report = module.run(args)

    assert report["accepted"] is False
    assert report["decision"] == "rejected"
    assert report["execution_authority"] == "none"
    assert module.exit_code(report) == 2
    assert json.loads(out.read_text(encoding="utf-8")) == report
    assert report["evidence"]["journal"]["sha256"] == (
        "5630aefd980fdef8984d7a49ca9ed1b85a694370b69a7f14f1ef0c1d8e8a98f5"
    )


def test_script_refuses_to_replace_immutable_output(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "v32-acceptance.json"
    out.write_text("{}\n", encoding="utf-8")
    args = module.build_parser().parse_args(["--out", str(out)])

    with pytest.raises(FileExistsError, match="already exists"):
        module.run(args)


def _module() -> object:
    spec = spec_from_file_location("v32_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v32 acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _aggregate() -> dict[str, object]:
    return {
        "accepted": True,
        "decision": "accepted",
        "reasons": [],
        "run": {"run_id": "v32-live-run"},
    }


def _raw() -> dict[str, object]:
    return {
        "accepted": False,
        "decision": "rejected",
        "reasons": ["pressure_cutoff_mismatch"],
    }


@contextmanager
def _snapshots(
    unused_root: Path, unused_run_id: str
) -> Iterator[
    tuple[
        list[dict[str, object]], dict[str, list[dict[str, object]]], dict[str, object]
    ]
]:
    del unused_root, unused_run_id
    yield (
        [],
        {},
        {
            "cohort_ledger_prefix": {"sha256": "cohort-hash"},
            "asset_ledger_prefixes": {},
        },
    )
