"""Compatibility entry point for the packaged cohort_resume_after_reboot tool."""

from importlib import import_module
import sys

_service = import_module("hypervector_supervision.cohort_resume_after_reboot")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
