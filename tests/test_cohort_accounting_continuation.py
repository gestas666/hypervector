"""Tests for immutable accounting continuity across adjacent profiles."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_accounting_continuation import (
    build_accounting_continuation_manifest,
    validate_accounting_continuation,
)
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch

_PROFILE_A = "a" * 64
_PROFILE_B = "b" * 64
_PROFILE_C = "c" * 64
_START_MS = 1_787_164_729_837


def test_continuation_preserves_parent_start_and_inherited_closed_trades() -> None:
    """A successor profile must retain the exact funded-campaign boundary."""
    report = build_accounting_continuation_manifest(
        _rollover(),
        _parent(),
        _checkpoint(),
        parent_manifest_evidence=_evidence(b'{"parent":true}\n'),
    )

    assert report["accounting_epoch"] == {
        "epoch_id": "a_b_growth_5000",
        "profile_fingerprint": _PROFILE_B,
        "start_venue_timestamp_ms": _START_MS,
        "included_profile_fingerprints": [_PROFILE_A, _PROFILE_B],
    }
    assert report["acceptance"] == {
        "inherited_closed_trades": 8,
        "successor_closed_trades_at_boundary": 0,
        "open_lifecycles": 0,
        "venue_equity_usd": 4_876.25,
        "sizing_reference_equity_usd": 5_000.0,
    }
    assert (
        report["continuation"]["parent_accounting_epoch"]
        == _parent()["accounting_epoch"]
    )
    assert report["contract"]["profile_lineage_continued"] is True


def test_continuation_appends_to_existing_profile_lineage() -> None:
    """A second successor must retain every earlier funded-campaign profile."""
    parent = _parent()
    parent["successor_identity"] = _identity("profile_b", _PROFILE_B)
    parent["accounting_epoch"] = {
        "epoch_id": "a_b_growth_5000",
        "profile_fingerprint": _PROFILE_B,
        "start_venue_timestamp_ms": _START_MS,
        "included_profile_fingerprints": [_PROFILE_A, _PROFILE_B],
    }
    checkpoint = _checkpoint()
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"] = parent[
        "accounting_epoch"
    ]
    rollover = _rollover()
    rollover["prior_identity"] = _identity("profile_b", _PROFILE_B)
    rollover["successor_identity"] = _identity("profile_c", _PROFILE_C)

    report = build_accounting_continuation_manifest(
        rollover,
        parent,
        checkpoint,
        parent_manifest_evidence=_evidence(b'{"parent":true}\n'),
    )

    assert report["accounting_epoch"] == {
        "epoch_id": "a_b_growth_5000",
        "profile_fingerprint": _PROFILE_C,
        "start_venue_timestamp_ms": _START_MS,
        "included_profile_fingerprints": [_PROFILE_A, _PROFILE_B, _PROFILE_C],
    }


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda parent, _checkpoint_value: parent["successor_identity"].update(
                {"profile_fingerprint": "c" * 64}
            ),
            "parent successor",
        ),
        (
            lambda _parent_value, checkpoint: checkpoint["audit"][
                "portfolio_archive"
            ].update({"accounting_epoch": None}),
            "checkpoint accounting epoch",
        ),
        (
            lambda parent, _checkpoint_value: parent["accounting_epoch"].update(
                {"included_profile_fingerprints": [_PROFILE_A, _PROFILE_B]}
            ),
            "parent accounting epoch",
        ),
    ],
)
def test_continuation_rejects_non_adjacent_or_inconsistent_parent(
    mutator: Callable[[dict[str, object], dict[str, object]], None],
    message: str,
) -> None:
    """Only an exact adjacent lineage may parent the successor bundle."""
    parent = _parent()
    checkpoint = _checkpoint()
    mutator(parent, checkpoint)

    with pytest.raises(ValueError, match=message):
        build_accounting_continuation_manifest(
            _rollover(),
            parent,
            checkpoint,
            parent_manifest_evidence=_evidence(b'{"parent":true}\n'),
        )


def test_loaded_continuation_verifies_internal_parent_manifest(tmp_path: Path) -> None:
    """Changing copied parent evidence must make live loading fail closed."""
    parent_raw = json.dumps(_parent(), sort_keys=True).encode("utf-8") + b"\n"
    (tmp_path / "parent_accounting_epoch_manifest.json").write_bytes(parent_raw)
    report = build_accounting_continuation_manifest(
        _rollover(),
        _parent(),
        _checkpoint(),
        parent_manifest_evidence=_evidence(parent_raw),
    )
    epoch = CohortAccountingEpoch(
        "a_b_growth_5000",
        _PROFILE_B,
        _START_MS,
        included_profile_fingerprints=(_PROFILE_A, _PROFILE_B),
    )

    validate_accounting_continuation(tmp_path, report, epoch)
    (tmp_path / "parent_accounting_epoch_manifest.json").write_text(
        "changed\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="parent accounting epoch evidence differs"):
        validate_accounting_continuation(tmp_path, report, epoch)


def _rollover() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_accounting_epoch_rollover_v1",
        "prior_identity": _identity("profile_a", _PROFILE_A),
        "successor_identity": _identity("profile_b", _PROFILE_B),
        "accounting_epoch": {
            "epoch_id": "a_b_growth_5000",
            "profile_fingerprint": _PROFILE_B,
            "start_venue_timestamp_ms": 1_787_396_800_000,
        },
        "acceptance": {
            "all_time_closed_trades": 0,
            "current_run_closed_trades": 0,
            "open_lifecycles": 0,
            "venue_equity_usd": 4_876.25,
            "sizing_reference_equity_usd": 5_000.0,
        },
        "contract": {
            "report_only": True,
            "automatic_live_start": False,
            "live_risk_flags_required_separately": True,
            "prior_history_preserved": True,
            "prior_history_excluded_from_new_epoch_metrics": True,
            "current_venue_equity_retained": True,
        },
    }


def _parent() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_accounting_epoch_rollover_v1",
        "successor_identity": _identity("profile_a", _PROFILE_A),
        "accounting_epoch": {
            "epoch_id": "a_growth_5000",
            "profile_fingerprint": _PROFILE_A,
            "start_venue_timestamp_ms": _START_MS,
        },
    }


def _checkpoint() -> dict[str, object]:
    return {
        "audit": {
            "open_trade_reflections": {"open_lifecycles": 0, "trades": []},
            "portfolio_archive": {
                "accounting_epoch": _parent()["accounting_epoch"],
                "performance": {"total": {"closed_trades": 8}},
            },
        }
    }


def _identity(profile_id: str, fingerprint: str) -> dict[str, object]:
    return {
        "profile_id": profile_id,
        "profile_fingerprint": fingerprint,
        "source_path": f"configs/{profile_id}.toml",
        "run_id": None,
    }


def _evidence(raw: bytes) -> dict[str, object]:
    return {
        "path": "parent_accounting_epoch_manifest.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
