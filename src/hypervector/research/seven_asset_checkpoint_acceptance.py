"""Automatic acceptance attachment for exact seven-asset live checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v79_poststart_acceptance import (
    build_v79_poststart_acceptance,
)

_V79_FINGERPRINT = "6c12d96e3fe09dd5dcefd24761bc7462ec6d6aa0b0d0f023a21e4b8597b646f7"
_V80_FINGERPRINT = "89c84ecf8f927d1b22b3db7b28a9b6e62c89685d7049ef02f0cca90fc568d5ca"
_V85_FINGERPRINT = "18306afaaad1912b368f483c770c507a94a2403f9bd2741691776220b38633e8"
_V86_FINGERPRINT = "f454101eadaef46fd026c1a901bb7873bad61d7e7183a4c2e342e477e4e38733"
_V79_EPOCH = {
    "epoch_id": "v79_seven_asset_all_active_6c12d96_20260903T0220Z",
    "profile_fingerprint": _V79_FINGERPRINT,
    "start_venue_timestamp_ms": 1_788_402_027_059,
}


def attach_seven_asset_poststart_acceptance(
    checkpoint: dict[str, object],
    config_path: Path,
    *,
    observed_at: datetime,
) -> bool:
    """Attach a verdict for exact V79 or an epoch-bound exact V80 profile."""
    config = load_multi_asset_live_config(config_path, mode="observe")
    epoch = _expected_epoch(checkpoint, config.profile_fingerprint)
    if epoch is None:
        return False
    checkpoint["poststart_acceptance"] = build_v79_poststart_acceptance(
        checkpoint,
        config,
        epoch,
        now_utc=observed_at,
    )
    return True


def _expected_epoch(
    checkpoint: Mapping[str, object],
    profile_fingerprint: str,
) -> Mapping[str, object] | None:
    if profile_fingerprint == _V79_FINGERPRINT:
        return _V79_EPOCH
    supported = {_V80_FINGERPRINT, _V85_FINGERPRINT, _V86_FINGERPRINT}
    if profile_fingerprint not in supported:
        return None
    audit = checkpoint.get("audit")
    archive = audit.get("portfolio_archive") if isinstance(audit, Mapping) else None
    epoch = archive.get("accounting_epoch") if isinstance(archive, Mapping) else None
    if not isinstance(epoch, Mapping):
        return None
    epoch_id = epoch.get("epoch_id")
    expected_prefix = {
        _V80_FINGERPRINT: "v80_entry_ioc_hardened_89c84ec_",
        _V85_FINGERPRINT: "v85_btc_tuned_retired_18306afa_",
        _V86_FINGERPRINT: "v86_failed_routes_retired_f454101e_",
    }[profile_fingerprint]
    valid = (
        isinstance(epoch_id, str)
        and epoch_id.startswith(expected_prefix)
        and epoch.get("profile_fingerprint") == profile_fingerprint
        and isinstance(epoch.get("start_venue_timestamp_ms"), int)
    )
    return epoch if valid else None
