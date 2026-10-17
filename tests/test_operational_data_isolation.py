"""Unit tests must not depend on or mutate the operator's real trading data."""

import builtins
import io
from pathlib import Path

import pytest


@pytest.mark.parametrize("surface", ["live", "paper"])
@pytest.mark.parametrize("surface_api", ["builtin", "io", "pathlib"])
def test_unit_io_refuses_operational_data(surface: str, surface_api: str) -> None:
    """The refusal happens before opening any real file, including absent paths."""
    path = Path(__file__).resolve().parents[1] / "data" / surface / "unit-probe.jsonl"
    reader = {"builtin": builtins.open, "io": io.open, "pathlib": Path.open}[
        surface_api
    ]
    with pytest.raises(AssertionError, match="operational"):
        reader(path, "r")
