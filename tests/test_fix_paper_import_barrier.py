"""Paper/shadow entry points never load signing or live execution modules.

The textual scan in ``test_paper_no_submit`` only covers ``hypervector/paper``.
This check imports every paper entry point in a fresh interpreter and inspects
``sys.modules`` so transitive imports through shared strategy, data, regime or
command modules are covered too (SRS_HV1_HONESTY).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAPER_SPECS = REPO / "src" / "hypervector" / "commands" / "specs" / "paper"

# Engine and command entry points of the paper/shadow path, plus the modules
# those functions import lazily at call time.
ENTRY_MODULES = (
    "hypervector.paper",
    "hypervector.paper.runner",
    "hypervector.paper.session",
    "hypervector.paper.report",
    "hypervector.paper.live_node",
    "hypervector.paper.event_stream_pump",
    "hypervector.paper.warmup",
    "hypervector.runtime_lock",
    "hypervector.ml.metalabel",
    "hypervector.ml.features",
    "hypervector.data.hl",
    "hypervector.data.pipeline",
    "hypervector.commands.paper",
)
# ``paper check`` reads live readiness metadata on purpose; nothing else may load.
ALLOWED_LIVE = frozenset({"hypervector.live", "hypervector.live.policy"})
FORBIDDEN_PREFIXES = (
    "hypervector.live",
    "eth_account",
    "hyperliquid.exchange",
    "hyperliquid.utils.signing",
    "nautilus_trader.adapters.hyperliquid",
)


def _spec_handler_modules() -> list[str]:
    """Return in-process handler modules declared by the paper command specs."""
    modules: set[str] = set()
    for spec_path in sorted(PAPER_SPECS.glob("*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        target = spec.get("handler")
        if isinstance(target, str) and ":" in target:
            modules.add(target.split(":", 1)[0])
    return sorted(modules)


def test_paper_entry_points_do_not_load_signing_or_execution_modules() -> None:
    modules = sorted(set(ENTRY_MODULES) | set(_spec_handler_modules()))
    assert "hypervector.commands.paper" in modules
    program = "\n".join(
        (
            "import importlib, json, sys",
            f"sys.path[:0] = {[str(REPO / 'src'), str(REPO / 'scripts')]!r}",
            f"for name in {modules!r}:",
            "    importlib.import_module(name)",
            # paper check imports live readiness metadata at call time.
            "importlib.import_module('hypervector.live.policy')",
            "import hypervector",
            "print(json.dumps({'origin': hypervector.__file__, 'modules': sorted(sys.modules)}))",
        )
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert Path(report["origin"]).resolve().is_relative_to(REPO / "src")
    loaded = report["modules"]
    assert "hypervector.paper.runner" in loaded
    offenders = [
        name
        for name in loaded
        if name.startswith(FORBIDDEN_PREFIXES) and name not in ALLOWED_LIVE
    ]
    assert offenders == [], f"paper path loaded execution/signing modules: {offenders}"
