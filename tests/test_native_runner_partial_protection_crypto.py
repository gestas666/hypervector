"""Partial protective executions reach the real seven-engine runner: crypto perp symbols.

The HIP-3 symbols run from ``test_native_runner_partial_protection_hip3.py``; the split lets
``--dist loadfile`` place the two halves of these full recorded polls on separate workers.
"""

from pathlib import Path

import pytest
from native_runner_partial_case_fixture import (
    assert_partial_protection_final_state,
    final_cohort,
    partial_case,
)
from test_native_partial_protective_execution import CASES, assert_partial_economics
from test_native_replay_adapter import deny_external_ports

__all__ = ["deny_external_ports"]
CRYPTO_CASES = [case for case in CASES if not case[0].startswith("xyz:")]


@pytest.mark.parametrize("symbol,kind,last_side", CRYPTO_CASES)
def test_partial_protection_precedes_recorded_acquisition_and_truthful_final_state(
    tmp_path: Path, symbol: str, kind: str, last_side: bool
) -> None:
    """The configured runner publishes the reduced protected target or completed stop exit."""
    assert_partial_protection_final_state(tmp_path, symbol, kind, last_side)


def test_runner_exposes_unprotected_stop_remainder_and_its_pending_exit(
    tmp_path: Path,
) -> None:
    """A partial follow-up IOC cannot appear flat or protected while its exit remains owed."""
    case = partial_case(tmp_path, "BTC", "stop", False, partial_close=True)
    assert case.runner.poll_once() == 0
    cohort = final_cohort(case)
    asset = next(row for row in cohort["assets"] if row["symbol"] == "BTC")
    assert cohort["open_position_count"] == 1
    assert asset["state"] == "EXIT_PENDING"
    assert asset["protective_exit_pending"] is True
    assert asset["stop_protection"] == "missing"
    assert asset["opened_at_ms"] == case.original.opened_at_ms
    assert asset["position_size_signed"] == case.replay.engines["BTC"].snapshot.position_size_signed
    assert case.replay.mutations.count("close") == 1
    assert_partial_economics(case.replay)
