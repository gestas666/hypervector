"""Recoverable reset of Hypervelocity shadow portfolio telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from hypervector.shadow_reset import reset_shadow_state


def _seed_root(root: Path) -> tuple[Path, Path, Path]:
    decisions = root / "paper" / "decisions" / "decisions.jsonl"
    backend_log = root / "paper" / "hypervelocity-shadow.log"
    cache = root / "cache" / "BTC_1m_30d.parquet"
    decisions.parent.mkdir(parents=True)
    cache.parent.mkdir(parents=True)
    decisions.write_text('{"action":"close"}\n', encoding="utf-8")
    backend_log.write_text("backend evidence\n", encoding="utf-8")
    cache.write_bytes(b"market-cache")
    return decisions, backend_log, cache


def test_reset_defaults_to_non_mutating_dry_run(tmp_path: Path) -> None:
    root = tmp_path / "ops"
    decisions, backend_log, cache = _seed_root(root)

    report = reset_shadow_state(root, confirmed=False)

    assert report.dry_run is True
    assert report.backup_dir is None
    assert decisions.read_text() == '{"action":"close"}\n'
    assert backend_log.read_text() == "backend evidence\n"
    assert cache.read_bytes() == b"market-cache"


def test_confirmed_reset_backs_up_then_clears_only_shadow_logs(tmp_path: Path) -> None:
    root = tmp_path / "ops"
    decisions, backend_log, cache = _seed_root(root)
    now = datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc)

    report = reset_shadow_state(root, confirmed=True, now=now)

    assert report.dry_run is False
    assert report.backup_dir == root / "backups" / "shadow_reset_20260725T143000Z"
    assert decisions.read_text() == ""
    assert backend_log.read_text() == ""
    assert cache.read_bytes() == b"market-cache"
    backup = report.backup_dir
    assert backup is not None
    assert (backup / "paper/decisions/decisions.jsonl").read_text() == (
        '{"action":"close"}\n'
    )
    assert (backup / "paper/hypervelocity-shadow.log").read_text() == (
        "backend evidence\n"
    )
