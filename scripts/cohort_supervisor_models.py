"""Compatibility import for the packaged cohort_supervisor_models service."""
from importlib import import_module
import sys
_module = import_module("hypervector_supervision.cohort_supervisor_models")
sys.modules[__name__] = _module
