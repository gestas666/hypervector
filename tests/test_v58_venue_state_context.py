"""Fresh venue-state evidence for the report-only V58 loop."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
import json
from pathlib import Path

import pytest

_OBSERVED = datetime(2026, 8, 19, 14, 49, tzinfo=UTC)
_ACTIVE_ID = "multi_asset_growth_first_5000_spcx_short_containment_v57"
_CANDIDATE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_ACTIVE_FINGERPRINT = "7" * 64
_CANDIDATE_FINGERPRINT = "8" * 64
_SYMBOLS = ("BTC", "ETH")


def test_fresh_matching_flat_preflight_verifies_current_venue_state(
    tmp_path: Path,
) -> None:
    """Fresh exact public-wallet evidence may establish flat/order-free state."""
    module = import_module("hypervector.research.v58_venue_state_context")

    context = module.load_v58_venue_state_context(
        _write(tmp_path, _payload()),
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
        active_profile_id=_ACTIVE_ID,
        active_profile_fingerprint=_ACTIVE_FINGERPRINT,
        candidate_profile_id=_CANDIDATE_ID,
        candidate_profile_fingerprint=_CANDIDATE_FINGERPRINT,
        candidate_symbols=_SYMBOLS,
    )
    payload = module.venue_state_context_payload(context)

    assert payload["current_venue_position_order_state_verified"] is True
    assert payload["venue_flat_no_orders"] is True
    assert payload["venue_ledger_reconciled"] is True
    assert payload["preflight_fresh"] is True
    assert payload["actual_account_value_usd"] == pytest.approx(4_875.84)
    assert payload["sizing_reference_equity_usd"] == pytest.approx(5_000.0)
    assert payload["execution_authority"] == "none"


def test_stale_preflight_remains_visible_but_does_not_verify_current_state(
    tmp_path: Path,
) -> None:
    """Historical flatness must not be presented as current venue truth."""
    payload = _payload()
    payload["observed_at_utc"] = "2026-08-19T14:40:00+00:00"
    module = import_module("hypervector.research.v58_venue_state_context")

    context = module.load_v58_venue_state_context(
        _write(tmp_path, payload),
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
        active_profile_id=_ACTIVE_ID,
        active_profile_fingerprint=_ACTIVE_FINGERPRINT,
        candidate_profile_id=_CANDIDATE_ID,
        candidate_profile_fingerprint=_CANDIDATE_FINGERPRINT,
        candidate_symbols=_SYMBOLS,
    )

    assert (
        module.venue_state_context_payload(context)[
            "current_venue_position_order_state_verified"
        ]
        is False
    )
    assert context.preflight_fresh is False


def test_nonflat_preflight_verifies_state_without_claiming_flatness(
    tmp_path: Path,
) -> None:
    """A current position or order must remain explicit rather than safe-shaped."""
    payload = _payload()
    payload["portfolio"]["flat_no_orders"] = False
    payload["portfolio"]["open_positions"] = 1
    payload["assets"][0]["position"]["size_signed"] = 0.1
    module = import_module("hypervector.research.v58_venue_state_context")

    context = module.load_v58_venue_state_context(
        _write(tmp_path, payload),
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
        active_profile_id=_ACTIVE_ID,
        active_profile_fingerprint=_ACTIVE_FINGERPRINT,
        candidate_profile_id=_CANDIDATE_ID,
        candidate_profile_fingerprint=_CANDIDATE_FINGERPRINT,
        candidate_symbols=_SYMBOLS,
    )

    result = module.venue_state_context_payload(context)
    assert result["current_venue_position_order_state_verified"] is True
    assert result["venue_flat_no_orders"] is False
    assert result["venue_open_positions"] == 1


def test_sequential_account_samples_use_conservative_minimum(tmp_path: Path) -> None:
    """Moving account marks must use and disclose the lowest sampled value."""
    payload = _payload()
    payload["assets"][1]["sizing"]["actual_account_value_usd"] = 4_700.0
    module = import_module("hypervector.research.v58_venue_state_context")

    context = module.load_v58_venue_state_context(
        _write(tmp_path, payload),
        observed_at=_OBSERVED,
        maximum_age_seconds=180.0,
        active_profile_id=_ACTIVE_ID,
        active_profile_fingerprint=_ACTIVE_FINGERPRINT,
        candidate_profile_id=_CANDIDATE_ID,
        candidate_profile_fingerprint=_CANDIDATE_FINGERPRINT,
        candidate_symbols=_SYMBOLS,
    )
    result = module.venue_state_context_payload(context)

    assert result["actual_account_value_usd"] == pytest.approx(4_700.0)
    assert result["maximum_sampled_account_value_usd"] == pytest.approx(4_875.84)
    assert result["account_value_sampling_range_usd"] == pytest.approx(175.84)
    assert result["actual_account_value_selection"] == "minimum_sequential_sample"


def test_wrong_candidate_identity_is_rejected(tmp_path: Path) -> None:
    """A similar roster cannot alias the exact V58 candidate."""
    payload = _payload()
    payload["identity"]["candidate_profile_fingerprint"] = "9" * 64
    module = import_module("hypervector.research.v58_venue_state_context")

    with pytest.raises(ValueError, match="candidate profile fingerprint"):
        module.load_v58_venue_state_context(
            _write(tmp_path, payload),
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
            active_profile_id=_ACTIVE_ID,
            active_profile_fingerprint=_ACTIVE_FINGERPRINT,
            candidate_profile_id=_CANDIDATE_ID,
            candidate_profile_fingerprint=_CANDIDATE_FINGERPRINT,
            candidate_symbols=_SYMBOLS,
        )


def test_preflight_with_execution_authority_is_rejected(tmp_path: Path) -> None:
    """The continuous report must accept only non-executing venue evidence."""
    payload = _payload()
    payload["authority"]["execution_authority"] = "hyperliquid_mainnet"
    module = import_module("hypervector.research.v58_venue_state_context")

    with pytest.raises(ValueError, match="authority-none"):
        module.load_v58_venue_state_context(
            _write(tmp_path, payload),
            observed_at=_OBSERVED,
            maximum_age_seconds=180.0,
            active_profile_id=_ACTIVE_ID,
            active_profile_fingerprint=_ACTIVE_FINGERPRINT,
            candidate_profile_id=_CANDIDATE_ID,
            candidate_profile_fingerprint=_CANDIDATE_FINGERPRINT,
            candidate_symbols=_SYMBOLS,
        )


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload() -> dict[str, object]:
    assets = [_asset(symbol) for symbol in _SYMBOLS]
    return {
        "schema_version": 1,
        "observed_at_utc": "2026-08-19T14:48:23+00:00",
        "authority": {
            "execution_authority": "none",
            "execution_client_constructed": False,
            "signing_key_required": False,
            "operation": "multi_asset_read_only_preflight",
        },
        "identity": {
            "active_profile_id": _ACTIVE_ID,
            "active_profile_fingerprint": _ACTIVE_FINGERPRINT,
            "candidate_profile_id": _CANDIDATE_ID,
            "candidate_profile_fingerprint": _CANDIDATE_FINGERPRINT,
            "network": "mainnet",
        },
        "portfolio": {
            "configured_assets": len(_SYMBOLS),
            "flat_no_orders": True,
            "ledger_reconciled": True,
            "open_orders": 0,
            "open_positions": 0,
            "readiness_reasons": [],
            "sizing_reference_equity_usd": 5_000.0,
        },
        "assets": assets,
    }


def _asset(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "sizing": {
            "actual_account_value_usd": 4_875.84,
            "sizing_reference_equity_usd": 5_000.0,
        },
        "position": {"size_signed": 0.0},
        "open_orders": [],
        "ledger_reconciliation": {
            "matches": True,
            "orders_match": True,
            "position_matches": True,
            "venue_owned_order_ids": [],
        },
    }
