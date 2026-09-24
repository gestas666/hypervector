"""Wait for a reachable venue and check its market contract before an armed start.

An armed start writes a gigabyte-scale pre-start bundle and replays every ledger
before it builds a venue client. On an offline host that work is wasted, and the
crash that follows is charged to the supervisor's restart budget. When a
market's metadata contradicts the profile, every relaunch fails the same way.
This probe runs inside the runtime lock, before the bundle, with public unsigned
reads only: it waits in process while the venue is unreachable, and it refuses
the start when a market's maximum leverage differs from the configured contract.

While it waits it keeps a small marker next to the process lock, so a supervisor
can tell a backend that is waiting for the venue from one that is hung.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile

import requests

from hypervector.data.hl import HL_INFO_URL
from hypervector.live.hyperliquid_perp_parsing import parse_market_for_symbol
from hypervector.live.hyperliquid_perp_reader import VenueMetadataMismatchError
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfigError
from hypervector.live.perp_venue_identity import (
    configured_perp_dexes,
    parse_perp_venue_identity,
)
from hypervector.live.transient_transport import transient_read_failure_reason

# Read by scripts/cohort_supervisor_venue_wait.py; the two names must agree.
VENUE_WAIT_MARKER = "venue_wait.json"
REQUEST_TIMEOUT_SECONDS = 10.0
INITIAL_BACKOFF_SECONDS = 15.0
MAXIMUM_BACKOFF_SECONDS = 300.0
# A STOP file is noticed within this long even during the longest backoff.
_STOP_CHECK_SECONDS = 5.0

MetaFetcher = Callable[[str], object]


def http_meta_fetcher(session: requests.Session) -> MetaFetcher:
    """Return a public, unauthenticated reader of one perp dex's market metadata."""

    def fetch(dex: str) -> object:
        response = session.post(
            HL_INFO_URL,
            json={"type": "meta", "dex": dex},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()

    return fetch


def fresh_session_unreachable_reason(symbols: Sequence[str]) -> str | None:
    """Return why the venue is unreachable from this host, or None when it answers.

    It repeats the start probe's public metadata reads on a new HTTP session, so
    a fault confined to a running process's own connections cannot pass for an
    offline host. Only a transport failure that a later read may clear counts as
    unreachable, on any configured dex, because a relaunch's start probe would
    wait on that dex too; any other answer shows the venue can be reached.
    """
    dexes = configured_perp_dexes(tuple(symbols)) or ("",)
    with requests.Session() as session:
        fetch = http_meta_fetcher(session)
        for dex in dexes:
            try:
                fetch(dex)
            except requests.RequestException as exc:
                reason = transient_read_failure_reason(exc)
                if reason is not None:
                    return reason
    return None


def await_venue_start(
    expected_max_leverage: Mapping[str, int],
    *,
    fetch_meta: MetaFetcher,
    stop_file: Path,
    marker: Path,
    sleep_fn: Callable[[float], None],
    now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    emit: Callable[[str], None] = print,
) -> int:
    """Return the attempt count once every configured market matches the venue.

    Only a transport failure that a later read may clear (as classified for the
    running cohort) is waited out; any other read failure propagates unchanged.
    """
    if not expected_max_leverage:
        raise ValueError("venue start probe requires at least one market")
    dexes = configured_perp_dexes(tuple(expected_max_leverage)) or ("",)
    attempts = 0
    waiting_since: str | None = None
    try:
        while True:
            _refuse_on_stop(stop_file)
            attempts += 1
            try:
                metadata = {dex: fetch_meta(dex) for dex in dexes}
            except requests.RequestException as exc:
                reason = transient_read_failure_reason(exc)
                if reason is None:
                    raise
                delay = backoff_seconds(attempts)
                waiting_since = waiting_since or now_fn().isoformat()
                _write_marker(marker, waiting_since, now_fn(), attempts, reason, emit)
                emit(
                    f"venue unreachable before live start ({reason}); "
                    f"attempt {attempts}, next in {delay:.0f}s"
                )
                _sleep_watching_stop(delay, stop_file, sleep_fn)
                continue
            break
    finally:
        marker.unlink(missing_ok=True)
    require_market_contract(expected_max_leverage, metadata)
    emit(
        f"venue start probe passed: markets={len(expected_max_leverage)} attempts={attempts}"
    )
    return attempts


def backoff_seconds(attempt: int) -> float:
    """Return the wait after a failed attempt: 15 s doubling to a 300 s cap."""
    if attempt < 1:
        raise ValueError("attempt must be positive")
    return min(MAXIMUM_BACKOFF_SECONDS, INITIAL_BACKOFF_SECONDS * 2.0 ** (attempt - 1))


def require_market_contract(
    expected_max_leverage: Mapping[str, int],
    metadata: Mapping[str, object],
) -> None:
    """Refuse when any market's maximum leverage differs from its configuration."""
    mismatches = []
    for symbol, expected in expected_max_leverage.items():
        dex = parse_perp_venue_identity(symbol).perp_dex
        observed = parse_market_for_symbol(metadata[dex], symbol).max_leverage
        if observed != expected:
            mismatches.append(
                f"{symbol} max leverage mismatch: expected {expected}, "
                f"observed {observed}"
            )
    if mismatches:
        raise VenueMetadataMismatchError("; ".join(mismatches))


def _refuse_on_stop(stop_file: Path) -> None:
    if stop_file.exists():
        raise MultiAssetLiveConfigError(
            f"operator stop file exists; inspect before removing: {stop_file}"
        )


def _sleep_watching_stop(
    seconds: float, stop_file: Path, sleep_fn: Callable[[float], None]
) -> None:
    remaining = seconds
    while remaining > 0.0:
        _refuse_on_stop(stop_file)
        step = min(_STOP_CHECK_SECONDS, remaining)
        sleep_fn(step)
        remaining -= step


def _write_marker(
    marker: Path,
    waiting_since: str,
    now: datetime,
    attempts: int,
    reason: str,
    emit: Callable[[str], None],
) -> None:
    """Publish the wait atomically; the marker is advisory, so failure only warns."""
    payload = {
        "schema_version": 1,
        "pid": os.getpid(),
        "waiting_since_utc": waiting_since,
        "updated_at_utc": now.isoformat(),
        "attempts": attempts,
        "reason": reason,
    }
    try:
        descriptor, temporary = tempfile.mkstemp(
            dir=marker.parent, prefix=f".{marker.name}."
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, allow_nan=False, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, marker)
        finally:
            Path(temporary).unlink(missing_ok=True)
    except OSError as exc:
        emit(f"venue wait marker not written: {type(exc).__name__}")
