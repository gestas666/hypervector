"""Compatibility entry point for the packaged cohort_transition_drain_archive tool."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.cohort_transition_drain_archive")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
