"""Stable process-independent identity hashing for live cohort profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


class LiveIdentityError(ValueError):
    """A profile contains a value that cannot be canonically fingerprinted."""


def stable_fingerprint(values: Mapping[str, object]) -> str:
    """Return a deterministic SHA-256 fingerprint for supported profile values."""
    payload = json.dumps(
        _canonical_value(values),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise LiveIdentityError("fingerprint mappings must use string keys")
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=_sort_key)
    raise LiveIdentityError(
        f"fingerprint contains unsupported value type: {type(value).__name__}"
    )


def _sort_key(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
