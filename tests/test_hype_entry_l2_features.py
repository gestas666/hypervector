"""Causal venue L2 feature tests for HYPE breakout entries."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import REST_L2_SOURCE
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hype_entry_l2_features import (
    HYPE_ENTRY_L2_FEATURES,
    build_hype_entry_l2_dataset,
    hype_l2_features_at_decision,
)


def test_builder_uses_only_covered_rows_and_preserves_exact_identity(
    tmp_path: Path,
) -> None:
    """Vendor gaps remain excluded and cannot be silently imputed."""
    raw = _raw_rows(2)
    covered = _audit_row(tmp_path, raw.iloc[0], status="covered")
    missing = _audit_row(tmp_path, raw.iloc[1], status="missing_pre_entry_snapshot")
    _write_bundle(Path(str(covered["bundle_path"])), raw.iloc[0])

    result = build_hype_entry_l2_dataset(raw, pd.DataFrame([covered, missing]))

    assert len(result.rows) == 1
    assert result.rows.iloc[0]["signal_time_utc"] == pd.Timestamp(
        str(raw.iloc[0]["signal_time_utc"])
    )
    assert result.report["coverage"]["covered_rows"] == 1
    assert result.report["coverage"]["excluded_rows"] == 1
    assert result.report["selection_bias"]["excluded"]["rows"] == 1
    assert set(HYPE_ENTRY_L2_FEATURES).issubset(result.rows.columns)


def test_post_entry_book_changes_only_execution_diagnostics(tmp_path: Path) -> None:
    """Post-fill observations cannot alter any model input feature."""
    raw = _raw_rows(1)
    audit = _audit_row(tmp_path, raw.iloc[0], status="covered")
    bundle = Path(str(audit["bundle_path"]))
    _write_bundle(bundle, raw.iloc[0], post_bid=100.2, post_ask=100.3)
    first = build_hype_entry_l2_dataset(raw, pd.DataFrame([audit]))
    _write_bundle(bundle, raw.iloc[0], post_bid=102.0, post_ask=102.1, replace=True)
    second = build_hype_entry_l2_dataset(raw, pd.DataFrame([audit]))

    pd.testing.assert_series_equal(
        first.rows.iloc[0][list(HYPE_ENTRY_L2_FEATURES)],
        second.rows.iloc[0][list(HYPE_ENTRY_L2_FEATURES)],
    )
    assert (
        first.rows.iloc[0]["l2_post_mid_move_bps"]
        != second.rows.iloc[0]["l2_post_mid_move_bps"]
    )


def test_features_directionalize_pressure_and_returns(tmp_path: Path) -> None:
    """Identical buy pressure is favorable for long and adverse for short."""
    raw = _raw_rows(2)
    raw.loc[1, ["signal_time_utc", "entry_time_utc", "exit_time_utc"]] = [
        "2026-01-01T01:00:00+00:00",
        "2026-01-01T01:01:00+00:00",
        "2026-01-01T02:01:00+00:00",
    ]
    raw.loc[1, "side"] = "short"
    raw.loc[1, "entry_side"] = "short"
    audits = [_audit_row(tmp_path, row, status="covered") for _, row in raw.iterrows()]
    for row, audit in zip(raw.to_dict("records"), audits, strict=True):
        _write_bundle(Path(str(audit["bundle_path"])), pd.Series(row))

    result = build_hype_entry_l2_dataset(raw, pd.DataFrame(audits))

    long_row, short_row = result.rows.iloc[0], result.rows.iloc[1]
    assert long_row["l2_aligned_imbalance_top5_latest"] > 0.0
    assert short_row["l2_aligned_imbalance_top5_latest"] < 0.0
    assert long_row["l2_aligned_mid_return_30s_bps"] > 0.0
    assert short_row["l2_aligned_mid_return_30s_bps"] < 0.0


def test_builder_rejects_identity_mismatch_and_crossed_books(tmp_path: Path) -> None:
    """A feature row cannot inherit another signal's book or invalid depth."""
    raw = _raw_rows(1)
    audit = _audit_row(tmp_path, raw.iloc[0], status="covered")
    mismatched = dict(audit)
    mismatched["side"] = "short"
    with pytest.raises(ValueError, match="identity"):
        build_hype_entry_l2_dataset(raw, pd.DataFrame([mismatched]))

    _write_bundle(Path(str(audit["bundle_path"])), raw.iloc[0], crossed=True)
    with pytest.raises(ValueError, match="crossed"):
        build_hype_entry_l2_dataset(raw, pd.DataFrame([audit]))


def test_builder_can_match_a_frozen_live_sampling_cadence(tmp_path: Path) -> None:
    """Archive snapshots are causally bucketed to the observed live cadence."""
    raw = _raw_rows(1)
    audit = _audit_row(tmp_path, raw.iloc[0], status="covered")
    _write_bundle(Path(str(audit["bundle_path"])), raw.iloc[0])

    result = build_hype_entry_l2_dataset(
        raw,
        pd.DataFrame([audit]),
        sampling_interval_ms=15_000,
    )

    assert result.rows.iloc[0]["l2_snapshot_rate_60s"] == pytest.approx(3.0 / 60.0)
    assert result.report["sampling"]["interval_ms"] == 15_000
    assert result.report["sampling"]["mode"] == "causal_last_snapshot_per_bucket"


