"""Integrity and fail-closed tests for cohort pre-start backups."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import gzip
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_prestart_backup import (
    CohortPrestartBackupError,
    create_cohort_prestart_backup,
    verify_cohort_prestart_backup,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


def _write_config(root: Path, *, profile: str) -> Path:
    path = root / "configs" / f"{profile}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''profile = "{profile}"
network = "mainnet"
margin_mode = "isolated"
maximum_positions = 2

[runtime]
cohort_ledger = "{root}/data/live/bidirectional_cohort/decisions.jsonl"
stop_file = "{root}/data/live/bidirectional_cohort/STOP"
poll_seconds = 15.0
lookback_days = 14

[[assets]]
symbol = "BTC"
sides = ["long", "short"]
leverage = 5.0
venue_max_leverage = 40.0
margin_fraction = 0.03
max_notional_usd = 25.0
market_slippage_cap_fraction = 0.01
stop_bps = 80.0
maximum_hold_seconds = 28800

[[assets]]
symbol = "HYPE"
sides = ["long", "short"]
leverage = 5.0
venue_max_leverage = 10.0
margin_fraction = 0.03
max_notional_usd = 25.0
market_slippage_cap_fraction = 0.01
stop_bps = 80.0
maximum_hold_seconds = 28800

[[providers]]
strategy_id = "hulk_expansion_bidirectional_tuned_v2"
symbols = ["BTC", "HYPE"]
sides = ["long", "short"]
priority = 10
timeframe = "30m"
maximum_entry_delay_seconds = 60
execution_symbols = ["BTC", "HYPE"]
execution = {{ entry_liquidity = "taker_ioc", stop_policy = "fixed_bps", stop_bps = 80.0, target_policy = "none", maximum_hold_seconds = 28800 }}
''',
        encoding="utf-8",
    )
    return path


def _seed_state(root: Path, previous_config: Path) -> Path:
    live = root / "data/live/bidirectional_cohort"
    runtime = root / "data/runtime/bidirectional_cohort"
    live.mkdir(parents=True)
    runtime.mkdir(parents=True)
    previous = load_multi_asset_live_config(previous_config, mode="observe")
    identity = {
        "event_type": "configuration_identity",
        "profile_id": previous.profile_id,
        "profile_fingerprint": previous.profile_fingerprint,
        "run_fingerprint": previous.run_fingerprint,
        "run_id": "previous-run",
        "payload": {
            "config_source_path": str(previous_config),
            "enabled_symbols": list(previous.symbols),
            "providers": [],
        },
    }
    decisions = live / "decisions.jsonl"
    decisions.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    for symbol in ("btc", "hype"):
        (live / f"{symbol}.jsonl").write_text(f"{symbol}-ledger\n", encoding="utf-8")
    checkpoint = {"generated_at_utc": "2026-08-05T12:00:00+00:00"}
    (runtime / "latest_checkpoint.json").write_text(
        json.dumps(checkpoint), encoding="utf-8"
    )
    return decisions


def _implementation_sources(root: Path) -> dict[str, Path]:
    path = root / "runtime" / "engine.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ENGINE_VERSION = 1\n", encoding="utf-8")
    return {"engine": path}


def test_backup_is_immutable_hash_verified_and_recovers_exact_bytes(
    tmp_path: Path,
) -> None:
    """A strategy transition preserves exact prior and target state."""
    previous = _write_config(tmp_path, profile="previous-profile")
    target = _write_config(tmp_path, profile="target-profile")
    decisions = _seed_state(tmp_path, previous)
    config = load_multi_asset_live_config(
        target, mode="live", enabled=True, accepts_live_risk=True
    )

    result = create_cohort_prestart_backup(
        config,
        now=datetime(2026, 8, 5, 12, 30, tzinfo=UTC),
        implementation_sources=_implementation_sources(tmp_path),
    )
    manifest = verify_cohort_prestart_backup(result.path)

    assert result.strategy_changed is True
    assert manifest["strategy_changed"] is True
    assert manifest["previous_identity"]["run_id"] == "previous-run"
    assert manifest["target_identity"]["profile_id"] == "target-profile"
    assert manifest["execution_authority"] == "none"
    records = {record["role"]: record for record in manifest["files"]}
    archive = result.path / records["cohort_ledger"]["archive_path"]
    with gzip.open(archive, "rb") as handle:
        assert handle.read() == decisions.read_bytes()


def test_observe_identity_cannot_hide_previous_armed_live_profile(
    tmp_path: Path,
) -> None:
    """Pre-start transition evidence remains bound to the latest live run."""
    previous = _write_config(tmp_path, profile="previous-live-profile")
    target = _write_config(tmp_path, profile="target-live-profile")
    decisions = _seed_state(tmp_path, previous)
    rows = [json.loads(decisions.read_text(encoding="utf-8"))]
    rows[0].update({"execution_mode": "live", "live_armed": True})
    observed = load_multi_asset_live_config(target, mode="observe")
    rows.append(
        {
            "event_type": "configuration_identity",
            "execution_mode": "observe",
            "live_armed": False,
            "profile_id": observed.profile_id,
            "profile_fingerprint": observed.profile_fingerprint,
            "run_fingerprint": observed.run_fingerprint,
            "run_id": "later-observe-run",
            "payload": {
                "config_source_path": str(target),
                "enabled_symbols": list(observed.symbols),
                "providers": [],
            },
        }
    )
    decisions.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    config = load_multi_asset_live_config(
        target, mode="live", enabled=True, accepts_live_risk=True
    )

    result = create_cohort_prestart_backup(
        config,
        now=datetime(2026, 8, 5, 12, 30, tzinfo=UTC),
        implementation_sources=_implementation_sources(tmp_path),
    )
    manifest = verify_cohort_prestart_backup(result.path)

    assert result.strategy_changed is True
    assert manifest["previous_identity"]["run_id"] == "previous-run"
    assert manifest["previous_identity"]["profile_id"] == "previous-live-profile"


def test_corrupt_archive_fails_verification(tmp_path: Path) -> None:
    """Archive corruption is observable and cannot pass restore verification."""
    previous = _write_config(tmp_path, profile="same-profile")
    _seed_state(tmp_path, previous)
    config = load_multi_asset_live_config(
        previous, mode="live", enabled=True, accepts_live_risk=True
    )
    result = create_cohort_prestart_backup(
        config,
        implementation_sources=_implementation_sources(tmp_path),
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    archive = result.path / manifest["files"][0]["archive_path"]
    archive.write_bytes(archive.read_bytes() + b"corruption")

    with pytest.raises(CohortPrestartBackupError, match="archive checksum mismatch"):
        verify_cohort_prestart_backup(result.path)


def test_partial_ledger_state_refuses_backup_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    """A missing asset ledger cannot yield a success-shaped backup bundle."""
    target = _write_config(tmp_path, profile="target-profile")
    previous = _write_config(tmp_path, profile="previous-profile")
    _seed_state(tmp_path, previous)
    (tmp_path / "data/live/bidirectional_cohort/hype.jsonl").unlink()
    config = load_multi_asset_live_config(
        target, mode="live", enabled=True, accepts_live_risk=True
    )

    with pytest.raises(CohortPrestartBackupError, match="partial ledger state"):
        create_cohort_prestart_backup(
            config,
            implementation_sources=_implementation_sources(tmp_path),
        )

    backup_root = tmp_path / "data/backups/bidirectional_cohort"
    assert not backup_root.exists() or list(backup_root.iterdir()) == []


def test_backup_accepts_a_new_asset_without_prior_ledger_and_records_it(
    tmp_path: Path,
) -> None:
    """A candidate-only asset is explicit absence, not lost active state."""
    previous = _write_config(tmp_path, profile="previous-profile")
    target = _write_config(tmp_path, profile="target-profile")
    _seed_state(tmp_path, previous)
    loaded = load_multi_asset_live_config(
        target, mode="live", enabled=True, accepts_live_risk=True
    )
    hip3 = replace(
        loaded.assets[1],
        symbol="xyz:SP500",
        live_ledger=loaded.cohort_ledger.parent / "xyz:sp500.jsonl",
    )
    config = replace(
        loaded,
        maximum_positions=3,
        assets=(*loaded.assets, hip3),
    )

    result = create_cohort_prestart_backup(
        config,
        implementation_sources=_implementation_sources(tmp_path),
    )
    manifest = verify_cohort_prestart_backup(result.path)
    roles = {record["role"] for record in manifest["files"]}

    assert manifest["new_assets_without_prior_ledgers"] == ["xyz:SP500"]
    assert "asset_btc_ledger" in roles
    assert "asset_hype_ledger" in roles
    assert "asset_xyz_sp500_ledger" not in roles


def test_in_place_strategy_change_is_refused(tmp_path: Path) -> None:
    """A post-edit snapshot cannot pretend to contain the prior TOML bytes."""
    active = _write_config(tmp_path, profile="target-profile")
    decisions = _seed_state(tmp_path, active)
    identity = json.loads(decisions.read_text(encoding="utf-8"))
    identity["profile_fingerprint"] = "fingerprint-before-in-place-edit"
    decisions.write_text(json.dumps(identity) + "\n", encoding="utf-8")
    config = load_multi_asset_live_config(
        active, mode="live", enabled=True, accepts_live_risk=True
    )

    with pytest.raises(CohortPrestartBackupError, match="separate candidate file"):
        create_cohort_prestart_backup(
            config,
            implementation_sources=_implementation_sources(tmp_path),
        )


def test_backup_preserves_implementation_bytes_and_fingerprint(
    tmp_path: Path,
) -> None:
    """A live bundle identifies and restores the code selected for startup."""
    active = _write_config(tmp_path, profile="same-profile")
    _seed_state(tmp_path, active)
    implementation = tmp_path / "runtime" / "strategy.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("SIGNAL = 'first'\n", encoding="utf-8")
    config = load_multi_asset_live_config(
        active, mode="live", enabled=True, accepts_live_risk=True
    )

    first = create_cohort_prestart_backup(
        config,
        now=datetime(2026, 8, 5, 13, 0, tzinfo=UTC),
        implementation_sources={"strategy_runtime": implementation},
    )
    first_manifest = verify_cohort_prestart_backup(first.path)
    first_identity = first_manifest["implementation_identity"]
    records = {record["role"]: record for record in first_manifest["files"]}
    archive = first.path / records["implementation_strategy_runtime"]["archive_path"]

    assert first_identity["file_count"] == 1
    assert first_identity["sha256"]
    assert first.implementation_file_count == 1
    assert first.implementation_sha256 == first_identity["sha256"]
    with gzip.open(archive, "rb") as handle:
        assert handle.read() == b"SIGNAL = 'first'\n"

    implementation.write_text("SIGNAL = 'second'\n", encoding="utf-8")
    second = create_cohort_prestart_backup(
        config,
        now=datetime(2026, 8, 5, 13, 1, tzinfo=UTC),
        implementation_sources={"strategy_runtime": implementation},
    )
    second_manifest = verify_cohort_prestart_backup(second.path)

    assert (
        second_manifest["implementation_identity"]["sha256"] != first_identity["sha256"]
    )


def test_backup_preserves_transition_drain_before_recovery_rebind(
    tmp_path: Path,
) -> None:
    """Recovery can prove the exact old run-bound drain state it replaced."""
    active = _write_config(tmp_path, profile="same-profile")
    _seed_state(tmp_path, active)
    drain = tmp_path / "data/live/bidirectional_cohort/transition_drain.json"
    drain.write_text('{"status":"active","run_id":"old-run"}\n', encoding="utf-8")
    original = drain.read_bytes()
    config = load_multi_asset_live_config(
        active, mode="live", enabled=True, accepts_live_risk=True
    )

    result = create_cohort_prestart_backup(
        config,
        now=datetime(2026, 8, 5, 13, 2, tzinfo=UTC),
        implementation_sources=_implementation_sources(tmp_path),
    )
    manifest = verify_cohort_prestart_backup(result.path)
    records = {record["role"]: record for record in manifest["files"]}

    archive = result.path / records["transition_drain"]["archive_path"]
    with gzip.open(archive, "rb") as handle:
        assert handle.read() == original


def test_live_backup_refuses_missing_implementation_sources(tmp_path: Path) -> None:
    """A configuration-only bundle cannot authorize a future live start."""
    active = _write_config(tmp_path, profile="same-profile")
    _seed_state(tmp_path, active)
    config = load_multi_asset_live_config(
        active, mode="live", enabled=True, accepts_live_risk=True
    )

    with pytest.raises(
        CohortPrestartBackupError,
        match="implementation sources are required",
    ):
        create_cohort_prestart_backup(config)
