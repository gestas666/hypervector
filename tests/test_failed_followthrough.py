"""Loss control must work before profit activation and respect completed evidence."""

import pytest

from hypervector.research.failed_followthrough import failed_followthrough


def test_losing_trade_can_exit_without_ever_arming_profit_protection() -> None:
    assert failed_followthrough(
        age_seconds=1800, current_bps=-51, peak_close_bps=10, initial_stop_bps=100
    )


@pytest.mark.parametrize(
    "age,pnl,peak", [(1799, -60, 0), (1800, -49, 0), (1800, -60, 25), (1800, 10, 20)]
)
def test_grace_adverse_threshold_and_prior_followthrough(
    age: int, pnl: float, peak: float
) -> None:
    assert not failed_followthrough(
        age_seconds=age, current_bps=pnl, peak_close_bps=peak, initial_stop_bps=100
    )


def test_nonfinite_evidence_is_rejected() -> None:
    with pytest.raises(ValueError):
        failed_followthrough(
            age_seconds=1800,
            current_bps=float("nan"),
            peak_close_bps=0,
            initial_stop_bps=100,
        )
