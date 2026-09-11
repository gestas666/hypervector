"""Legacy admission clocks must not be relabeled as final dispatch evidence."""

import pytest
from test_cohort_entry_age_diagnostics import _cycle, _identity

from hypervector.research.cohort_entry_age_diagnostics import (
    build_entry_age_diagnostics,
)


@pytest.mark.parametrize(
    "boundary,proven,status",
    [
        (None, False, "admission_check_observed"),
        ("engine_admission", False, "admission_check_observed"),
        ("adapter_dispatch", False, "adapter_dispatch_check_observed"),
        ("sdk_dispatch", True, "sdk_dispatch_contract_observed"),
    ],
)
def test_only_sdk_boundary_proves_dispatch_check(
    boundary: str | None, proven: bool, status: str
) -> None:
    """The same numeric clock supports different claims at different boundaries."""
    rows = _cycle(
        cutoff_age_ms=25_000,
        routing_age_ms=31_000,
        eligible=True,
        enter_action=True,
        submission_age_ms=29_000,
    )
    if boundary is not None:
        rows[0]["payload"]["actions"][0]["submission_boundary"] = boundary
    report = build_entry_age_diagnostics(rows, _identity())
    assert report["entry_submission_enforcement_observed"] is proven
    assert report["contract"]["entry_enforcement_changed"] is False
    assert report["sdk_dispatch_checks"] == int(proven)
    assert report["by_provider_symbol"]["provider_v1|BTC"]["status"] == status


@pytest.mark.parametrize(
    "boundary", [None, "engine_admission", "adapter_dispatch", "sdk_dispatch"]
)
def test_late_dispatch_proof_requires_the_dispatch_boundary(
    boundary: str | None,
) -> None:
    """An older unknown-stage clock cannot establish a final dispatch breach."""
    rows = _cycle(
        cutoff_age_ms=25_000,
        routing_age_ms=32_000,
        eligible=True,
        enter_action=True,
        submission_age_ms=31_000,
    )
    rows[0]["payload"]["actions"][0]["submission_boundary"] = boundary
    report = build_entry_age_diagnostics(rows, _identity())
    assert report["executed_late_entries_proven"] is (boundary == "sdk_dispatch")
    assert report["entry_submission_enforcement_observed"] is False


@pytest.mark.parametrize("boundary", ["venue_fill", [], True])
def test_unsupported_submission_boundary_is_rejected(boundary: object) -> None:
    """Unknown stages cannot quietly become accepted timestamp evidence."""
    rows = _cycle(
        cutoff_age_ms=25_000,
        routing_age_ms=31_000,
        eligible=True,
        enter_action=True,
        submission_age_ms=29_000,
    )
    rows[0]["payload"]["actions"][0]["submission_boundary"] = boundary
    with pytest.raises(ValueError, match="boundary"):
        build_entry_age_diagnostics(rows, _identity())


def test_named_submission_boundary_requires_actual_clock_evidence() -> None:
    """A stage label alone cannot turn an old entry into verified dispatch."""
    rows = _cycle(
        cutoff_age_ms=25_000,
        routing_age_ms=31_000,
        eligible=True,
        enter_action=True,
        submission_boundary="sdk_dispatch",
    )
    with pytest.raises(ValueError, match="lacks clock evidence"):
        build_entry_age_diagnostics(rows, _identity())


def test_mixed_legacy_and_sdk_entries_do_not_prove_complete_enforcement() -> None:
    """A newly instrumented entry must not retroactively certify older entries."""
    old = _cycle(
        cutoff_age_ms=25_000, routing_age_ms=31_000, eligible=True, enter_action=True
    )
    new = _cycle(
        cutoff_age_ms=25_000,
        routing_age_ms=31_000,
        eligible=True,
        enter_action=True,
        submission_age_ms=29_000,
        submission_boundary="sdk_dispatch",
    )
    report = build_entry_age_diagnostics(old + new, _identity())
    assert report["sdk_dispatch_checks"] == 1
    assert report["enter_actions"] == 2
    assert report["entry_submission_enforcement_observed"] is False
    assert report["by_provider_symbol"]["provider_v1|BTC"]["status"] == (
        "mixed_submission_boundaries_observed"
    )
