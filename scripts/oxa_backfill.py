"""Compatibility entry point for the packaged oxa_backfill tool."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.oxa_backfill")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
