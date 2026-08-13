"""Generate and validate durable Hyperliquid client-order identities."""

from __future__ import annotations

import re
import secrets


_CLIENT_ORDER_ID_PATTERN = re.compile(r"0x[0-9a-f]{32}")


class SolClientOrderIdError(ValueError):
    """A client-order identity does not satisfy the venue wire contract."""


def new_client_order_id() -> str:
    """Return a lowercase 16-byte Hyperliquid client-order identity."""
    return "0x" + secrets.token_hex(16)


def validate_client_order_id(value: str) -> str:
    """Return a valid lowercase Hyperliquid client-order identity or fail."""
    if not isinstance(value, str) or _CLIENT_ORDER_ID_PATTERN.fullmatch(value) is None:
        raise SolClientOrderIdError(
            "client order id must be 0x followed by 32 lowercase hexadecimal digits"
        )
    return value
