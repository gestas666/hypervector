"""Exact supplemental path-repair tests for prospective HIP-3 evidence."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.hip3_prospective_path_repair import (
    Hip3ProspectivePathRepairConfig,
    build_hip3_prospective_path_repair,
)

_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_SYMBOL = "xyz:SKHX"


def test_archive_repairs_only_the_unresolved_exact_bar() -> None:
    base = _base_audit()
    report = build_hip3_prospective_path_repair(
        base_audit=base,
        mark_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 3_000),
        l2_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 1_000),
        archive_evidence=_archive_evidence(),
        config=_config(),
    )

    assert report["technical_assessment"] == {
        "candle_ohlc_parity_resolved": False,
        "original_unresolved_bars": 1,
        "prospective_bar_path_coverage_resolved": True,
        "repaired_bars": 1,
        "unresolved_bars": 0,
    }
    assert report["bar_diagnostics"][0]["path_source"] == "live_prospective"
    repaired = report["bar_diagnostics"][1]
    assert repaired["path_source"] == "0xarchive_exact_exchange_history"
    assert repaired["original"]["resolved"] is False
    assert repaired["mark"]["maximum_gap_ms"] == 3_000
    assert repaired["l2"]["maximum_gap_ms"] == 1_000
    assert base == _base_audit()


def test_incomplete_supplement_remains_explicitly_unresolved() -> None:
    report = build_hip3_prospective_path_repair(
        base_audit=_base_audit(),
        mark_timestamps_ms=(_START_MS + _BAR_MS + 1_000,),
        l2_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 1_000),
        archive_evidence=_archive_evidence(),
        config=_config(),
    )

    assessment = report["technical_assessment"]
    assert assessment["prospective_bar_path_coverage_resolved"] is False
    assert assessment["repaired_bars"] == 0
    assert assessment["unresolved_bars"] == 1
    assert report["bar_diagnostics"][1]["path_source"] == "unresolved"


def test_repair_rejects_wrong_or_incomplete_archive_identity() -> None:
    wrong_symbol = _archive_evidence()
    wrong_symbol["symbol"] = "xyz:MU"
    with pytest.raises(ValueError, match="symbol"):
        _build(wrong_symbol)

    incomplete = _archive_evidence()
    incomplete["complete"] = False
    with pytest.raises(ValueError, match="complete"):
        _build(incomplete)


def test_repair_rejects_timestamp_outside_archive_bounds() -> None:
    marks = (*_timestamps(_START_MS + _BAR_MS, 3_000), _START_MS - 1)
    with pytest.raises(ValueError, match="outside repair bounds"):
        build_hip3_prospective_path_repair(
            base_audit=_base_audit(),
            mark_timestamps_ms=marks,
            l2_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 1_000),
            archive_evidence=_archive_evidence(),
            config=_config(),
        )


def test_repair_rejects_authoritative_or_malformed_base_audit() -> None:
    for mutation, message in (
        (("contract", "execution_authority", "live"), "authority"),
        (("source", "symbol", "xyz:MU"), "symbol"),
        (("technical_assessment", "unresolved_bars", 2), "unresolved"),
    ):
        base = _base_audit()
        base[mutation[0]][mutation[1]] = mutation[2]
        with pytest.raises(ValueError, match=message):
            build_hip3_prospective_path_repair(
                base_audit=base,
                mark_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 3_000),
                l2_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 1_000),
                archive_evidence=_archive_evidence(),
                config=_config(),
            )


def _build(evidence: dict[str, object]) -> dict[str, object]:
    return build_hip3_prospective_path_repair(
        base_audit=_base_audit(),
        mark_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 3_000),
        l2_timestamps_ms=_timestamps(_START_MS + _BAR_MS, 1_000),
        archive_evidence=evidence,
        config=_config(),
    )


def _config() -> Hip3ProspectivePathRepairConfig:
    return Hip3ProspectivePathRepairConfig(
        symbol=_SYMBOL,
        start_ms=_START_MS + _BAR_MS,
        end_ms=_START_MS + 2 * _BAR_MS,
    )


def _timestamps(start: int, cadence: int) -> tuple[int, ...]:
    return tuple(range(start, start + _BAR_MS, cadence))


def _archive_evidence() -> dict[str, object]:
    return {
        "complete": True,
        "market_family": "hip3",
        "symbol": _SYMBOL,
        "sha256": "a" * 64,
    }


def _base_audit() -> dict[str, object]:
    rows = [_bar(_START_MS, True), _bar(_START_MS + _BAR_MS, False)]
    return deepcopy(
        {
            "schema_version": "hip3_prospective_path_audit_v1",
            "mode": "prospective_public_venue_path_coverage",
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "promotion_authority": "none",
                "runtime_strategy_changed": False,
            },
            "source": {"symbol": _SYMBOL, "observed_at_ms": _START_MS + 3 * _BAR_MS},
            "coverage": {
                "first_full_bar_open_ms": _START_MS,
                "completed_bar_end_ms": _START_MS + 2 * _BAR_MS,
                "completed_bars": 2,
                "timeframe_minutes": 15,
            },
            "evidence_identity": {
                "completed_bar_trades": {"rows": 2, "sha256": "b" * 64}
            },
            "channels": {},
            "bar_diagnostics": rows,
            "technical_assessment": {
                "prospective_bar_path_coverage_resolved": False,
                "unresolved_bars": 1,
                "candle_ohlc_parity_resolved": False,
            },
            "limitations": [],
        }
    )


def _bar(start: int, resolved: bool) -> dict[str, object]:
    quality = {
        "observations": 2 if resolved else 1,
        "maximum_gap_ms": 1_000 if resolved else 10_000,
        "complete": resolved,
    }
    return {
        "bar_open_ms": start,
        "bar_close_ms": start + _BAR_MS,
        "mark": dict(quality),
        "l2": dict(quality),
        "resolved": resolved,
    }
