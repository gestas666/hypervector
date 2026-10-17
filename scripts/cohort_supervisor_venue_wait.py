"""Compatibility import for the packaged cohort_supervisor_venue_wait service."""
from importlib import import_module
import sys
_module = import_module("hypervector_supervision.cohort_supervisor_venue_wait")
sys.modules[__name__] = _module
