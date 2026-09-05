"""Outcome-blind BTC liquidation treatment-episode tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence


def _write_bundle(
    root: Path,
    name: str,
    start: datetime,
    end: datetime,
    rows: list[dict[str, object]],
) -> Path:
    bundle = root / name
    bundle.mkdir()
    labels = bundle / "liquidations.jsonl.gz"
    with gzip.open(labels, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 2,
        "normalization_version": "explicit_vendor_direction_v2",
        "source": "0xarchive_hyperliquid_liquidations",
        "symbol": "BTC",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "event_count": len(rows),
        "complete": True,
        "continuation_cursor": None,
        "files": {labels.name: file_evidence(labels)},
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _row(timestamp: datetime, direction: str, trade_id: int) -> dict[str, object]:
    price = "10" if direction == "long" else "11"
    return {
        "ts_exchange_ms": int(timestamp.timestamp() * 1_000),
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "symbol": "BTC",
        "liquidated_direction": direction,
        "vendor_direction": "Close Long" if direction == "long" else "Close Short",
        "exchange_side": "A" if direction == "long" else "B",
        "price": price,
        "size": "2",
        "notional_usd": str(Decimal(price) * Decimal("2")),
        "trade_id": trade_id,
        "tx_hash": f"0x{trade_id}",
        "source": "0xarchive_hyperliquid_liquidations",
        "normalization_version": "explicit_vendor_direction_v2",
    }


def test_episode_clustering_is_same_direction_and_two_second_causal() -> None:
    """Interleaved directions stay separate and gaps above two seconds reset."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(1_000, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(1_500, "short", Decimal("20"), Decimal("1"), 2),
        LiquidationLabel(2_500, "long", Decimal("12"), Decimal("2"), 3),
        LiquidationLabel(5_001, "long", Decimal("11"), Decimal("1"), 4),
        LiquidationLabel(5_002, "short", Decimal("21"), Decimal("1"), 5),
    )

    episodes = build_liquidation_episodes(labels)

    assert [
        (
            row.direction,
            row.start_ms,
            row.end_ms,
            row.trade_count,
            row.notional_usd,
        )
        for row in episodes
    ] == [
        ("long", 1_000, 2_500, 2, Decimal("34")),
        ("short", 1_500, 1_500, 1, Decimal("20")),
        ("long", 5_001, 5_001, 1, Decimal("11")),
        ("short", 5_002, 5_002, 1, Decimal("21")),
    ]


def test_episode_preserves_exact_size_and_volume_weighted_price() -> None:
    """Episode VWAP must remain derived from exact decimal notional and size."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(1_000, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(2_000, "long", Decimal("12"), Decimal("2"), 2),
    )

    episode = build_liquidation_episodes(labels)[0]

    assert episode.total_size == Decimal("3")
    assert episode.volume_weighted_price == Decimal("34") / Decimal("3")


def test_episode_trailing_notionals_use_open_left_causal_windows() -> None:
    """Trailing intensity includes only same-side labels in (end-window, end]."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(0, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(1_000, "long", Decimal("11"), Decimal("2"), 2),
        LiquidationLabel(2_000, "short", Decimal("99"), Decimal("1"), 3),
        LiquidationLabel(3_501, "long", Decimal("12"), Decimal("1"), 4),
        LiquidationLabel(6_000, "long", Decimal("13"), Decimal("1"), 5),
    )

    episodes = [
        row for row in build_liquidation_episodes(labels) if row.direction == "long"
    ]

    assert [row.trailing_5s_notional_usd for row in episodes] == [
        Decimal("32"),
        Decimal("44"),
        Decimal("25"),
    ]
    assert [row.trailing_15s_notional_usd for row in episodes] == [
        Decimal("32"),
        Decimal("44"),
        Decimal("57"),
    ]


def test_episode_builder_rejects_duplicate_trade_identity() -> None:
    """A treatment fill cannot contribute more than once across bundles."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(1_000, "long", Decimal("10"), Decimal("1"), 7),
        LiquidationLabel(2_000, "long", Decimal("11"), Decimal("1"), 7),
    )

    with pytest.raises(ValueError, match="duplicate liquidation trade_id"):
        build_liquidation_episodes(labels)


def test_episode_builder_rejects_nonchronological_labels() -> None:
    """Causal windows must not silently sort a malformed treatment stream."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(2_000, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(1_000, "short", Decimal("11"), Decimal("1"), 2),
    )

    with pytest.raises(ValueError, match="chronological"):
        build_liquidation_episodes(labels)


def test_loader_verifies_and_merges_contiguous_v2_bundles(tmp_path: Path) -> None:
    """Only manifest-bound normalized labels may enter treatment construction."""
    from hypervector.research.btc_liquidation_episodes import (
        load_liquidation_bundles,
    )

    start = datetime(2026, 1, 1, tzinfo=UTC)
    middle = start + timedelta(days=1)
    end = middle + timedelta(days=1)
    first = _write_bundle(
        tmp_path,
        "first",
        start,
        middle,
        [_row(start + timedelta(seconds=1), "long", 1)],
    )
    second = _write_bundle(
        tmp_path,
        "second",
        middle,
        end,
        [_row(middle + timedelta(seconds=1), "short", 2)],
    )

    labels = load_liquidation_bundles((second, first), symbol="BTC")

    assert [(row.trade_id, row.direction, row.notional_usd) for row in labels] == [
        (1, "long", Decimal("20")),
        (2, "short", Decimal("22")),
    ]


