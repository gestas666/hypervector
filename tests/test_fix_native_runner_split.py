"""The recorded-runner cases are split for ``--dist loadfile`` without losing a case.

Each case runs one full configured seven-asset recorded poll (about 5 s), and loadfile keeps a
module on one worker, so the modules are kept small enough not to serialize the suite. These
checks pin the split to exactly the original case matrix.
"""

import pytest
import test_native_runner_partial_protection_crypto as partial_crypto
import test_native_runner_partial_protection_hip3 as partial_hip3
import test_native_runner_protective_control_first_side as protective_first
import test_native_runner_protective_control_last_side as protective_last
from native_runner_protective_case_fixture import CASES as PROTECTIVE_CASES
from test_native_partial_protective_execution import CASES as PARTIAL_CASES

# Recorded-runner polls per module; about 5 s each, so a module stays near 40 s or less.
MAX_RECORDED_POLLS_PER_MODULE = 8
PROTECTIVE_TEST = "test_protective_exit_precedes_recorded_acquisition_and_final_cohort_snapshot"
PARTIAL_TEST = "test_partial_protection_precedes_recorded_acquisition_and_truthful_final_state"


def _parametrized_cases(module: object, name: str) -> list[tuple[object, ...]]:
    marks = [mark for mark in getattr(module, name).pytestmark if mark.name == "parametrize"]
    assert len(marks) == 1
    return [tuple(case) for case in marks[0].args[1]]


def test_partial_protection_modules_partition_the_original_cases() -> None:
    """Crypto and HIP-3 modules together run every partial case exactly once."""
    crypto = _parametrized_cases(partial_crypto, PARTIAL_TEST)
    hip3 = _parametrized_cases(partial_hip3, PARTIAL_TEST)
    assert sorted(crypto + hip3) == sorted(PARTIAL_CASES)
    assert not set(crypto) & set(hip3)
    assert all(symbol.startswith("xyz:") for symbol, _kind, _side in hip3)
    assert not any(symbol.startswith("xyz:") for symbol, _kind, _side in crypto)
    remainder = "test_runner_exposes_unprotected_stop_remainder_and_its_pending_exit"
    assert callable(getattr(partial_crypto, remainder))
    assert len(crypto) + 1 <= MAX_RECORDED_POLLS_PER_MODULE
    assert len(hip3) <= MAX_RECORDED_POLLS_PER_MODULE


@pytest.mark.parametrize(
    "module,last_side", [(protective_first, False), (protective_last, True)]
)
def test_protective_control_modules_cover_both_sides_of_every_case(
    module: object, last_side: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each side module runs the full protective matrix with its own fixed entry side."""
    assert _parametrized_cases(module, PROTECTIVE_TEST) == [tuple(c) for c in PROTECTIVE_CASES]
    assert len(PROTECTIVE_CASES) <= MAX_RECORDED_POLLS_PER_MODULE
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        module,
        "assert_protective_exit_final_cohort",
        lambda root, symbol, kind, *, last_side: calls.append((root, symbol, kind, last_side)),
    )
    getattr(module, PROTECTIVE_TEST)("root", "BTC", "stop")
    assert calls == [("root", "BTC", "stop", last_side)]
