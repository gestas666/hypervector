"""Compatibility entry point for the packaged cohort_runtime_validation_check tool."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.cohort_runtime_validation_check")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
