"""Command-surface tests for the immutable flow-exhaustion screen."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest


_SCRIPT = Path("scripts/flow_exhaustion_screen.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("flow_exhaustion_screen", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load flow-exhaustion script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _argv(output: Path) -> list[str]:
    return [
        "--database",
        "market.duckdb",
        "--start",
        "2025-08-04T00:00:00Z",
        "--end",
        "2026-01-28T00:00:00Z",
        "--segment",
        "development",
        "--btc-funding",
        "btc.parquet",
        "--sol-funding",
        "sol.parquet",
        "--out",
        str(output),
    ]


def test_parser_exposes_only_the_frozen_report_only_window(tmp_path: Path) -> None:
    """The runner must name every authority input and the preregistered segment."""
    args = _module().build_parser().parse_args(_argv(tmp_path / "result.json"))

    assert args.segment == "development"
    assert args.btc_funding == [Path("btc.parquet")]
    assert args.sol_funding == [Path("sol.parquet")]


def test_window_rejects_unregistered_dates() -> None:
    """Changing the frozen development boundary requires a new contract."""
    module = _module()
    args = module.build_parser().parse_args(
        [
            value if value != "2025-08-04T00:00:00Z" else "2025-08-05T00:00:00Z"
            for value in _argv(Path("result.json"))
        ]
    )

    with pytest.raises(ValueError, match="frozen development window"):
        module.validated_window(args)


def test_immutable_parquet_refuses_to_replace_existing_file(tmp_path: Path) -> None:
    """Sidecars must retain prior losing and winning runs alike."""
    module = _module()
    path = tmp_path / "signals.parquet"
    path.write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="immutable parquet"):
        module.write_immutable_parquet(path, pd.DataFrame({"value": [1]}))


def test_command_surface_has_no_live_execution_vocabulary() -> None:
    """The development runner must have no mechanism for placing orders."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