def test_live_decision_features_match_vendor_formula(tmp_path: Path) -> None:
    """The prospective recorder path must reproduce frozen feature formulas."""
    raw = _raw_rows(1)
    audit = _audit_row(tmp_path, raw.iloc[0], status="covered")
    _write_bundle(Path(str(audit["bundle_path"])), raw.iloc[0])
    frozen = build_hype_entry_l2_dataset(
        raw,
        pd.DataFrame([audit]),
        sampling_interval_ms=1_000,
    ).rows.iloc[0]
    entry_ms = int(pd.Timestamp(raw.iloc[0]["entry_time_utc"]).timestamp() * 1_000)

    live = hype_l2_features_at_decision(
        _live_books(entry_ms),
        decision_time_ms=entry_ms,
        side="long",
        sampling_interval_ms=1_000,
    )

    assert list(live) == list(HYPE_ENTRY_L2_FEATURES)
    for name in HYPE_ENTRY_L2_FEATURES:
        assert live[name] == pytest.approx(float(frozen[name]))


def test_live_decision_features_exclude_at_or_after_boundary() -> None:
    """A book received for the next interval cannot alter the entry score."""
    entry_ms = 1_800_000
    baseline = hype_l2_features_at_decision(
        _live_books(entry_ms),
        decision_time_ms=entry_ms,
        side="long",
    )
    changed = (*_live_books(entry_ms), _live_book(entry_ms, 200.0, 200.1))

    observed = hype_l2_features_at_decision(
        changed,
        decision_time_ms=entry_ms,
        side="long",
    )

    assert observed == baseline


def _raw_rows(samples: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(samples):
        signal = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=index)
        rows.append(
            {
                "entry_side": "long",
                "side": "long",
                "signal_time_utc": signal.isoformat(),
                "entry_time_utc": (signal + pd.Timedelta(minutes=1)).isoformat(),
                "exit_time_utc": (signal + pd.Timedelta(hours=1)).isoformat(),
                "gross_return_bps": 20.0 if index == 0 else -10.0,
                "net_return_bps": 7.0 if index == 0 else -23.0,
                "exit_reason": "maximum_hold",
            }
        )
    return pd.DataFrame(rows)


def _audit_row(tmp_path: Path, row: pd.Series, *, status: str) -> dict[str, object]:
    entry = pd.Timestamp(str(row["entry_time_utc"]))
    identity = entry.strftime("%Y%m%dT%H%M%S")
    covered = status == "covered"
    return {
        "window_id": f"window-{identity}",
        "side": row["side"],
        "signal_time_utc": row["signal_time_utc"],
        "entry_time_utc": row["entry_time_utc"],
        "bundle_path": str(tmp_path / identity),
        "status": status,
        "manifest_complete": True,
        "row_count": 5 if covered else 0,
        "pre_entry_rows": 4 if covered else 0,
        "post_entry_rows": 1 if covered else 0,
        "last_pre_entry_age_ms": 100 if covered else None,
        "first_post_entry_delay_ms": 200 if covered else None,
        "causal_covered": covered,
        "execution_covered": covered,
    }


def _write_bundle(
    directory: Path,
    row: pd.Series,
    *,
    post_bid: float = 100.4,
    post_ask: float = 100.5,
    crossed: bool = False,
    replace: bool = False,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if replace:
        (directory / "books.jsonl.gz").unlink()
        (directory / "manifest.json").unlink()
    entry_ms = int(pd.Timestamp(str(row["entry_time_utc"])).timestamp() * 1_000)
    rows = [
        _book(entry_ms - 50_000, 100.0, 100.1),
        _book(entry_ms - 30_000, 100.1, 100.2),
        _book(entry_ms - 10_000, 100.2, 100.3),
        _book(entry_ms - 100, 100.3, 100.2 if crossed else 100.4),
        _book(entry_ms + 200, post_bid, post_ask),
    ]
    books = directory / "books.jsonl.gz"
    with gzip.open(books, "wt", encoding="utf-8") as handle:
        for payload in rows:
            handle.write(json.dumps(payload) + "\n")
    manifest = {
        "source": "0xarchive_hyperliquid_native_l2",
        "symbol": "HYPE",
        "complete": True,
        "continuation_cursor": None,
        "row_count": len(rows),
        "files": {"books.jsonl.gz": file_evidence(books)},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _book(timestamp_ms: int, bid: float, ask: float) -> dict[str, object]:
    bids = [
        {"px": f"{bid - level * 0.01:.2f}", "sz": str(8.0 - level), "n": 1}
        for level in range(5)
    ]
    asks = [
        {"px": f"{ask + level * 0.01:.2f}", "sz": str(2.0 + level), "n": 1}
        for level in range(5)
    ]
    return {
        "ts_exchange_ms": timestamp_ms,
        "symbol": "HYPE",
        "source": "0xarchive_hyperliquid_native_l2",
        "best_bid": str(bid),
        "best_ask": str(ask),
        "bids": bids,
        "asks": asks,
    }


def _live_books(entry_ms: int) -> tuple[L2SnapshotEvent, ...]:
    values = (
        (entry_ms - 50_000, 100.0, 100.1),
        (entry_ms - 30_000, 100.1, 100.2),
        (entry_ms - 10_000, 100.2, 100.3),
        (entry_ms - 100, 100.3, 100.4),
    )
    return tuple(_live_book(timestamp, bid, ask) for timestamp, bid, ask in values)


def _live_book(timestamp_ms: int, bid: float, ask: float) -> L2SnapshotEvent:
    bids = tuple(BookLevel(bid - level * 0.01, 8.0 - level, 1) for level in range(5))
    asks = tuple(BookLevel(ask + level * 0.01, 2.0 + level, 1) for level in range(5))
    return L2SnapshotEvent(
        "HYPE",
        timestamp_ms,
        timestamp_ms * 1_000_000,
        bids,
        asks,
        source=REST_L2_SOURCE,
    )
