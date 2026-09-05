"""Immutable outcome-blind BTC liquidation episode artifact tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence


def _source_row(timestamp_ms: int, trade_id: int) -> dict[str, object]:
    timestamp = datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)
    price = Decimal("10") if trade_id == 1 else Decimal("20")
    return {
        "ts_exchange_ms": timestamp_ms,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "symbol": "BTC",
        "liquidated_direction": "long",
        "vendor_direction": "Close Long",
        "exchange_side": "A",
        "price": str(price),
        "size": "1",
        "notional_usd": str(price),
        "trade_id": trade_id,
        "tx_hash": f"0x{trade_id}",
        "source": "0xarchive_hyperliquid_liquidations",
        "normalization_version": "explicit_vendor_direction_v2",
    }


def _write_source_bundle(root: Path) -> Path:
    bundle = root / "source"
    bundle.mkdir()
    rows = [
        _source_row(1_000, 1),
        _source_row(5_000, 2),
        _source_row(5_500, 3),
        _source_row(6_000, 4),
    ]
    labels = bundle / "liquidations.jsonl.gz"
    with gzip.open(labels, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    start = datetime(1970, 1, 1, tzinfo=UTC)
    manifest = {
        "schema_version": 2,
        "normalization_version": "explicit_vendor_direction_v2",
        "source": "0xarchive_hyperliquid_liquidations",
        "symbol": "BTC",
        "requested_start": start.isoformat(),
        "requested_end": (start + timedelta(days=1)).isoformat(),
        "event_count": len(rows),
        "complete": True,
        "continuation_cursor": None,
        "files": {labels.name: file_evidence(labels)},
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _write_empty_source_bundle(root: Path) -> Path:
    bundle = root / "empty-source"
    bundle.mkdir()
    labels = bundle / "liquidations.jsonl.gz"
    with gzip.open(labels, "wt", encoding="utf-8"):
        pass
    start = datetime(1970, 1, 1, tzinfo=UTC)
    manifest = {
        "schema_version": 2,
        "normalization_version": "explicit_vendor_direction_v2",
        "source": "0xarchive_hyperliquid_liquidations",
        "symbol": "BTC",
        "requested_start": start.isoformat(),
        "requested_end": (start + timedelta(days=1)).isoformat(),
        "event_count": 0,
        "complete": True,
        "continuation_cursor": None,
        "files": {labels.name: file_evidence(labels)},
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def test_publisher_freezes_exact_outcome_blind_treatment_rows(tmp_path: Path) -> None:
    """A bundle must bind causal episode rows without market outcomes."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = tmp_path / "episodes"

    published = publish_liquidation_episode_bundle(
        (source,), output, symbol="BTC", lookback_ms=5_000
    )

    assert published == output
    rows = _read_jsonl(output / "episodes.jsonl.gz")
    eligible = _read_jsonl(output / "eligible_episodes.jsonl.gz")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert len(eligible) == 1
    assert eligible[0]["candidate_branch"] == "exhaustion_reclaim_long"
    assert eligible[0]["total_size"] == "3"
    assert eligible[0]["notional_usd"] == "60"
    assert eligible[0]["volume_weighted_price"] == "20"
    assert eligible[0]["eligible_arms"] == [
        "5s_p95",
        "5s_p99",
        "15s_p95",
        "15s_p99",
    ]
    assert manifest["execution_authority"] == "none"
    assert manifest["strategy_outcomes_inspected"] is False
    assert manifest["market_covariates_acquired"] is False
    assert manifest["counts"]["episodes"] == 2
    assert manifest["counts"]["eligible_episodes"] == 1
    assert manifest["coverage"]["observed_start_ms"] == 1_000
    assert (
        manifest["source_manifests"][0]["sha256"]
        == file_evidence(source / "manifest.json")["sha256"]
    )
    assert manifest["files"]["episodes.jsonl.gz"] == file_evidence(
        output / "episodes.jsonl.gz"
    )


