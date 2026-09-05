"""Floating-point integrity checks for V58 route readiness."""

from hypervector.research.v58_route_opportunity import parse_route_opportunity


def test_parser_accepts_machine_scale_readiness_roundoff() -> None:
    """A computed mean may exceed an equal endpoint by floating-point ulps."""
    readiness = {
        "count": 24,
        "eligible": 0,
        "first_fraction": 0.8,
        "minimum_fraction": 0.8,
        "mean_fraction": 0.8000000000000002,
        "latest_fraction": 0.8,
        "maximum_fraction": 0.8,
        "progressions": 0,
        "regressions": 0,
        "state_transitions": 0,
        "unchanged": 23,
        "blockers": {"fresh_breakout_onset_absent": 24},
        "reasons": {"fresh_breakout_onset_absent": 24},
        "latest_reason": "fresh_breakout_onset_absent",
        "latest_side": None,
    }
    score = {"research_state": "unresolved", "confidence": "low"}

    result = parse_route_opportunity("provider|xyz:SP500", readiness, score)

    assert result.mean_fraction == 0.8000000000000002
