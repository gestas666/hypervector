"""Research status must reach the atomic checkpoint through each publisher path."""

import json
from pathlib import Path

import pytest

from hypervector.research.cohort_background_sync import BackgroundResearchSync
from hypervector.research.cohort_live_checkpoint import publish_live_checkpoint
from hypervector.research.cohort_research_sync_telemetry import ResearchSyncTelemetry
from hypervector.research.cohort_rolling_checkpoint import publish_rolling_checkpoint
from hypervector.research.cohort_checkpoint_history import HistoricalProjectionStale
from test_cohort_live_checkpoint import _write_rows, _GENERATED_AT
from test_multi_asset_live_audit import _asset_rows, _cohort_rows
from test_multi_asset_bidirectional_live_checkpoint_script import _load_module


_CHECKPOINT_CONFIG = ["--config", "tests/fixtures/profiles/cohort_base.toml"]


@pytest.mark.parametrize("failure", [False, True])
def test_once_import_status_reaches_real_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    """One-shot publication retains failed imports even with a usable live snapshot."""
    module = _load_module()
    captured = []
    monkeypatch.setattr(
        module,
        "publish_rolling_checkpoint",
        lambda *args, **kwargs: captured.append(kwargs) or False,
    )

    def sync(*_args: Path) -> dict[str, object]:
        if failure:
            raise module.ResearchSyncError("database locked")
        return {"imported_events": 4}

    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + [
            "--once",
            "--research-database",
            str(tmp_path / "db"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    result = module.run_checkpoint_loop(args, sync_fn=sync)
    assert result == (2 if failure else 0)
    status = captured[0]["research_sync"]
    assert status["state"] == ("failed" if failure else "ready")
    assert status["error"] == ("database locked" if failure else None)


def test_continuous_deferral_survives_log_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The current-run-only fast path must expose a failed research importer."""
    module = _load_module()
    captured = []
    controller = BackgroundResearchSync(
        tmp_path / "db", tmp_path, 120, lambda *_: {}, minimum_free_bytes=10**20
    )
    monkeypatch.setattr(module, "_background_sync", lambda *_: controller)
    monkeypatch.setattr(
        module,
        "publish_rolling_checkpoint",
        lambda *args, **kwargs: captured.append(kwargs) or False,
    )

    def stop(_seconds: float) -> None:
        raise RuntimeError("bounded test stop")

    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + ["--research-database", str(tmp_path / "db"), "--out", str(tmp_path / "out")]
    )
    with pytest.raises(RuntimeError, match="bounded test stop"):
        module.run_checkpoint_loop(args, sync_fn=lambda *_: {}, sleep_fn=stop)
    assert controller.pop_error() is None
    assert captured[0]["current_run_only"] is True
    assert captured[0]["research_sync"]["state"] == "deferred"
    assert "disk space" in captured[0]["research_sync"]["error"]


def test_sync_status_is_part_of_atomic_published_document(tmp_path: Path) -> None:
    """A fresh optional omission cannot inherit a prior successful import label."""
    ledger = tmp_path / "ledgers"
    ledger.mkdir()
    _write_rows(ledger / "decisions.jsonl", _cohort_rows())
    for symbol in ("BTC", "ETH", "SOL", "HYPE"):
        _write_rows(ledger / f"{symbol.lower()}.jsonl", _asset_rows(symbol))
    output = tmp_path / "latest.json"
    tracker = ResearchSyncTelemetry(clock=lambda: _GENERATED_AT)
    tracker.begin_attempt()
    tracker.failed("bounded import timed out")
    expected = tracker.snapshot()
    result = publish_live_checkpoint(
        ledger,
        output,
        run_id="cohort-live-a",
        generated_at=_GENERATED_AT,
        research_sync=expected,
    )
    assert result["research_sync"] == expected
    assert json.loads(output.read_text())["research_sync"] == expected
    legacy = publish_live_checkpoint(
        ledger, output, run_id="cohort-live-a", generated_at=_GENERATED_AT
    )
    assert "research_sync" not in legacy


def test_historical_refresh_keeps_current_sync_status(tmp_path: Path) -> None:
    """A cached-history retry cannot discard the new import failure evidence."""
    captured = []
    status = ResearchSyncTelemetry(enabled=False).snapshot()

    def publish(*_args: object, **kwargs: object) -> dict[str, object]:
        captured.append(kwargs)
        if len(captured) == 1:
            raise HistoricalProjectionStale("history changed")
        return {}

    assert publish_rolling_checkpoint(
        publish,
        tmp_path,
        tmp_path / "checkpoint.json",
        requested_run_id="run",
        config_path=tmp_path / "config",
        once=True,
        venue_portfolio=None,
        opportunity_matrix_path=None,
        supplemental_opportunity_matrix_paths=(),
        eligible_policy_forward=False,
        funding_evidence_fn=None,
        portfolio_archive=None,
        asymmetric_forward_journal_path=None,
        research_sync=status,
    )
    assert [row["research_sync"] for row in captured] == [status, status]
