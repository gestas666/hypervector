"""Compatibility entry point for the packaged cohort_prechange_backup tool."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.cohort_prechange_backup")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
