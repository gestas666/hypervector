"""Compatibility import for the packaged cohort_supervisor_host service."""
from importlib import import_module
import sys
_module = import_module("hypervector_supervision.cohort_supervisor_host")
sys.modules[__name__] = _module

if __name__ == "__main__":
    raise SystemExit(_module.main())
