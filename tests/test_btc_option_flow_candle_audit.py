"""Tests for outcome-blind BTC option-flow candle cadence audits."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_option_flow_candle_audit import (
    audit_candle_cadence,
    build_candle_source_record,
)


def test_cadence_audit_classifies_every_missing_run_against_bound() -> None:
    """Every absent minute must be registered as repairable or rejected."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    expected = pd.date_range(start, periods=12, freq="1min")
    observed = expected.delete([2, 3, 7, 8, 9])
    frame = pd.DataFrame({"timestamp": observed})

    audit = audit_candle_cadence(
        frame,
        start=start,
        end=start + pd.Timedelta(minutes=12),
        maximum_repair_minutes=2,
    )

    assert audit.expected_rows == 12
    assert audit.observed_rows == 7
    assert audit.missing_rows == 5
    assert audit.gap_run_count == 2
    assert audit.maximum_gap_minutes == 3
    assert audit.repairable_missing_rows == 2
    assert audit.rejected_missing_rows == 3
    assert audit.contract_pass is False
    assert [gap.minutes for gap in audit.gaps] == [2, 3]
    assert [gap.repairable for gap in audit.gaps] == [True, False]


def test_cadence_audit_rejects_leading_gap_even_inside_duration_bound() -> None:
    """A bounded leading gap cannot be carry-forward repaired causally."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    timestamps = pd.date_range(start + pd.Timedelta(minutes=1), periods=4, freq="1min")

    audit = audit_candle_cadence(
        pd.DataFrame({"timestamp": timestamps}),
        start=start,
        end=start + pd.Timedelta(minutes=5),
        maximum_repair_minutes=2,
    )

    assert audit.leading_gap is True
    assert audit.contract_pass is False


def test_cadence_audit_accepts_unique_complete_or_bounded_internal_gaps() -> None:
    """Ordered unique bounds with only bounded internal gaps satisfy the source gate."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    expected = pd.date_range(start, periods=5, freq="1min")

    audit = audit_candle_cadence(
        pd.DataFrame({"timestamp": expected.delete(2)}),
        start=start,
        end=start + pd.Timedelta(minutes=5),
        maximum_repair_minutes=2,
    )

    assert audit.contract_pass is True
    assert audit.repairable_missing_rows == 1
    assert audit.rejected_missing_rows == 0


def test_source_record_binds_expected_contract_result_and_evidence() -> None:
    """A source record must retain exact evidence and the expected gate result."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    expected = pd.date_range(start, periods=5, freq="1min")

    record = build_candle_source_record(
        pd.DataFrame({"timestamp": expected.delete(2)}),
        source_revision="outcome_blind_v2",
        start=start,
        end=start + pd.Timedelta(minutes=5),
        maximum_repair_minutes=2,
        expected_contract_pass=True,
        evidence={"sha256": "abc", "raw_reproduction_matches": True},
    )

    assert record["source_revision"] == "outcome_blind_v2"
    assert record["expected_contract_pass"] is True
    assert record["audit"]["contract_pass"] is True
    assert record["evidence"] == {
        "sha256": "abc",
        "raw_reproduction_matches": True,
    }


def test_source_record_fails_when_observed_gate_differs_from_contract() -> None:
    """A caller cannot register a failing source as an expected pass."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    timestamps = pd.date_range(start + pd.Timedelta(minutes=1), periods=4, freq="1min")

    with pytest.raises(ValueError, match="contract result differs"):
        build_candle_source_record(
            pd.DataFrame({"timestamp": timestamps}),
            source_revision="invalid",
            start=start,
            end=start + pd.Timedelta(minutes=5),
            maximum_repair_minutes=2,
            expected_contract_pass=True,
            evidence={},
        )
