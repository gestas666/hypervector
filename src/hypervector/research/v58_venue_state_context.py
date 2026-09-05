"""Exact public-wallet venue state for the report-only V58 loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]


@dataclass(frozen=True)
class VenueStateContext:
    """Validated point-in-time position and order reconciliation."""

    observed_at_utc: str
    preflight_age_seconds: float
    preflight_fresh: bool
    venue_flat_no_orders: bool
    venue_ledger_reconciled: bool
    venue_open_positions: int
    venue_open_orders: int
    actual_account_value_usd: float
    maximum_sampled_account_value_usd: float
    account_value_sampling_range_usd: float
    sizing_reference_equity_usd: float
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_venue_state_context(
    path: Path,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
    active_profile_id: str,
    active_profile_fingerprint: str,
    candidate_profile_id: str,
    candidate_profile_fingerprint: str,
    candidate_symbols: tuple[str, ...],
) -> VenueStateContext:
    """Load exact preflight state while treating stale evidence as historical."""
    observed = _aware_utc(observed_at, "observation time")
    maximum_age = _positive_number(maximum_age_seconds, "maximum age")
    reference = file_evidence(path)
    raw = path.read_bytes()
    if _raw_evidence(raw) != reference:
        raise ValueError("V58 venue preflight changed while reading")
    payload = _mapping(json.loads(raw), "venue preflight")
    _require_authority_none(payload)
    _require_identity(
        payload,
        active_profile_id,
        active_profile_fingerprint,
        candidate_profile_id,
        candidate_profile_fingerprint,
    )
    state = _venue_state(payload, candidate_symbols)
    source_time = _timestamp(payload.get("observed_at_utc"), "preflight observed_at")
    age = _nonnegative_age(observed, source_time)
    if file_evidence(path) != reference:
        raise ValueError("V58 venue preflight changed during evaluation")
    evidence = {"preflight": {"path": str(path.resolve()), **reference}}
    return VenueStateContext(
        source_time.isoformat(), age, age <= maximum_age, *state, evidence
    )


def venue_state_context_payload(context: VenueStateContext) -> dict[str, object]:
    """Serialize venue truth without treating a stale snapshot as current."""
    return {
        "venue_preflight_observed_at_utc": context.observed_at_utc,
        "venue_preflight_age_seconds": context.preflight_age_seconds,
        "preflight_fresh": context.preflight_fresh,
        "current_venue_position_order_state_verified": context.preflight_fresh,
        "venue_flat_no_orders": context.venue_flat_no_orders,
        "venue_ledger_reconciled": context.venue_ledger_reconciled,
        "venue_open_positions": context.venue_open_positions,
        "venue_open_orders": context.venue_open_orders,
        "actual_account_value_usd": context.actual_account_value_usd,
        "maximum_sampled_account_value_usd": (
            context.maximum_sampled_account_value_usd
        ),
        "account_value_sampling_range_usd": context.account_value_sampling_range_usd,
        "actual_account_value_selection": "minimum_sequential_sample",
        "sizing_reference_equity_usd": context.sizing_reference_equity_usd,
        "automatic_live_change": False,
        "execution_authority": context.execution_authority,
    }


def _venue_state(
    payload: Record, expected_symbols: tuple[str, ...]
) -> tuple[bool, bool, int, int, float, float, float, float]:
    portfolio = _mapping(payload.get("portfolio"), "preflight portfolio")
    rows = payload.get("assets")
    if not isinstance(rows, list):
        raise ValueError("V58 preflight assets must be a list")
    assets = tuple(_mapping(row, "preflight asset") for row in rows)
    symbols = tuple(_text(row.get("symbol"), "asset symbol") for row in assets)
    if len(symbols) != len(set(symbols)) or set(symbols) != set(expected_symbols):
        raise ValueError("V58 venue preflight asset coverage is inconsistent")
    open_positions, open_orders, reconciled = _asset_totals(assets)
    flat = open_positions == 0 and open_orders == 0
    if _integer(portfolio.get("open_positions"), "open positions") != open_positions:
        raise ValueError("V58 venue preflight position total is inconsistent")
    if _integer(portfolio.get("open_orders"), "open orders") != open_orders:
        raise ValueError("V58 venue preflight order total is inconsistent")
    if _boolean(portfolio.get("flat_no_orders"), "flat state") != flat:
        raise ValueError("V58 venue preflight flat state is inconsistent")
    if _boolean(portfolio.get("ledger_reconciled"), "ledger state") != reconciled:
        raise ValueError("V58 venue preflight ledger state is inconsistent")
    actual_min, actual_max, reference = _equity_state(portfolio, assets)
    return (
        flat,
        reconciled,
        open_positions,
        open_orders,
        actual_min,
        actual_max,
        actual_max - actual_min,
        reference,
    )


def _equity_state(
    portfolio: Record, assets: tuple[Record, ...]
) -> tuple[float, float, float]:
    actual_values: list[float] = []
    reference_values: list[float] = []
    for asset in assets:
        symbol = _text(asset.get("symbol"), "asset symbol")
        sizing = _mapping(asset.get("sizing"), f"{symbol} sizing")
        actual_values.append(
            _positive_number(sizing.get("actual_account_value_usd"), "account value")
        )
        reference_values.append(
            _positive_number(
                sizing.get("sizing_reference_equity_usd"), "sizing reference"
            )
        )
    if not actual_values:
        raise ValueError("V58 venue preflight actual account value is unavailable")
    actual_min = min(actual_values)
    actual_max = max(actual_values)
    reference = _consistent_value(reference_values, "sizing reference")
    portfolio_reference = _positive_number(
        portfolio.get("sizing_reference_equity_usd"), "portfolio sizing reference"
    )
    if not isclose(reference, portfolio_reference, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("V58 venue preflight sizing reference is inconsistent")
    return actual_min, actual_max, reference


def _consistent_value(values: list[float], label: str) -> float:
    if not values:
        raise ValueError(f"V58 venue preflight {label} is unavailable")
    first = values[0]
    if any(not isclose(value, first, rel_tol=1e-12, abs_tol=1e-12) for value in values):
        raise ValueError(f"V58 venue preflight {label} is inconsistent")
    return first


def _asset_totals(assets: tuple[Record, ...]) -> tuple[int, int, bool]:
    positions = 0
    orders = 0
    reconciled = True
    for row in assets:
        symbol = _text(row.get("symbol"), "asset symbol")
        position = _mapping(row.get("position"), f"{symbol} position")
        positions += int(_number(position.get("size_signed"), "position size") != 0.0)
        raw_orders = row.get("open_orders")
        if not isinstance(raw_orders, list):
            raise ValueError(f"V58 {symbol} open orders must be a list")
        orders += len(raw_orders)
        ledger = _mapping(row.get("ledger_reconciliation"), f"{symbol} ledger")
        flags = tuple(
            _boolean(ledger.get(key), f"{symbol} {key}")
            for key in ("matches", "orders_match", "position_matches")
        )
        reconciled &= all(flags)
    return positions, orders, reconciled


def _require_authority_none(payload: Record) -> None:
    authority = _mapping(payload.get("authority"), "preflight authority")
    expected = {
        "execution_authority": "none",
        "execution_client_constructed": False,
        "signing_key_required": False,
        "operation": "multi_asset_read_only_preflight",
    }
    if any(authority.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 venue preflight is not authority-none evidence")


def _require_identity(
    payload: Record,
    active_id: str,
    active_fingerprint: str,
    candidate_id: str,
    candidate_fingerprint: str,
) -> None:
    identity = _mapping(payload.get("identity"), "preflight identity")
    expected = {
        "active_profile_id": _text(active_id, "active profile id"),
        "active_profile_fingerprint": _sha256_text(
            active_fingerprint, "active profile fingerprint"
        ),
        "candidate_profile_id": _text(candidate_id, "candidate profile id"),
        "candidate_profile_fingerprint": _sha256_text(
            candidate_fingerprint, "candidate profile fingerprint"
        ),
    }
    for key, value in expected.items():
        if identity.get(key) != value:
            raise ValueError(f"V58 venue preflight {key.replace('_', ' ')} differs")
    if identity.get("network") != "mainnet":
        raise ValueError("V58 venue preflight network differs")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"V58 {label} must be non-empty text")
    return value


def _sha256_text(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"V58 {label} must be lowercase sha256")
    return text


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"V58 {label} must be boolean")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 {label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    output = float(value)
    if not isfinite(output):
        raise ValueError(f"V58 {label} must be finite")
    return output


def _positive_number(value: object, label: str) -> float:
    output = _number(value, label)
    if output <= 0.0:
        raise ValueError(f"V58 {label} must be positive")
    return output


def _timestamp(value: object, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, label))
    except ValueError as exc:
        raise ValueError(f"V58 {label} is invalid") from exc
    return _aware_utc(parsed, label)


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"V58 {label} must be timezone-aware")
    return value.astimezone(UTC)


def _nonnegative_age(observed: datetime, source: datetime) -> float:
    age = (observed - source).total_seconds()
    if age < 0.0:
        raise ValueError("V58 venue preflight is from the future")
    return age


def _raw_evidence(raw: bytes) -> dict[str, object]:
    return {"sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
