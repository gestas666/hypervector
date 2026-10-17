"""Synthetic owned protective receipts with real recorded acquisition: last executable side.

Entries take the last sorted executable side of each symbol's provider (``last_side=True``).
The first-side cases run from ``test_native_runner_protective_control_first_side.py``; the
split lets ``--dist loadfile`` place these full recorded polls on separate workers.
"""

from pathlib import Path

import pytest
from native_runner_protective_case_fixture import CASES, assert_protective_exit_final_cohort
from test_native_replay_adapter import deny_external_ports

__all__ = ["deny_external_ports"]


@pytest.mark.parametrize("symbol,kind", CASES)
def test_protective_exit_precedes_recorded_acquisition_and_final_cohort_snapshot(
    tmp_path: Path, symbol: str, kind: str
) -> None:
    """The actual runner must publish its cleaned final account after an owned exit."""
    assert_protective_exit_final_cohort(tmp_path, symbol, kind, last_side=True)