def test_loader_rejects_a_gap_between_requested_windows(tmp_path: Path) -> None:
    """Missing treatment windows must remain explicit rather than disappear."""
    from hypervector.research.btc_liquidation_episodes import (
        load_liquidation_bundles,
    )

    start = datetime(2026, 1, 1, tzinfo=UTC)
    middle = start + timedelta(days=1)
    gap_end = middle + timedelta(hours=1)
    end = gap_end + timedelta(days=1)
    first = _write_bundle(tmp_path, "first", start, middle, [])
    second = _write_bundle(tmp_path, "second", gap_end, end, [])

    with pytest.raises(ValueError, match="contiguous"):
        load_liquidation_bundles((first, second), symbol="BTC")


def test_loader_rejects_normalized_rows_changed_after_manifest(tmp_path: Path) -> None:
    """A hash-valid manifest must bind the exact treatment rows loaded."""
    from hypervector.research.btc_liquidation_episodes import (
        load_liquidation_bundles,
    )

    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    bundle = _write_bundle(
        tmp_path,
        "bundle",
        start,
        end,
        [_row(start + timedelta(seconds=1), "long", 1)],
    )
    changed = _row(start + timedelta(seconds=1), "long", 1)
    changed["price"] = "12"
    changed["notional_usd"] = "24"
    with gzip.open(bundle / "liquidations.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(changed, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="evidence (byte count|checksum) mismatch"):
        load_liquidation_bundles((bundle,), symbol="BTC")


def test_rolling_burst_thresholds_are_strictly_prior_and_nearest_rank() -> None:
    """The current episode cannot influence its own causal percentile threshold."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        assess_rolling_bursts,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(0, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(3_000, "long", Decimal("20"), Decimal("1"), 2),
        LiquidationLabel(5_500, "long", Decimal("30"), Decimal("1"), 3),
        LiquidationLabel(8_000, "long", Decimal("40"), Decimal("1"), 4),
        LiquidationLabel(8_500, "long", Decimal("30"), Decimal("1"), 5),
        LiquidationLabel(9_000, "long", Decimal("30"), Decimal("1"), 6),
    )
    episodes = build_liquidation_episodes(labels)

    current = assess_rolling_bursts(
        episodes,
        source_start_ms=0,
        lookback_ms=8_000,
    )[-1]

    assert current.prior_episode_count == 2
    assert current.threshold_5s_p95_usd == Decimal("50")
    assert current.threshold_5s_p99_usd == Decimal("50")
    assert current.threshold_15s_p95_usd == Decimal("60")
    assert current.threshold_15s_p99_usd == Decimal("60")
    assert current.eligible_arms == ("5s_p95", "5s_p99", "15s_p95", "15s_p99")


def test_burst_thresholds_remain_unavailable_during_full_lookback_warmup() -> None:
    """A partial prior window cannot masquerade as a causal 30-day threshold."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        assess_rolling_bursts,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(0, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(3_000, "long", Decimal("50"), Decimal("1"), 2),
        LiquidationLabel(3_500, "long", Decimal("50"), Decimal("1"), 3),
        LiquidationLabel(4_000, "long", Decimal("50"), Decimal("1"), 4),
    )
    current = assess_rolling_bursts(
        build_liquidation_episodes(labels),
        source_start_ms=0,
        lookback_ms=10_000,
    )[-1]

    assert current.prior_episode_count == 1
    assert current.threshold_5s_p95_usd is None
    assert current.threshold_15s_p99_usd is None
    assert current.eligible_arms == ()


def test_prior_episode_at_exact_lookback_boundary_is_included() -> None:
    """The rolling history is inclusive at its causal lower boundary."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationLabel,
        assess_rolling_bursts,
        build_liquidation_episodes,
    )

    labels = (
        LiquidationLabel(1_000, "long", Decimal("10"), Decimal("1"), 1),
        LiquidationLabel(5_000, "long", Decimal("20"), Decimal("1"), 2),
        LiquidationLabel(6_000, "long", Decimal("20"), Decimal("1"), 3),
        LiquidationLabel(7_000, "long", Decimal("20"), Decimal("1"), 4),
    )

    current = assess_rolling_bursts(
        build_liquidation_episodes(labels),
        source_start_ms=1_000,
        lookback_ms=6_000,
    )[-1]

    assert current.prior_episode_count == 1
    assert current.threshold_5s_p95_usd == Decimal("10")
    assert current.eligible_arms == ("5s_p95", "5s_p99", "15s_p95", "15s_p99")


def test_future_intensity_cannot_change_an_earlier_threshold() -> None:
    """Coordinate compression may see values but causal ranks may not use them."""
    from hypervector.research.btc_liquidation_episodes import (
        LiquidationEpisode,
        assess_rolling_bursts,
    )

    prior = LiquidationEpisode(
        "short", 0, 0, 3, Decimal("1"), Decimal("10"), Decimal("10"), Decimal("10")
    )
    current = LiquidationEpisode(
        "short",
        1_000,
        1_000,
        3,
        Decimal("1"),
        Decimal("20"),
        Decimal("20"),
        Decimal("20"),
    )
    future = LiquidationEpisode(
        "short",
        2_000,
        2_000,
        3,
        Decimal("1"),
        Decimal("999999"),
        Decimal("999999"),
        Decimal("999999"),
    )

    prefix = assess_rolling_bursts(
        (prior, current), source_start_ms=0, lookback_ms=1_000
    )[1]
    with_future = assess_rolling_bursts(
        (prior, current, future), source_start_ms=0, lookback_ms=1_000
    )[1]

    assert with_future == prefix
    assert with_future.threshold_5s_p99_usd == Decimal("10")
