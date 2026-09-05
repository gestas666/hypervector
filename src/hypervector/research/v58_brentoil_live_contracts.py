"""Authority contracts for exact V58 BRENTOIL lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping


def require_v58_checkpoint_contract(contract: Mapping[str, object]) -> None:
    """Require the backend checkpoint's exact authority-none schema."""
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "balance_gate": False,
        "performance_gate": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 BRENTOIL checkpoint authority contract differs")
