"""Report-only HIP-3 mark-source parity tests."""

from __future__ import annotations

import pytest

from hypervector.research.hip3_mark_source_parity import (
    Hip3MarkParitySpec,
    build_hip3_mark_source_parity,
)


def test_resolved_overlap_reports_one_to_one_mark_parity() -> None:
    """Independent nearby rows resolve without granting execution authority."""
    report = build_hip3_mark_source_parity(
        _paired_rows((1000, 4000, 7000), (1100, 3900, 7100)),
        Hip3MarkParitySpec("xyz:SP500", 250, 3, 1.0),
    )

    assert report["status"] == "resolved"
    assert report["parity_passed"] is True
    assert report["matched_pairs"] == 3
    assert report["maximum_pair_age_ms"] == 100.0
    symmetric_bps = abs(100.005 - 100.0) / ((100.005 + 100.0) / 2.0) * 10_000.0
    assert report["maximum_mark_difference_bps"] == pytest.approx(symmetric_bps)
    assert report["execution_authority"] == "none"
    assert report["automatic_live_change"] is False


def test_missing_websocket_overlap_is_explicitly_unresolved() -> None:
    """REST cadence alone cannot claim transport parity."""
    rows = tuple(_row("rest", value, 100.0) for value in (1000, 4000, 7000))

    report = build_hip3_mark_source_parity(
        rows, Hip3MarkParitySpec("xyz:SP500", 250, 3, 1.0)
    )

    assert report["status"] == "insufficient_overlap"
    assert report["parity_passed"] is False
    assert report["matched_pairs"] == 0
    assert report["websocket_rows"] == 0


def test_one_websocket_row_cannot_be_reused_to_inflate_overlap() -> None:
    """One-to-one matching preserves the independent-pair count."""
    rows = (
        _row("rest", 1000, 100.0),
        _row("rest", 1100, 100.0),
        _row("ws", 1050, 100.0),
    )

    report = build_hip3_mark_source_parity(
        rows, Hip3MarkParitySpec("xyz:SP500", 100, 2, 1.0)
    )

    assert report["matched_pairs"] == 1
    assert report["status"] == "insufficient_overlap"


def test_resolved_overlap_can_falsify_price_parity() -> None:
    """Sufficient overlap stays resolved while an excessive delta fails parity."""
    rows = _paired_rows((1000, 4000, 7000), (1000, 4000, 7000), ws_price=99.0)

    report = build_hip3_mark_source_parity(
        rows, Hip3MarkParitySpec("xyz:SP500", 100, 3, 1.0)
    )

    assert report["status"] == "resolved"
    assert report["parity_passed"] is False
    assert report["maximum_mark_difference_bps"] > 100.0


def test_conflicting_same_source_receipt_is_rejected() -> None:
    """A source cannot assert two prices at one exact receipt boundary."""
    rows = (
        _row("rest", 1000, 100.0),
        _row("rest", 1000, 101.0),
        _row("ws", 1000, 100.0),
    )

    with pytest.raises(ValueError, match="conflicting duplicate"):
        build_hip3_mark_source_parity(
            rows, Hip3MarkParitySpec("xyz:SP500", 100, 1, 1.0)
        )


def _paired_rows(
    rest_times: tuple[int, ...],
    ws_times: tuple[int, ...],
    *,
    ws_price: float = 100.005,
) -> tuple[dict[str, object], ...]:
    return tuple(_row("rest", value, 100.0) for value in rest_times) + tuple(
        _row("ws", value, ws_price) for value in ws_times
    )


def _row(source: str, received_ms: int, mark_price: float) -> dict[str, object]:
    identities = {
        "rest": "hyperliquid_info_metaAndAssetCtxs",
        "ws": "hyperliquid_ws_activeAssetCtx",
    }
    return {
        "symbol": "xyz:SP500",
        "received_ts_ns": received_ms * 1_000_000,
        "mark_price": mark_price,
        "source": identities[source],
    }
