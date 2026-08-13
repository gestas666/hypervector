"""Contract tests for the report-only Market Cipher legacy audit."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/market_cipher_legacy_audit.py")


def _module() -> ModuleType:
    """Load the script as a module for contract testing."""
    spec = spec_from_file_location("market_cipher_legacy_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Market Cipher audit script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_requires_both_source_roots_and_output() -> None:
    """Source identity and immutable output path are mandatory."""
    with pytest.raises(SystemExit):
        _module()._parser().parse_args([])


def test_existing_output_is_rejected_before_source_access(tmp_path: Path) -> None:
    """An audit must not overwrite prior evidence."""
    output = tmp_path / "audit.json"
    output.write_text("existing\n", encoding="utf-8")
    argv = [
        "--mc-scalper-root",
        str(tmp_path / "missing-scalper"),
        "--market-cipher-cli-root",
        str(tmp_path / "missing-cli"),
        "--out",
        str(output),
    ]

    with pytest.raises(FileExistsError, match="output exists"):
        _module().main(argv)


def test_command_surface_has_no_execution_authority() -> None:
    """The legacy audit must remain structurally unable to place orders."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
