"""hypervector.nautilus must not import NautilusTrader/plotly until an engine name is used."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import hypervector.nautilus as nautilus_pkg

# Probe this checkout's sources, not whatever editable install the interpreter
# would otherwise resolve.
_SRC = Path(__file__).resolve().parents[1] / "src"

_PROBE = """
import json, sys
import {module}
import hypervector
print(json.dumps({{
    "pkg_file": hypervector.__file__,
    "nautilus_trader": "nautilus_trader" in sys.modules,
    "plotly": "plotly" in sys.modules,
    "actor": "hypervector.nautilus.actor" in sys.modules,
    "runner": "hypervector.nautilus.runner" in sys.modules,
}}))
"""


def _probe(module: str) -> dict[str, bool]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_SRC), *filter(None, [env.get("PYTHONPATH")])]
    )
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
        env=env,
    )
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    assert Path(loaded.pop("pkg_file")).resolve().is_relative_to(_SRC)
    return loaded


def test_margin_math_import_does_not_load_engine() -> None:
    loaded = _probe("hypervector.nautilus.hyperliquid_margin")
    assert loaded == {
        "nautilus_trader": False,
        "plotly": False,
        "actor": False,
        "runner": False,
    }


def test_load_export_import_does_not_load_engine() -> None:
    loaded = _probe("hypervector.nautilus.load_export")
    assert loaded["nautilus_trader"] is False
    assert loaded["actor"] is False


def test_light_helper_modules_do_not_load_engine() -> None:
    for module in (
        "hypervector.nautilus.errors",
        "hypervector.nautilus.venue_spec",
        "hypervector.nautilus.costs",
    ):
        loaded = _probe(module)
        assert loaded["nautilus_trader"] is False, module


def test_package_exports_resolve_lazily() -> None:
    # Every public name still resolves through the package.
    for name in nautilus_pkg.__all__:
        assert getattr(nautilus_pkg, name) is not None
    from hypervector.nautilus import (  # noqa: F401
        HypervectorStrategy,
        Phase2StubConfig,
        load_strategy_loadout,
        run_phase2_backtest,
    )

    assert set(nautilus_pkg.__all__) <= set(dir(nautilus_pkg))


def test_unknown_attribute_raises_attribute_error() -> None:
    try:
        nautilus_pkg.no_such_export  # noqa: B018
    except AttributeError as exc:
        assert "no_such_export" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("expected AttributeError")
