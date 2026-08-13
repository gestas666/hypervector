"""Atomic, identity-bound operator command inbox for the armed cohort backend."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_SYMBOL = re.compile(r"(?:xyz:)?[A-Z0-9-]{2,16}")
_OPERATOR_MINIMUM_AGE_SECONDS = 60.0
_OPERATOR_MAXIMUM_AGE_SECONDS = 180.0
_OPERATOR_POLL_WINDOWS = 2.0
_OPERATOR_SYMBOL_IO_ALLOWANCE_SECONDS = 10.0
_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "run_id",
        "profile_fingerprint",
        "created_at_utc",
        "action",
        "symbol",
        "provider",
        "side",
        "settings",
    }
)


@dataclass(frozen=True)
class CohortAssetStage:
    """Editable next-run envelope for one configured asset."""

    symbol: str
    leverage: float
    margin_fraction: float
    max_notional_usd: float
    stop_bps: float
    maximum_hold_seconds: int


@dataclass(frozen=True)
class CohortProviderStage:
    """Editable next-run execution scope for one provider."""

    strategy_id: str
    execution_symbols: tuple[str, ...]


@dataclass(frozen=True)
class CohortProfileSettings:
    """Complete validated settings submitted for a staged next-run profile."""

    maximum_positions: int
    poll_seconds: float
    assets: tuple[CohortAssetStage, ...]
    providers: tuple[CohortProviderStage, ...]


@dataclass(frozen=True)
class CohortOperatorCommand:
    """One validated manual request bound to an exact live backend run."""

    request_id: str
    run_id: str
    profile_fingerprint: str
    created_at_utc: str
    action: str
    symbol: str
    provider: str | None
    side: str | None
    settings: CohortProfileSettings | None


@dataclass(frozen=True)
class CohortOperatorClaim:
    """One atomically claimed file plus its validation result."""

    request_id: str
    path: Path
    command: CohortOperatorCommand | None
    issue: str | None


class CohortOperatorInboxError(RuntimeError):
    """The command transport cannot preserve atomicity or audit identity."""


def operator_command_maximum_age_seconds(
    *,
    poll_seconds: float,
    symbol_count: int,
) -> float:
    """Return a finite command TTL covering one serialized cohort cycle."""
    if not math.isfinite(poll_seconds) or poll_seconds <= 0.0:
        raise ValueError("operator command poll seconds must be positive")
    if isinstance(symbol_count, bool) or symbol_count <= 0:
        raise ValueError("operator command symbol count must be positive")
    cycle_budget = (
        _OPERATOR_POLL_WINDOWS * poll_seconds
        + _OPERATOR_SYMBOL_IO_ALLOWANCE_SECONDS * symbol_count
    )
    return min(
        _OPERATOR_MAXIMUM_AGE_SECONDS,
        max(_OPERATOR_MINIMUM_AGE_SECONDS, cycle_budget),
    )


class CohortOperatorInbox:
    """Claim, validate, and finalize local commands exactly once."""

    def __init__(
        self,
        *,
        root: Path,
        run_id: str,
        profile_fingerprint: str,
        now_fn: Callable[[], datetime],
        maximum_age_seconds: float = 30.0,
    ) -> None:
        if not run_id.strip() or not profile_fingerprint.strip():
            raise ValueError("operator inbox requires run and profile identity")
        if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
            raise ValueError("operator command maximum age must be positive")
        self._root = root
        self._run_id = run_id
        self._profile_fingerprint = profile_fingerprint
        self._now_fn = now_fn
        self._maximum_age_seconds = maximum_age_seconds
        for name in ("pending", "claimed", "completed", "rejected", "outcomes"):
            (root / name).mkdir(parents=True, exist_ok=True)

    def claim_pending(self) -> tuple[CohortOperatorClaim, ...]:
        """Atomically claim every pending request and validate its envelope."""
        claims = list(self._recover_orphans())
        for source in sorted((self._root / "pending").glob("*.json")):
            request_id = source.stem
            target = self._root / "claimed" / source.name
            if target.exists():
                claims.append(
                    CohortOperatorClaim(
                        request_id,
                        source,
                        None,
                        "request id was already claimed",
                    )
                )
                continue
            try:
                os.replace(source, target)
            except OSError as exc:
                raise CohortOperatorInboxError(
                    f"operator command claim failed for {source.name}: {exc}"
                ) from exc
            claims.append(self._parse_claim(request_id, target))
        return tuple(claims)

    def finalize(
        self,
        claim: CohortOperatorClaim,
        *,
        status: str,
        reason: str,
    ) -> None:
        """Publish an outcome and move the claimed request to its terminal state."""
        if status not in {"completed", "rejected"}:
            raise ValueError("operator outcome must be completed or rejected")
        if not reason.strip():
            raise ValueError("operator outcome reason must be non-empty")
        destination = self._root / status / f"{claim.request_id}.json"
        if destination.exists():
            raise CohortOperatorInboxError("operator request already has an outcome")
        outcome = {
            "schema_version": 1,
            "request_id": claim.request_id,
            "run_id": self._run_id,
            "status": status,
            "reason": reason,
            "completed_at_utc": self._now_utc().isoformat(),
        }
        self._write_outcome(claim.request_id, outcome)
        try:
            os.replace(claim.path, destination)
        except OSError as exc:
            raise CohortOperatorInboxError(
                f"operator command finalization failed: {exc}"
            ) from exc

    def _recover_orphans(self) -> tuple[CohortOperatorClaim, ...]:
        return tuple(
            CohortOperatorClaim(
                path.stem,
                path,
                None,
                "request was left claimed by a previous backend",
            )
            for path in sorted((self._root / "claimed").glob("*.json"))
        )

    def _parse_claim(self, request_id: str, path: Path) -> CohortOperatorClaim:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return CohortOperatorClaim(
                request_id, path, None, "request JSON is invalid"
            )
        try:
            command = self._parse_command(request_id, raw)
        except ValueError as exc:
            return CohortOperatorClaim(request_id, path, None, str(exc))
        return CohortOperatorClaim(request_id, path, command, None)

    def _parse_command(
        self,
        request_id: str,
        raw: object,
    ) -> CohortOperatorCommand:
        if not isinstance(raw, dict) or frozenset(raw) != _FIELDS:
            raise ValueError("request fields do not match the command schema")
        values: Mapping[str, object] = raw
        if not _REQUEST_ID.fullmatch(request_id) or values["request_id"] != request_id:
            raise ValueError("request id is invalid")
        if values["schema_version"] != 1:
            raise ValueError("request schema version is unsupported")
        run_id = _text(values, "run_id")
        profile = _text(values, "profile_fingerprint")
        if run_id != self._run_id:
            raise ValueError("request run_id does not match active backend")
        if profile != self._profile_fingerprint:
            raise ValueError("request profile does not match active backend")
        created = _timestamp(_text(values, "created_at_utc"))
        age = (self._now_utc() - created).total_seconds()
        if age > self._maximum_age_seconds:
            raise ValueError("request is stale")
        if age < -5.0:
            raise ValueError("request timestamp is in the future")
        return _action_command(request_id, run_id, profile, created, values)

    def _write_outcome(self, request_id: str, payload: Mapping[str, object]) -> None:
        target = self._root / "outcomes" / f"{request_id}.json"
        temporary = self._root / "outcomes" / f".{request_id}.{os.getpid()}.tmp"
        try:
            temporary.write_text(
                json.dumps(payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, target)
        except OSError as exc:
            raise CohortOperatorInboxError(
                f"operator outcome publication failed: {exc}"
            ) from exc

    def _now_utc(self) -> datetime:
        value = self._now_fn()
        if value.tzinfo is None or value.utcoffset() is None:
            raise CohortOperatorInboxError(
                "operator inbox clock must be timezone-aware"
            )
        return value.astimezone(timezone.utc)


def _action_command(
    request_id: str,
    run_id: str,
    profile: str,
    created: datetime,
    values: Mapping[str, object],
) -> CohortOperatorCommand:
    action = _text(values, "action")
    symbol = _text(values, "symbol")
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("request symbol is invalid")
    provider = _optional_text(values, "provider")
    side = _optional_text(values, "side")
    if action == "manual_enter" and (provider is None or side not in {"long", "short"}):
        raise ValueError("manual entry requires provider and long/short side")
    if action == "manual_close" and (provider is not None or side is not None):
        raise ValueError("manual close requires null provider and side")
    settings = _profile_settings(values.get("settings"))
    if action in {"manual_enter", "manual_close"} and settings is not None:
        raise ValueError("manual requests require null settings")
    if action == "stage_profile":
        if (
            symbol != "MULTI"
            or provider is not None
            or side is not None
            or settings is None
        ):
            raise ValueError(
                "profile stage requires MULTI, null direction, and settings"
            )
    if action == "transition_drain" and (
        symbol != "MULTI"
        or provider is not None
        or side is not None
        or settings is not None
    ):
        raise ValueError("transition drain requires MULTI and null trade fields")
    if action not in {
        "manual_enter",
        "manual_close",
        "stage_profile",
        "transition_drain",
    }:
        raise ValueError("request action is unsupported")
    return CohortOperatorCommand(
        request_id,
        run_id,
        profile,
        created.isoformat(),
        action,
        symbol,
        provider,
        side,
        settings,
    )


def _text(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"request {key} must be non-empty text")
    return value.strip()


def _optional_text(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"request {key} must be null or non-empty text")
    return value.strip()


def _profile_settings(value: object) -> CohortProfileSettings | None:
    if value is None:
        return None
    values = _exact_mapping(
        value,
        {"maximum_positions", "poll_seconds", "assets", "providers"},
        "profile settings",
    )
    assets = _object_rows(values.get("assets"), "profile assets")
    providers = _object_rows(values.get("providers"), "profile providers")
    return CohortProfileSettings(
        maximum_positions=_positive_integer(values, "maximum_positions"),
        poll_seconds=_positive_number(values, "poll_seconds"),
        assets=tuple(_asset_stage(row) for row in assets),
        providers=tuple(_provider_stage(row) for row in providers),
    )


def _asset_stage(values: Mapping[str, object]) -> CohortAssetStage:
    _require_fields(
        values,
        {
            "symbol",
            "leverage",
            "margin_fraction",
            "max_notional_usd",
            "stop_bps",
            "maximum_hold_seconds",
        },
        "asset stage",
    )
    return CohortAssetStage(
        _text(values, "symbol"),
        _positive_number(values, "leverage"),
        _positive_number(values, "margin_fraction"),
        _positive_number(values, "max_notional_usd"),
        _positive_number(values, "stop_bps"),
        _positive_integer(values, "maximum_hold_seconds"),
    )


def _provider_stage(values: Mapping[str, object]) -> CohortProviderStage:
    _require_fields(values, {"strategy_id", "execution_symbols"}, "provider stage")
    symbols = values.get("execution_symbols")
    if not isinstance(symbols, list) or not all(
        isinstance(item, str) and item for item in symbols
    ):
        raise ValueError("provider execution_symbols must be a text list")
    return CohortProviderStage(_text(values, "strategy_id"), tuple(symbols))


def _exact_mapping(value: object, fields: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return value


def _require_fields(values: Mapping[str, object], fields: set[str], label: str) -> None:
    if set(values) != fields:
        raise ValueError(f"{label} fields are invalid")


def _object_rows(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, dict) for item in value)
    ):
        raise ValueError(f"{label} must be non-empty objects")
    return tuple(value)


def _positive_number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"profile {key} must be positive and finite")
    return float(value)


def _positive_integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"profile {key} must be a positive integer")
    return value


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("request created_at_utc is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("request created_at_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc)