def test_publisher_rejects_an_empty_treatment_source(tmp_path: Path) -> None:
    """An absent observed start must fail explicitly and publish nothing."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
    )

    source = _write_empty_source_bundle(tmp_path)
    output = tmp_path / "episodes"

    with pytest.raises(ValueError, match="no liquidation labels"):
        publish_liquidation_episode_bundle((source,), output, symbol="BTC")

    assert not output.exists()


def test_verifier_rejects_changed_episode_evidence(tmp_path: Path) -> None:
    """Published rows must remain byte-for-byte bound to their manifest."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    with (output / "episodes.jsonl.gz").open("ab") as handle:
        handle.write(b"changed")

    with pytest.raises(ValueError, match="evidence (byte count|checksum) mismatch"):
        verify_liquidation_episode_bundle(output)


def test_verifier_reconciles_manifest_episode_counts(tmp_path: Path) -> None:
    """A manifest cannot claim a different treatment sample size."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["episodes"] = 3
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="episode count mismatch"):
        verify_liquidation_episode_bundle(output)


def test_verifier_requires_eligible_rows_to_be_an_exact_subset(tmp_path: Path) -> None:
    """An eligible sidecar cannot introduce a treatment absent from all rows."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    eligible_path = output / "eligible_episodes.jsonl.gz"
    eligible = _read_jsonl(eligible_path)
    eligible[0]["episode_id"] = "0" * 64
    with gzip.open(eligible_path, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(eligible[0], sort_keys=True) + "\n")
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][eligible_path.name] = file_evidence(eligible_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="eligible episode is absent"):
        verify_liquidation_episode_bundle(output)


def test_verifier_rechecks_source_manifest_identity(tmp_path: Path) -> None:
    """Treatment evidence must retain its transitive normalized-source identity."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    source_manifest = source / "manifest.json"
    source_manifest.write_text(
        source_manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="source manifest evidence mismatch"):
        verify_liquidation_episode_bundle(output)


def test_verifier_recomputes_direction_and_arm_counts(tmp_path: Path) -> None:
    """Declared treatment-arm composition must equal the published rows."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["by_eligible_arm"]["5s_p95"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="composition count mismatch"):
        verify_liquidation_episode_bundle(output)


def test_verifier_rechecks_source_bundle_files_transitively(tmp_path: Path) -> None:
    """An unchanged source manifest cannot hide changed normalized labels."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    with (source / "liquidations.jsonl.gz").open("ab") as handle:
        handle.write(b"changed")

    with pytest.raises(
        ValueError, match="bundle evidence (byte count|checksum) mismatch"
    ):
        verify_liquidation_episode_bundle(output)


def test_verifier_reproduces_rows_from_normalized_labels(tmp_path: Path) -> None:
    """Coherently rehashed but fabricated treatment values must still fail."""
    from hypervector.research.btc_liquidation_episode_storage import (
        publish_liquidation_episode_bundle,
        verify_liquidation_episode_bundle,
    )

    source = _write_source_bundle(tmp_path)
    output = publish_liquidation_episode_bundle(
        (source,), tmp_path / "episodes", symbol="BTC", lookback_ms=5_000
    )
    episodes_path = output / "episodes.jsonl.gz"
    eligible_path = output / "eligible_episodes.jsonl.gz"
    episodes = _read_jsonl(episodes_path)
    eligible = _read_jsonl(eligible_path)
    eligible_id = eligible[0]["episode_id"]
    for row in episodes:
        if row["episode_id"] == eligible_id:
            row["notional_usd"] = "61"
    eligible[0]["notional_usd"] = "61"
    _write_jsonl(episodes_path, episodes)
    _write_jsonl(eligible_path, eligible)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][episodes_path.name] = file_evidence(episodes_path)
    manifest["files"][eligible_path.name] = file_evidence(eligible_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="does not reproduce"):
        verify_liquidation_episode_bundle(output)
