"""Command contract for the immutable HIP-3 early-adverse experiment."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

_SCRIPT = Path("scripts/hip3_early_adverse_exit_experiment.py")
_SPEC = importlib.util.spec_from_file_location("hip3_early_adverse_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_parser_fixes_the_preregistered_source_and_three_policy_scope() -> None:
    args = _MODULE.build_parser().parse_args([])

    assert args.source.name == (
        "hip3_swing_ha_transfer_sndk_gold_disabled_brent_v1.json"
    )
    assert args.output.name.startswith("hip3_early_adverse_ha_flip_")
    assert args.trades_output.name.endswith(".trades.parquet")


def test_command_refuses_to_replace_any_existing_evidence(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    output.write_text("preserve", encoding="utf-8")
    args = _MODULE.build_parser().parse_args(
        [
            "--source",
            str(tmp_path / "missing.json"),
            "--output",
            str(output),
            "--trades-output",
            str(tmp_path / "trades.parquet"),
        ]
    )

    with pytest.raises(FileExistsError, match="immutable HIP-3 exit outputs"):
        _MODULE.run_command(args)

    assert output.read_text(encoding="utf-8") == "preserve"
