"""Compatibility entry point for the packaged multi_asset_bidirectional_observer_checkpoint service."""

from importlib import import_module
import sys

_service = import_module("hypervector.operations.multi_asset_bidirectional_observer_checkpoint")
if __name__ == "__main__":
    raise SystemExit(_service.main())
sys.modules[__name__] = _service
