"""Local environment loading with secret-value-free credential telemetry."""

from __future__ import annotations

import os
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hypervector.live.policy import SECRET_ENV_API_KEY, SECRET_ENV_WALLET


@dataclass(frozen=True)
class CredentialPresence:
    """Boolean-only status for the two Hyperliquid credential variables."""

    wallet_configured: bool
    signing_key_configured: bool


def load_dotenv_if_present(
    *,
    candidates: Sequence[Path] | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Load existing dotenv files without replacing process environment values."""
    return _load_dotenv(candidates=candidates, environ=environ, allowed_keys=None)


def load_wallet_env_if_present(
    *,
    candidates: Sequence[Path] | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Load only the public wallet identity for an execution-incapable process."""
    return _load_dotenv(
        candidates=candidates,
        environ=environ,
        allowed_keys=frozenset({SECRET_ENV_WALLET}),
    )


def load_selected_env_if_present(
    allowed_keys: frozenset[str], *, candidates: Sequence[Path] | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Load only the environment names required by one non-execution workflow."""
    return _load_dotenv(candidates=candidates, environ=environ, allowed_keys=allowed_keys)


def _load_dotenv(
    *,
    candidates: Sequence[Path] | None,
    environ: MutableMapping[str, str] | None,
    allowed_keys: frozenset[str] | None,
) -> tuple[Path, ...]:
    paths = candidates or (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    )
    target = environ if environ is not None else os.environ
    loaded: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        for raw in resolved.read_text(encoding="utf-8").splitlines():
            parsed = _parse_dotenv_line(raw)
            if parsed is None:
                continue
            key, value = parsed
            if allowed_keys is not None and key not in allowed_keys:
                continue
            if key not in target:
                target[key] = value
        loaded.append(resolved)
    return tuple(loaded)


def dotenv_key_presence(
    keys: Sequence[str],
    *,
    candidates: Sequence[Path] | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, bool]:
    """Report which keys are configured (process environment first, then dotenv).

    Precedence matches the real loaders: a name already present in the process
    environment (even empty) is never replaced by a dotenv value. Values are read
    into a scratch mapping that is cleared before returning; the process
    environment is never modified and no value leaves this function.
    """
    source = environ if environ is not None else os.environ
    scratch: dict[str, str] = {key: source[key] for key in keys if key in source}
    try:
        _load_dotenv(
            candidates=candidates, environ=scratch, allowed_keys=frozenset(keys)
        )
        return {key: bool((scratch.get(key) or "").strip()) for key in keys}
    finally:
        scratch.clear()


def credential_presence_from_env(
    *,
    environ: MutableMapping[str, str] | None = None,
) -> CredentialPresence:
    """Return credential presence without copying values into telemetry."""
    source = environ if environ is not None else os.environ
    return CredentialPresence(
        wallet_configured=bool((source.get(SECRET_ENV_WALLET) or "").strip()),
        signing_key_configured=bool((source.get(SECRET_ENV_API_KEY) or "").strip()),
    )


def _parse_dotenv_line(raw: str) -> tuple[str, str] | None:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, _, raw_value = line.partition("=")
    clean_key = key.strip()
    if not clean_key:
        return None
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return clean_key, value
