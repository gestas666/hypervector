"""Compatibility entry point for the packaged hip3_roster_observer tool."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.hip3_roster_observer")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
