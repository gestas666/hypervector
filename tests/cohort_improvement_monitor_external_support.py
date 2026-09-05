"""Shared loading and evidence helpers for external improvement tests."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

_SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_improvement_monitor.py"


def contract() -> dict[str, object]:
    """Return the frozen report-only external-candidate contract."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def evidence(path: Path) -> dict[str, object]:
    """Describe one exact local evidence file without mutating it."""
    raw = path.read_bytes()
    return {"path": path.name, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def load_monitor() -> ModuleType:
    """Load the monitor script through the same test-local import boundary."""
    spec = spec_from_file_location("cohort_improvement_monitor_external", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
