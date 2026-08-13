"""Exact core and HIP-3 perpetual venue identities."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.data.oxa_api import validate_hip3_symbol, validate_symbol


@dataclass(frozen=True)
class PerpVenueIdentity:
    """One exact venue symbol and its optional builder-perp namespace."""

    symbol: str
    perp_dex: str


def configured_perp_dexes(symbols: tuple[str, ...]) -> tuple[str, ...]:
    """Return unique non-core perp namespaces in configuration order."""
    identities = tuple(parse_perp_venue_identity(symbol) for symbol in symbols)
    namespaces = tuple(
        dict.fromkeys(identity.perp_dex for identity in identities if identity.perp_dex)
    )
    if namespaces and any(not identity.perp_dex for identity in identities):
        return ("", *namespaces)
    return namespaces


def parse_perp_venue_identity(value: str) -> PerpVenueIdentity:
    """Validate one exact core or lowercase-dex/uppercase-asset identity."""
    if value != value.strip() or not value:
        raise ValueError("perpetual venue identity must not contain outer whitespace")
    if ":" not in value:
        try:
            validate_symbol(value)
        except ValueError as exc:
            raise ValueError(f"perpetual venue identity is invalid: {exc}") from exc
        return PerpVenueIdentity(value, "")
    try:
        dex, _ = validate_hip3_symbol(value)
    except ValueError as exc:
        raise ValueError(f"perpetual venue identity is invalid: {exc}") from exc
    return PerpVenueIdentity(value, dex)
