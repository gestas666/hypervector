"""Compatibility import for the packaged cohort_backend_supervisor service."""
from importlib import import_module
import sys
_module = import_module("hypervector_supervision.cohort_backend_supervisor")
sys.modules[__name__] = _module

if __name__ == "__main__":
    raise SystemExit(_module.main())
