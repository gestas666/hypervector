"""Partial protective executions reach the real seven-engine runner: HIP-3 symbols.

The crypto perp symbols run from ``test_native_runner_partial_protection_crypto.py``; the split
lets ``--dist loadfile`` place the two halves of these full recorded polls on separate workers.
"""

from pathlib import Path

import pytest
from native_runner_partial_case_fixture import assert_partial_protection_final_state
from test_native_partial_protective_execution import CASES
from test_native_replay_adapter import deny_external_ports

__all__ = ["deny_external_ports"]
HIP3_CASES = [case for case in CASES if case[0].startswith("xyz:")]


@pytest.mark.parametrize("symbol,kind,last_side", HIP3_CASES)
def test_partial_protection_precedes_recorded_acquisition_and_truthful_final_state(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """The configured runner publishes the reduced protected target or completed stop exit."""
    assert_partial_protection_final_state(tmp_path, symbol, kind, last_side)
