"""Read-only execution capability metadata without importing execution clients."""

from importlib.util import find_spec


def is_submit_wired() -> bool:
    """Report installed execution code, without claiming operational readiness."""
    return find_spec("hypervector.live.exec_client") is not None
