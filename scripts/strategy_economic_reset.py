"""Compatibility entry for the packaged read-only accounting report."""
from importlib import import_module
import sys
_module = import_module("hypervector.operations.strategy_economic_reset")
sys.modules[__name__] = _module
if __name__ == "__main__":
    raise SystemExit(_module.main())
