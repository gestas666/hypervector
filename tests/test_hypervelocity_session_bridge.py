"""Telemetry-transition tests for the event-shadow ledger bridge."""

from hypervector.paper.hypervelocity_session_bridge import _new_annotations


def test_repeated_execution_annotation_is_emitted_once_until_recovery() -> None:
    emitted, latest = _new_annotations(
        None,
        ("execution_evidence_uncertain",),
    )
    repeated, latest = _new_annotations(
        latest,
        ("execution_evidence_uncertain",),
    )
    recovered, latest = _new_annotations(latest, ())
    emitted_again, latest = _new_annotations(
        latest,
        ("execution_evidence_uncertain",),
    )

    assert emitted == ("execution_evidence_uncertain",)
    assert repeated == ()
    assert recovered == ()
    assert emitted_again == ("execution_evidence_uncertain",)
    assert latest == "execution_evidence_uncertain"
