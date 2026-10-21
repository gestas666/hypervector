"""Read-only monitoring must follow complete same-profile backend restarts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_rolling_checkpoint import publish_rolling_checkpoint
from test_cohort_checkpoint_bounded_transition import _complete_checkpoint
from test_multi_asset_bidirectional_live_checkpoint_script import _load_module

_CONFIG = Path("tests/fixtures/profiles/noncrypto_live.toml")


_CHECKPOINT_CONFIG = ["--config", "tests/fixtures/profiles/cohort_base.toml"]


def _snapshot(run_id: str) -> dict[str, object]:
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    return {
        "event_type": "cohort_snapshot",
        "run_id": run_id,
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "execution_mode": "live",
        "execution_authority": "hyperliquid_mainnet",
        "live_armed": True,
        "payload": {},
    }


def _publish(root: Path, requested: str | None = None) -> dict[str, object]:
    calls: list[dict[str, object]] = []

    def publish(_root: Path, _out: Path, **options: object) -> dict[str, object]:
        calls.append(options)
        return {}

    publish_rolling_checkpoint(
        publish,
        root,
        root / "latest.json",
        requested_run_id=requested,
        config_path=_CONFIG,
        once=False,
        venue_portfolio=None,
        portfolio_archive=None,
        follow_latest_run=True,
    )
    assert len(calls) == 1
    return calls[0]


def test_follows_complete_restarted_run_without_cached_run_pin(tmp_path: Path) -> None:
    """A restart advances the monitor and keeps each publication bounded."""
    old = _snapshot("old")
    _complete_checkpoint(tmp_path / "latest.json", str(old["profile_fingerprint"]))
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(json.dumps(old) + "\n")
    assert _publish(tmp_path)["run_id"] == "old"

    with ledger.open("a") as handle:
        handle.write(json.dumps(_snapshot("new")) + "\n")
        handle.write('{"event_type":"cohort_snapshot","run_id":"partial"')
    options = _publish(tmp_path)

    assert options["run_id"] == "new"
    assert options["current_run_only"] is True
    assert options["compatible_execution_history"] is False
    assert options["complete_historical_checkpoint"] is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("profile_fingerprint", "different"),
        ("profile_id", "different"),
        ("execution_mode", "observe"),
        ("execution_authority", "none"),
        ("live_armed", False),
        ("live_armed", 1),
        ("run_id", ""),
    ],
)
def test_rejects_unmatched_or_nonlive_latest_snapshot(
    tmp_path: Path, key: str, value: object
) -> None:
    """Following a process restart cannot silently adopt another profile."""
    row = {**_snapshot("new"), key: value}
    (tmp_path / "decisions.jsonl").write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="follow-latest-run"):
        _publish(tmp_path)


def test_follow_rejects_explicit_run_pin(tmp_path: Path) -> None:
    """Contradictory follow and pin instructions are an actionable error."""
    with pytest.raises(ValueError, match="--run-id"):
        _publish(tmp_path, requested="pinned")


def test_complete_malformed_snapshot_is_not_silently_skipped(tmp_path: Path) -> None:
    """A committed broken row must be visible rather than selecting old evidence."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(json.dumps(_snapshot("old")) + '\n{"cohort_snapshot":\n')
    with pytest.raises(ValueError):
        _publish(tmp_path)


def test_cli_forwards_explicit_follow_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service CLI forwards follow mode through the real publication path."""
    module = _load_module()
    calls: list[dict[str, object]] = []

    def rolling(*_args: object, **kwargs: object) -> bool:
        calls.append(kwargs)
        return False

    monkeypatch.setattr(module, "publish_rolling_checkpoint", rolling)
    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + ["--follow-latest-run", "--out", str(tmp_path / "latest.json")]
    )
    module._publish_real_snapshot(
        args, module.publish_live_checkpoint, None, None, None
    )
    assert calls[0]["follow_latest_run"] is True
    assert calls[0]["requested_run_id"] is None
