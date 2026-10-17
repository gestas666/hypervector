"""Compatibility entry point for the packaged hip3_pressure_dependency_group service."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.hip3_pressure_dependency_group")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
