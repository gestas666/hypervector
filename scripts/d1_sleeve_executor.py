#!/usr/bin/env python3
"""D1 sleeve executor v1: follows the observe-only D1 shadow on a Hyperliquid sub-account.

The shadow ledger (scripts/d1_shadow_runner.py, sha256 pinned in the config) is
the only source of universe, signals and exits. This executor allocates each
fresh virtual entry at today's open against the REAL sub-account book (10 slots,
gross <= 1.5 x book equity, sub collateral) in the shadow's priority order,
sizes it at ``risk_fraction`` of BOOK equity (master + sub) with a stop of
2 x ATR(signal) x unit from the Hyperliquid fill, closes a real position when
its virtual trade closes for any reason (or its own Hyperliquid stop fires),
and makes every owned position end every armed run with exactly one verified,
resting, reduce-only market stop.

Protection does not depend on reading the fill back (a lost reply and an
info node that lags make a fill look unowned or flat):

- A1: every entry IOC carries a reduce-only stop-market child in the same
  action (grouping normalTpsl), at the rule distance from the IOC's reference
  mid. The venue places it the moment the IOC fully fills, whatever becomes
  of the reply or the reads; a partial fill leaves no child and the sleeve
  stops the fill as before (from the read, or from the acks when no read
  shows it). Once a read shows the position the stop is re-anchored to the
  venue fill (place, then cancel), as pre-registered.
- A2: every sweep gives every position the reads show, owned or not, a
  reduce-only stop covering all of it. A position the sleeve cannot
  attribute gets a guard stop at the rule distance (shadow ATR, else the
  journal's, else 15% of its entry price), on the protective side of the
  mark and inside its liquidation price; it stays critical and is never
  traded down or closed.

Safety (SRS_HV1_HONESTY, SRS_HV1_NO_GATES):

- Without ``--enabled --i-accept-live-risk --approval PATH`` every command is a
  DRY RUN: the private key is never loaded, the SDK is never imported, no
  exchange object exists, the transport guard refuses ``/exchange`` and the
  log says ``signing_client=none exchange_posts=0``. Nothing is written.
- Armed, every mutation passes ``SubAccountGateway._mutate``: vault = the
  sub-account (never None, never the master), signer = the sleeve API wallet
  (never the engine's ``hl-api``), one of order/cancel/cancelByCloid/
  updateLeverage, a main-dex coin that is not delisted, outside the quiet
  window and the phase deadline, inside the per-run budget, and new risk only
  when allowed (never under STOP, in the sweep, flatten or exit phases).
- Mainnet only. The only network peer is api.hyperliquid.xyz (HTTPS POST to
  /info, and /exchange when armed), paced and budgeted per run; no
  Hyperliquid call is made in minutes 57-03, except one kind: a protective
  reduce-only stop order (one action, weight 1; an owned position's rule
  stop or a guard stop), which may be sent after the deadline and inside the
  quiet window so a fill is never left without its stop. The final check
  (P7) keeps a budget reserve of its own for that protection.
- Only technical failure aborts. There is no drawdown, P&L or kill limit.
- Logs, the journal, alerts and status carry fingerprints, booleans and
  numbers only: never an address, a key or a webhook URL.
- Armed runs hold a repo lock and a host-wide lock per sub-account (any
  checkout), and an armed run refused before its session starts still
  alerts (banner, alerts.jsonl, webhook).

Commands: probe, run (default; launchd hourly at :15), canary, flatten, status,
approval-template. Exit codes: 0 ok (including quiet-window and deferred
no-ops), 2 technical failure or a critical problem left at run end, 3 refusal
before any mutation.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
import fcntl
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import traceback
from typing import Any
import urllib.request
from urllib.parse import urlparse
import uuid

import requests
from requests.adapters import BaseAdapter, HTTPAdapter

sys.path.append(str(Path(__file__).resolve().parent))

import d1_shadow_runner as runner  # noqa: E402
import d1_sleeve_core as core  # noqa: E402
from d1_sleeve_core import (  # noqa: E402
    CRITICAL,
    ENV_AGENT,
    ENV_DEADMAN,
    ENV_ENGINE_KEY,
    ENV_KEY,
    ENV_MASTER,
    ENV_SUB,
    ENV_WEBHOOK,
    HL_HOST,
    HL_URL,
    NOTICE,
    PUBLIC_ENV_KEYS,
    REPO_ROOT,
    Paths,
    RefusalError,
    SleeveConfig,
    TechnicalError,
)

USER_AGENT = "hypervector-d1-sleeve/1"
APPROVAL_DOCUMENT = "d1_sleeve_arming_approval"
APPROVAL_PLACEHOLDER = "<ALBERT'S OWN WORDS>"
# The template never passes: the operator sets "approved_for_live" by hand.
APPROVAL_TEMPLATE_STATUS = "draft_set_approved_for_live_to_arm"
IOC = {"limit": {"tif": "Ioc"}}
CANARY_NOTIONAL_USD = 15.0  # its stop at 0.9 x entry stays above the $10 minimum
CANARY_MAX_LEVERAGE = 3  # the live leverage ceiling, so the canary proves it
CANARY_STOP_FRACTION = 0.9
# Probe capacity guideline (a hint, never a failure): the historical book
# peaked at ~51% of book in isolated margin at 1% risk (mostly L = 1-2), plus
# the 5% collateral reserve. Below it, later entries of a crowded day scale
# down (to no less than 25%) or skip as sub_collateral and retry next hour.
FULL_BOOK_MARGIN_FRACTION = 0.6
# Per-run budget held back from P1-P6 and released only to the final check
# (P7), so budget exhaustion in an earlier phase still leaves P7 enough to
# re-read the book and place missing stops (the configured per-run maxima
# are never exceeded).
FINAL_RESERVE_WEIGHT = 80
FINAL_RESERVE_CALLS = 12
FINAL_RESERVE_ACTIONS = 20
# Weight kept free in the 60 s window before an entry: its mid, the leverage
# update, the IOC, the fill's position refresh, an orderStatus, a mid and the
# stop must not wait on the per-minute window between the fill and the stop.
ENTRY_PROTECT_WEIGHT = 12
# One more venue read, this long after the first, before believing a read
# that contradicts an acked fill or a journal-open trade (an info node lags).
REREAD_DELAY_S = 1.0
# P7: further order reads, this far apart, before closing a position as
# unprotectable when a stop this session saw acked resting would verify it
# (an order listing node a few seconds behind; about 16 s in all).
LISTING_REREAD_TRIES = 3
LISTING_REREAD_BACKOFF_S = 5.0
# ``never_landed`` is decided 5 s after an expiresAfter taken from the host
# clock; beyond this skew from the venue's Date header that proof is unsound.
CLOCK_SKEW_LIMIT_S = 3.0
# A position_unverified entry is settled by a flat read no sooner than this
# after its mark (an info node's lag is seconds; runs are hourly).
UNVERIFIED_SETTLE_AFTER = timedelta(minutes=10)
# A2: guard-stop placements per coin per run (two sweeps' worth, each a first
# try and one retry); a guard the venue keeps rejecting stays critical.
GUARD_MAX_TRIES = 4
# A technical failure or unprotected exposure in this run stops new entries
# (never exits or protection) until the next hourly run, which retries them
# inside the entry window: a technical-failure abort, not a strategy gate.
HALT_ENTRY_CODES = frozenset(
    {
        "technical_failure",
        "unprotectable",
        "unprotected_position",
        "exit_incomplete",
        "not_isolated",
        "stop_behind_liquidation",
        "unresolved_entry",
        "fill_not_visible",
        "clock_skew",
        "entry_overfill",
    }
)
FILLS_PAGE_LIMIT = 2000
FUNDING_PAGE_LIMIT = 500
MAX_REPORT_ITEMS = 2000
INFO_WEIGHTS = {
    "clearinghouseState": 2,
    "spotClearinghouseState": 2,
    "allMids": 2,
    "orderStatus": 2,
    "userRole": 60,
    "meta": 20,
    "frontendOpenOrders": 20,
    "extraAgents": 20,
    "subAccounts": 20,
    "userAbstraction": 20,
    "userFees": 20,
    "userFillsByTime": 20,
    "userFunding": 20,
}
_ADDRESS_ANY = core._ADDRESS_ANY_CASE


class EgressRefusedError(TechnicalError):
    """A request to anything but HTTPS POST api.hyperliquid.xyz/info|/exchange."""


class NotSentError(TechnicalError):
    """Refused locally before any request left the process (never ambiguous)."""


class BudgetExhausted(NotSentError):
    """A per-run Hyperliquid budget would be exceeded (hl_budget_exhausted)."""


class QuietWindowReached(NotSentError):
    """A Hyperliquid call would fall in minutes 57-03; the run stops cleanly."""


class GatewayRefused(NotSentError):
    """``_mutate`` refused a mutation before any POST."""


class PagedItems(list):
    """A paged history; ``truncated`` when the walk stopped before the end."""

    truncated: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _safe(text: str) -> str:
    """Last-line safety net for printed output: no 40-hex address survives."""
    return _ADDRESS_ANY.sub("0x<addr>", text)


def _json_line(record: Mapping[str, Any]) -> str:
    """One JSON line with keys in insertion order (``{"plan": ...}`` first)."""
    return json.dumps(runner._jsonable(record), separators=(",", ":"), allow_nan=False)


def _frames(exc: BaseException) -> str:
    """Where an unexpected exception came from: its stack frames and TYPE only.

    Never the exception's message, which may carry a URL, a key or a venue
    reply (``traceback.format_exc`` would print it).
    """
    frames = "".join(traceback.format_tb(exc.__traceback__))
    return core.redact(f"{frames}{type(exc).__name__}", 4000)


def _https_url_ok(value: str) -> bool:
    """One https:// URL with a host and no whitespace or control character.

    A value like ``https://host/token # note`` (an inline comment the env
    parser keeps) would make urllib raise with the token in its message.
    """
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    if not value.startswith("https://"):
        return False
    try:
        return bool(urlparse(value).hostname)
    except ValueError:
        return False


# ----------------------------------------------------------------- credentials


def default_env_file() -> Path:
    return Path.home() / ".config" / "hypervector" / "d1_sleeve.env"


@dataclass(frozen=True, repr=False)
class SleeveEnv:
    master: str
    sub: str
    agent: str
    webhook: str | None = None
    deadman: str | None = None
    private_key: str | None = None

    def fps(self, cfg: SleeveConfig) -> dict[str, str]:
        return {
            "master": core.address_fp(self.master, cfg.sleeve_id),
            "sub": core.address_fp(self.sub, cfg.sleeve_id),
            "agent": core.address_fp(self.agent, cfg.sleeve_id),
        }

    def __repr__(self) -> str:
        fps = self.fps(SleeveConfig())
        return (
            f"SleeveEnv(fp_master={fps['master']}, fp_sub={fps['sub']}, "
            f"fp_agent={fps['agent']}, key_loaded={self.private_key is not None})"
        )

    __str__ = __repr__


def _check_env_file(path: Path, repo_root: Path) -> None:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise RefusalError(f"env file is unreadable ({type(exc).__name__})") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RefusalError("env file is a symlink; use a regular file")
    if not stat.S_ISREG(info.st_mode):
        raise RefusalError("env file is not a regular file")
    if info.st_uid != os.getuid():
        raise RefusalError("env file is not owned by this user")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise RefusalError(
            f"env file mode is {stat.S_IMODE(info.st_mode):04o}; it must be 0600"
        )
    resolved = path.resolve()
    for root in {REPO_ROOT.resolve(), Path(repo_root).resolve()}:
        if resolved == root or root in resolved.parents:
            raise RefusalError("env file must live outside the repository")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def load_sleeve_env(
    path: Path | None,
    *,
    include_private_key: bool,
    repo_root: Path = REPO_ROOT,
) -> SleeveEnv:
    """Sleeve credentials: the process environment first, then the env file.

    Only the sleeve's keys are read; any other line is skipped unparsed. The
    engine key's name is refused outright, so the engine's env cannot be
    copied in. The private key is read only when ``include_private_key``.
    """
    allowed = set(PUBLIC_ENV_KEYS)
    if include_private_key:
        allowed.add(ENV_KEY)
    values: dict[str, str] = {}
    for key in sorted(allowed):
        value = os.environ.get(key)
        if value:
            values[key] = value
    file_path = Path(path).expanduser() if path is not None else default_env_file()
    if os.path.lexists(file_path):
        _check_env_file(file_path, repo_root)
        text = file_path.read_text(encoding="utf-8")
        if ENV_ENGINE_KEY in text:
            raise RefusalError(
                f"env file names {ENV_ENGINE_KEY}; the sleeve never uses the engine key"
            )
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            if key not in allowed or key in values:
                continue
            parsed = _unquote(value)
            if parsed:
                values[key] = parsed
    for name in (ENV_WEBHOOK, ENV_DEADMAN):
        url = values.get(name)
        if url and not _https_url_ok(url):
            raise RefusalError(
                f"{name} must be a single https:// URL with no spaces, control "
                "characters or inline comment (the value is not shown)"
            )
    master = core.normalize_address(values.get(ENV_MASTER), ENV_MASTER)
    sub = core.normalize_address(values.get(ENV_SUB), ENV_SUB)
    agent = core.normalize_address(values.get(ENV_AGENT), ENV_AGENT)
    key = values.get(ENV_KEY) if include_private_key else None
    if include_private_key and not key:
        raise RefusalError(f"{ENV_KEY} is not set (env file or environment)")
    return SleeveEnv(
        master=master,
        sub=sub,
        agent=agent,
        webhook=values.get(ENV_WEBHOOK) or None,
        deadman=values.get(ENV_DEADMAN) or None,
        private_key=key,
    )


def engine_key_absent() -> bool:
    """The engine's signing key name is absent from this process environment."""
    return ENV_ENGINE_KEY not in os.environ


# ----------------------------------------------------------------- approval


def code_hashes() -> dict[str, str]:
    """sha256 of the code actually loaded: executor, core and the shadow runner."""
    return {
        "scripts/d1_sleeve_executor.py": core.file_sha256(Path(__file__)),
        "scripts/d1_sleeve_core.py": core.file_sha256(Path(core.__file__)),
        "scripts/d1_shadow_runner.py": runner_file_sha256(),
    }


def runner_file_sha256() -> str:
    return core.file_sha256(Path(runner.__file__))


def check_runner_sha(cfg: SleeveConfig) -> None:
    if runner_file_sha256() != cfg.shadow_runner_sha256:
        raise RefusalError(
            "d1_shadow_runner.py does not match the pinned sha256; the shadow "
            "code changed and needs a new approval"
        )


def approval_template(cfg: SleeveConfig, env: SleeveEnv) -> dict[str, Any]:
    fps = env.fps(cfg)
    return {
        "document_type": APPROVAL_DOCUMENT,
        "schema_version": 1,
        "sleeve_id": cfg.sleeve_id,
        "approval_status": APPROVAL_TEMPLATE_STATUS,
        "operator_approval": APPROVAL_PLACEHOLDER,
        "approved_at_utc": "",
        "risk_fraction": cfg.risk_fraction,
        "config_fingerprint": cfg.fingerprint(),
        "shadow_config_fingerprint": cfg.shadow_config_fingerprint,
        "code": code_hashes(),
        "accounts": {
            "master_fp": fps["master"],
            "sub_fp": fps["sub"],
            "agent_fp": fps["agent"],
        },
        "prereg_amendment": {"path": "", "sha256": ""},
    }


def verify_approval(
    path: Path | None,
    cfg: SleeveConfig,
    env: SleeveEnv,
    *,
    repo_root: Path = REPO_ROOT,
) -> str:
    """Refuse unless the operator's approval pins this exact code, config and accounts.

    Returns the approval file's sha256 for the run_start record.
    """
    if path is None:
        raise RefusalError("--approval PATH is required when armed")
    try:
        raw = Path(path).read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise RefusalError(f"approval is unreadable ({type(exc).__name__})") from exc
    if not isinstance(document, dict):
        raise RefusalError("approval is not a JSON object")

    def require(ok: bool, what: str) -> None:
        if not ok:
            raise RefusalError(f"approval refused: {what}")

    require(document.get("document_type") == APPROVAL_DOCUMENT, "document_type")
    require(document.get("schema_version") == 1, "schema_version")
    require(document.get("sleeve_id") == cfg.sleeve_id, "sleeve_id")
    require(document.get("approval_status") == "approved_for_live", "approval_status")
    words = document.get("operator_approval")
    require(
        isinstance(words, str)
        and bool(words.strip())
        and words.strip() != APPROVAL_PLACEHOLDER,
        "operator_approval is empty or the template placeholder",
    )
    require(document.get("risk_fraction") == cfg.risk_fraction, "risk_fraction")
    require(
        document.get("config_fingerprint") == cfg.fingerprint(), "config_fingerprint"
    )
    require(
        document.get("shadow_config_fingerprint") == cfg.shadow_config_fingerprint,
        "shadow_config_fingerprint",
    )
    code = document.get("code")
    require(isinstance(code, dict), "code")
    for name, digest in code_hashes().items():
        require(code.get(name) == digest, f"code sha256 of {name}")
    fps = env.fps(cfg)
    accounts = document.get("accounts")
    require(isinstance(accounts, dict), "accounts")
    for role in ("master", "sub", "agent"):
        require(accounts.get(f"{role}_fp") == fps[role], f"accounts.{role}_fp")
    amendment = document.get("prereg_amendment")
    require(isinstance(amendment, dict), "prereg_amendment")
    amendment_path = amendment.get("path")
    require(
        isinstance(amendment_path, str) and bool(amendment_path.strip()),
        "prereg_amendment.path",
    )
    root = Path(repo_root).resolve()
    target = (root / amendment_path).resolve()
    require(root in target.parents and target.is_file(), "prereg_amendment.path")
    require(
        core.file_sha256(target) == amendment.get("sha256"), "prereg_amendment.sha256"
    )
    return hashlib.sha256(raw).hexdigest()


# ----------------------------------------------------------------- network


class HlAllowListTransport(BaseAdapter):
    """Transport guard: HTTPS POST to api.hyperliquid.xyz /info (and /exchange armed).

    Anything else raises before a socket is opened. It counts what it sends per
    path and what it refuses per host, so the run log reports observed traffic.
    """

    def __init__(
        self, delegate: BaseAdapter | None = None, *, allow_exchange: bool = False
    ) -> None:
        super().__init__()
        self._delegate = delegate if delegate is not None else HTTPAdapter()
        self.allow_exchange = allow_exchange
        self.sent: Counter[str] = Counter()
        self.refused: Counter[str] = Counter()

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> Any:
        parsed = urlparse(request.url or "")
        host = parsed.hostname or "<none>"
        paths = {"/info", "/exchange"} if self.allow_exchange else {"/info"}
        if (
            parsed.scheme != "https"
            or host != HL_HOST
            or parsed.port not in (None, 443)
            or request.method != "POST"
            or parsed.path not in paths
            or parsed.query
        ):
            self.refused[host] += 1
            raise EgressRefusedError(
                f"refusing {request.method} {parsed.scheme}://{host}{parsed.path}: "
                f"only HTTPS POST to {HL_HOST} {sorted(paths)} is allowed"
            )
        self.sent[parsed.path] += 1
        return self._delegate.send(request, **kwargs)

    def close(self) -> None:
        self._delegate.close()


def _guarded_session(guard: HlAllowListTransport) -> requests.Session:
    session = requests.Session()
    _harden(session, guard)
    return session


def _harden(session: requests.Session, guard: HlAllowListTransport) -> None:
    session.trust_env = False
    session.max_redirects = 0
    session.mount("https://", guard)
    session.mount("http://", guard)


class HlPacer:
    """Spacing, a sliding 60 s weight cap and per-run budgets for Hyperliquid."""

    def __init__(
        self,
        cfg: SleeveConfig,
        *,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cfg = cfg
        self._clock = clock
        self._sleep = sleep
        self._window: deque[tuple[float, int]] = deque()
        self._last: float | None = None
        self.info_weight = 0
        self.info_calls = 0
        self.exchange_actions = 0
        # FINAL_RESERVE_* stays held back until the final check releases it.
        self.final_reserve_open = False

    def _now(self) -> float:
        return self._clock().timestamp()

    def now(self) -> datetime:
        return self._clock()

    def _quiet_check(self) -> None:
        if self._clock().minute in self.cfg.quiet_minutes:
            raise QuietWindowReached(
                "quiet window: no Hyperliquid call in minutes 57-03"
            )

    def open_final_reserve(self) -> None:
        """Release the budget held back for the final check (P7)."""
        self.final_reserve_open = True

    def _limit(self, full: int, held: int) -> int:
        return full if self.final_reserve_open else max(0, full - held)

    def before(self, kind: str, weight: int, *, protective: bool = False) -> None:
        """Every Hyperliquid request passes here: quiet window, budget, pacing.

        ``protective`` (a reduce-only stop order only; the gateway enforces
        that) is exempt from the quiet window, never from the budget.
        """
        cfg = self.cfg
        quiet = not (protective and kind == "exchange")
        if quiet:
            self._quiet_check()
        if kind == "info":
            if self.info_calls + 1 > self._limit(
                cfg.hl_max_info_calls_per_run, FINAL_RESERVE_CALLS
            ) or self.info_weight + weight > self._limit(
                cfg.hl_max_info_weight_per_run, FINAL_RESERVE_WEIGHT
            ):
                raise BudgetExhausted("hl_budget_exhausted: per-run info budget")
        elif self.exchange_actions + 1 > self._limit(
            cfg.hl_max_exchange_actions_per_run, FINAL_RESERVE_ACTIONS
        ):
            raise BudgetExhausted("hl_budget_exhausted: per-run exchange budget")
        self._wait(weight)
        if quiet:
            self._quiet_check()
        if kind == "info":
            self.info_calls += 1
            self.info_weight += weight
        else:
            self.exchange_actions += 1

    def add_weight(self, extra: int) -> None:
        """Weight known only after the response (items returned)."""
        if extra <= 0:
            return
        self.info_weight += extra
        self._window.append((self._now(), extra))

    def _wait(self, weight: int) -> None:
        cfg = self.cfg
        now = self._now()
        if self._last is not None:
            gap = cfg.hl_min_spacing_s - (now - self._last)
            if gap > 0:
                self._sleep(gap)
                now = self._now()
        for _ in range(64):
            while self._window and now - self._window[0][0] >= 60.0:
                self._window.popleft()
            used = sum(item[1] for item in self._window)
            if used + weight <= cfg.hl_weight_per_minute or not self._window:
                break
            self._sleep(60.0 - (now - self._window[0][0]) + 0.01)
            now = self._now()
        else:
            raise TechnicalError("hl pacer could not free the weight window")
        self._last = now
        self._window.append((now, weight))

    def make_room(self, weight: int) -> None:
        """Wait (without spending) until ``weight`` fits in the 60 s window.

        Called before an entry IOC so the position refresh and the stop that
        follow a fill are not held up by the per-minute cap.
        """
        cfg = self.cfg
        self._quiet_check()
        now = self._now()
        for _ in range(64):
            while self._window and now - self._window[0][0] >= 60.0:
                self._window.popleft()
            used = sum(item[1] for item in self._window)
            if used + weight <= cfg.hl_weight_per_minute or not self._window:
                break
            self._sleep(60.0 - (now - self._window[0][0]) + 0.01)
            now = self._now()
        else:
            raise TechnicalError("hl pacer could not free the weight window")
        self._quiet_check()

    def remaining_weight(self) -> int:
        return self.cfg.hl_max_info_weight_per_run - self.info_weight

    def remaining_calls(self) -> int:
        return self.cfg.hl_max_info_calls_per_run - self.info_calls

    def remaining_actions(self) -> int:
        return self.cfg.hl_max_exchange_actions_per_run - self.exchange_actions

    def reserve_ok(self) -> bool:
        """Entries and exits stop while any per-run budget is inside its reserve.

        The reserve sits ABOVE the P7 hold-back while that is held back, so
        the sweep keeps its full reserve and an entry started at the cut-off
        has room to finish (about 9 info calls in the worst case) before the
        hard limit.
        """
        held = not self.final_reserve_open
        return (
            self.remaining_weight() - (FINAL_RESERVE_WEIGHT if held else 0)
            >= self.cfg.hl_sweep_reserve_weight
            and self.remaining_calls() - (FINAL_RESERVE_CALLS if held else 0)
            >= self.cfg.hl_sweep_reserve_calls
            and self.remaining_actions() - (FINAL_RESERVE_ACTIONS if held else 0)
            >= self.cfg.hl_sweep_reserve_actions
        )


class HlInfoReader:
    """Read-only Hyperliquid /info client behind the guard, pacer and budgets.

    ``transport`` replaces the network adapter behind the guard and ``post``
    replaces HTTP altogether (tests only). User fields always carry the sub or
    the master address; only ``user_role`` is asked about the agent.
    """

    def __init__(
        self,
        cfg: SleeveConfig | None = None,
        *,
        transport: BaseAdapter | None = None,
        post: Callable[[dict], Any] | None = None,
        pacer: HlPacer | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.cfg = cfg or SleeveConfig()
        self.guard = HlAllowListTransport(transport, allow_exchange=False)
        self.session = _guarded_session(self.guard)
        self.session.headers.update(
            {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        )
        self._post_fn = post
        self.pacer = pacer
        self._sleep = sleep or time.sleep
        # Host clock minus the venue's Date header, smallest seen this run
        # (the header is whole seconds and latency only adds): None if unseen.
        self.clock_skew_s: float | None = None

    def bind(self, pacer: HlPacer, sleep: Callable[[float], None]) -> None:
        self.pacer = pacer
        self._sleep = sleep
        self.clock_skew_s = None

    def _note_date(self, response: requests.Response) -> None:
        stamp = response.headers.get("Date") if response.headers else None
        if not stamp:
            return
        try:
            server = parsedate_to_datetime(stamp)
        except (TypeError, ValueError, IndexError):
            return
        if server.tzinfo is None:
            server = server.replace(tzinfo=UTC)
        skew = (self._pacer().now() - server).total_seconds()
        if self.clock_skew_s is None or skew < self.clock_skew_s:
            self.clock_skew_s = skew

    def _pacer(self) -> HlPacer:
        if self.pacer is None:
            self.pacer = HlPacer(self.cfg, sleep=self._sleep)
        return self.pacer

    def _request(self, payload: dict) -> Any:
        weight = INFO_WEIGHTS[payload["type"]]
        throttled = failures = 0
        while True:
            self._pacer().before("info", weight)
            if self._post_fn is not None:
                return self._post_fn(payload)
            try:
                response = self.session.post(
                    f"{HL_URL}/info",
                    json=payload,
                    timeout=self.cfg.http_timeout_s,
                    allow_redirects=False,
                )
            except EgressRefusedError:
                raise
            except requests.RequestException as exc:
                if failures >= 2:
                    raise TechnicalError(
                        f"hl info {payload['type']} transport error "
                        f"({type(exc).__name__})"
                    ) from exc
                self._sleep(2.0 * (2**failures))
                failures += 1
                continue
            status = response.status_code
            if status == 429:
                if throttled >= 2:
                    raise TechnicalError(f"hl info {payload['type']} HTTP 429")
                throttled += 1
                self._sleep(10.0)
                continue
            if status >= 500:
                if failures >= 2:
                    raise TechnicalError(f"hl info {payload['type']} HTTP {status}")
                self._sleep(2.0 * (2**failures))
                failures += 1
                continue
            if status != 200:
                raise TechnicalError(f"hl info {payload['type']} HTTP {status}")
            self._note_date(response)
            try:
                return response.json()
            except ValueError as exc:
                raise TechnicalError(f"hl info {payload['type']} non-JSON") from exc

    def _object(self, payload: dict) -> Mapping[str, Any]:
        value = self._request(payload)
        if not isinstance(value, Mapping):
            raise TechnicalError(f"hl info {payload['type']} has the wrong shape")
        return value

    def _list(self, payload: dict) -> list:
        value = self._request(payload)
        if not isinstance(value, list):
            raise TechnicalError(f"hl info {payload['type']} has the wrong shape")
        return value

    def meta(self) -> Mapping[str, Any]:
        return self._object({"type": "meta", "dex": ""})

    def all_mids(self) -> Mapping[str, Any]:
        return self._object({"type": "allMids", "dex": ""})

    def clearinghouse_state(self, user: str) -> Mapping[str, Any]:
        return self._object({"type": "clearinghouseState", "user": user, "dex": ""})

    def spot_state(self, user: str) -> Mapping[str, Any]:
        return self._object({"type": "spotClearinghouseState", "user": user})

    def frontend_open_orders(self, user: str) -> list:
        return self._list({"type": "frontendOpenOrders", "user": user, "dex": ""})

    def order_status(self, user: str, cloid: str) -> Mapping[str, Any]:
        return self._object({"type": "orderStatus", "user": user, "oid": cloid})

    def user_role(self, user: str) -> Mapping[str, Any]:
        return self._object({"type": "userRole", "user": user})

    def extra_agents(self, user: str) -> list:
        return self._list({"type": "extraAgents", "user": user})

    def sub_accounts(self, user: str) -> Any:
        value = self._request({"type": "subAccounts", "user": user})
        if value is not None and not isinstance(value, list):
            raise TechnicalError("hl info subAccounts has the wrong shape")
        return value

    def user_abstraction(self, user: str) -> Any:
        return self._request({"type": "userAbstraction", "user": user})

    def _paged(
        self, kind: str, user: str, start_ms: int, end_ms: int, page_limit: int
    ) -> PagedItems:
        """Time-paged history with an inclusive cursor and exact-duplicate removal.

        Items that share the last timestamp of a full page (every coin's hourly
        funding does) are re-read by the next page instead of skipped; the
        result is flagged ``truncated`` when the item cap or a page of one
        timestamp stops the walk early.
        """
        items = PagedItems()
        seen: set[str] = set()
        cursor = int(start_ms)
        while True:
            payload: dict[str, Any] = {
                "type": kind,
                "user": user,
                "startTime": cursor,
                "endTime": int(end_ms),
            }
            if kind == "userFillsByTime":
                payload["aggregateByTime"] = False
            page = self._list(payload)
            self._pacer().add_weight(math.ceil(len(page) / 20))
            added = 0
            for item in page:
                key = json.dumps(item, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
                    added += 1
            if len(items) >= MAX_REPORT_ITEMS:
                items.truncated = (
                    len(items) > MAX_REPORT_ITEMS or len(page) >= page_limit
                )
                break
            if len(page) < page_limit:
                break
            try:
                cursor = int(page[-1]["time"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TechnicalError(f"hl info {kind} page has no time") from exc
            if added == 0:  # a full page of one timestamp: cannot advance
                items.truncated = True
                break
        if len(items) > MAX_REPORT_ITEMS:
            del items[MAX_REPORT_ITEMS:]
        return items

    def user_fills_by_time(self, user: str, start_ms: int, end_ms: int) -> PagedItems:
        return self._paged("userFillsByTime", user, start_ms, end_ms, FILLS_PAGE_LIMIT)

    def user_funding(self, user: str, start_ms: int, end_ms: int) -> PagedItems:
        return self._paged("userFunding", user, start_ms, end_ms, FUNDING_PAGE_LIMIT)

    def traffic(self) -> tuple[Counter[str], Counter[str]]:
        return self.guard.sent, self.guard.refused


# ----------------------------------------------------------------- identity


@dataclass
class IdentityReport:
    checks: dict[str, bool]
    informational: dict[str, bool]
    agent_days_left: int | None
    master_mode: str | None
    sub_mode: str | None
    fps: dict[str, str]
    reused: bool = False

    @property
    def ok(self) -> bool:
        return all(self.checks.values())

    def line(self) -> str:
        flags = " ".join(
            f"{name}={'true' if value else 'false'}"
            for name, value in {**self.checks, **self.informational}.items()
        )
        return (
            f"identity: {flags} agent_days_left={self.agent_days_left} "
            f"master_mode={_mode_text(self.master_mode)} "
            f"sub_mode={_mode_text(self.sub_mode)} fp_master={self.fps['master']} "
            f"fp_sub={self.fps['sub']} fp_agent={self.fps['agent']}"
            + (" reused=true" if self.reused else "")
        )


def _mode_text(mode: object) -> str:
    return core.redact(mode, 32) if isinstance(mode, str) else "unknown"


def verify_identity(
    reader: HlInfoReader,
    env: SleeveEnv,
    cfg: SleeveConfig,
    now: datetime,
    *,
    signer_address: str | None = None,
) -> IdentityReport:
    """Read-only identity proofs; booleans only (raw responses are never kept).

    ``signer_address`` (armed only) adds the local key and environment checks.
    """
    checks: dict[str, bool] = {}
    addresses = (env.master, env.sub, env.agent)
    checks["addresses_valid"] = all(core.is_address(a) for a in addresses)
    checks["addresses_distinct"] = len(set(addresses)) == 3
    role = reader.user_role(env.agent)
    data = role.get("data") if isinstance(role, Mapping) else None
    parent = data.get("user") if isinstance(data, Mapping) else None
    checks["signer_is_agent_of_master"] = (
        role.get("role") == "agent"
        and isinstance(parent, str)
        and parent.strip().lower() == env.master
    )
    agents = core.parse_extra_agents(reader.extra_agents(env.master))
    mine = [entry for entry in agents if entry.address == env.agent]
    entry = mine[0] if len(mine) == 1 else None
    checks["signer_listed"] = entry is not None
    checks["signer_name_ok"] = entry is not None and entry.base_name == cfg.agent_name
    checks["signer_not_engine_name"] = (
        entry is not None and entry.base_name != cfg.engine_agent_name
    )
    checks["signer_not_engine_address"] = not any(
        e.base_name == cfg.engine_agent_name and e.address == env.agent for e in agents
    )
    informational = {
        "engine_agent_listed": any(e.base_name == cfg.engine_agent_name for e in agents)
    }
    stamp = core.now_ms(now)
    days_left: int | None = None
    if entry is not None and entry.valid_until_ms is not None:
        days_left = math.floor((entry.valid_until_ms - stamp) / core.DAY_MS)
    checks["signer_valid"] = (
        entry is not None
        and entry.valid_until_ms is not None
        and entry.valid_until_ms > stamp + cfg.agent_min_days_to_arm * core.DAY_MS
    )
    pairs = core.parse_sub_accounts(reader.sub_accounts(env.master))
    checks["sub_listed_under_master"] = pairs.count((env.sub, env.master)) == 1 and (
        sum(1 for sub, _ in pairs if sub == env.sub) == 1
    )
    master_mode = reader.user_abstraction(env.master)
    sub_mode = reader.user_abstraction(env.sub)
    checks["master_mode_ok"] = master_mode in core.ACCOUNT_MODES
    checks["sub_mode_ok"] = sub_mode in core.ACCOUNT_MODES
    if signer_address is not None:
        checks["signer_matches_agent"] = signer_address.lower() == env.agent
        checks["engine_key_absent_from_env"] = engine_key_absent()
    return IdentityReport(
        checks=checks,
        informational=informational,
        agent_days_left=days_left,
        master_mode=master_mode if isinstance(master_mode, str) else None,
        sub_mode=sub_mode if isinstance(sub_mode, str) else None,
        fps=env.fps(cfg),
    )


# ----------------------------------------------------------------- SDK / gateway


@dataclass(frozen=True)
class Sdk:
    Exchange: Any
    Account: Any
    Cloid: Any
    mainnet_url: str


def _load_sdk() -> Sdk:
    """The only place the signing SDK and eth_account are imported (armed only)."""
    from eth_account import Account
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils.constants import MAINNET_API_URL
    from hyperliquid.utils.types import Cloid

    if MAINNET_API_URL != HL_URL:
        raise RefusalError("the SDK's mainnet URL is not https://api.hyperliquid.xyz")
    return Sdk(
        Exchange=Exchange, Account=Account, Cloid=Cloid, mainnet_url=MAINNET_API_URL
    )


def build_exchange(
    sdk: Sdk,
    *,
    key: str,
    meta: Mapping[str, Any],
    sub: str,
    cfg: SleeveConfig,
    transport: BaseAdapter | None = None,
) -> Any:
    """The one construction site of a signing client: vault = the sub-account.

    Meta and an empty spot meta are injected, so construction makes no request
    and spot names cannot resolve. The guard is mounted on both sessions at once.
    """
    if sdk.mainnet_url != HL_URL:
        raise RefusalError("the SDK's mainnet URL is not https://api.hyperliquid.xyz")
    wallet = sdk.Account.from_key(key)
    exchange = sdk.Exchange(
        wallet,
        HL_URL,
        meta=dict(meta),
        vault_address=sub,
        account_address=None,
        spot_meta={"universe": [], "tokens": []},
        timeout=cfg.http_timeout_s,
    )
    guard = HlAllowListTransport(transport, allow_exchange=True)
    _harden(exchange.session, guard)
    _harden(exchange.info.session, guard)
    return exchange


class BaseGateway:
    ALLOWED_ACTIONS = frozenset({"order", "cancel", "cancelByCloid", "updateLeverage"})
    signing = False

    def __init__(
        self,
        *,
        cfg: SleeveConfig,
        env: SleeveEnv,
        markets: Mapping[str, core.MarketInfo],
        pacer: HlPacer,
        clock: Callable[[], datetime],
    ) -> None:
        self.cfg = cfg
        self.env = env
        self.markets = markets
        self.pacer = pacer
        self.clock = clock
        self.allow_new_risk = False
        self.deadline: datetime | None = None
        self.posts = 0

    def prepare(
        self, action: str, coin: str, *, new_risk: bool, protective: bool = False
    ) -> None:
        """Checks (and, when signing, pacing) BEFORE the caller fixes expiresAfter."""
        self.check(action, coin, new_risk=new_risk, protective=protective)

    def check(
        self, action: str, coin: str, *, new_risk: bool, protective: bool = False
    ) -> None:
        """I4. ``protective`` exempts one thing from the quiet window and the
        phase deadline: a reduce-only order (``order`` checks it is a stop
        trigger) protecting an owned position. It is never new risk."""
        if action not in self.ALLOWED_ACTIONS:
            raise GatewayRefused(f"action {action} is not allow-listed")
        if not core.tradeable(self.markets, coin):
            raise GatewayRefused(f"{coin} is not a tradeable main-dex coin")
        if protective and (action != "order" or new_risk):
            raise GatewayRefused("only a reduce-only stop order is protective")
        now = self.clock()
        if not protective:
            if now.minute in self.cfg.quiet_minutes:
                raise GatewayRefused("quiet window")
            if self.deadline is not None and now >= self.deadline:
                raise GatewayRefused("phase deadline passed")
        if new_risk and not self.allow_new_risk:
            raise GatewayRefused("new risk is not allowed in this phase")

    @staticmethod
    def check_protective_order(
        order_type: Mapping[str, Any], reduce_only: bool, protective: bool
    ) -> None:
        if protective and not (reduce_only and "trigger" in order_type):
            raise GatewayRefused("only a reduce-only stop trigger is protective")

    @staticmethod
    def entry_requests(
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        stop_px: float,
        cloid: Any,
        stop_cloid: Any,
    ) -> list[dict[str, Any]]:
        """A1: an entry IOC and its reduce-only stop-market child, built here
        so no caller can send anything else as one normalTpsl action: the
        child is on the closing side, of the parent's size, and its trigger
        is on the protective side of the parent's limit price."""
        if not (stop_px > 0 and (limit_px - stop_px) * (1 if is_buy else -1) > 0):
            raise GatewayRefused("the stop child is not on the protective side")
        return [
            {
                "coin": coin,
                "is_buy": is_buy,
                "sz": sz,
                "limit_px": limit_px,
                "order_type": dict(IOC),
                "reduce_only": False,
                "cloid": cloid,
            },
            {
                "coin": coin,
                "is_buy": not is_buy,
                "sz": sz,
                "limit_px": stop_px,
                "order_type": {
                    "trigger": {"triggerPx": stop_px, "isMarket": True, "tpsl": "sl"}
                },
                "reduce_only": True,
                "cloid": stop_cloid,
            },
        ]


class SubAccountGateway(BaseGateway):
    """The only signing path. Every mutation passes ``_mutate``."""

    signing = True

    def __init__(
        self,
        exchange: Any,
        *,
        cfg: SleeveConfig,
        env: SleeveEnv,
        markets: Mapping[str, core.MarketInfo],
        pacer: HlPacer,
        clock: Callable[[], datetime],
        cloid_cls: Any = None,
        armed: bool = True,
    ) -> None:
        super().__init__(cfg=cfg, env=env, markets=markets, pacer=pacer, clock=clock)
        self.exchange = exchange
        self.armed = armed
        self._cloid_cls = cloid_cls
        self._paced = False

    def _assert_identity(self) -> None:
        if not self.armed:
            raise GatewayRefused("gateway is not armed")
        vault = getattr(self.exchange, "vault_address", None)
        if not isinstance(vault, str):
            raise GatewayRefused("exchange vault is not the sub-account")
        if vault.lower() != self.env.sub or vault.lower() == self.env.master:
            raise GatewayRefused("exchange vault is not the sub-account")
        wallet = getattr(getattr(self.exchange, "wallet", None), "address", None)
        if not isinstance(wallet, str) or wallet.lower() != self.env.agent:
            raise GatewayRefused("exchange signer is not the sleeve API wallet")

    def prepare(
        self, action: str, coin: str, *, new_risk: bool, protective: bool = False
    ) -> None:
        """Every check, then the pacer's wait and count for the NEXT mutation.

        The caller fixes expiresAfter only after this returns, and ``_mutate``
        then sends without waiting again, so an action never leaves after its
        own expiry because the per-minute weight window was full.
        """
        self._paced = False
        self._assert_identity()
        self.check(action, coin, new_risk=new_risk, protective=protective)
        self.pacer.before("exchange", 1, protective=protective)
        self._paced = True

    def _mutate(
        self,
        action: str,
        coin: str,
        *,
        new_risk: bool,
        send: Callable[[], Any],
        protective: bool = False,
    ) -> Any:
        paced, self._paced = self._paced, False
        self._assert_identity()
        self.check(action, coin, new_risk=new_risk, protective=protective)
        if not paced:
            self.pacer.before("exchange", 1, protective=protective)
        self.posts += 1
        return send()

    def _cloid(self, cloid: str) -> Any:
        return self._cloid_cls.from_str(cloid) if self._cloid_cls else cloid

    def set_expires_after(self, expires_ms: int) -> None:
        self.exchange.set_expires_after(expires_ms)

    def update_leverage(self, coin: str, leverage: int) -> Any:
        return self._mutate(
            "updateLeverage",
            coin,
            new_risk=True,
            send=lambda: self.exchange.update_leverage(leverage, coin, is_cross=False),
        )

    def order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Mapping[str, Any],
        reduce_only: bool,
        cloid: str,
        protective: bool = False,
    ) -> Any:
        self.check_protective_order(order_type, reduce_only, protective)
        return self._mutate(
            "order",
            coin,
            new_risk=not reduce_only,
            protective=protective,
            send=lambda: self.exchange.order(
                coin,
                is_buy,
                sz,
                limit_px,
                dict(order_type),
                reduce_only=reduce_only,
                cloid=self._cloid(cloid),
            ),
        )

    def order_with_stop(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        cloid: str,
        stop_px: float,
        stop_cloid: str,
    ) -> Any:
        """A1: the entry IOC and its reduce-only stop child in ONE action
        (grouping normalTpsl). The venue places the child the moment the
        parent fully fills, whatever becomes of the reply to this POST."""
        requests_ = self.entry_requests(
            coin,
            is_buy,
            sz,
            limit_px,
            stop_px,
            self._cloid(cloid),
            self._cloid(stop_cloid),
        )
        return self._mutate(
            "order",
            coin,
            new_risk=True,
            send=lambda: self.exchange.bulk_orders(requests_, grouping="normalTpsl"),
        )

    def cancel(self, coin: str, oid: int) -> Any:
        return self._mutate(
            "cancel", coin, new_risk=False, send=lambda: self.exchange.cancel(coin, oid)
        )

    def cancel_by_cloid(self, coin: str, cloid: str) -> Any:
        return self._mutate(
            "cancelByCloid",
            coin,
            new_risk=False,
            send=lambda: self.exchange.cancel_by_cloid(coin, self._cloid(cloid)),
        )


class DryRunGateway(BaseGateway):
    """Plans only: the same checks as ``_mutate``, simulated acks, no client."""

    def __init__(self, *, mid: Callable[[str], float | None], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._mid = mid
        self._next_oid = 9_000_000_000

    def _oid(self) -> int:
        self._next_oid += 1
        return self._next_oid

    def set_expires_after(self, expires_ms: int) -> None:
        return None

    def update_leverage(self, coin: str, leverage: int) -> Any:
        self.check("updateLeverage", coin, new_risk=True)
        return {"status": "ok", "response": {"type": "default"}}

    def order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Mapping[str, Any],
        reduce_only: bool,
        cloid: str,
        protective: bool = False,
    ) -> Any:
        self.check_protective_order(order_type, reduce_only, protective)
        self.check("order", coin, new_risk=not reduce_only, protective=protective)
        if "trigger" in order_type:
            status: dict[str, Any] = {"resting": {"oid": self._oid()}}
        else:
            price = self._mid(coin) or limit_px
            status = {
                "filled": {"totalSz": str(sz), "avgPx": str(price), "oid": self._oid()}
            }
        return {
            "status": "ok",
            "response": {"type": "order", "data": {"statuses": [status]}},
        }

    def order_with_stop(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        cloid: str,
        stop_px: float,
        stop_cloid: str,
    ) -> Any:
        self.entry_requests(coin, is_buy, sz, limit_px, stop_px, cloid, stop_cloid)
        self.check("order", coin, new_risk=True)
        price = self._mid(coin) or limit_px
        filled = {"totalSz": str(sz), "avgPx": str(price), "oid": self._oid()}
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": filled}, "waitingForTrigger"]},
            },
        }

    def cancel(self, coin: str, oid: int) -> Any:
        self.check("cancel", coin, new_risk=False)
        return {"status": "ok", "response": {"data": {"statuses": ["success"]}}}

    def cancel_by_cloid(self, coin: str, cloid: str) -> Any:
        self.check("cancelByCloid", coin, new_risk=False)
        return {"status": "ok", "response": {"data": {"statuses": ["success"]}}}


# ----------------------------------------------------------------- shadow


def _ledger_stat(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_size, info.st_mtime_ns


def read_shadow(
    path: Path, cfg: SleeveConfig, sleep: Callable[[float], None]
) -> list[dict]:
    """Lock-free read: never opens ledger.jsonl.lock, retries while it changes."""
    for attempt in range(cfg.shadow_read_retries + 1):
        before = _ledger_stat(path)
        try:
            events = runner.load_ledger(path)
        except runner.LedgerError as exc:
            if "last line is incomplete" not in str(exc):
                raise
        else:
            if _ledger_stat(path) == before:
                return events
        if attempt < cfg.shadow_read_retries:
            sleep(cfg.shadow_read_retry_s)
    raise core.ShadowUnavailable(
        "the shadow ledger kept changing during every read attempt"
    )


# ----------------------------------------------------------------- alerts

BACKEND_CRITICAL = "backend_critical"
INFORMATIONAL = "informational"
CRITICAL_TITLE = "HYPERVECTOR D1 SLEEVE ALERT"
NOTICE_TITLE = "Hypervector D1 sleeve notice"
RECOVERED_TITLE = "Hypervector D1 sleeve recovered"


@dataclass(frozen=True)
class Problem:
    code: str
    severity: str
    key: str
    message: str = ""

    def record(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "key": self.key,
            "message": core.redact(self.message),
        }


def _delivery_failure(channel: str, failure: str) -> None:
    print(
        _json_line(
            {"event": "alert_delivery_failed", "channel": channel, "failure": failure}
        ),
        file=sys.stderr,
        flush=True,
    )


def _notify_mac(title: str, body: str) -> None:
    """Best-effort Notification Centre banner (the only subprocess use)."""
    if not Path("/usr/bin/osascript").exists():
        return
    script = (
        f"display notification {json.dumps(body)} with title {json.dumps(title)}"
        ' sound name "Basso"'
    )
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            _delivery_failure("mac_notification", "nonzero_exit")
    except (OSError, subprocess.SubprocessError) as exc:
        _delivery_failure("mac_notification", type(exc).__name__)


def _http_post_json(url: str, data: bytes, title: str) -> None:
    """Webhook delivery, best effort: never raises, never logs the URL.

    Any failure (``http.client.InvalidURL`` carries the URL in its message)
    is reported by exception TYPE only.
    """
    try:
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Title": title},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10):  # noqa: S310
            return
    except Exception as exc:  # any failure: its TYPE only (see the docstring)
        _delivery_failure("webhook", type(exc).__name__)


def _http_get(url: str) -> None:
    """Dead-man ping, best effort: never raises, never logs the URL."""
    try:
        with urllib.request.urlopen(url, timeout=10):  # noqa: S310
            return
    except Exception as exc:  # any failure: its TYPE only (see _http_post_json)
        _delivery_failure("deadman", type(exc).__name__)


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def dispatch_alerts(
    *,
    problems: Mapping[str, Problem],
    previous: Mapping[str, Any] | None,
    now: datetime,
    cfg: SleeveConfig,
    paths: Paths,
    webhook: str | None,
) -> tuple[dict[str, str], list[Problem]]:
    """Alert when the problem set changes; remind about criticals every N hours.

    Returns (last_alerted, problems alerted this time).
    """
    previous = previous or {}
    before = {item.get("key") for item in previous.get("problems", []) or []}
    last_alerted: dict[str, str] = {
        key: stamp
        for key, stamp in (previous.get("last_alerted") or {}).items()
        if key in problems
    }
    current = set(problems)
    stamp = core.utc_now_iso(now)
    alerted: list[Problem] = []
    if current != before:
        if not current:
            _deliver(RECOVERED_TITLE, "all problems cleared", [], now, cfg, paths, None)
            return {}, []
        alerted = [problems[key] for key in sorted(current)]
    else:
        remind = timedelta(hours=cfg.alert_remind_hours)
        for key in sorted(current):
            problem = problems[key]
            if problem.severity != CRITICAL:
                continue
            last = last_alerted.get(key)
            if last is None or now - datetime.fromisoformat(last) >= remind:
                alerted.append(problem)
    if not alerted:
        return last_alerted, []
    critical = any(problem.severity == CRITICAL for problem in alerted)
    ordered = sorted(problems.values(), key=lambda p: (p.severity != CRITICAL, p.key))
    body = ", ".join(core.redact(p.key, 80) for p in ordered)
    _deliver(
        CRITICAL_TITLE if critical else NOTICE_TITLE,
        body,
        [p.record() for p in ordered],
        now,
        cfg,
        paths,
        webhook if critical else None,
    )
    for problem in alerted:
        last_alerted[problem.key] = stamp
    return last_alerted, alerted


def _deliver(
    title: str,
    body: str,
    records: list[dict[str, str]],
    now: datetime,
    cfg: SleeveConfig,
    paths: Paths,
    webhook: str | None,
) -> None:
    critical = title == CRITICAL_TITLE
    record = {
        "title": title,
        "body": core.redact(body, 1000),
        "alerted_at_utc": core.utc_now_iso(now),
        "sleeve_id": cfg.sleeve_id,
        "problems": records,
        "alert_class": BACKEND_CRITICAL if critical else INFORMATIONAL,
    }
    try:
        _append_jsonl(paths.alerts, record)
    except OSError as exc:
        _delivery_failure("jsonl", type(exc).__name__)
    _notify_mac(title, record["body"])
    if critical and webhook:
        data = json.dumps({"text": f"{title}: {record['body']}", **record}).encode()
        _http_post_json(webhook, data, title)


def _write_status(path: Path, status: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(runner._jsonable(status), sort_keys=True, indent=1))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_status(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


# ----------------------------------------------------------------- journal writer


class JournalWriter:
    """Appends (fsynced) when ``path`` is set; a dry run keeps events in memory."""

    def __init__(
        self,
        path: Path | None,
        events: Sequence[dict],
        book: core.SleeveBook,
        clock: Callable[[], datetime],
    ) -> None:
        self.path = path
        self.events = list(events)
        self.book = book
        self.clock = clock
        self.run_id = uuid.uuid4().hex
        self.seq = 0
        self.chain = core.journal_chain(self.events)
        self.appended: list[dict] = []

    def append(self, kind: str, payload: Mapping[str, Any]) -> dict:
        self.seq += 1
        body = dict(payload)
        if kind == "run_end":
            body["journal_chain_before"] = self.chain
        event = core.make_journal_event(
            self.run_id, self.seq, kind, body, core.utc_now_iso(self.clock())
        )
        if self.path is not None:
            core.append_journal(self.path, [event])
        self.chain = core.journal_step(self.chain, event)
        self.events.append(event)
        self.appended.append(event)
        self.book.apply(event)
        return event


# ----------------------------------------------------------------- the session


@dataclass(frozen=True)
class SendResult:
    cloid: str
    status: str
    oid: int | None = None
    filled_sz: float = 0.0
    avg_px: float | None = None
    error: str | None = None

    @property
    def resting(self) -> bool:
        return self.status in ("resting", "open")


@dataclass
class Context:
    cfg: SleeveConfig
    paths: Paths
    clock: Callable[[], datetime]
    sleep: Callable[[float], None]
    reader: HlInfoReader | None
    exchange_factory: Callable[..., Any] | None
    env_file: Path | None
    out: Callable[[str], None] = field(default=lambda line: print(_safe(line)))
    err: Callable[[str], None] = field(
        default=lambda line: print(_safe(line), file=sys.stderr)
    )


class SleeveSession:
    """One process invocation: snapshot, reconcile, protect, exit, enter, report."""

    def __init__(
        self,
        ctx: Context,
        *,
        cmd: str,
        env: SleeveEnv,
        armed: bool,
        journal_events: Sequence[dict],
        approval_sha256: str | None = None,
    ) -> None:
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.paths = ctx.paths
        self.clock = ctx.clock
        self.sleep = ctx.sleep
        self.cmd = cmd
        self.env = env
        self.armed = armed
        self.dry = not armed
        self.approval_sha256 = approval_sha256
        self.started = self.clock()
        self.pacer = HlPacer(self.cfg, clock=self.clock, sleep=self.sleep)
        if cmd != "run":  # only run() has a final check (P7) to hold budget for
            self.pacer.open_final_reserve()
        self.reader = ctx.reader or HlInfoReader(self.cfg)
        self.reader.bind(self.pacer, self.sleep)
        self.book = core.derive_book(journal_events)
        self.journal = JournalWriter(
            self.paths.journal if armed else None, journal_events, self.book, self.clock
        )
        self.problems: dict[str, Problem] = {}
        self.counts: Counter[str] = Counter()
        self.markets: dict[str, core.MarketInfo] = {}
        self.meta_raw: Mapping[str, Any] | None = None
        self.mids: dict[str, float] = {}
        self.positions: dict[str, core.VenuePosition] = {}
        self.orders: list[core.VenueOrder] = []
        self.sub_value: core.AccountValue | None = None
        self.master_value: core.AccountValue | None = None
        self.book_equity: float | None = None
        self.sub_free: float = 0.0
        self.identity: IdentityReport | None = None
        self.view: core.ShadowView | None = None
        self.shadow_state = "unread"
        self.gateway: BaseGateway | None = None
        self.exchange: Any = None
        self.exchange_guard: HlAllowListTransport | None = None
        self.signing_client = "none"
        self.signer_address: str | None = None
        self.sdk: Sdk | None = None
        self.phase = "setup"
        self.closed_this_run: list[tuple[core.OpenTrade, str, int]] = []
        self.opened_this_run: list[str] = []
        self.blocked_coins: dict[str, str] = {}
        self.account_stale = False
        self.entries_halted: str | None = None
        # Coins reconciled flat with no known close fill this run: their owned
        # orders are kept until a later run confirms the coin flat again.
        self.hold_orders_on: set[str] = set()
        # Entries whose reads at open showed less than their acked fills (a
        # node between two fills, or one behind them all): trade_id -> (coin,
        # acked size). Once the trade is open, its last read of the run must
        # show the acked size (check_acked_entries), or the run is critical.
        self.acked_unseen: dict[str, tuple[str, float]] = {}
        # trade_id -> the largest same-side size a position read of THIS
        # session showed for an open trade (note_seen): part of the proof of
        # fills (fill_proof), so a later read from a node that lags one of
        # them never re-sizes the stop below what a read already showed.
        self.seen_sz: dict[str, float] = {}
        # trade_id -> what an entry this session did not close as dust could
        # have filled (open_trade: a dust read while an attempt's fill is
        # unsettled): part of fill_proof for the session, so its stop covers
        # the attempts' whole size and no later read re-sizes it down.
        self.cover_floor: dict[str, float] = {}
        # cloid -> each stop THIS session saw acked resting (note_local_stop)
        # and has not since sent a cancel for: when they would verify a
        # trade's stop that the order listing lacks (acked_plan_ok), P7
        # re-reads the listing before closing the position as unprotectable.
        self.acked_stops: dict[str, core.VenueOrder] = {}
        # Local stand-in oids (negative) for stops acked resting without one
        # (an entry's stop child): replaced by the next order read.
        self._placeholder_oid = 0
        self.guard_tries: Counter[str] = Counter()
        # Journal intents with a larger ``order`` were written by this session.
        self.session_order = self.book.events_seen
        self.stop_present = self.paths.stop_file.exists()
        hour = self.started.replace(minute=0, second=0, microsecond=0)
        self.trade_open_at = hour + timedelta(minutes=self.cfg.trade_minute_first)
        self.trade_end = hour + timedelta(minutes=self.cfg.trade_minute_last + 1)
        self.sweep_end = hour + timedelta(minutes=self.cfg.sweep_minute_last + 1)
        self.today = (self.started - runner.SETTLE_DELAY).date()

    # -------------------------------------------------------- utilities
    def out(self, line: str) -> None:
        self.ctx.out(line)

    def plan(self, kind: str, **values: Any) -> None:
        if self.dry:
            self.out(_json_line({"plan": kind, **values}))

    def problem(
        self,
        code: str,
        key: str | None = None,
        message: str = "",
        severity: str | None = None,
    ) -> None:
        level = severity or (CRITICAL if code in core.CRITICAL_CODES else NOTICE)
        full = f"{code}:{key}" if key else code
        if code in HALT_ENTRY_CODES:
            self.halt_entries(full)
        existing = self.problems.get(full)
        if existing is not None and existing.severity == CRITICAL:
            return
        self.problems[full] = Problem(code, level, full, core.redact(message))

    def halt_entries(self, reason: str) -> None:
        """No new entry for the rest of this run (the next run retries them)."""
        if self.entries_halted is None:
            self.entries_halted = reason

    def now(self) -> datetime:
        return self.clock()

    def in_trade_window(self) -> bool:
        now = self.now()
        return (
            self.trade_open_at <= now < self.trade_end
            and now.minute not in self.cfg.quiet_minutes
        )

    def in_sweep_window(self) -> bool:
        now = self.now()
        return now < self.sweep_end and now.minute not in self.cfg.quiet_minutes

    TRADE_PHASES = frozenset({"exit", "entry", "canary"})

    def phase_deadline(self) -> datetime:
        """Exits, entries and the canary end at :45; protective work at :56."""
        return self.trade_end if self.phase in self.TRADE_PHASES else self.sweep_end

    def can_mutate(self) -> bool:
        if self.phase in self.TRADE_PHASES:
            return self.in_trade_window() and self.pacer.reserve_ok()
        return self.in_sweep_window()

    def set_phase(self, phase: str, *, new_risk: bool = False) -> None:
        self.phase = phase
        if self.gateway is not None:
            self.gateway.allow_new_risk = new_risk and not self.stop_present
            self.gateway.deadline = self.phase_deadline()

    def market(self, coin: str) -> core.MarketInfo:
        market = self.markets.get(coin)
        if market is None:
            raise TechnicalError(f"{coin} is not in this run's meta")
        return market

    def owned_order(self, order: core.VenueOrder) -> bool:
        return core.is_owned_cloid(self.cfg, order.cloid) or (
            order.oid in self.book.known_oids
        )

    def owned_orders(self, coin: str | None = None) -> list[core.VenueOrder]:
        return [
            order
            for order in self.orders
            if self.owned_order(order) and (coin is None or order.coin == coin)
        ]

    def owned_positions(self) -> dict[str, core.VenuePosition]:
        pending = self.book.pending_opens()
        owned: dict[str, core.VenuePosition] = {}
        for coin, position in self.positions.items():
            trade = self.book.open_trades.get(coin)
            if trade is not None:
                if trade.direction == position.direction:
                    owned[coin] = position
            elif coin in pending and (
                int(pending[coin].context.get("d", 0)) == position.direction
            ):
                owned[coin] = position
        return owned

    def gross_used(self) -> float:
        total = 0.0
        for coin, position in self.positions.items():
            mid = self.mids.get(coin)
            total += position.size * mid if mid else abs(position.position_value)
        return total

    def mid_now(self, coin: str) -> float | None:
        self.mids = core.parse_mids(self.reader.all_mids()) or self.mids
        return self.mids.get(coin)

    def refresh_positions(self) -> None:
        if self.dry:
            return
        self.positions = core.parse_positions(
            self.reader.clearinghouse_state(self.env.sub)
        )
        self.note_seen()

    def note_seen(self) -> None:
        """Record, for each open trade, the largest same-side size a position
        read of this session showed (seen_sz; fill_proof). Called after every
        position read of the run that can follow an entry, and when a trade
        opens or is recovered from the read in hand. Local state only."""
        for coin, position in self.positions.items():
            trade = self.book.open_trades.get(coin)
            if trade is not None and trade.direction == position.direction:
                tid = trade.trade_id
                self.seen_sz[tid] = max(self.seen_sz.get(tid, 0.0), position.size)

    def refresh_orders(self) -> None:
        if self.dry:
            return
        self.orders = core.parse_open_orders(
            self.reader.frontend_open_orders(self.env.sub)
        )

    def refresh_account(self) -> None:
        """Re-read the sub's positions, equity and free collateral after closes.

        A close frees isolated margin and realises P&L; entries at the same
        open must size against that, not the P1 snapshot. Book equity is
        recomputed from the P1 master value and the fresh sub value.
        """
        self.account_stale = False
        if self.dry or self.identity is None:
            return
        sub_mode = core.parse_account_mode(self.identity.sub_mode)
        perp = self.reader.clearinghouse_state(self.env.sub)
        self.positions = core.parse_positions(perp)
        self.note_seen()
        spot = (
            self.reader.spot_state(self.env.sub)
            if sub_mode == "unifiedAccount"
            else None
        )
        self.sub_value = core.parse_account_value(sub_mode, perp, spot)
        self.sub_free = self.sub_value.free_usd
        if self.master_value is None or self.book_equity is None:
            return
        equity = self.master_value.equity_usd + self.sub_value.equity_usd
        if math.isfinite(equity) and equity > 0:
            self.book_equity = equity
        else:
            self.book_equity = None
            self.problem("equity_invalid", message="book equity is not positive")

    def apply_dry_fill(
        self, coin: str, is_buy: bool, size: float, price: float, leverage: int
    ) -> None:
        """Dry run: the planned fill updates the local book (nothing is sent)."""
        delta = size if is_buy else -size
        current = self.positions.get(coin)
        szi = (current.szi if current else 0.0) + delta
        if abs(szi) < 1e-12:
            self.positions.pop(coin, None)
            return
        entry = (
            current.entry_px if current and (current.szi > 0) == (szi > 0) else price
        )
        self.positions[coin] = core.VenuePosition(
            coin=coin,
            szi=szi,
            entry_px=entry,
            position_value=abs(szi) * price,
            liquidation_px=None,
            leverage_type="isolated",
            leverage_value=leverage or (current.leverage_value if current else 1),
            margin_used=0.0,
        )

    # -------------------------------------------------------- order primitives
    def send_order(
        self,
        *,
        trade_id: str,
        role: str,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Mapping[str, Any],
        reduce_only: bool,
        n: int,
        context: Mapping[str, Any] | None = None,
        kind: str | None = None,
        protective: bool = False,
    ) -> SendResult:
        """Write-ahead order: pace, then intent (fsynced), expiresAfter, send, outcome.

        The gateway paces and checks BEFORE the expiry is fixed and journaled,
        so the journaled expiry is the one the venue sees and nothing waits
        between it and the POST. ``protective`` (a stop of an owned position)
        may be sent after the phase deadline and in the quiet window.
        """
        assert self.gateway is not None
        cloid = core.cloid_for(self.cfg, self.env.sub, trade_id, role, n)
        try:
            self.gateway.check_protective_order(order_type, reduce_only, protective)
            self.gateway.prepare(
                "order", coin, new_risk=not reduce_only, protective=protective
            )
        except GatewayRefused as exc:  # nothing was sent and no intent exists
            self.plan("refused", role=role, coin=coin, reason=core.redact(exc))
            return SendResult(cloid, "rejected", error=core.redact(exc))
        expires = core.now_ms(self.now()) + self.cfg.expires_after_seconds * 1000
        trigger = order_type.get("trigger", {}).get("triggerPx")
        tif = order_type.get("limit", {}).get("tif")
        intent: dict[str, Any] = {
            "action": "order",
            "cloid": cloid,
            "role": role,
            "trade_id": trade_id,
            "coin": coin,
            "is_buy": is_buy,
            "sz": sz,
            "limit_px": limit_px,
            "trigger_px": trigger,
            "reduce_only": reduce_only,
            "tif": tif,
            "n": n,
            "expires_after_ms": expires,
            "context": dict(context or {}),
        }
        if kind:
            intent["kind"] = kind
        self.journal.append("intent", intent)
        self.plan(
            role,
            coin=coin,
            trade_id=trade_id,
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            trigger_px=trigger,
            reduce_only=reduce_only,
            tif=tif,
            cloid=cloid,
            n=n,
        )
        try:
            self.gateway.set_expires_after(expires)
            response = self.gateway.order(
                coin,
                is_buy,
                sz,
                limit_px,
                order_type,
                reduce_only,
                cloid,
                protective=protective,
            )
        except NotSentError as exc:
            self._order_outcome(cloid, "rejected", error=f"not_sent: {exc}", kind=kind)
            if not isinstance(exc, GatewayRefused):
                raise
            return SendResult(cloid, "rejected", error=core.redact(exc))
        except Exception as exc:  # transport or SDK error: the order may have landed
            self._order_outcome(
                cloid, "ambiguous", error=f"{type(exc).__name__}: {exc}", kind=kind
            )
            return self.resolve(self.book.intents[cloid])
        try:
            (ack,) = core.parse_order_statuses(response, 1)
        except TechnicalError as exc:
            self._order_outcome(cloid, "ambiguous", error=str(exc), kind=kind)
            return self.resolve(self.book.intents[cloid])
        status = ack.status
        if status == "filled" and ack.filled_sz < sz * (1 - 1e-9):
            status = "partial"
        elif status == "error":
            status = "rejected"
        self._order_outcome(
            cloid,
            status,
            oid=ack.oid,
            filled_sz=ack.filled_sz,
            avg_px=ack.avg_px,
            error=ack.error,
            kind=kind,
        )
        return SendResult(cloid, status, ack.oid, ack.filled_sz, ack.avg_px, ack.error)

    def send_entry(
        self,
        *,
        trade_id: str,
        role: str,
        stop_role: str,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        stop_px: float,
        n: int,
        context: Mapping[str, Any] | None = None,
        kind: str | None = None,
    ) -> tuple[SendResult, SendResult]:
        """A1, write-ahead: an entry IOC and its venue-attached stop child.

        One action (grouping normalTpsl) carries the IOC and a reduce-only
        stop-market child of the same size at ``stop_px``. Both intents are
        journaled (fsynced) before the send, both outcomes after it. The
        venue places the child the moment the parent fully fills, so a full
        fill is protected at the venue even when the reply is lost and every
        read lags it; a parent that does not fully fill leaves no child.

        The child's outcome follows from the parent's ack: ``resting`` after
        a full fill, ``canceled`` otherwise, ``rejected`` on a child error.
        When the send is ambiguous both stay ambiguous: the parent is
        resolved here (as send_order does), the child by the next
        resolve_unresolved (P7, or the next run's P2), and a listing of the
        child proves it rests (learn_listed_oids).
        """
        assert self.gateway is not None
        cloid = core.cloid_for(self.cfg, self.env.sub, trade_id, role, n)
        stop_n = self.book.attempts.get((trade_id, stop_role), 0) + 1
        stop_cloid = core.cloid_for(self.cfg, self.env.sub, trade_id, stop_role, stop_n)
        try:
            self.gateway.prepare("order", coin, new_risk=True)
        except GatewayRefused as exc:  # nothing was sent and no intent exists
            self.plan("refused", role=role, coin=coin, reason=core.redact(exc))
            return (
                SendResult(cloid, "rejected", error=core.redact(exc)),
                SendResult(stop_cloid, "rejected", error=core.redact(exc)),
            )
        expires = core.now_ms(self.now()) + self.cfg.expires_after_seconds * 1000
        common: dict[str, Any] = {
            "action": "order",
            "trade_id": trade_id,
            "coin": coin,
            "sz": sz,
            "expires_after_ms": expires,
            "grouping": "normalTpsl",
        }
        if kind:
            common["kind"] = kind
        parent: dict[str, Any] = {
            **common,
            "cloid": cloid,
            "role": role,
            "is_buy": is_buy,
            "limit_px": limit_px,
            "trigger_px": None,
            "reduce_only": False,
            "tif": "Ioc",
            "n": n,
            "context": {**dict(context or {}), "stop_child": stop_cloid},
        }
        child: dict[str, Any] = {
            **common,
            "cloid": stop_cloid,
            "role": stop_role,
            "is_buy": not is_buy,
            "limit_px": stop_px,
            "trigger_px": stop_px,
            "reduce_only": True,
            "tif": None,
            "n": stop_n,
            "context": {
                "child_of": cloid,
                "trigger_px": stop_px,
                "d": 1 if is_buy else -1,
            },
        }
        self.journal.append("intent", parent)
        self.journal.append("intent", child)
        self.plan(
            role,
            coin=coin,
            trade_id=trade_id,
            is_buy=is_buy,
            sz=sz,
            limit_px=limit_px,
            trigger_px=None,
            reduce_only=False,
            tif="Ioc",
            cloid=cloid,
            n=n,
        )
        self.plan(
            stop_role,
            coin=coin,
            trade_id=trade_id,
            is_buy=not is_buy,
            sz=sz,
            limit_px=stop_px,
            trigger_px=stop_px,
            reduce_only=True,
            tif=None,
            cloid=stop_cloid,
            n=stop_n,
            child_of=cloid,
        )
        try:
            self.gateway.set_expires_after(expires)
            response = self.gateway.order_with_stop(
                coin, is_buy, sz, limit_px, cloid, stop_px, stop_cloid
            )
        except NotSentError as exc:
            for each in (cloid, stop_cloid):
                self._order_outcome(
                    each, "rejected", error=f"not_sent: {exc}", kind=kind
                )
            if not isinstance(exc, GatewayRefused):
                raise
            return (
                SendResult(cloid, "rejected", error=core.redact(exc)),
                SendResult(stop_cloid, "rejected", error=core.redact(exc)),
            )
        except Exception as exc:  # transport or SDK error: the orders may have landed
            for each in (cloid, stop_cloid):
                self._order_outcome(
                    each, "ambiguous", error=f"{type(exc).__name__}: {exc}", kind=kind
                )
            return self.resolve(self.book.intents[cloid]), SendResult(
                stop_cloid, "ambiguous"
            )
        try:
            ack, child_ack = core.parse_grouped_statuses(response)
        except TechnicalError as exc:
            for each in (cloid, stop_cloid):
                self._order_outcome(each, "ambiguous", error=str(exc), kind=kind)
            return self.resolve(self.book.intents[cloid]), SendResult(
                stop_cloid, "ambiguous"
            )
        status = ack.status
        if status == "filled" and ack.filled_sz < sz * (1 - 1e-9):
            status = "partial"
        elif status == "error":
            status = "rejected"
        self._order_outcome(
            cloid,
            status,
            oid=ack.oid,
            filled_sz=ack.filled_sz,
            avg_px=ack.avg_px,
            error=ack.error,
            kind=kind,
        )
        if child_ack.status == "error":
            child_status = "rejected"
        elif status == "filled":
            child_status = "resting"  # placed by the venue on the full fill
        else:
            child_status = "canceled"  # no full fill: no child
        self._order_outcome(
            stop_cloid,
            child_status,
            oid=child_ack.oid,
            error=child_ack.error,
            kind=kind,
            venue_status=None if child_ack.status == "error" else child_ack.status,
        )
        if child_status == "resting":
            self.note_local_stop(
                coin, stop_cloid, child_ack.oid, not is_buy, sz, stop_px
            )
        return (
            SendResult(cloid, status, ack.oid, ack.filled_sz, ack.avg_px, ack.error),
            SendResult(stop_cloid, child_status, child_ack.oid, error=child_ack.error),
        )

    def note_local_stop(
        self,
        coin: str,
        cloid: str,
        oid: int | None,
        is_buy: bool,
        sz: float,
        trigger_px: float,
    ) -> None:
        """A stop acked resting joins the local order list until the next
        read replaces it (P7 verifies it is listed). A child's ack carries no
        oid: a negative placeholder stands in (it is cancelled by cloid)."""
        if oid is None:
            self._placeholder_oid -= 1
            oid = self._placeholder_oid
        order = core.VenueOrder(
            coin=coin,
            oid=oid,
            cloid=cloid,
            is_buy=is_buy,
            sz=sz,
            is_trigger=True,
            trigger_px=trigger_px,
            reduce_only=True,
            order_type="Stop Market",
            has_cloid_field=True,
        )
        self.orders.append(order)
        self.acked_stops[cloid] = order

    def _order_outcome(
        self,
        cloid: str,
        status: str,
        *,
        oid: int | None = None,
        filled_sz: float = 0.0,
        avg_px: float | None = None,
        error: str | None = None,
        kind: str | None = None,
        venue_status: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "action": "order",
            "cloid": cloid,
            "status": status,
            "oid": oid,
            "filled_sz": filled_sz,
            "avg_px": avg_px,
            "error": core.redact(error) if error else None,
        }
        if venue_status is not None:
            payload["venue_status"] = venue_status
        if kind:
            payload["kind"] = kind
        self.journal.append("outcome", payload)

    def resolve(self, record: core.IntentRecord) -> SendResult:
        """Resolve an ambiguous order after its expiry via orderStatus(cloid).

        The wait ends before a READ, not a mutation, so it is bounded by the
        sweep deadline (:57) in every phase: an entry sent at :45:50 is still
        resolved (and, if it filled, protected) in the same run.
        """
        if self.dry:
            return SendResult(record.cloid, "ambiguous")
        deadline = self.sweep_end
        expires = int(record.expires_after_ms or 0)
        wait = (expires + 5000 - core.now_ms(self.now())) / 1000.0
        if wait > 0:
            wait = min(wait, 50.0)
            if self.now() + timedelta(seconds=wait) >= deadline:
                return SendResult(record.cloid, "ambiguous")
            self.sleep(wait)
        queried = core.parse_order_status(
            self.reader.order_status(self.env.sub, record.cloid)
        )
        self._order_outcome(
            record.cloid,
            queried.status,
            oid=queried.oid,
            filled_sz=queried.filled_sz,
            kind="canary" if record.canary else None,
            venue_status=queried.venue_status,
        )
        return SendResult(record.cloid, queried.status, queried.oid, queried.filled_sz)

    def resolve_unresolved(self) -> None:
        """Resolve every ambiguous order (reads only), oldest first.

        A malformed answer for one intent is a technical failure for that
        intent; the rest are still resolved and the sweep still runs.
        """
        if self.dry:
            return
        for record in sorted(self.book.unresolved.values(), key=lambda r: r.order):
            if not self.in_sweep_window():
                return
            try:
                self.resolve(record)
            except NotSentError:
                raise
            except TechnicalError as exc:
                self.problem("technical_failure", f"resolve:{record.coin}", str(exc))

    def set_leverage(
        self, coin: str, leverage: int, trade_id: str, kind: str | None = None
    ) -> bool:
        assert self.gateway is not None
        self.plan("update_leverage", coin=coin, leverage=leverage, is_cross=False)
        payload: dict[str, Any] = {
            "coin": coin,
            "trade_id": trade_id,
            "leverage": leverage,
            "is_cross": False,
        }
        if kind:
            payload["kind"] = kind
        try:
            self.gateway.prepare("updateLeverage", coin, new_risk=True)
            self.gateway.set_expires_after(
                core.now_ms(self.now()) + self.cfg.expires_after_seconds * 1000
            )
            response = self.gateway.update_leverage(coin, leverage)
        except NotSentError as exc:
            self.journal.append(
                "leverage", {**payload, "status": "not_sent", "error": core.redact(exc)}
            )
            if not isinstance(exc, GatewayRefused):
                raise
            return False
        except Exception as exc:  # idempotent: a failure or ambiguity skips
            self.journal.append(
                "leverage",
                {
                    **payload,
                    "status": "ambiguous",
                    "error": core.redact(type(exc).__name__),
                },
            )
            return False
        ok, error = core.parse_leverage_ack(response)
        self.journal.append(
            "leverage",
            {**payload, "status": "ok" if ok else "rejected", "error": error},
        )
        return ok

    def cancel_order(self, order: core.VenueOrder, kind: str | None = None) -> bool:
        assert self.gateway is not None
        trade_id, role = self.book.known_oids.get(order.oid, ("", ""))
        record = self.book.intents.get(order.cloid or "")
        if record is not None:
            trade_id, role = record.trade_id, record.role
        payload: dict[str, Any] = {
            "action": "cancel",
            "role": "cancel",
            "trade_id": trade_id,
            "coin": order.coin,
            "oid": order.oid,
            "cloid": order.cloid,
            "n": 0,
        }
        if kind:
            payload["kind"] = kind
        action = "cancelByCloid" if order.cloid else "cancel"
        try:
            self.gateway.prepare(action, order.coin, new_risk=False)
        except GatewayRefused as exc:  # nothing was sent and no intent exists
            self.plan(
                "refused", role="cancel", coin=order.coin, reason=core.redact(exc)
            )
            return False
        self.journal.append("intent", payload)
        # Once a cancel may go out, the stop no longer counts as acked resting
        # (acked_stops): a later read must list it.
        self.acked_stops = {
            cloid: acked
            for cloid, acked in self.acked_stops.items()
            if cloid != order.cloid and acked.oid != order.oid
        }
        self.plan("cancel", coin=order.coin, oid=order.oid, cloid=order.cloid)
        try:
            self.gateway.set_expires_after(
                core.now_ms(self.now()) + self.cfg.expires_after_seconds * 1000
            )
            if order.cloid:
                response = self.gateway.cancel_by_cloid(order.coin, order.cloid)
            else:
                response = self.gateway.cancel(order.coin, order.oid)
        except NotSentError as exc:
            self.journal.append(
                "outcome",
                {
                    "action": "cancel",
                    "cloid": order.cloid,
                    "oid": order.oid,
                    "status": "rejected",
                    "error": core.redact(f"not_sent: {exc}"),
                },
            )
            if not isinstance(exc, GatewayRefused):
                raise
            return False
        except Exception as exc:
            self.journal.append(
                "outcome",
                {
                    "action": "cancel",
                    "cloid": order.cloid,
                    "oid": order.oid,
                    "status": "ambiguous",
                    "error": core.redact(type(exc).__name__),
                },
            )
            return False
        ok, error = core.parse_cancel_ack(response)
        gone = not ok and core.cancel_target_gone(error)
        self.journal.append(
            "outcome",
            {
                "action": "cancel",
                "cloid": order.cloid,
                "oid": order.oid,
                "status": "canceled" if ok else "gone" if gone else "rejected",
                "error": error,
            },
        )
        if gone:  # filled, triggered or venue-cancelled: nothing rests to cancel
            self.orders = [o for o in self.orders if o.oid != order.oid]
            return True
        if ok:
            self.orders = [o for o in self.orders if o.oid != order.oid]
            if role in ("stop", "canary_stop") and kind is None:
                self.journal.append(
                    "stop_cancelled",
                    {
                        "trade_id": trade_id,
                        "coin": order.coin,
                        "cloid": order.cloid,
                        "oid": order.oid,
                        "version": record.n if record else None,
                    },
                )
        return ok

    # -------------------------------------------------------- positions
    def close_ladder(
        self,
        coin: str,
        trade_id: str,
        role: str,
        reason: str,
        kind: str | None = None,
        cap: float | None = None,
    ) -> list[tuple[float, float]]:
        """Reduce-only IOC ladder until flat (re-read after each step).

        ``cap`` (a dust close): the ladder sells at most that much in all,
        and stops at a read that shows more than is left of it. That read is
        not the dust the close was decided on (a fill the proof missed, or
        an order the sleeve did not send), and selling it at the ladder's
        prices would close a position that is not dust."""
        fills: list[tuple[float, float]] = []
        market = self.market(coin)
        half_lot = 0.5 * 10.0**-market.sz_decimals
        for bps in self.cfg.exit_ladder_bps:
            position = self.positions.get(coin)
            if position is None or not self.can_mutate():
                break
            if cap is not None:
                left = cap - sum(item[0] for item in fills)
                if position.size > left + half_lot:
                    break
            mid = self.mid_now(coin)
            if mid is None:
                break
            is_buy = position.szi < 0
            n = self.book.attempts.get((trade_id, role), 0) + 1
            result = self.send_order(
                trade_id=trade_id,
                role=role,
                coin=coin,
                is_buy=is_buy,
                sz=position.size,
                limit_px=core.ioc_limit(mid, is_buy, bps, market.sz_decimals),
                order_type=IOC,
                reduce_only=True,
                n=n,
                context={"reason": reason, "bps": bps},
                kind=kind,
            )
            if result.filled_sz > 0:
                fills.append((result.filled_sz, result.avg_px or mid))
                if self.dry:
                    self.apply_dry_fill(
                        coin, is_buy, min(result.filled_sz, position.size), mid, 0
                    )
            if not self.dry:
                self.refresh_positions()
        return fills

    def flat_unexplained(
        self,
        coin: str,
        start: core.VenuePosition | None,
        fills: list[tuple[float, float]],
    ) -> bool:
        """After a close ladder whose last read shows ``coin`` flat: the fills
        its reduce-only IOCs were acked for close less than the position it
        started from (by half a lot or more), or it started from a read that
        already showed the coin flat (a read made for another coin, such as
        an earlier close's ladder, so no IOC was sent). Something else may
        explain it (a venue stop or a liquidation between the reads), but so
        may a read from an info node that lags the entry fill; only the
        fills, read later, tell them apart. Dry runs apply their own fills."""
        if self.dry:
            return False
        if start is None:
            return True
        market = self.markets.get(coin)
        half_lot = 0.5 * 10.0 ** -(market.sz_decimals if market else 8)
        return sum(item[0] for item in fills) < start.size - half_lot

    def close_position(
        self,
        coin: str,
        reason: str,
        *,
        decision: core.ExitDecision | None = None,
        operator_reason: str | None = None,
        cap: float | None = None,
    ) -> bool:
        """Close an owned position (reduce-only ladder), then its owned orders.
        ``cap``: the most the ladder may sell in all (close_ladder)."""
        trade = self.book.open_trades.get(coin)
        if trade is None:
            self.problem("exit_incomplete", coin, "no journal trade for the position")
            return False
        role = core.close_role(reason)
        start = self.positions.get(coin)
        if start is not None:  # the fills must also explain what children prove
            start = self.proven_position(trade, start)[0]
        fills = self.close_ladder(coin, trade.trade_id, role, reason, cap=cap)
        if coin in self.positions:
            self.problem(
                "exit_incomplete",
                coin,
                f"{reason}: not flat after the reduce-only ladder",
            )
            return False
        if self.flat_unexplained(coin, start, fills):
            # The read says flat but the acked close fills do not account for
            # the position: an info node lagging the entry fill shows the coin
            # flat (H6: one lagging or incomplete read must not close a live
            # trade). Keep the trade open and its orders. If the position is
            # still there, a later read of the run that shows it protects it
            # (P7 after a P3 or P5 close); after a close in flatten, in P7's
            # re-sweep or in its final loop no read follows, and the next
            # run's P3 does. The next run's P2 reconciles a truly flat coin
            # from its fills (venue stop, liquidation, this close) after a
            # second read.
            self.problem(
                "exit_incomplete",
                coin,
                f"{reason}: the flat read is not explained by the close fills",
            )
            return False
        for order in self.owned_orders(coin):
            self.cancel_order(order)
        size = sum(item[0] for item in fills)
        exit_px = sum(item[0] * item[1] for item in fills) / size if size else None
        virtual = decision.virtual if decision else None
        payload: dict[str, Any] = {
            "trade_id": trade.trade_id,
            "coin": coin,
            "reason": reason,
            "exit_px": exit_px,
            "closed_pnl": None,
            "fees": None,
            "funding": None,
            "net_usd": None,
            "net_r": None,
            "late_exit_days": (
                core.late_exit_days(decision, self.today) if decision else 0
            ),
            "virtual": virtual,
        }
        if operator_reason:
            payload["operator_reason"] = core.redact(operator_reason)
        self.journal.append("trade_closed", payload)
        self.closed_this_run.append((trade, reason, core.now_ms(self.now())))
        self.counts["exits"] += 1
        self.account_stale = True
        return True

    def place_stop(
        self,
        trade_id: str,
        position: core.VenuePosition,
        trigger_px: float,
        *,
        role: str = "stop",
        context: Mapping[str, Any] | None = None,
    ) -> SendResult:
        """The one protective send (it may go out after the deadline and in
        the quiet window): a reduce-only stop-market trigger for all of
        ``position``. Role ``stop``: an owned trade's rule stop (versioned,
        journaled stop_placed). Role ``guard``: A2's protective stop for a
        position the sleeve cannot attribute (trade_id guard:<coin>)."""
        version = self.book.attempts.get((trade_id, role), 0) + 1
        result = self.send_order(
            trade_id=trade_id,
            role=role,
            coin=position.coin,
            is_buy=position.szi < 0,
            sz=position.size,
            limit_px=trigger_px,
            order_type={
                "trigger": {"triggerPx": trigger_px, "isMarket": True, "tpsl": "sl"}
            },
            reduce_only=True,
            n=version,
            context=context,
            protective=True,
        )
        if result.resting and result.oid is not None:
            if role == "stop":
                self.journal.append(
                    "stop_placed",
                    {
                        "trade_id": trade_id,
                        "coin": position.coin,
                        "cloid": result.cloid,
                        "oid": result.oid,
                        "trigger_px": trigger_px,
                        "sz": position.size,
                        "version": version,
                    },
                )
            self.note_local_stop(
                position.coin,
                result.cloid,
                result.oid,
                position.szi < 0,
                position.size,
                trigger_px,
            )
        return result

    def fill_proof(self, trade_id: str, coin: str) -> float:
        """The size THIS session has proof the trade's entry filled, whatever
        a read shows.

        Each entry attempt of this session proves the larger of its acked (or
        resolved) fill and its stop child's size when the venue showed that
        child resting (A1: the venue places a child only once its entry has
        fully filled): listed now, or journaled open (a listing, through
        learn_listed_oids, or its orderStatus), which stays proof after
        protect() cancels the child to re-anchor the stop.

        The attempts add up: one may be proven only by its child (a lost reply
        and an orderStatus that lags it: never_landed) and another only by its
        ack, while a read between the two fills shows one of them. A fill
        journaled from a position read (position_reread) proves nothing a read
        does not. The acked fills a read at open showed less of (acked_unseen)
        are these attempts' acks, so they are part of it.

        For a trade with an entry attempt in this session, the proof is at
        least the largest same-side size a position read of this session
        showed for it (seen_sz): a fill whose reply was lost and that left no
        child (a partial fill, or a child the venue rejected) proves nothing
        by itself, and a later read from a node that lags it would otherwise
        re-size the stop below what an earlier read showed. It is also at
        least the cover floor open_trade set when it did not close a dust
        read as dust because an attempt's fill was unsettled (cover_floor).

        The position holds at least that while nothing has reduced it, so the
        proof is scoped to this session (an info node lags a fill by seconds
        to minutes; runs are hourly) and void once this session has sent a
        close for the trade: a reduction never reads as a lag."""
        if any(
            record.trade_id == trade_id
            and record.role in core.CLOSE_ROLES
            and record.order > self.session_order
            for record in self.book.intents.values()
        ):
            return 0.0
        listed: dict[str, float] = {}
        for order in self.orders:
            if order.coin == coin and order.cloid:
                listed[order.cloid] = max(listed.get(order.cloid, 0.0), order.sz)
        proven = 0.0
        attempted = False
        for record in self.book.intents.values():
            if (
                record.trade_id != trade_id
                or record.coin != coin
                or record.role != "entry"
                or record.canary
                or record.order <= self.session_order
            ):
                continue
            attempted = True
            outcome = record.outcome or {}
            acked = 0.0
            if record.filled and outcome.get("venue_status") != "position_reread":
                acked = float(outcome.get("filled_sz") or 0.0)
            proven += max(acked, self.child_proof(record, listed))
        if attempted:
            proven = max(
                proven,
                self.seen_sz.get(trade_id, 0.0),
                self.cover_floor.get(trade_id, 0.0),
            )
        return proven

    def child_proof(
        self, entry: core.IntentRecord, listed: Mapping[str, float]
    ) -> float:
        """The size ``entry``'s stop child proves filled (fill_proof): its
        listed size, or its journaled size once a listing or its orderStatus
        showed it resting (outcome open: it stays proof after this session
        cancels it); 0 otherwise (a partial fill, no fill or rejection leaves
        no child). A child acked resting needs no proof of its own: its
        entry's full-fill ack is the same size."""
        cloid = str(entry.context.get("stop_child") or "")
        child = self.book.intents.get(cloid) if cloid else None
        if child is None:
            return 0.0
        if cloid in listed:
            return listed[cloid]
        if child.status == "open":  # resting: its full-fill ack proves it
            return child.sz
        return 0.0

    def proven_position(
        self, trade: core.OpenTrade, position: core.VenuePosition
    ) -> tuple[core.VenuePosition, bool]:
        """The position to protect: the read, or more when this session has
        proof of fills the read misses (fill_proof: an info node lagging a
        retry's or a remainder's fill). True when the read lags that proof."""
        market = self.markets.get(position.coin)
        half_lot = 0.5 * 10.0 ** -(market.sz_decimals if market else 8)
        proven = self.fill_proof(trade.trade_id, position.coin)
        if position.direction != trade.direction or proven <= position.size + half_lot:
            return position, False
        return replace(position, szi=position.direction * proven), True

    def protect(self, trade: core.OpenTrade, position: core.VenuePosition) -> bool:
        """Section 13: make exactly one good stop rest, or close the position.

        When the read shows less than this session has proof of (fill_proof:
        acked fills, listed stop children), the read lags a fill: the stop
        covers the proven size and the trade's children are kept, so the
        proof (and their protection) stays until a read shows it all. The
        run end raises it critical if no read did (check_acked_entries)."""
        coin = position.coin
        market = self.market(coin)
        position, lagging = self.proven_position(trade, position)

        def cancel_others(orders: Sequence[core.VenueOrder]) -> None:
            for order in orders:
                record = self.book.intents.get(order.cloid or "")
                if (
                    lagging
                    and record is not None
                    and record.trade_id == trade.trade_id
                    and record.context.get("child_of")
                ):
                    continue  # it protects (and proves) a fill the read misses
                self.cancel_order(order)

        plan = core.plan_protection(
            position,
            trade.stop_px,
            self.owned_orders(coin),
            self.mids.get(coin),
            market,
        )
        if plan.action == "ok":
            cancel_others(plan.cancel)
            return True
        if plan.action == "breach":
            return self.close_position(coin, "breach")
        # The stop itself is protective: it may go out after the deadline and
        # in the quiet window. Nothing else may, so past the sweep deadline
        # there is no mid read, no breach check and no close.
        result = self.place_stop(trade.trade_id, position, plan.expected_px)
        if not result.resting:
            mid = self.mid_now(coin) if self.in_sweep_window() else None
            if mid is not None and position.direction * (mid - plan.expected_px) <= 0:
                return self.close_position(coin, "breach")
            result = self.place_stop(trade.trade_id, position, plan.expected_px)
        if not result.resting and not self.in_sweep_window():
            self.problem(
                "stop_missing",
                coin,
                "the stop did not rest before the quiet window; the next run "
                "places it first",
            )
            return False
        if not result.resting:
            self.problem("unprotectable", coin, "stop placement failed twice")
            self.close_position(coin, "unprotectable")
            return False
        cancel_others(plan.cancel)
        return True

    def check_leverage(
        self, trade: core.OpenTrade, position: core.VenuePosition
    ) -> bool:
        """Returns True when the position was closed (the stop cannot protect it)."""
        coin = position.coin
        if position.leverage_type != "isolated":
            self.problem("not_isolated", coin, "position is not isolated margin")
            return self.close_position(coin, "not_isolated")
        liq = position.liquidation_px
        d = position.direction
        if liq is not None and d * (trade.stop_px - liq) <= 0:
            self.problem(
                "stop_behind_liquidation", coin, "liquidation price is before the stop"
            )
            return self.close_position(coin, "stop_behind_liquidation")
        if liq is not None and position.entry_px > 0 and trade.stop_fraction > 0:
            buffer = abs(position.entry_px - liq) / position.entry_px
            floor = self.cfg.liq_buffer_warn_fraction * 2.5 * trade.stop_fraction
            if buffer < floor:
                self.problem("liq_buffer_low", coin, f"buffer {buffer:.4f}")
        if trade.leverage and position.leverage_value != trade.leverage:
            self.problem("leverage_mismatch", coin, "venue leverage differs", NOTICE)
        return False

    def check_overfill(self, coin: str, size: float, intended: object) -> None:
        """Critical (and no further entry this run) when the venue holds a lot
        or more above the size this entry was sized for (fill_fraction > 1).

        The coin was flat before the entry and fills never exceed the sized
        amount, so any excess is a duplicate entry (for example a retry after
        a lagging orderStatus) or an order the sleeve did not send: risk above
        1R at the stop, sized for 1x gross and margin. The stop still covers
        the whole position; nothing is sold (SRS_HV1_NO_GATES).
        """
        market = self.markets.get(coin)
        if market is None or not isinstance(intended, (int, float)) or intended <= 0:
            return
        lot = 10.0**-market.sz_decimals
        if size > float(intended) + 0.5 * lot:
            self.problem(
                "entry_overfill",
                coin,
                f"venue size is {size / float(intended):.3f} x the sized entry",
            )

    def check_growth(self, trade: core.OpenTrade, position: core.VenuePosition) -> None:
        """P3/P7: critical entry_overfill, once per new size, when an opened
        trade's position is a lot or more above its sized entry, its opened
        size and every size already raised for it.

        The sleeve never adds to a position (no top-ups; exits only reduce),
        so that growth is a duplicate entry fill the read at open missed (a
        retry after a lagging orderStatus and a lagging position read) or an
        order the sleeve did not send. The stop is re-sized to cover it
        (plan_protection); nothing is sold (SRS_HV1_NO_GATES). position_grew
        is journaled so later runs do not raise it again for that size.
        """
        market = self.markets.get(trade.coin)
        if market is None or position.direction != trade.direction:
            return
        tid = trade.trade_id
        sized = self.book.sized_entry(tid)
        seen = max(trade.sz, sized or 0.0, self.book.grown_sz.get(tid, 0.0))
        if position.size <= seen + 0.5 * 10.0**-market.sz_decimals:
            return
        self.journal.append(
            "position_grew",
            {
                "trade_id": tid,
                "coin": trade.coin,
                "sz": position.size,
                "opened_sz": trade.sz,
                "sized_sz": sized,
            },
        )
        base = sized or trade.sz
        self.problem(
            "entry_overfill",
            trade.coin,
            f"the position grew to {position.size / base:.3f} x the sized entry "
            "after it opened"
            if base > 0
            else "the position grew after it opened",
        )

    def has_stop_cover(self, coin: str, position: core.VenuePosition) -> bool:
        """Local state shows an owned reduce-only stop that closes the whole position."""
        market = self.markets.get(coin)
        half_lot = 0.5 * 10.0 ** -(market.sz_decimals if market else 8)
        return any(
            order.is_trigger
            and order.reduce_only
            and order.is_buy == (position.szi < 0)
            and order.sz >= position.size - half_lot
            for order in self.owned_orders(coin)
        )

    def flag_unprotected(self) -> None:
        """After P7 was skipped or cut short: stop_missing for every owned
        position the local book shows without a covering stop (no network).

        The next run's P3 places those stops before its exits and entries.
        First, every entry attempt of this session that said never_landed
        (trade not opened) is marked position_unverified, unless its coin is
        held on the other side (a side this session closed there does not
        count: mark_unverified): without P7's reads nothing shows whether it
        filled unseen, so the next run's P3 adopts and protects a
        same-direction position on its coin instead of leaving it unowned
        (unresolved_entry is raised at run end). A same-side position an
        earlier read of this run showed becomes owned by that mark, so the
        loop below raises stop_missing for it in this run. A trade opened
        from a read below its acked fills that no later read showed in full
        is critical fill_not_visible (check_acked_entries).
        """
        try:
            self.mark_unverified(why="no_final_check")
        except Exception:  # a local journal write; never mask the original failure
            pass
        try:
            self.check_acked_entries("acked entry fills not shown; no final check")
        except Exception:  # local state only; never mask the original failure
            pass
        try:
            owned = self.owned_positions()
        except Exception:  # local state only; never mask the original failure
            return
        for coin, position in owned.items():
            if not self.has_stop_cover(coin, position):
                self.problem(
                    "stop_missing",
                    coin,
                    "no verified stop at run end; the next run places it first",
                )
        try:
            bare = self.unguarded()
        except Exception:  # local state only; never mask the original failure
            return
        for coin in bare:  # A2: the next run's P3 guards it first
            self.problem(
                "unknown_position",
                coin,
                "a position the sleeve does not own has no protective stop and "
                "the final check did not run; the next run guards it",
            )

    def check_acked_entries(self, message: str) -> None:
        """Run end (P7, or flag_unprotected when P7 was lost): critical
        fill_not_visible for each entry whose reads at open showed less than
        its acked fills (acked_unseen), whose trade is open (opened at open
        or from P7's reads) and whose last read still shows less than those
        fills. Its stop covers only the size read, so the rest has none until
        a read shows it (the next run's P3 re-sizes the stop). The same for
        each open trade whose last read shows less than this session's proof
        of its fills (fill_proof: acks, children and the largest size an
        earlier read of the run showed), or shows the coin flat (or held only
        on the other side) while that proof is more than the size the trade
        opened at and every growth already raised for it. Local state only;
        no network."""
        for tid, (coin, acked) in self.acked_unseen.items():
            trade = self.book.open_trades.get(coin)
            if trade is None or trade.trade_id != tid:
                continue  # closed in this run (breach, unprotectable, dust)
            if not self.shows_fill(self.positions.get(coin), trade.direction, acked):
                self.problem("fill_not_visible", coin, message)
        for coin, trade in self.book.open_trades.items():
            # A1: this session's acks, stop children and earlier reads prove
            # more than the last read shows (a retry's fill behind a lost
            # reply, or a node behind a fill an earlier read showed). The
            # stop covers them (protect); the read still lags, so it is
            # critical. So is a last read that shows the coin flat while they
            # prove more than the trade opened at and every growth already
            # raised: nothing this session sent reduced it (fill_proof), so a
            # doubled entry would otherwise end the run silent under its two
            # stops. A read that shows only the other side shows nothing of
            # this trade (a node behind the close of the side this session
            # closed there): it counts as flat.
            position = self.positions.get(coin)
            if position is not None and position.direction != trade.direction:
                position = None
            if position is None:
                market = self.markets.get(coin)
                half_lot = 0.5 * 10.0 ** -(market.sz_decimals if market else 8)
                shown = max(trade.sz, self.book.grown_sz.get(trade.trade_id, 0.0))
                if self.fill_proof(trade.trade_id, coin) > shown + half_lot:
                    self.problem("fill_not_visible", coin, message)
            elif self.proven_position(trade, position)[1]:
                self.problem("fill_not_visible", coin, message)
            if self.attempts_unproven(trade):
                self.problem(
                    "fill_not_visible",
                    coin,
                    "two attempts of this entry said never_landed and it is "
                    "open: one may have filled unseen",
                )

    def ensure_trade(
        self, coin: str, position: core.VenuePosition
    ) -> core.OpenTrade | None:
        """The journal trade for an owned position; recover trade_opened if missing."""
        trade = self.book.open_trades.get(coin)
        if trade is not None:
            return trade
        record = self.book.pending_opens().get(coin)
        if record is None:
            return None
        context = record.context
        market = self.market(coin)
        d = int(context["d"])
        stop_dist = float(context["stop_dist"])
        stop_px = core.normalize_price(
            position.entry_px - d * stop_dist, market.sz_decimals
        )
        virtual = dict(context.get("virtual") or {})
        self.journal.append(
            "trade_opened",
            {
                "trade_id": record.trade_id,
                "coin": coin,
                "direction": d,
                "side": "long" if d > 0 else "short",
                "label": "trend" if d > 0 else "hedge",
                "signal_date": context.get("signal_date"),
                "entry_date": context.get("entry_date"),
                "sz": position.size,
                "entry_px": position.entry_px,
                "notional": position.size * position.entry_px,
                "leverage": context.get("L"),
                "stop_px": stop_px,
                "stop_dist": stop_dist,
                "stop_fraction": stop_dist / position.entry_px,
                "risk_usd": context.get("risk_usd"),
                "actual_risk_usd": position.size * stop_dist,
                "book_equity": context.get("book_equity"),
                "liq_px": position.liquidation_px,
                "recovered": True,
                "opened_ms": core.now_ms(self.now()),
                "virtual": {
                    "taken": virtual.get("taken"),
                    "stop_px": virtual.get("stop_px"),
                    "priority_rank": virtual.get("priority_rank"),
                },
            },
        )
        self.note_seen()  # the read that recovered it (fill_proof)
        self.check_overfill(coin, position.size, context.get("sizing_sz"))
        return self.book.open_trades.get(coin)

    # -------------------------------------------------------- phases
    def load_signer(self) -> None:
        """Armed only: import the SDK and prove the key is the sleeve agent's."""
        self.sdk = _load_sdk()
        try:
            account = self.sdk.Account.from_key(self.env.private_key)
            self.signer_address = str(account.address).lower()
        except Exception as exc:  # never echo the key or its parse error
            raise RefusalError("the sleeve private key could not be loaded") from exc

    def p1_identity(self) -> None:
        now = self.now()
        last = self.book.last_identity
        reuse = (
            self.armed
            and self.cmd == "run"
            and last is not None
            and last.get("utc_date") == now.date().isoformat()
            and last.get("fps") == self.env.fps(self.cfg)
            and all((last.get("checks") or {}).values())
        )
        if reuse:
            assert last is not None
            checks = {
                "signer_matches_agent": self.signer_address == self.env.agent,
                "engine_key_absent_from_env": engine_key_absent(),
            }
            report = IdentityReport(
                checks=checks,
                informational={},
                agent_days_left=last.get("agent_days_left"),
                master_mode=last.get("master_mode"),
                sub_mode=last.get("sub_mode"),
                fps=self.env.fps(self.cfg),
                reused=True,
            )
        else:
            report = verify_identity(
                self.reader, self.env, self.cfg, now, signer_address=self.signer_address
            )
        self.identity = report
        self.out(report.line())
        if not report.ok:
            if self.book.open_trades:
                self.problem(
                    "identity_refused_with_positions",
                    message="identity refused while the sleeve holds positions",
                )
            failed = sorted(name for name, ok in report.checks.items() if not ok)
            raise RefusalError(f"identity refused: {','.join(failed)}")
        if self.armed and not report.reused:
            self.journal.append(
                "identity_verified",
                {
                    "utc_date": now.date().isoformat(),
                    "checks": report.checks,
                    "agent_days_left": report.agent_days_left,
                    "master_mode": report.master_mode,
                    "sub_mode": report.sub_mode,
                    "fps": report.fps,
                },
            )
        days = report.agent_days_left
        if days is not None and days < self.cfg.agent_critical_days:
            self.problem("agent_expiring", message=f"{days} days", severity=CRITICAL)
        elif days is not None and days < self.cfg.agent_warn_days:
            self.problem("agent_expiring", message=f"{days} days", severity=NOTICE)

    def p1_snapshot(self) -> None:
        assert self.identity is not None
        sub_mode = core.parse_account_mode(self.identity.sub_mode)
        master_mode = core.parse_account_mode(self.identity.master_mode)
        self.meta_raw = self.reader.meta()
        self.markets = core.parse_meta(self.meta_raw)
        self.mids = core.parse_mids(self.reader.all_mids())
        perp = self.reader.clearinghouse_state(self.env.sub)
        self.positions = core.parse_positions(perp)
        spot = (
            self.reader.spot_state(self.env.sub)
            if sub_mode == "unifiedAccount"
            else None
        )
        self.orders = core.parse_open_orders(
            self.reader.frontend_open_orders(self.env.sub)
        )
        self.sub_value = core.parse_account_value(sub_mode, perp, spot)
        self.sub_free = self.sub_value.free_usd
        try:
            if master_mode == "unifiedAccount":
                master_perp: Any = None
                master_spot: Any = self.reader.spot_state(self.env.master)
            else:
                master_perp = self.reader.clearinghouse_state(self.env.master)
                master_spot = None
            self.master_value = core.parse_account_value(
                master_mode, master_perp, master_spot
            )
            equity = self.master_value.equity_usd + self.sub_value.equity_usd
            if math.isfinite(equity) and equity > 0:
                self.book_equity = equity
            else:
                self.problem("equity_invalid", message="book equity is not positive")
        except NotSentError:
            raise
        except TechnicalError as exc:
            self.problem("equity_invalid", message=str(exc))
        self.build_gateway()

    def build_gateway(self) -> None:
        kwargs = {
            "cfg": self.cfg,
            "env": self.env,
            "markets": self.markets,
            "pacer": self.pacer,
            "clock": self.clock,
        }
        if self.dry:
            self.gateway = DryRunGateway(mid=lambda coin: self.mids.get(coin), **kwargs)
            return
        assert self.sdk is not None and self.env.private_key is not None
        assert self.meta_raw is not None
        factory = self.ctx.exchange_factory or functools.partial(
            build_exchange, self.sdk
        )
        self.exchange = factory(
            key=self.env.private_key, meta=self.meta_raw, sub=self.env.sub, cfg=self.cfg
        )
        self.signing_client = "constructed"
        session = getattr(self.exchange, "session", None)
        if isinstance(session, requests.Session):
            adapter = session.get_adapter(HL_URL)
            if isinstance(adapter, HlAllowListTransport):
                self.exchange_guard = adapter
        self.gateway = SubAccountGateway(
            self.exchange,
            cloid_cls=self.sdk.Cloid,
            **kwargs,  # type: ignore[arg-type]
        )

    def flat_trades(self) -> list[core.OpenTrade]:
        return [
            trade
            for coin, trade in self.book.open_trades.items()
            if coin not in self.positions
        ]

    def p2_reconcile(self) -> None:
        self.set_phase("sweep")
        if self.dry:
            if self.book.unresolved:
                self.problem(
                    "unresolved_intents",
                    message=f"{len(self.book.unresolved)} unresolved",
                    severity=NOTICE,
                )
        else:
            self.settle_unverified_entries()
            self.resolve_unresolved()
        try:
            self.reconcile_flat_trades()
        finally:  # unowned exposure is flagged (and blocked) even if that failed
            self.classify()
        for coin, trade in self.book.open_trades.items():
            position = self.positions.get(coin)
            if position is not None and position.direction == trade.direction:
                market = self.markets.get(coin)
                if market and not core.sizes_equal(
                    position.size, trade.sz, market.sz_decimals
                ):
                    self.counts["size_mismatch"] += 1
        self.journal_snapshot()

    def reconcile_flat_trades(self) -> None:
        """Journal-open trades the venue shows flat: close them with their reason."""
        flat = self.flat_trades()
        if flat and self.dry:
            for trade in flat:
                self.problem(
                    "venue_flat_pending",
                    trade.coin,
                    "journal open, venue flat",
                    severity=NOTICE,
                )
            return
        if not flat:
            return
        start = min(trade.opened_ms for trade in flat) - 60_000
        fills = core.parse_fills(
            self.reader.user_fills_by_time(
                self.env.sub, max(0, start), core.now_ms(self.now())
            )
        )
        if any(self.flat_reason(t, fills) == "venue_flat_other" for t in flat):
            # No fill explains the flat coin: one lagging or incomplete
            # position read must not close a live trade (and so cancel its
            # stop as a flat-coin order). Read once more first.
            self.sleep(REREAD_DELAY_S)
            self.refresh_positions()
            flat = self.flat_trades()
        for trade in flat:
            self.reconcile_flat(trade, fills)

    def flat_reason(self, trade: core.OpenTrade, fills: list[core.Fill]) -> str:
        """Why a journal-open trade is flat on the venue, from its fills."""
        mine = [
            f
            for f in fills
            if f.coin == trade.coin and f.time_ms >= trade.opened_ms - 60_000
        ]
        stop_oids = self.book.stop_oids.get(trade.trade_id, set()) | {
            oid  # a guard stop the sweep placed on the coin (A2)
            for oid, (tid, role) in self.book.known_oids.items()
            if role == "guard" and tid == f"{core.GUARD_TRADE_PREFIX}{trade.coin}"
        }
        if any(f.liquidation for f in mine):
            return "liquidation"
        if any(f.oid in stop_oids for f in mine):
            return "venue_stop"
        closes = [
            f
            for f in mine
            if self.book.known_oids.get(f.oid, ("", ""))[0] == trade.trade_id
            and self.book.known_oids[f.oid][1] in core.CLOSE_ROLES
        ]
        if not closes:
            return "venue_flat_other"
        record = next(
            (
                r
                for r in self.book.intents.values()
                if r.trade_id == trade.trade_id
                and r.role in core.CLOSE_ROLES
                and r.filled
            ),
            None,
        )
        return str((record.context if record else {}).get("reason", "exit"))

    def reconcile_flat(self, trade: core.OpenTrade, fills: list[core.Fill]) -> None:
        mine = [
            f
            for f in fills
            if f.coin == trade.coin and f.time_ms >= trade.opened_ms - 60_000
        ]
        reason = self.flat_reason(trade, fills)
        if reason == "liquidation":
            self.problem("liquidation", trade.coin, "the venue liquidated the position")
        elif reason == "venue_flat_other":
            self.problem(
                "venue_flat_other", trade.coin, "flat with no known close fill"
            )
            # Two reads agreed it is flat, but nothing explains it: keep its
            # reduce-only stop this run (harmless if truly flat, since the
            # venue cancels it) rather than strip a live position of it, and
            # open nothing on the coin this run (a same-run reversal could
            # otherwise trade against a position the reads do not show).
            self.hold_orders_on.add(trade.coin)
            self.blocked_coins[trade.coin] = "venue_flat_other"
        closing = [
            f
            for f in self.trade_fills(trade, fills)
            if f.is_buy == (trade.direction < 0)
        ] or [f for f in mine if f.is_buy == (trade.direction < 0)]
        size = sum(f.sz for f in closing)
        exit_px = sum(f.px * f.sz for f in closing) / size if size else None
        self.journal.append(
            "trade_closed",
            {
                "trade_id": trade.trade_id,
                "coin": trade.coin,
                "reason": reason,
                "exit_px": exit_px,
                "closed_pnl": None,
                "fees": None,
                "funding": None,
                "net_usd": None,
                "net_r": None,
                "late_exit_days": 0,
                "virtual": None,
                "reconciled": True,
            },
        )
        self.closed_this_run.append((trade, reason, core.now_ms(self.now())))
        self.counts["exits"] += 1

    def trade_fills(
        self, trade: core.OpenTrade, fills: list[core.Fill]
    ) -> list[core.Fill]:
        """Fills of this trade's own orders (known oids) plus venue liquidations."""
        return [
            f
            for f in fills
            if f.coin == trade.coin
            and f.time_ms >= trade.opened_ms - 60_000
            and (
                self.book.known_oids.get(f.oid, ("", ""))[0] == trade.trade_id
                or f.liquidation
            )
        ]

    def classify(self) -> None:
        pending = self.book.pending_opens()
        residue = self.book.canary_residue()
        for coin, position in self.positions.items():
            trade = self.book.open_trades.get(coin)
            if trade is not None:
                if trade.direction != position.direction:
                    self.problem(
                        "direction_conflict", coin, "venue side opposes the journal"
                    )
                    self.blocked_coins[coin] = "direction_conflict"
            elif coin in residue and position.direction > 0:
                self.problem(
                    "canary_residue",
                    coin,
                    "an interrupted canary left this position; run flatten --coin",
                )
                self.blocked_coins[coin] = "canary_residue"
            elif not (
                coin in pending
                and int(pending[coin].context.get("d", 0)) == position.direction
            ):
                self.problem(
                    "unknown_position", coin, "position not placed by the sleeve"
                )
                self.blocked_coins[coin] = "unowned"
        for order in self.orders:
            if not self.owned_order(order):
                self.problem(
                    "unknown_order",
                    f"{order.coin}:{order.oid}",
                    "order not placed by the sleeve",
                )
                self.blocked_coins[order.coin] = "unowned"

    def journal_snapshot(self) -> None:
        owned = self.owned_positions()
        self.journal.append(
            "snapshot",
            {
                "positions": [
                    {
                        "coin": p.coin,
                        "szi": p.szi,
                        "entry_px": p.entry_px,
                        "liq_px": p.liquidation_px,
                        "lev_type": p.leverage_type,
                        "lev_value": p.leverage_value,
                        "owned": p.coin in owned,
                    }
                    for p in self.positions.values()
                ],
                "orders": {
                    "owned": len(self.owned_orders()),
                    "unowned": len(self.orders) - len(self.owned_orders()),
                },
                "master_equity": self.master_value.equity_usd
                if self.master_value
                else None,
                "sub_equity": self.sub_value.equity_usd if self.sub_value else None,
                "sub_free": self.sub_free,
                "book_equity": self.book_equity,
                "gross_used": self.gross_used(),
                "slots_used": len(self.positions),
            },
        )

    def p3_sweep(self) -> None:
        self.sweep(first=True)

    def sweep(self, *, first: bool = False) -> None:
        """P3/P7: protect every owned position, then give every position still
        without a covering stop a guard stop (A2, owned or not); cancel owned
        orders on flat coins unless a flat read may hide their position.

        Positions with no stop at all go first. A failure on one coin is
        recorded for that coin and the sweep moves on, so one bad reply never
        leaves the other coins unprotected.
        """
        self.set_phase("sweep")
        self.learn_listed_oids()
        owned = sorted(
            self.owned_positions().items(),
            key=lambda item: any(o.is_trigger for o in self.owned_orders(item[0])),
        )
        for coin, position in owned:
            if not self.in_sweep_window():
                self.problem("sweep_deadline", message="sweep stopped at its deadline")
                return
            if coin not in self.positions:
                continue
            try:
                self.protect_coin(coin, position, first=first)
            except NotSentError:
                raise
            except TechnicalError as exc:
                self.problem("technical_failure", coin, str(exc))
            except Exception as exc:  # the TYPE only: a message may hold a secret
                self.problem("technical_failure", coin, type(exc).__name__)
        self.guard_positions()
        for order in core.plan_flat_cancels(self.positions, self.owned_orders()):
            if not self.in_sweep_window():
                return
            if self.keeps_on_flat(order):
                continue  # flat on the venue but not confirmed flat: keep its stop
            self.cancel_order(order)

    def order_intent(self, order: core.VenueOrder) -> core.IntentRecord | None:
        """The journal intent behind a listed order (by cloid, else by oid)."""
        record = self.book.intents.get(order.cloid or "")
        if record is not None:
            return record
        for candidate in self.book.intents.values():
            if (candidate.outcome or {}).get("oid") == order.oid:
                return candidate
        return None

    def keeps_on_flat(self, order: core.VenueOrder) -> bool:
        """An owned order on a coin the reads show flat that must not be
        cancelled (sweep and flatten): a flat read may come from an info node
        that lags a fill, and the stop is then all that protects it.

        Kept: every order on a coin with an open trade (a close its fills did
        not explain) or reconciled venue_flat_other in this run
        (hold_orders_on); and, on any coin, a reduce-only stop of an entry
        whose trade never opened (its venue-attached child, placed only once
        that entry fully filled, or a stop from its acked fills: either
        contradicts the flat read) or a guard stop (A2). On a coin that is
        truly flat such a stop is inert (reduce-only); protect() cancels it
        once a later trade on the coin has its own verified stop."""
        if order.coin in self.book.open_trades or order.coin in self.hold_orders_on:
            return True
        if not (order.is_trigger and order.reduce_only):
            return False
        record = self.order_intent(order)
        if record is None:
            return False
        if record.role == "guard":
            return True
        return record.role == "stop" and record.trade_id not in self.book.opened_ids

    def learn_listed_oids(self) -> None:
        """Journal the oid of an owned stop the venue lists whose own ack gave
        none (an entry's stop child) or was lost (outcome open, venue_status
        listed): the listing proves it rests. known_oids then owns it by oid
        too, and a fill of it reconciles its trade as venue_stop."""
        if self.dry:
            return
        for order in self.orders:
            record = self.book.intents.get(order.cloid or "")
            if (
                record is None
                or not record.reduce_only
                or record.role not in ("stop", "guard", "canary_stop")
                or (record.outcome or {}).get("oid") is not None
            ):
                continue
            self._order_outcome(
                record.cloid,
                "open",
                oid=order.oid,
                kind="canary" if record.canary else None,
                venue_status="listed",
            )

    def guard_positions(self) -> None:
        """A2, in every sweep: each position the reads show without a
        reduce-only stop that closes all of it (whoever placed that stop)
        gets one, whether or not the sleeve can attribute the position.

        An owned position got its rule stop from protect() just before; one
        still bare here (its protection failed or raised) gets that rule
        stop again as a guard. Any other position (unknown_position,
        direction_conflict, canary_residue: all critical, raised in P2 or
        P7) gets a stop at the rule distance from its entry price, using the
        latest shadow ATR for the coin, else the ATR its last journaled entry
        was sized with, else GUARD_FALLBACK_FRACTION of the entry price
        (guard_distance): on the protective side of the mark and never at or
        beyond the liquidation price (core.guard_stop_px). Such a position
        is never traded down or closed. A position that stays bare is
        critical unprotected_position."""
        for coin, position in sorted(self.positions.items()):
            market = self.markets.get(coin)
            if market is None:
                self.problem(
                    "unprotected_position", coin, "the coin is not in this run's meta"
                )
                continue
            if core.stop_covers(position, self.orders, market.sz_decimals):
                guards = [
                    order
                    for order in self.owned_orders(coin)
                    if (record := self.order_intent(order)) is not None
                    and record.role == "guard"
                ]
                if guards and core.stop_covers(position, guards, market.sz_decimals):
                    # Every run while a guard is what protects it (a steady
                    # notice: the problem set, and so the alerts, stay put).
                    self.problem(
                        "position_guarded",
                        coin,
                        "protected by a guard stop; never traded down",
                        severity=NOTICE,
                    )
                continue
            if not self.in_sweep_window():
                self.problem("sweep_deadline", message="sweep stopped at its deadline")
                return
            try:
                self.guard(coin, position, market)
            except NotSentError:
                raise
            except TechnicalError as exc:
                self.problem("technical_failure", f"guard:{coin}", str(exc))
            except Exception as exc:  # the TYPE only: a message may hold a secret
                self.problem("technical_failure", f"guard:{coin}", type(exc).__name__)

    def guard_distance(
        self, coin: str, position: core.VenuePosition
    ) -> tuple[float, str]:
        """The rule distance (2 x ATR(signal) x unit) for a guard stop: the
        latest shadow entry on the coin, else the latest journaled entry
        attempt on it, else GUARD_FALLBACK_FRACTION of the entry price."""
        unit = core.price_unit(coin)
        if self.view is not None:
            for event in reversed(list(self.view.entry_events.values())):
                atr = event.get("atr_signal")
                if event.get("coin") == coin and core._finite(atr) and atr > 0:
                    return runner.STOP_ATR_MULT * float(atr) * unit, "shadow_atr"
        for record in sorted(
            self.book.intents.values(), key=lambda r: r.order, reverse=True
        ):
            dist = record.context.get("stop_dist")
            if (
                record.role == "entry"
                and not record.canary
                and record.coin == coin
                and core._finite(dist)
                and dist > 0
            ):
                return float(dist), "journal_atr"
        return core.GUARD_FALLBACK_FRACTION * position.entry_px, "fallback"

    def guard(
        self, coin: str, position: core.VenuePosition, market: core.MarketInfo
    ) -> None:
        d = position.direction
        trade = self.book.open_trades.get(coin)
        owned = coin in self.owned_positions()
        if owned and trade is not None and trade.direction == d:
            desired = trade.stop_px
            dist = abs(position.entry_px - trade.stop_px) or trade.stop_dist
            source = "rule_stop"
        else:
            dist, source = self.guard_distance(coin, position)
            desired = position.entry_px - d * dist
        for _attempt in range(2):
            if self.guard_tries[coin] >= GUARD_MAX_TRIES:
                break
            self.guard_tries[coin] += 1
            mark = self.mid_now(coin) if self.in_sweep_window() else self.mids.get(coin)
            px = core.guard_stop_px(position, mark, desired, dist, market.sz_decimals)
            if px is None:
                break
            result = self.place_stop(
                f"{core.GUARD_TRADE_PREFIX}{coin}",
                position,
                px,
                role="guard",
                context={
                    "d": d,
                    "dist": dist,
                    "source": source,
                    "mark": mark,
                    "entry_px": position.entry_px,
                    "owned": owned,
                },
            )
            if result.resting:
                self.problem(
                    "position_guarded",
                    coin,
                    "protected by a guard stop; never traded down",
                    severity=NOTICE,
                )
                return
        self.problem(
            "unprotected_position",
            coin,
            "no protective stop rests on this position",
        )

    def acked_plan_ok(self, coin: str) -> bool:
        """I6 holds for the owned trade on ``coin`` against the listed orders
        plus the stops this session saw acked resting and has not sent a
        cancel for (acked_stops): the only gap, if any, is an order listing
        that lags them (a node behind a stop placed seconds earlier). Local
        state only."""
        trade = self.book.open_trades.get(coin)
        position = self.positions.get(coin)
        if trade is None or position is None or position.direction != trade.direction:
            return False
        listed = self.owned_orders(coin)
        cloids = {order.cloid for order in listed if order.cloid}
        acked = [
            order
            for cloid, order in self.acked_stops.items()
            if order.coin == coin and cloid not in cloids
        ]
        plan = core.plan_protection(
            self.proven_position(trade, position)[0],
            trade.stop_px,
            [*listed, *acked],
            self.mids.get(coin),
            self.market(coin),
        )
        return plan.action == "ok"

    def proven_sizes(self) -> dict[str, float]:
        """The size each owned trade's stop must cover now (proven_position)."""
        sizes: dict[str, float] = {}
        for coin, position in self.owned_positions().items():
            trade = self.book.open_trades.get(coin)
            if trade is not None:
                sizes[coin] = self.proven_position(trade, position)[0].size
        return sizes

    def stops_short(self, swept: Mapping[str, float]) -> bool:
        """P7, after its second reads: an owned trade whose size to cover
        (proven_position) grew past ``swept``, its size when the sweep
        protected it (0 if the first final read hid the coin), and that no
        listed stop nor any stop this session saw acked resting (acked_stops)
        covers: the second position read showed a fill the first missed, or
        the second order read listed a stop child that raised the proof of
        fills. P7 sweeps once more so protect() stops it in full, instead of
        the final check failing I6 and closing it as unprotectable. A stop
        the order listing merely lags is not short (the final check re-reads
        the listing for it), so no duplicate is placed for it."""
        for coin, position in self.owned_positions().items():
            trade = self.book.open_trades.get(coin)
            market = self.markets.get(coin)
            if trade is None or market is None:
                continue
            proven = self.proven_position(trade, position)[0]
            half_lot = 0.5 * 10.0**-market.sz_decimals
            if proven.size <= swept.get(coin, 0.0) + half_lot:
                continue
            listed = self.owned_orders(coin)
            acked = [order for order in self.acked_stops.values() if order.coin == coin]
            if not core.stop_covers(proven, [*listed, *acked], market.sz_decimals):
                return True
        return False

    def unguarded(self) -> list[str]:
        """Positions the reads show without a covering reduce-only stop that
        unverified_stops does not already judge (it covers owned positions)."""
        owned = self.owned_positions()
        bare: list[str] = []
        for coin, position in sorted(self.positions.items()):
            if coin in owned:
                continue
            market = self.markets.get(coin)
            szd = market.sz_decimals if market else 8
            if not core.stop_covers(position, self.orders, szd):
                bare.append(coin)
        return bare

    def protect_coin(
        self, coin: str, position: core.VenuePosition, *, first: bool
    ) -> None:
        opened_before = coin in self.book.open_trades
        trade = self.ensure_trade(coin, position)
        if trade is None:
            return
        if self.check_leverage(trade, position):
            return
        position = self.positions.get(coin, position)
        if coin not in self.positions:
            return
        if (
            first
            and opened_before
            and not any(order.is_trigger for order in self.owned_orders(coin))
        ):
            # An opened trade whose position has no stop at all: the sleeve's
            # stop was cancelled outside the sleeve or dropped by the venue,
            # or an earlier run opened it and hit its deadline (the quiet
            # window) before the stop rested. (A trade recovered just now, in
            # ensure_trade, was already flagged by the run that lost it.)
            self.problem(
                "stop_missing",
                coin,
                "the sleeve's stop is no longer listed; re-placing"
                if self.book.stop_oids.get(trade.trade_id)
                else "the trade opened without a stop; placing it first",
            )
        self.protect(trade, position)  # the stop first; then the local alert
        current = self.positions.get(coin)
        still_open = self.book.open_trades.get(coin)
        if (
            current is None
            or still_open is None
            or still_open.trade_id != trade.trade_id
        ):
            return  # protect() closed it (breach, unprotectable): nothing grew
        self.check_growth(trade, self.proven_position(trade, current)[0])

    def p4_shadow(self) -> None:
        try:
            events = read_shadow(self.paths.shadow_ledger, self.cfg, self.sleep)
            self.view = core.build_shadow_view(events, self.now(), self.cfg)
        except core.ShadowUnavailable as exc:
            self.shadow_state = "unavailable"
            self.problem("shadow_unavailable", message=str(exc))
            return
        except core.ShadowConfigMismatch as exc:
            self.shadow_state = "invalid"
            self.problem("shadow_config_mismatch", message=str(exc))
            return
        except (core.ShadowViewError, runner.LedgerError) as exc:
            self.shadow_state = "invalid"
            self.problem("shadow_ledger_invalid", message=str(exc))
            return
        view = self.view
        self.shadow_state = view.state
        if not view.fresh:
            midnight = datetime(
                view.today.year, view.today.month, view.today.day, tzinfo=UTC
            )
            now = self.now()
            if now >= midnight + timedelta(
                hours=self.cfg.shadow_stale_critical_hour_utc
            ):
                self.problem(
                    "shadow_stale", message=str(view.mark_date), severity=CRITICAL
                )
            elif now >= midnight + timedelta(
                hours=self.cfg.shadow_stale_notice_hour_utc
            ):
                self.problem(
                    "shadow_stale", message=str(view.mark_date), severity=NOTICE
                )
        self.census_notice()

    def census_notice(self) -> None:
        now = self.now()
        if now.day < 24:
            return
        threshold = now.replace(day=24, hour=0, minute=0, second=0, microsecond=0)
        try:
            mtime = datetime.fromtimestamp(self.paths.census.stat().st_mtime, UTC)
        except OSError:
            self.problem("census_refresh_due", message="census file missing")
            return
        if mtime < threshold:
            self.problem("census_refresh_due", message="refresh the census this week")

    def p5_exits(self) -> None:
        view = self.view
        if view is None:
            return
        self.set_phase("exit")
        closed_ids = {item[0].trade_id for item in self.closed_this_run}
        acted = False
        for coin, trade in list(self.book.open_trades.items()):
            position = self.positions.get(coin)
            if trade.trade_id in closed_ids or position is None:
                continue
            if position.direction != trade.direction:
                continue
            decision = core.plan_exit(trade.trade_id, view)
            if decision.action == "hold":
                continue
            if decision.action == "unknown":
                self.problem(
                    "trade_unknown_to_shadow", trade.trade_id, "held and protected"
                )
                continue
            if not self.can_mutate():
                break
            if decision.reason == "shadow_stop":
                self.problem(
                    "shadow_stop_parity_close", coin, "virtual stop hit on Binance"
                )
            acted = True
            self.close_position(coin, str(decision.reason), decision=decision)
        if acted:
            self.refresh_account()

    def check_clock(self) -> None:
        skew = self.reader.clock_skew_s
        if skew is not None and abs(skew) > CLOCK_SKEW_LIMIT_S:
            self.problem(
                "clock_skew",
                message=f"host clock is {skew:+.1f} s from the venue: keep NTP on",
            )

    def entries_blocked(self) -> bool:
        """Halted entries are not skipped: nothing is journaled, the next run retries."""
        if self.entries_halted is None:
            return False
        self.problem("entries_halted", message=self.entries_halted, severity=NOTICE)
        return True

    def p6_entries(self) -> None:
        view = self.view
        if view is None or not view.entries_today:
            return
        if not self.in_trade_window():
            return
        self.check_clock()
        if self.entries_blocked():
            return
        self.set_phase("entry", new_risk=True)
        window_end = datetime(
            view.today.year, view.today.month, view.today.day, tzinfo=UTC
        ) + timedelta(hours=self.cfg.entry_window_hours)
        unresolved_ids = {r.trade_id for r in self.book.unresolved.values()} | {
            r.trade_id for r in self.book.intents.values() if r.unverified
        }  # an unsettled position_unverified attempt waits like an ambiguous one
        for entry in view.entries_today:
            if self.entries_blocked():
                return
            tid = entry.trade_id
            if (
                tid in self.book.opened_ids
                or tid in self.book.terminal_skips
                or tid in unresolved_ids
                or self.book.entry_filled(tid)
            ):
                continue
            if self.now() > window_end:
                self.skip(entry, "window_expired")
                self.problem("entry_missed", tid, "window_expired")
                continue
            if not self.stop_present and self.paths.stop_file.exists():
                self.stop_present = True  # STOP touched mid-run applies at once
                self.set_phase("entry", new_risk=True)
            if self.stop_present:
                self.skip(entry, "stop_file")
                continue
            if not core.tradeable(self.markets, entry.coin):
                self.skip(entry, "coin_not_tradeable")
                continue
            blocked = self.blocked_coins.get(entry.coin)
            if blocked == "unowned":
                self.skip(entry, "coin_held_unowned")
                self.problem("coin_held_unowned", entry.coin, tid)
                continue
            if blocked is not None:  # direction conflict, canary residue, ambiguity
                self.skip(entry, "coin_not_flat")
                continue
            if (
                entry.coin in self.positions
                or entry.coin in self.book.open_trades
                or entry.coin in self.book.unresolved_coins()
            ):
                self.skip(entry, "coin_not_flat")
                continue
            if self.book.attempts.get((tid, "entry"), 0) >= self.cfg.entry_max_attempts:
                self.skip(entry, "attempts_exhausted")
                self.problem("entry_missed", tid, "attempts_exhausted")
                continue
            if not self.in_trade_window() or not self.pacer.reserve_ok():
                return
            if self.account_stale:
                self.refresh_account()
            if self.book_equity is None:
                return
            self.enter(entry)

    def skip(
        self,
        entry: core.VirtualEntry,
        reason: str,
        *,
        shortfall: float | None = None,
    ) -> None:
        retryable = reason not in core.TERMINAL_SKIPS
        self.counts["skips"] += 1
        if retryable and self.book.last_skip.get(entry.trade_id) == reason:
            return
        payload: dict[str, Any] = {
            "trade_id": entry.trade_id,
            "coin": entry.coin,
            "reason": reason,
            "retryable": retryable,
        }
        if shortfall is not None:
            payload["collateral_shortfall_usd"] = shortfall
        self.journal.append("skip", payload)
        self.plan("skip", trade_id=entry.trade_id, coin=entry.coin, reason=reason)

    @staticmethod
    def shows_fill(
        position: core.VenuePosition | None, direction: int, acked: float
    ) -> bool:
        """The coin was flat before the entry, so the position holds every fill."""
        return (
            position is not None
            and position.direction == direction
            and position.size >= acked * (1 - 1e-9)
        )

    def enter(self, entry: core.VirtualEntry) -> None:
        coin, tid, d = entry.coin, entry.trade_id, entry.direction
        market = self.market(coin)
        assert self.sub_value is not None and self.book_equity is not None
        self.pacer.make_room(ENTRY_PROTECT_WEIGHT)
        mid = self.mid_now(coin)
        if mid is None:
            self.skip(entry, "no_mid")
            return
        sizing = core.size_entry(
            entry,
            mid,
            market,
            self.book_equity,
            self.gross_used(),
            len(self.positions),
            self.sub_free,
            self.sub_value.equity_usd,
            self.cfg,
        )
        if not sizing.take:
            reason = str(sizing.reason)
            self.skip(entry, reason, shortfall=sizing.collateral_shortfall_usd)
            if sizing.critical:
                self.problem(reason, tid, f"ratio={sizing.ratio}")
            if reason == "sub_collateral":
                self.problem(
                    "collateral_shortfall_usd",
                    tid,
                    f"{sizing.collateral_shortfall_usd:.2f}",
                )
            return
        if sizing.scaled:
            self.problem(
                "scaled_by_cap", tid, f"{sizing.room:.2f} of {sizing.want:.2f}"
            )
        if not self.set_leverage(coin, sizing.leverage, tid):
            self.skip(entry, "leverage_failed")
            return
        context = {
            "d": d,
            "atr_signal": entry.atr_signal,
            "unit": sizing.unit,
            "stop_dist": sizing.stop_dist,
            "L": sizing.leverage,
            "risk_usd": sizing.risk_usd,
            "book_equity": self.book_equity,
            "signal_date": entry.signal_date,
            "entry_date": entry.entry_date,
            "virtual": {
                "entry_px": entry.entry_px,
                "stop_px": entry.stop_px,
                "priority_rank": entry.priority_rank,
                "taken": entry.taken,
            },
        }
        want_sz = sizing.sz
        attempts = self.book.attempts.get((tid, "entry"), 0)
        sends = 0
        ambiguous = False
        acked = 0.0  # size the venue said filled (acks or resolved statuses)
        acked_value = 0.0  # its notional at the acked prices (the mid if none)
        lagging: str | None = None  # an attempt its status missed but the book shows
        last_cloid: str | None = None
        try:
            while sends < 2 and attempts < self.cfg.entry_max_attempts:
                if not self.can_mutate():
                    break
                if sends and not self.dry and acked == 0 and last_cloid is not None:
                    # Before ANY retry after an attempt with no acked fill
                    # (no_fill, never_landed, canceled): the coin was flat before
                    # the entry, so a position now means that attempt DID fill and
                    # an orderStatus node (or the ack) lagged it. Never send a
                    # second full-size IOC on top of it.
                    held = self.reread_before_retry(coin, last_cloid)
                    if held is not None:
                        if held.direction != d:
                            self.problem(
                                "unknown_position",
                                coin,
                                "opposite position during entry",
                            )
                            self.blocked_coins[coin] = "unowned"
                            return
                        # That read IS the proof of the fill: journal it for the
                        # attempt now (pending_opens owns it, so P7 or the next
                        # run's P3 protects it even if this run fails before its
                        # stop) and adopt the position it showed. No second read
                        # is trusted over it: another node may still lag the fill.
                        self._order_outcome(
                            last_cloid,
                            "filled",
                            oid=self.known_oid(last_cloid),
                            filled_sz=held.size,
                            venue_status="position_reread",
                        )
                        lagging = last_cloid
                        break
                if sends:
                    self.pacer.make_room(ENTRY_PROTECT_WEIGHT)
                    mid = self.mid_now(coin) or mid
                # A1: the IOC carries its own stop, the rule distance from
                # the reference mid its limit comes from; the venue places it
                # on a full fill even if this reply is lost and every read
                # lags. The trade's stop stays anchored to the venue fill:
                # protect() re-anchors (place, then cancel this child) once a
                # read shows the position, unless the two prices agree.
                result, _child = self.send_entry(
                    trade_id=tid,
                    role="entry",
                    stop_role="stop",
                    coin=coin,
                    is_buy=d > 0,
                    sz=want_sz,
                    limit_px=core.ioc_limit(
                        mid, d > 0, self.cfg.entry_slippage_bps, market.sz_decimals
                    ),
                    stop_px=core.normalize_price(
                        mid - d * sizing.stop_dist, market.sz_decimals
                    ),
                    n=attempts + 1,
                    context={**context, "mid": mid, "sizing_sz": sizing.sz},
                )
                # Only a journaled intent uses an attempt (a local refusal does not).
                attempts = self.book.attempts.get((tid, "entry"), 0)
                sends += 1
                last_cloid = result.cloid if result.cloid in self.book.intents else None
                if self.dry and result.filled_sz > 0:
                    self.apply_dry_fill(
                        coin,
                        d > 0,
                        result.filled_sz,
                        result.avg_px or mid,
                        sizing.leverage,
                    )
                if result.status in ("filled", "partial"):
                    acked += result.filled_sz
                    acked_value += result.filled_sz * (result.avg_px or mid)
                if result.status == "ambiguous":
                    ambiguous = True
                    break
                if result.status == "filled":
                    break
                if result.status == "partial":
                    remainder = core.size_remainder(
                        want_sz, result.filled_sz, market.sz_decimals
                    )
                    if remainder * mid < self.cfg.min_order_usd:
                        break
                    want_sz = remainder
                    continue
                if result.status in ("no_fill", "never_landed", "canceled"):
                    continue
                break
            if lagging is None:
                self.refresh_positions()
            # else: self.positions is the re-read that showed the lagging fill.
        except Exception as exc:
            # Any failure from the first send to the first read after the
            # loop (a re-read before a retry, a mid read, that read, the
            # quiet window, the budget): an attempt of this trade that said
            # never_landed in this session may have filled unseen (the H1
            # lag) and the reads that would show it were cut short. Mark
            # EVERY such attempt, not only the last one.
            self.mark_unverified(tid)
            if acked > 0 and not self.dry and not isinstance(exc, core.RefusalError):
                # The acks prove a fill no read of this entry showed: stop it
                # from the acks now (a reduce-only stop is exempt from the
                # quiet window and the phase deadline), unless a stop already
                # covers it (a full fill's child does). Never masks ``exc``.
                try:
                    self.protect_acked(
                        tid, coin, d, acked, acked_value / acked, sizing, market
                    )
                except Exception:  # never mask the original failure
                    pass
            raise
        position = self.positions.get(coin)
        if not self.dry and acked > 0 and not self.shows_fill(position, d, acked):
            # The info node may lag the fill ack: read once more before the
            # stop is sized, and never size the next entry on a book that
            # misses this fill.
            self.sleep(REREAD_DELAY_S)
            self.refresh_positions()
            position = self.positions.get(coin)
            if position is None or position.direction != d:
                self.blocked_coins[coin] = "fill_not_visible"
                # P7 (or the next run) opens the trade from the first read that
                # shows it; if that read shows less than the acks, the run is
                # critical (check_acked_entries). If it opens nothing,
                # check_entry_intents raises fill_not_visible at run end.
                self.acked_unseen[tid] = (coin, acked)
                if self.never_landed_attempt(tid):
                    # These reads lag an acked fill, so the flat re-read that
                    # allowed the retry (or the status of the never_landed
                    # attempt) proves nothing: that attempt may have filled
                    # too, and a later read that shows only one of the fills
                    # opens the trade at it (known limit a). Critical now.
                    self.problem(
                        "fill_not_visible",
                        coin,
                        "the reads at open miss an acked entry fill and an "
                        "attempt of this entry said never_landed: it may have "
                        "filled unseen",
                    )
                else:
                    self.halt_entries(f"fill_not_visible:{coin}")
                if not self.dry:
                    self.protect_acked(
                        tid, coin, d, acked, acked_value / acked, sizing, market
                    )
                return
            if not self.shows_fill(position, d, acked):
                # The acks prove more than the read shows (a node between two
                # fills): the trade opens, and its stop is sized, at the read
                # size. P7's reads must show the acked size, or the run is
                # critical (check_acked_entries); the next read that shows it
                # re-sizes the stop.
                self.acked_unseen[tid] = (coin, acked)
        if ambiguous and (position is None or position.direction != d):
            self.blocked_coins[coin] = "ambiguous_entry"
            self.halt_entries(f"ambiguous_entry:{coin}")
            return
        if position is None or position.direction != d:
            if attempts >= self.cfg.entry_max_attempts:
                self.skip(entry, "attempts_exhausted")
                self.problem("entry_missed", tid, "attempts_exhausted")
            return
        if lagging is not None:  # raised first: it stands even if the open fails
            self.problem(
                "order_status_lag",
                coin,
                "the position showed a fill its entry's status had missed; adopted",
                severity=NOTICE,
            )
        self.open_trade(entry, sizing, position, mid, market)
        if lagging is not None:
            self.requery_status(lagging)

    def protect_acked(
        self,
        trade_id: str,
        coin: str,
        d: int,
        acked: float,
        avg_px: float,
        sizing: core.EntrySizing,
        market: core.MarketInfo,
    ) -> None:
        """No read shows an entry the venue acked (an info node lags every
        read): stop it from the fill as acked. A reduce-only stop for the
        acked size at the rule distance from the acked average price, unless
        a stop already covers it (the child of one full fill does). If the
        fill is somehow gone, a reduce-only stop is inert; the first read
        that shows the position re-anchors it to the venue entryPx."""
        acked_position = core.VenuePosition(
            coin=coin,
            szi=d * acked,
            entry_px=avg_px,
            position_value=acked * avg_px,
            liquidation_px=None,
            leverage_type="isolated",
            leverage_value=sizing.leverage,
            margin_used=0.0,
        )
        if core.stop_covers(
            acked_position, self.owned_orders(coin), market.sz_decimals
        ):
            return
        trigger = core.normalize_price(
            avg_px - d * sizing.stop_dist, market.sz_decimals
        )
        if trigger <= 0:
            return
        self.set_phase("protect")
        try:
            for _attempt in range(2):
                if self.place_stop(trade_id, acked_position, trigger).resting:
                    return
        finally:
            self.set_phase("entry", new_risk=True)

    def attempts_unproven(self, trade: core.OpenTrade) -> bool:
        """Run end: two or more entry attempts of the open ``trade`` in THIS
        session whose fill no ack or orderStatus attributes (they said
        never_landed, still or since marked position_unverified, or a
        position read adopted them: position_reread), and no read of the
        run showed every attempt filled (seen_sz below the attempts' summed
        size). The trade is open and the coin was flat before the entry, so
        at least one of those statuses was wrong and the other proves nothing
        either: it may have filled unseen, with no read, ack or listed child
        showing it (a doubled entry covered only by the sum of its stops)."""
        records = [
            record
            for record in self.book.intents.values()
            if record.trade_id == trade.trade_id
            and record.role == "entry"
            and not record.canary
            and record.order > self.session_order
        ]
        unattributed = [
            record
            for record in records
            if record.status == "never_landed"
            or record.unverified
            or (record.outcome or {}).get("venue_status") == "position_reread"
        ]
        if len(unattributed) < 2:
            return False
        market = self.markets.get(trade.coin)
        half_lot = 0.5 * 10.0 ** -(market.sz_decimals if market else 8)
        total = sum(record.sz for record in records)
        return self.seen_sz.get(trade.trade_id, 0.0) < total - half_lot

    def unsettled_entry_sz(self, trade_id: str) -> float:
        """The summed size of THIS session's entry attempts of ``trade_id``
        whose fill neither an ack nor an orderStatus settled: never_landed (a
        lost reply and an orderStatus that did not know it) or still
        ambiguous (its resolution would have passed the sweep deadline). Each
        may have filled in full unseen. (open_trade is its only caller: an
        attempt is marked position_unverified only on a failure that ends
        its entry before the trade opens.)"""
        return sum(
            record.sz
            for record in self.book.intents.values()
            if record.trade_id == trade_id
            and record.role == "entry"
            and not record.canary
            and record.order > self.session_order
            and (record.status == "never_landed" or not record.resolved)
        )

    def never_landed_attempt(self, trade_id: str) -> bool:
        """An entry attempt of ``trade_id`` in THIS session said never_landed
        (a lost POST response and an orderStatus that did not know it)."""
        return any(
            record.trade_id == trade_id
            and record.role == "entry"
            and record.order > self.session_order
            and record.status == "never_landed"
            for record in self.book.intents.values()
        )

    def known_oid(self, cloid: str) -> int | None:
        record = self.book.intents.get(cloid)
        oid = (record.outcome or {}).get("oid") if record is not None else None
        return int(oid) if oid is not None else None

    def reread_before_retry(self, coin: str, cloid: str) -> core.VenuePosition | None:
        """The sub position on ``coin`` REREAD_DELAY_S after an entry attempt
        (``cloid``) with no acked fill, before its retry.

        If that read fails, enter() marks every never_landed attempt of the
        trade position_unverified (mark_unverified) before the error goes on.
        """
        self.sleep(REREAD_DELAY_S)
        self.refresh_positions()
        return self.positions.get(coin)

    def mark_unverified(
        self, trade_id: str | None = None, why: str = "reread_failed"
    ) -> None:
        """Entry attempts of THIS session that said never_landed (possibly a
        lagging orderStatus node) and that no read of a LATER session has
        proven flat: they may have filled unseen. Journal each one
        position_unverified (a local write) so it owns a same-direction
        position on its coin (pending_opens): P7 or the next run's P3 adopts
        and protects it, and a later session's read settles it
        (settle_unverified_entries).

        ``trade_id``: one trade, after a failure during its entry (enter()).
        None: every trade not opened, at the end of P7 or when a run loses
        P7 (flag_unprotected). Only a coin the local reads show held on the
        OTHER side from the attempt (unknown_position), or that the entry saw
        held on the other side (blocked unowned), is skipped: that position
        is not the sleeve's to own. A coin shown held on the attempt's own
        side is marked: that may be the attempt's own fill (a later entry's
        read or P7's first read showed it, then the run lost P7 before
        adopt_lagging_entries), and the mark is what owns it.

        The other side is not skipped when it is a side THIS session closed
        on that coin (a same-run reversal: P5 closed the long, P6 entered
        short): a read from a node that lags the close still shows the
        sleeve's own closed position there, which proves nothing about the
        attempt's fill. Ownership stays direction-filtered (owned_positions,
        classify), so the mark never owns a position on the other side.
        ``why`` is journaled as the mark's venue_status."""
        unowned = {
            coin for coin, reason in self.blocked_coins.items() if reason == "unowned"
        }
        closed_sides = {(t.coin, t.direction) for t, _, _ in self.closed_this_run}
        for record in sorted(self.book.intents.values(), key=lambda r: r.order):
            if trade_id is not None:
                in_scope = record.trade_id == trade_id
            else:
                d = int(record.context.get("d", 0))
                shown = self.positions.get(record.coin)
                other_side = (
                    shown is not None
                    and shown.direction != d
                    and (record.coin, shown.direction) not in closed_sides
                )
                seen_unowned = (
                    record.coin in unowned and (record.coin, -d) not in closed_sides
                )
                in_scope = not other_side and not seen_unowned
            if (
                in_scope
                and record.role == "entry"
                and not record.canary
                and record.order > self.session_order
                and record.status == "never_landed"
                and record.trade_id not in self.book.opened_ids
                and record.trade_id not in self.book.closed_ids
            ):
                self._order_outcome(
                    record.cloid,
                    core.POSITION_UNVERIFIED,
                    venue_status=why,
                )

    def settle_unverified_entries(self) -> None:
        """P2: an entry left position_unverified by an EARLIER session at least
        UNVERIFIED_SETTLE_AFTER ago, whose coin this session's P1 read shows
        flat, never filled (an info node lags by seconds, not minutes): settle
        it as never_landed, so it cannot own a later position on that coin.
        Not while the P1 order read lists a stop child of that trade (A1: the
        child exists only if the entry filled). Local journal writes only."""
        if self.dry:
            return
        now = self.now()
        # A listed stop child proves its entry filled (the venue places it
        # only on a full fill): the flat read lags, so the mark stands.
        filled_children = set()
        for order in self.orders:
            child = self.book.intents.get(order.cloid or "")
            if child is not None and child.context.get("child_of"):
                filled_children.add(child.trade_id)
        for record in list(self.book.intents.values()):
            if not record.unverified or record.order > self.session_order:
                continue
            if record.trade_id in filled_children:
                continue
            try:
                marked = datetime.fromisoformat(
                    str((record.outcome or {}).get("recorded_at"))
                )
            except ValueError:
                continue  # keep owning it; unresolved_entry stays critical
            if (
                now - marked >= UNVERIFIED_SETTLE_AFTER
                and record.coin not in self.positions
                and record.trade_id not in self.book.opened_ids
            ):
                self._order_outcome(
                    record.cloid,
                    "never_landed",
                    venue_status="position_flat",
                )

    def requery_status(self, cloid: str) -> None:
        """Best effort, after the position is protected: ask orderStatus again
        for an entry the book showed filled, and journal a fill answer if it
        adds to what the journal holds (so the fill's oid and fees join the
        trade). An answer that the order did not fill is not journaled: the
        position read already proved the fill."""
        record = self.book.intents.get(cloid)
        if record is None or self.dry:
            return
        try:
            queried = core.parse_order_status(
                self.reader.order_status(self.env.sub, cloid)
            )
        except TechnicalError:  # includes the quiet window and the budget
            return
        if queried.status not in ("filled", "partial"):
            return
        if queried.status != record.status or queried.oid != self.known_oid(cloid):
            self._order_outcome(
                cloid,
                queried.status,
                oid=queried.oid,
                filled_sz=queried.filled_sz,
                venue_status=queried.venue_status,
            )

    def open_trade(
        self,
        entry: core.VirtualEntry,
        sizing: core.EntrySizing,
        position: core.VenuePosition,
        mid: float,
        market: core.MarketInfo,
    ) -> None:
        d = entry.direction
        stop_px = core.normalize_price(
            position.entry_px - d * sizing.stop_dist, market.sz_decimals
        )
        midnight = datetime(
            self.today.year, self.today.month, self.today.day, tzinfo=UTC
        )
        liq = position.liquidation_px
        fill_fraction = position.size / sizing.sz if sizing.sz else None
        self.journal.append(
            "trade_opened",
            {
                "trade_id": entry.trade_id,
                "coin": entry.coin,
                "direction": d,
                "side": "long" if d > 0 else "short",
                "label": "trend" if d > 0 else "hedge",
                "signal_date": entry.signal_date,
                "entry_date": entry.entry_date,
                "sz": position.size,
                "entry_px": position.entry_px,
                "notional": position.size * position.entry_px,
                "leverage": sizing.leverage,
                "census_max_leverage": entry.max_leverage,
                "venue_max_leverage": market.max_leverage,
                "stop_px": stop_px,
                "stop_dist": sizing.stop_dist,
                "stop_fraction": sizing.stop_fraction,
                "risk_usd": sizing.risk_usd,
                "actual_risk_usd": position.size * sizing.stop_dist,
                "book_equity": self.book_equity,
                "liq_px": liq,
                "liq_buffer_stops": (
                    abs(position.entry_px - liq) / sizing.stop_dist
                    if liq is not None and sizing.stop_dist
                    else None
                ),
                "binance_open": entry.entry_px,
                "basis_bps": (position.entry_px / (entry.entry_px * sizing.unit) - 1)
                * 1e4,
                "slippage_bps_vs_mid": d * (position.entry_px / mid - 1) * 1e4,
                "delay_s_from_open": (self.now() - midnight).total_seconds(),
                "fill_fraction": fill_fraction,
                "scaled": sizing.scaled,
                "recovered": False,
                "opened_ms": core.now_ms(self.now()),
                "virtual": {
                    "taken": entry.taken,
                    "stop_px": entry.stop_px,
                    "priority_rank": entry.priority_rank,
                },
            },
        )
        self.note_seen()  # the read the trade opened at (fill_proof)
        self.opened_this_run.append(entry.trade_id)
        self.counts["entries"] += 1
        self.sub_free -= position.size * position.entry_px / max(1, sizing.leverage)
        if fill_fraction is not None and fill_fraction < 1 - 1e-9:
            self.problem("partial_fill", entry.trade_id, f"{fill_fraction:.3f}")
        self.check_overfill(entry.coin, position.size, sizing.sz)
        trade = self.book.open_trades[entry.coin]
        # Dust is decided on the most this session can prove the entry filled
        # (fill_proof: acks, children, the reads), never on the read alone: a
        # node that lags a remainder's fill shows only the first attempt's
        # dust partial. And never while an attempt's fill is unsettled (its
        # reply lost, its orderStatus lagging): it may have filled in full.
        # Then the stop covers what the attempts could have filled
        # (cover_floor, for the session: a reduce-only stop is inert beyond
        # the position), and nothing is sold.
        dust_sz = max(position.size, self.fill_proof(entry.trade_id, entry.coin))
        dust = dust_sz * min(position.entry_px, stop_px) < self.cfg.min_order_usd
        unsettled = self.unsettled_entry_sz(entry.trade_id)
        if dust and unsettled > 0:
            self.cover_floor[entry.trade_id] = dust_sz + unsettled
            dust = False
        self.set_phase("protect")
        try:
            if dust:
                if self.close_position(entry.coin, "dust_fill", cap=dust_sz):
                    return
                self.problem("dust_open", entry.coin, "the dust close did not complete")
                latest = self.positions.get(entry.coin)
                if latest is not None and latest.direction == d:
                    position = latest  # a read that showed more than the dust
            if not self.protect(trade, position):
                return
            if entry.coin in self.positions:
                self.check_leverage(trade, self.positions[entry.coin])
        finally:
            self.set_phase("entry", new_risk=True)

    def p7_final(self) -> None:
        self.set_phase("final")
        if not self.in_sweep_window():
            self.problem(
                "sweep_deadline", message="final sweep skipped at its deadline"
            )
            self.flag_unprotected()
            return
        # An order sent late in the run (an entry near :45, a stop, an exit)
        # may still land inside its expiry: resolve it before the final reads,
        # so a fill it made is adopted and protected in this run.
        self.resolve_unresolved()
        self.refresh_positions()
        self.refresh_orders()
        self.adopt_lagging_entries()
        self.sweep()
        self.set_phase("final")
        swept = self.proven_sizes()
        self.refresh_positions()
        self.refresh_orders()
        self.adopt_lagging_entries()
        if (
            any(coin not in self.book.open_trades for coin in self.owned_positions())
            or self.unguarded()
            or self.stops_short(swept)
        ):
            # An owned fill the first final read missed (adopted just now, or
            # owned by an unresolved or unverified entry), or a position no
            # stop covers (A2: one the first final read missed, or whose guard
            # is not listed; GUARD_MAX_TRIES bounds its placements), or a
            # trade whose position or proof of fills grew past its stops since
            # the sweep (a fill or a stop child the first final reads missed):
            # protect it in this run (the sweep leaves covered coins alone),
            # then re-read orders.
            self.sweep()
            self.set_phase("final")
            self.refresh_orders()
        self.protect_unseen_proofs()
        failing = self.unverified_stops()
        bare = self.unguarded()
        if (failing or bare) and not self.dry:
            # One more read before closing anything, REREAD_DELAY_S after the
            # last one (as every other re-read): the info node may lag the ack
            # of a stop placed a moment ago.
            self.sleep(REREAD_DELAY_S)
            self.refresh_orders()
            failing = self.unverified_stops()
            bare = self.unguarded()
        tries = 0
        while (
            not self.dry
            and tries < LISTING_REREAD_TRIES
            and any(self.acked_plan_ok(coin) for coin in failing)
            and self.pacer.reserve_ok()
        ):
            # A failing trade that a stop this session saw acked resting would
            # verify (acked_plan_ok): the order listing lags it (a node a few
            # seconds behind a stop placed moments ago). Re-read the listing,
            # further apart, before closing the position that stop protects;
            # the sweep window and the sweep reserve bound the waits. A stop
            # an earlier run placed that the listing no longer shows is gone,
            # not lagging (a node behind would still list it): no wait.
            tries += 1
            self.sleep(LISTING_REREAD_BACKOFF_S)
            if not self.in_sweep_window():
                break
            self.refresh_orders()
            failing = self.unverified_stops()
            bare = self.unguarded()
        for coin in bare:  # A2: its guard stop is not listed (the next P3 retries)
            self.problem(
                "unprotected_position",
                coin,
                "a position the sleeve does not own has no listed protective stop",
            )
        for coin in failing:
            trade = self.book.open_trades.get(coin)
            if trade is None:
                self.problem("unprotected_position", coin, "no journal trade")
                continue
            self.problem("unprotectable", coin, "no verified stop after repair")
            try:
                if self.in_sweep_window():
                    self.close_position(coin, "unprotectable")
            except NotSentError:
                raise
            except TechnicalError as exc:
                self.problem("technical_failure", coin, str(exc))
            except Exception as exc:  # the TYPE only: a message may hold a secret
                self.problem("technical_failure", coin, type(exc).__name__)
            if coin in self.positions:
                self.problem(
                    "unprotected_position", coin, "open without a verified stop"
                )
        self.check_caps()
        self.check_acked_entries("the final reads show less than the acked entry fills")
        # An attempt of this session that said never_landed, whose trade did
        # not open and whose coin the final reads show flat (a same-side
        # position they showed was adopted above; a coin held on the other
        # side is skipped, unless this session closed that side there):
        # every read of the run may have come from the same lagging node
        # (the H1 fault), so a flat read proves nothing.
        # Mark it: unresolved_entry is raised now,
        # and the next run's P3 adopts and protects a same-direction position
        # on its coin, or its first read settles the mark (flat, >= 10 min).
        if not self.dry:
            self.mark_unverified(why="flat_in_run")

    def protect_unseen_proofs(self) -> None:
        """P7, after the final reads and any re-sweep: an open trade with an
        entry attempt in THIS session whose final reads show no position on
        its side (flat, or only the other side: a node behind its fills, or
        behind a close this session made on that coin) while this session's
        proof of its fills (fill_proof: acks, children, the largest size a
        read of the run showed) is more than any one stop on the coin covers
        (listed, or acked resting and not cancelled) gets one reduce-only
        stop for the proof at the trade's stop.

        The sweep protects only the positions the reads show, so without it a
        fill an earlier read of the run showed (another coin's entry read)
        would end the run under the smaller stop the trade opened with. On a
        truly flat coin the stop is inert; check_acked_entries raises the run
        critical (fill_not_visible) either way. A failure on one coin is
        recorded for that coin and the rest go on (as in the sweep). A dry
        run's entries are its reads (apply_dry_fill), so it never gets here
        with a proof; its gateway would only plan the stop."""
        for coin, trade in sorted(self.book.open_trades.items()):
            shown = self.positions.get(coin)
            if shown is not None and shown.direction == trade.direction:
                continue  # the sweep protected it (proven_position)
            market = self.markets.get(coin)
            proof = self.fill_proof(trade.trade_id, coin)
            if market is None or proof <= 0:
                continue
            proven = core.VenuePosition(
                coin=coin,
                szi=trade.direction * proof,
                entry_px=trade.entry_px,
                position_value=proof * trade.entry_px,
                liquidation_px=None,
                leverage_type="isolated",
                leverage_value=trade.leverage,
                margin_used=0.0,
            )
            acked = [order for order in self.acked_stops.values() if order.coin == coin]
            if core.stop_covers(
                proven, [*self.owned_orders(coin), *acked], market.sz_decimals
            ):
                continue
            trigger = core.normalize_price(trade.stop_px, market.sz_decimals)
            if trigger <= 0:
                continue
            try:
                for _attempt in range(2):
                    if self.place_stop(trade.trade_id, proven, trigger).resting:
                        break
                else:
                    self.problem(
                        "stop_missing",
                        coin,
                        "the stop for fills the final reads miss did not rest; "
                        "the next run places it first",
                    )
            except NotSentError:
                raise
            except TechnicalError as exc:
                self.problem("technical_failure", coin, str(exc))
            except Exception as exc:  # the TYPE only: a message may hold a secret
                self.problem("technical_failure", coin, type(exc).__name__)

    def lagging_entry(self, coin: str, direction: int) -> core.IntentRecord | None:
        """The latest entry attempt of THIS session on ``coin``, in
        ``direction``, that said never_landed, for a trade not opened."""
        found = [
            record
            for record in self.book.intents.values()
            if record.role == "entry"
            and not record.canary
            and record.coin == coin
            and record.order > self.session_order
            and record.status == "never_landed"
            and record.trade_id not in self.book.opened_ids
            and record.trade_id not in self.book.closed_ids
            and int(record.context.get("d", 0)) == direction
        ]
        return max(found, key=lambda r: r.order) if found else None

    def adopt_lagging_entries(self) -> None:
        """P7, after each final position read: the H1 re-read rule applied to
        the final reads.

        A same-direction position on a coin whose entry attempt in THIS
        session said never_landed is that attempt's fill: the coin was flat
        before the entry, and a lagging info node answered both its
        orderStatus and the entry's own position reads. The fill is journaled
        for the attempt (filled, venue_status position_reread), so
        pending_opens owns it and the sweep protects it (ensure_trade checks
        it against the sized entry: a doubled position is entry_overfill).
        Any other position the sleeve does not own is critical
        unknown_position in this run, not first in the next run.
        """
        owned = self.owned_positions()
        residue = self.book.canary_residue()
        for coin, position in sorted(self.positions.items()):
            if coin in owned or coin in self.book.open_trades:
                continue  # owned, or its direction_conflict was raised in P2
            if coin in residue and position.direction > 0:
                continue  # its canary_residue was raised in P2
            record = None if self.dry else self.lagging_entry(coin, position.direction)
            if record is None:
                self.problem(
                    "unknown_position",
                    coin,
                    "position not placed by the sleeve (final check)",
                )
                continue
            self._order_outcome(
                record.cloid,
                "filled",
                oid=self.known_oid(record.cloid),
                filled_sz=position.size,
                venue_status="position_reread",
            )
            self.problem(
                "order_status_lag",
                coin,
                "the final read showed a fill its entry's status and reads had "
                "missed; adopted",
                severity=NOTICE,
            )

    def check_entry_intents(self) -> None:
        """Run end: no entry may be left unresolved, or filled but not adopted.

        Either one can mean a live position the sleeve has not protected.
        """
        for record in self.book.intents.values():
            if record.reduce_only:
                continue
            if not record.resolved:
                self.problem(
                    "unresolved_entry",
                    record.coin,
                    "an entry order may have filled; it has no verified stop",
                )
            elif (
                record.unverified
                and record.trade_id not in self.book.opened_ids
                and record.trade_id not in self.book.closed_ids
            ):
                self.problem(
                    "unresolved_entry",
                    record.coin,
                    "an entry said never_landed and no read of a later run has "
                    "shown its coin flat: it owns a same-direction position "
                    "there until one does",
                )
            elif (
                record.role == "entry"
                and record.filled
                and record.order > self.session_order
                and record.trade_id not in self.book.opened_ids
                and record.trade_id not in self.book.closed_ids
            ):
                self.problem(
                    "fill_not_visible",
                    record.coin,
                    "an acked entry fill is not in the position reads: no stop",
                )

    def unverified_stops(self) -> list[str]:
        """Owned positions without exactly one verified stop (I6); counts the rest."""
        self.counts["stops_ok"] = 0
        failing: list[str] = []
        for coin, position in self.owned_positions().items():
            trade = self.book.open_trades.get(coin)
            if trade is None:
                failing.append(coin)
                continue
            plan = core.plan_protection(
                self.proven_position(trade, position)[0],
                trade.stop_px,
                self.owned_orders(coin),
                self.mids.get(coin),
                self.market(coin),
            )
            if plan.action == "ok":
                self.counts["stops_ok"] += 1
            else:
                failing.append(coin)
        return failing

    def check_caps(self) -> None:
        """Slots and gross at run end.

        Entries enforce both caps over every sub position, so a breach at run
        end comes either from unowned exposure (critical) or from price moves
        on owned positions after entry, which move gross and book equity
        (a notice: nothing is sold to restore the ratio; SRS_HV1_NO_GATES).
        """
        slots = len(self.positions)
        unowned = slots - len(self.owned_positions())
        book = self.book_equity
        gross = self.gross_used()
        over_gross = book is not None and gross > self.cfg.gross_cap * book * (1 + 1e-9)
        detail = f"slots={slots} unowned={unowned} gross={gross:.2f}"
        if book is not None:
            detail += f" gross_to_book={gross / book:.3f}"
        if slots > self.cfg.max_slots or (over_gross and unowned):
            self.problem("slots_gross_violation", message=detail, severity=CRITICAL)
        elif over_gross:
            self.problem("gross_drift", message=detail, severity=NOTICE)

    def p8_report(self) -> None:
        view = self.view
        for trade, reason, _ in self.closed_this_run:
            if (
                reason == "venue_stop"
                and view is not None
                and trade.trade_id in view.open_ids
            ):
                self.problem("real_stopped_early", trade.coin, trade.trade_id)
        if self.dry or not self.closed_this_run:
            return
        try:
            start = min(item[0].opened_ms for item in self.closed_this_run) - 60_000
            end = core.now_ms(self.now())
            raw_fills = self.reader.user_fills_by_time(self.env.sub, max(0, start), end)
            raw_funding = self.reader.user_funding(self.env.sub, max(0, start), end)
            fills = core.parse_fills(raw_fills)
            funding = core.parse_funding(raw_funding)
        except TechnicalError as exc:
            self.problem("report_failed", message=str(exc), severity=NOTICE)
            return
        truncated = {
            "fills": bool(getattr(raw_fills, "truncated", False)),
            "funding": bool(getattr(raw_funding, "truncated", False)),
        }
        if any(truncated.values()):
            self.problem(
                "report_truncated",
                message=",".join(k for k, v in truncated.items() if v),
                severity=NOTICE,
            )
        for trade, reason, closed_ms in self.closed_this_run:
            mine = self.trade_fills(trade, fills)
            closing = [f for f in mine if f.is_buy == (trade.direction < 0)]
            closed_pnl = sum(f.closed_pnl for f in mine)
            fees = sum(f.fee for f in mine)
            paid = sum(
                d.usdc
                for d in funding
                if d.coin == trade.coin and trade.opened_ms <= d.time_ms <= closed_ms
            )
            traded = sum(f.px * f.sz for f in mine)
            net = closed_pnl - fees + paid
            size = sum(f.sz for f in closing)
            closed = view.closed_index.get(trade.trade_id) if view else None
            self.journal.append(
                "trade_report",
                {
                    "trade_id": trade.trade_id,
                    "coin": trade.coin,
                    "reason": reason,
                    "closed_pnl": closed_pnl,
                    "fees": fees,
                    "funding": paid,
                    "net_usd": net,
                    "net_r": net / trade.risk_usd if trade.risk_usd else None,
                    "actual_risk_usd": trade.actual_risk_usd or None,
                    "net_r_actual": (
                        net / trade.actual_risk_usd if trade.actual_risk_usd else None
                    ),
                    "truncated": truncated,
                    "avg_exit_px": (
                        sum(f.px * f.sz for f in closing) / size if size else None
                    ),
                    "taker_fee_bps": fees / traded * 1e4 if traded else None,
                    "virtual": {
                        "exit_reason": closed.exit_reason if closed else None,
                        "exit_px": closed.exit_px if closed else None,
                        "net_r": closed.net_r if closed else None,
                    },
                },
            )

    # -------------------------------------------------------- the run
    def begin(self) -> None:
        now = self.now()
        open_run = self.book.open_run_start
        if open_run is not None and self.armed:
            try:
                started = datetime.fromisoformat(str(open_run.get("recorded_at")))
            except ValueError:
                started = now
            if now - started > timedelta(minutes=30):
                self.problem("run_stuck", message="a previous run never finished")
        last_end = self.book.last_run_end
        if last_end is not None and self.armed:
            try:
                ended = datetime.fromisoformat(str(last_end.get("recorded_at")))
                if now - ended > timedelta(hours=3):
                    self.problem("runs_missed", message="last run ended over 3 h ago")
            except ValueError:
                pass
        if self.armed and not (self.env.webhook or self.env.deadman):
            self.problem(
                "no_offhost_alerts",
                message="set the webhook or dead-man URL: alerts stay on this host",
                severity=NOTICE,
            )
        if self.armed:
            self.load_signer()
        self.journal.append(
            "run_start",
            {
                "mode": "armed" if self.armed else "dry",
                "cmd": self.cmd,
                "code": code_hashes(),
                "config_fingerprint": self.cfg.fingerprint(),
                "approval_sha256": self.approval_sha256,
                "stop_file_present": self.stop_present,
            },
        )

    def run(self) -> int:
        status, code = "ok", 0
        try:
            self.begin()
            self.p1_identity()
            self.p1_snapshot()
            # A failure in one phase (ANY exception) is recorded as a critical
            # technical_failure and the later phases still run: protection
            # (P3, P7) and exits only reduce risk, and the failure halts new
            # entries for the rest of the run. Only a refusal or the quiet
            # window stops the process; budget exhaustion skips the remaining
            # phases but P7 still runs on the budget held back for it.
            phases: tuple[tuple[str, Callable[[], None]], ...] = (
                ("p2_reconcile", self.p2_reconcile),
                ("p3_sweep", self.p3_sweep),
                ("p4_shadow", self.p4_shadow),
                ("p5_exits", self.p5_exits),
                ("p6_entries", self.p6_entries),
            )
            for name, phase in phases:
                try:
                    phase()
                except (RefusalError, QuietWindowReached):
                    raise
                except BudgetExhausted as exc:
                    self.problem("hl_budget_exhausted", message=f"{name}: {exc}")
                    self.halt_entries(f"hl_budget_exhausted:{name}")
                    status, code = "failed", 2
                    break
                except TechnicalError as exc:
                    self.problem("technical_failure", name, str(exc))
                    status, code = "failed", 2
                except Exception as exc:  # the TYPE only: a message may hold a secret
                    self.problem("technical_failure", name, type(exc).__name__)
                    self.ctx.err(f"d1_sleeve {name} FAILED: {_frames(exc)}")
                    status, code = "failed", 2
            self.pacer.open_final_reserve()
            self.p7_final()
            self.p8_report()
        except RefusalError as exc:
            status, code = "refused", 3
            self.ctx.err(f"d1_sleeve REFUSED: {core.redact(exc, 400)}")
            self.flag_unprotected()
        except QuietWindowReached as exc:
            status = "deadline"
            self.problem("quiet_window_reached", message=str(exc), severity=NOTICE)
            self.flag_unprotected()
        except BudgetExhausted as exc:
            status, code = "failed", 2
            self.problem("hl_budget_exhausted", message=str(exc))
            self.flag_unprotected()
        except TechnicalError as exc:
            status, code = "failed", 2
            self.problem("technical_failure", self.phase, str(exc))
            self.ctx.err(f"d1_sleeve FAIL-CLOSED: {core.redact(exc, 400)}")
            self.flag_unprotected()
        except Exception as exc:  # any other failure also fails closed
            status, code = "failed", 2
            self.problem("technical_failure", self.phase, type(exc).__name__)
            self.ctx.err(f"d1_sleeve FAIL-CLOSED: unexpected {_frames(exc)}")
            self.flag_unprotected()
        return self.finish(status, code)

    def traffic(self) -> dict[str, Any]:
        sent: Counter[str] = Counter()
        refused: Counter[str] = Counter()
        for guard in (self.reader.guard, self.exchange_guard):
            if guard is not None:
                sent.update(guard.sent)
                refused.update(guard.refused)
        return {
            "info_weight": self.pacer.info_weight,
            "info_calls": self.pacer.info_calls,
            "exchange_actions": self.pacer.exchange_actions,
            "by_path": dict(sent),
            "refused": dict(refused),
            "clock_skew_s": self.reader.clock_skew_s,
        }

    def finish(self, status: str, code: int) -> int:
        if self.armed and self.journal.seq:
            self.check_entry_intents()
        critical = sorted(
            p.key for p in self.problems.values() if p.severity == CRITICAL
        )
        if code == 0 and critical:
            code = 2
        traffic = self.traffic()
        problems = [
            p.record() for p in sorted(self.problems.values(), key=lambda p: p.key)
        ]
        owned = self.owned_positions() if self.positions else {}
        counts = {
            "positions": len(self.positions),
            "owned": len(owned),
            "unowned": len(self.positions) - len(owned),
            "stops_ok": self.counts.get("stops_ok", 0),
            "exits": self.counts.get("exits", 0),
            "entries": self.counts.get("entries", 0),
            "skips": self.counts.get("skips", 0),
        }
        if self.armed and self.journal.seq:
            try:
                self.journal.append(
                    "run_end",
                    {
                        "status": status,
                        "counts": counts,
                        "problems": problems,
                        "traffic": traffic,
                    },
                )
            except OSError as exc:
                self.ctx.err(f"d1_sleeve journal run_end failed: {type(exc).__name__}")
                code = 2
            self.write_status_and_alert(status, counts)
            if self.env.deadman:
                _http_get(self.env.deadman)
        self.out(self.summary(counts, traffic))
        return code

    def write_status_and_alert(self, status: str, counts: Mapping[str, int]) -> None:
        now = self.now()
        previous = _read_status(self.paths.status)
        try:
            last_alerted, alerted = dispatch_alerts(
                problems=self.problems,
                previous=previous,
                now=now,
                cfg=self.cfg,
                paths=self.paths,
                webhook=self.env.webhook,
            )
        except Exception as exc:  # alerts are best effort
            _delivery_failure("dispatch", type(exc).__name__)
            last_alerted, alerted = {}, []
        for problem in alerted:
            try:
                self.journal.append(
                    "alert",
                    {
                        "severity": problem.severity,
                        "code": problem.code,
                        "key": problem.key,
                        "message": problem.message,
                    },
                )
            except OSError:
                break
        since = {
            item.get("key"): item.get("since")
            for item in (previous or {}).get("problems", []) or []
        }
        stamp = core.utc_now_iso(now)
        document = {
            "sleeve_id": self.cfg.sleeve_id,
            "last_run": {
                "run_id": self.journal.run_id,
                "cmd": self.cmd,
                "start": core.utc_now_iso(self.started),
                "end": stamp,
                "mode": "armed" if self.armed else "dry",
                "result": status,
            },
            "problems": [
                {**p.record(), "since": since.get(p.key) or stamp}
                for p in sorted(self.problems.values(), key=lambda p: p.key)
            ],
            "last_alerted": last_alerted,
            "positions": [
                {
                    "coin": p.coin,
                    "szi": p.szi,
                    "entry_px": p.entry_px,
                    "owned": p.coin in self.owned_positions(),
                }
                for p in self.positions.values()
            ],
            "shadow": {
                "state": self.shadow_state,
                "mark_date": self.view.mark_date if self.view else None,
                "today": self.view.today if self.view else None,
            },
            "agent_days_left": self.identity.agent_days_left if self.identity else None,
            "equity": {
                "master": self.master_value.equity_usd if self.master_value else None,
                "sub": self.sub_value.equity_usd if self.sub_value else None,
                "book": self.book_equity,
                "sub_free": self.sub_free,
            },
            "slots": {"used": len(self.positions), "max": self.cfg.max_slots},
            "counts": dict(counts),
        }
        try:
            _write_status(self.paths.status, document)
        except OSError as exc:
            _delivery_failure("status", type(exc).__name__)

    def summary(self, counts: Mapping[str, int], traffic: Mapping[str, Any]) -> str:
        codes = sorted({p.code for p in self.problems.values()})
        owned = counts["owned"]
        refused = sum(traffic["refused"].values())
        mark = self.view.mark_date.isoformat() if self.view else "none"
        today = self.view.today.isoformat() if self.view else self.today.isoformat()
        text = (
            f"{core.utc_now_iso(self.now())} d1_sleeve cmd={self.cmd} "
            f"mode={'armed' if self.armed else 'dry'} T={today} "
            f"shadow={self.shadow_state} mark={mark} positions={counts['positions']} "
            f"owned={owned} unowned={counts['unowned']} "
            f"stops_ok={counts['stops_ok']}/{owned} exits={counts['exits']} "
            f"entries={counts['entries']} skips={counts['skips']} "
            f"problems=[{','.join(codes)}] hl_info_weight={traffic['info_weight']} "
            f"hl_info_calls={traffic['info_calls']} "
            f"hl_exchange_actions={traffic['exchange_actions']} refused={refused} "
            f"signing_client={self.signing_client}"
        )
        if self.dry:
            posts = traffic["by_path"].get("/exchange", 0)
            text += f" exchange_posts={posts} (dry-run)"
        return text

    # -------------------------------------------------------- flatten / canary
    def flatten(self, coin: str | None, reason: str) -> int:
        status, code = "ok", 0
        try:
            self.begin()
            self.p1_identity()
            self.p1_snapshot()
            self.p2_reconcile()
            self.set_phase("flatten")
            self.learn_listed_oids()
            owned = self.owned_positions()
            residue = {
                c: record
                for c, record in self.book.canary_residue().items()
                if c in self.positions and self.positions[c].direction > 0
            }
            targets = [coin] if coin else sorted(set(owned) | set(residue))
            for target in targets:
                if target in residue and target not in owned:
                    self.flatten_canary_residue(target, residue[target])
                    continue
                if target not in owned:
                    self.out(
                        _json_line({"flatten": target, "skipped": "not_owned_or_flat"})
                    )
                    continue
                if self.ensure_trade(target, owned[target]) is None:
                    continue
                self.close_position(target, "manual_flatten", operator_reason=reason)
            for target in targets:
                # A trade still open on a coin read flat is a close its fills
                # did not explain (close_position): it keeps its orders. So
                # does a coin P2 reconciled venue_flat_other (hold_orders_on):
                # two reads that lag the entry fill may hide a live position,
                # and the stop is all that protects it (as in the hourly run).
                # So do the stop child of an entry that never opened and a
                # guard stop (keeps_on_flat).
                if target not in self.positions:
                    for order in self.owned_orders(target):
                        if not self.keeps_on_flat(order):
                            self.cancel_order(order)
            # A2: whatever flatten leaves (a position it does not own, or one
            # its close did not finish) ends with a covering stop.
            self.guard_positions()
        except RefusalError as exc:
            status, code = "refused", 3
            self.ctx.err(f"d1_sleeve REFUSED: {core.redact(exc, 400)}")
        except TechnicalError as exc:
            status, code = "failed", 2
            self.problem("technical_failure", self.phase, str(exc))
        except Exception as exc:
            status, code = "failed", 2
            self.problem("technical_failure", self.phase, type(exc).__name__)
            self.ctx.err(f"d1_sleeve FAIL-CLOSED: unexpected {_frames(exc)}")
        return self.finish(status, code)

    def canary(self, coin: str) -> int:
        checks: dict[str, bool] = {}
        numbers: dict[str, float | None] = {}
        status, code = "ok", 0
        trade_id = f"canary:{coin}:{self.today.isoformat()}"
        try:
            self.begin()
            self.p1_identity()
            self.p1_snapshot()
            self.p2_reconcile()
            if not core.tradeable(self.markets, coin):
                raise RefusalError(f"canary coin {coin} is not tradeable")
            if coin in self.positions or coin in self.book.open_trades:
                raise RefusalError(f"canary coin {coin} is not flat on the sub-account")
            if self.stop_present:
                raise RefusalError("STOP is present; the canary opens new risk")
            if not self.in_trade_window():
                raise RefusalError("the canary runs only in minutes :05-:45")
            self.canary_steps(coin, trade_id, checks, numbers)
        except RefusalError as exc:
            status, code = "refused", 3
            self.ctx.err(f"d1_sleeve REFUSED: {core.redact(exc, 400)}")
        except Exception as exc:
            status, code = "failed", 2
            detail = (  # our own (redacted) text, else the TYPE only
                f"{type(exc).__name__}: {exc}"
                if isinstance(exc, core.SleeveError)
                else type(exc).__name__
            )
            self.problem("canary_failed", coin, detail)
        # Whether the entry filled comes from the journal (an intent that
        # filled or is unresolved), never from how far the steps got: any
        # failure after the fill still closes the position and records it.
        filled = self.canary_entry_filled(trade_id)
        residue = False
        if filled and not (
            checks.get("canary_flat") and checks.get("canary_no_orders_left")
        ):
            residue = self.canary_cleanup(coin, trade_id)
        required = (
            "canary_entry_ack_parsed",
            "canary_entry_filled",
            "canary_stop_resting",
            "canary_stop_trigger_px_matches",
            "canary_stop_sz_matches",
            "canary_stop_order_type_ok",
            "canary_stop_survives_expiry",
            "canary_child_listed",
            "canary_child_cloid_matches",
            "canary_child_trigger_px_matches",
            "canary_child_sz_matches",
            "canary_child_order_type_ok",
            "canary_flat",
            "canary_no_orders_left",
        )
        if code == 0 and not all(checks.get(name) for name in required):
            status, code = "failed", 2
            if filled:
                self.problem("canary_failed", coin, "a required canary check failed")
        if self.journal.seq:
            self.journal.append(
                "canary_result",
                {
                    "kind": "canary",
                    "coin": coin,
                    "checks": checks,
                    "numbers": numbers,
                    "residue": residue,
                },
            )
        for name, value in checks.items():
            self.out(f"{name}={'true' if value else 'false'}")
        for name, value in numbers.items():
            self.out(f"{name}={'none' if value is None else _fmt(value)}")
        return self.finish(status, code)

    def canary_steps(
        self,
        coin: str,
        trade_id: str,
        checks: dict[str, bool],
        numbers: dict[str, float | None],
    ) -> None:
        market = self.market(coin)
        szd = market.sz_decimals
        start_ms = core.now_ms(self.now())
        leverage = canary_leverage(market)
        numbers["canary_leverage"] = float(leverage)
        mid = self.mid_now(coin)
        if mid is None:
            raise TechnicalError(f"no mid for {coin}")
        # Refuse BEFORE any order a coin whose lot size cannot run every step:
        # the half-size reduce-only close needs at least one lot, and the stop
        # at 0.9 x entry must clear the venue's $10 minimum (min_order_usd).
        try:
            sz = core.round_size_down(CANARY_NOTIONAL_USD / mid, szd)
            core.round_size_down(sz / 2, szd)
        except TechnicalError as exc:
            raise RefusalError(
                f"{coin} size step is too coarse for a ${CANARY_NOTIONAL_USD:.0f} "
                "canary: half its size must be at least one lot"
            ) from exc
        if sz * mid * CANARY_STOP_FRACTION < self.cfg.min_order_usd:
            raise RefusalError(
                f"{coin} size step is too coarse for a ${CANARY_NOTIONAL_USD:.0f} "
                "canary whose stop clears the minimum order value"
            )
        self.set_phase("canary", new_risk=True)
        checks["canary_leverage_ok"] = self.set_leverage(
            coin, leverage, trade_id, kind="canary"
        )
        if not checks["canary_leverage_ok"]:
            return
        # The same one-action entry as every live entry (A1): the IOC and its
        # reduce-only stop child (normalTpsl), which the venue must place on
        # the full fill and list with its cloid, size and trigger.
        child_px = core.normalize_price(mid * CANARY_STOP_FRACTION, szd)
        entry, child = self.send_entry(
            trade_id=trade_id,
            role="canary_entry",
            stop_role="canary_stop",
            coin=coin,
            is_buy=True,
            sz=sz,
            limit_px=core.ioc_limit(mid, True, 50, szd),
            stop_px=child_px,
            n=self.book.attempts.get((trade_id, "canary_entry"), 0) + 1,
            kind="canary",
        )
        # The grouped reply parsed as the live path needs it: the IOC acked
        # filled in full and so its child resting. Anything else turns every
        # live entry ambiguous (orderStatus, then the H1 re-read path).
        checks["canary_entry_ack_parsed"] = (
            entry.status == "filled" and child.status == "resting"
        )
        if self.dry and entry.filled_sz:
            self.apply_dry_fill(coin, True, entry.filled_sz, mid, leverage)
        self.set_phase("canary", new_risk=False)
        self.refresh_positions()
        position = self.positions.get(coin)
        checks["canary_entry_filled"] = position is not None and position.szi > 0
        if position is None:
            return
        checks["canary_isolated_ok"] = (
            position.leverage_type == "isolated" and position.leverage_value == leverage
        )
        trigger = core.normalize_price(position.entry_px * CANARY_STOP_FRACTION, szd)
        liq = position.liquidation_px
        checks["canary_liq_px_present"] = liq is not None and liq > 0
        checks["canary_liq_behind_stop"] = liq is None or liq < trigger
        numbers["canary_stop_notional_usd"] = position.size * trigger
        stop = self.send_order(
            trade_id=trade_id,
            role="canary_stop",
            coin=coin,
            is_buy=False,
            sz=position.size,
            limit_px=trigger,
            order_type={
                "trigger": {"triggerPx": trigger, "isMarket": True, "tpsl": "sl"}
            },
            reduce_only=True,
            n=self.book.attempts.get((trade_id, "canary_stop"), 0) + 1,
            kind="canary",
        )
        checks["canary_stop_resting"] = stop.resting
        self.refresh_orders()
        listed = [o for o in self.orders if stop.oid is not None and o.oid == stop.oid]
        if self.dry and stop.resting:
            listed = [
                core.VenueOrder(
                    coin,
                    stop.oid or 0,
                    stop.cloid,
                    False,
                    position.size,
                    True,
                    trigger,
                    True,
                    "Stop Market",
                    True,
                )
            ]
        checks["canary_stop_listed"] = bool(listed)
        checks["canary_stop_reduce_only"] = bool(listed) and listed[0].reduce_only
        checks["canary_stop_cloid_field_present"] = (
            bool(listed) and listed[0].has_cloid_field
        )
        checks["canary_stop_cloid_matches"] = (
            bool(listed) and listed[0].cloid == stop.cloid
        )
        # plan_protection (I6) and the final sweep compare the listed trigger
        # price, size and order type with what was placed; prove they echo.
        checks["canary_stop_trigger_px_matches"] = bool(listed) and core.prices_equal(
            listed[0].trigger_px, trigger
        )
        checks["canary_stop_sz_matches"] = bool(listed) and core.sizes_equal(
            listed[0].sz, position.size, szd
        )
        checks["canary_stop_order_type_ok"] = (
            bool(listed) and listed[0].order_type in core.STOP_ORDER_TYPES
        )
        # A1: the entry's venue-attached child rests beside the plain stop.
        others = [
            o
            for o in self.orders
            if o.coin == coin
            and o.is_trigger
            and o.reduce_only
            and (stop.oid is None or o.oid != stop.oid)
        ]
        by_cloid = [o for o in others if o.cloid == child.cloid]
        found = by_cloid or others
        checks["canary_child_listed"] = bool(found)
        checks["canary_child_cloid_matches"] = bool(by_cloid)
        checks["canary_child_trigger_px_matches"] = bool(found) and core.prices_equal(
            found[0].trigger_px, child_px
        )
        checks["canary_child_sz_matches"] = bool(found) and core.sizes_equal(
            found[0].sz, sz, szd
        )
        checks["canary_child_order_type_ok"] = (
            bool(found) and found[0].order_type in core.STOP_ORDER_TYPES
        )
        if self.dry:
            checks["canary_order_status_by_cloid_ok"] = True
        else:
            queried = core.parse_order_status(
                self.reader.order_status(self.env.sub, stop.cloid)
            )
            checks["canary_order_status_by_cloid_ok"] = (
                queried.status == "open" and queried.oid == stop.oid
            )
        checks["canary_stop_survives_expiry"] = self.canary_stop_survives(stop)
        half = core.round_size_down(position.size / 2, szd)
        mid = self.mid_now(coin) or mid
        small = self.send_order(
            trade_id=trade_id,
            role="canary_close",
            coin=coin,
            is_buy=False,
            sz=half,
            limit_px=core.ioc_limit(mid, False, 100, szd),
            order_type=IOC,
            reduce_only=True,
            n=self.book.attempts.get((trade_id, "canary_close"), 0) + 1,
            context={"reason": "canary_small"},
            kind="canary",
        )
        checks["canary_small_reduce_only_accepted"] = small.filled_sz > 0
        if self.dry and small.filled_sz:
            self.apply_dry_fill(coin, False, small.filled_sz, mid, 1)
        self.refresh_positions()
        self.close_ladder(coin, trade_id, "canary_close", "canary", kind="canary")
        checks["canary_flat"] = coin not in self.positions
        if checks["canary_flat"]:  # a position that is still open keeps its stop
            self.canary_cancel(coin)
        self.refresh_orders()
        checks["canary_no_orders_left"] = not any(o.coin == coin for o in self.orders)
        if not self.dry:
            fills = core.parse_fills(
                self.reader.user_fills_by_time(
                    self.env.sub, start_ms - 60_000, core.now_ms(self.now())
                )
            )
            mine = [
                f
                for f in fills
                if f.coin == coin
                and self.book.known_oids.get(f.oid, ("", ""))[0] == trade_id
            ]
            traded = sum(f.px * f.sz for f in mine)
            numbers["canary_taker_fee_bps"] = (
                sum(f.fee for f in mine) / traded * 1e4 if traded else None
            )

    def canary_stop_survives(self, stop: SendResult) -> bool:
        """The stop still rests after its action's expiresAfter has passed.

        The engine never sets expiresAfter; this proves the venue reads it as
        a deadline for the ACTION, not a lifetime for the resting order.
        """
        if self.dry:
            return stop.resting
        record = self.book.intents.get(stop.cloid)
        if not stop.resting or record is None:
            return False
        expires = int(record.expires_after_ms or 0)
        wait = max(0.0, (expires + 5000 - core.now_ms(self.now())) / 1000.0)
        if self.now() + timedelta(seconds=wait) >= self.sweep_end:
            return False
        if wait:
            self.sleep(min(wait, 50.0))
        queried = core.parse_order_status(
            self.reader.order_status(self.env.sub, stop.cloid)
        )
        return queried.status == "open" and queried.oid == stop.oid

    def canary_entry_filled(self, trade_id: str) -> bool:
        """This session's canary entry filled, or may have (unresolved)."""
        return any(
            record.trade_id == trade_id
            and record.role == "canary_entry"
            and record.order > self.session_order
            and (record.filled or not record.resolved)
            for record in self.book.intents.values()
        )

    def flatten_canary_residue(self, coin: str, record: core.IntentRecord) -> None:
        """Close what an interrupted canary left (its own long, reduce-only)."""
        self.close_ladder(
            coin, record.trade_id, "canary_close", "canary_residue", kind="canary"
        )
        if coin in self.positions:
            self.problem("exit_incomplete", coin, "canary residue is not flat")
            return
        self.canary_cancel(coin)
        self.journal.append(
            "canary_result",
            {
                "kind": "canary",
                "coin": coin,
                "checks": {"canary_residue_flat": True},
                "numbers": {},
                "residue": False,
            },
        )
        self.blocked_coins.pop(coin, None)
        self.problems.pop(f"canary_residue:{coin}", None)
        self.out(_json_line({"flatten": coin, "closed": "canary_residue"}))

    def canary_cancel(self, coin: str) -> None:
        for order in self.owned_orders(coin):
            self.cancel_order(order, kind="canary")

    def canary_cleanup(self, coin: str, trade_id: str) -> bool:
        """Close what the canary opened (reduce-only), then cancel once flat.

        Returns the residue as the venue shows it afterwards; a failed read
        counts as residue, so the next run flags it and ``flatten`` adopts it.
        """
        residue = True
        try:
            self.set_phase("flatten")
            self.refresh_positions()
            if coin in self.positions:
                self.close_ladder(
                    coin, trade_id, "canary_close", "canary_cleanup", kind="canary"
                )
            if coin not in self.positions:  # a position still open keeps its stop
                self.refresh_orders()
                self.canary_cancel(coin)
            self.refresh_positions()
            residue = coin in self.positions
        except Exception as exc:  # best effort; the alert says what is left
            self.problem("canary_failed", coin, f"cleanup {type(exc).__name__}")
        if residue or self.owned_orders(coin):
            self.problem("canary_failed", coin, "canary position or order left open")
        return residue


def canary_leverage(market: core.MarketInfo) -> int:
    """The canary proves the live leverage ceiling (3x), capped by the venue."""
    return max(1, min(CANARY_MAX_LEVERAGE, math.floor(market.max_leverage)))


# ----------------------------------------------------------------- commands


def _arming(args: argparse.Namespace) -> bool:
    enabled = bool(getattr(args, "enabled", False))
    accepted = bool(getattr(args, "i_accept_live_risk", False))
    if enabled != accepted:
        raise RefusalError(
            "arming needs BOTH --enabled and --i-accept-live-risk (exactly one given)"
        )
    if enabled and getattr(args, "approval", None) is None:
        raise RefusalError("arming needs --approval PATH")
    return enabled


class _Lock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def _session_command(ctx: Context, args: argparse.Namespace) -> int:
    """run / canary / flatten: P0 then the session."""
    cfg, paths = ctx.cfg, ctx.paths
    armed = _arming(args)
    now = ctx.clock()
    if now.minute in cfg.quiet_minutes:
        # The hourly run defers cleanly (exit 0); a flatten or canary did NOT
        # happen, so it must not look like success to a calling script.
        code = 0 if args.cmd == "run" else 3
        ctx.out(
            f"{core.utc_now_iso(now)} d1_sleeve cmd={args.cmd} quiet window "
            f"(minutes 57-03): no Hyperliquid call; exit {code}"
        )
        return code
    if not armed and args.cmd == "canary":
        env = load_sleeve_env(
            ctx.env_file, include_private_key=False, repo_root=paths.repo_root
        )
        ctx.out(
            _json_line(
                {
                    "plan": "canary",
                    "coin": args.coin,
                    "steps": [
                        "update_leverage min(3, maxLeverage) isolated",
                        "IOC buy $15 at mid+50bps",
                        "verify isolated, leverage and liquidation price",
                        "reduce-only stop at 0.9 x entry",
                        "verify listing, reduce-only, cloid, trigger, size, type",
                        "orderStatus by cloid",
                        "reduce-only IOC sell half",
                        "reduce-only ladder for the rest",
                        "cancel stop by cloid",
                        "fills: taker fee bps",
                    ],
                    "fp_sub": env.fps(cfg)["sub"],
                }
            )
        )
        ctx.out("canary dry plan only: add --enabled --i-accept-live-risk --approval")
        return 0
    lock = _Lock(paths.lock) if armed else None
    if lock is not None and not lock.acquire():
        ctx.out(
            f"{core.utc_now_iso(now)} d1_sleeve notice: another executor run "
            "holds the lock"
        )
        return 0 if args.cmd == "run" else 3
    host_lock: _Lock | None = None
    env: SleeveEnv | None = None
    try:
        try:
            env = load_sleeve_env(
                ctx.env_file, include_private_key=armed, repo_root=paths.repo_root
            )
            events = core.load_journal(paths.journal)
            approval_sha: str | None = None
            if armed:
                approval_sha = verify_approval(
                    args.approval, cfg, env, repo_root=paths.repo_root
                )
                if not engine_key_absent():
                    raise RefusalError(
                        f"{ENV_ENGINE_KEY} is set in this process environment; refusing"
                    )
            elif getattr(args, "approval", None) is not None:
                try:
                    verify_approval(args.approval, cfg, env, repo_root=paths.repo_root)
                    ctx.out("approval=ok (dry run: not required)")
                except RefusalError as exc:
                    ctx.out(f"approval=invalid ({core.redact(exc)})")
            check_runner_sha(cfg)
            if armed:
                # One armed run per SUB-ACCOUNT on this host, from any checkout.
                host_lock = _Lock(paths.host_lock(env.fps(cfg)["sub"]))
                if not host_lock.acquire():
                    host_lock = None
                    ctx.out(
                        f"{core.utc_now_iso(now)} d1_sleeve notice: another "
                        "executor run (any checkout) holds this sub-account's lock"
                    )
                    return 0 if args.cmd == "run" else 3
            session = SleeveSession(
                ctx,
                cmd=args.cmd,
                env=env,
                armed=armed,
                journal_events=events,
                approval_sha256=approval_sha,
            )
        except Exception as exc:
            if armed:
                preflight_alert(ctx, args.cmd, exc, env)
            raise
        if args.cmd == "run":
            return session.run()
        if args.cmd == "flatten":
            return session.flatten(None if args.all else args.coin, args.reason)
        return session.canary(args.coin)
    finally:
        if host_lock is not None:
            host_lock.release()
        if lock is not None:
            lock.release()


def preflight_alert(
    ctx: Context, cmd: str, exc: BaseException, env: SleeveEnv | None
) -> None:
    """An ARMED run refused before its session started: say so off the log.

    A torn journal, an approval that no longer matches the code, env-file
    drift and the like stop every hourly run (exits and stop repair included)
    until the operator acts, so they alert like a critical problem: banner,
    alerts.jsonl and the webhook when the env loaded, deduplicated through
    status.json with the usual reminders. The dead-man URL is NOT pinged.
    """
    code = "preflight_refused" if isinstance(exc, RefusalError) else "preflight_failed"
    problem = Problem(code, CRITICAL, code, core.redact(f"{cmd}: {exc}", 300))
    now = ctx.clock()
    if env is None:  # e.g. the key is missing: the public keys may still load
        try:
            env = load_sleeve_env(
                ctx.env_file, include_private_key=False, repo_root=ctx.paths.repo_root
            )
        except Exception:  # an unreadable env file: banner and JSONL only
            env = None
    previous = _read_status(ctx.paths.status)
    try:
        last_alerted, _ = dispatch_alerts(
            problems={problem.key: problem},
            previous=previous,
            now=now,
            cfg=ctx.cfg,
            paths=ctx.paths,
            webhook=env.webhook if env is not None else None,
        )
        since = {
            item.get("key"): item.get("since")
            for item in (previous or {}).get("problems", []) or []
        }
        stamp = core.utc_now_iso(now)
        document = dict(previous or {})
        document["sleeve_id"] = ctx.cfg.sleeve_id
        document["problems"] = [
            {**problem.record(), "since": since.get(problem.key) or stamp}
        ]
        document["last_alerted"] = last_alerted
        document["preflight"] = {"at": stamp, "cmd": cmd, "result": code}
        _write_status(ctx.paths.status, document)
    except Exception as error:  # alerting is best effort; the refusal stands
        _delivery_failure("preflight", type(error).__name__)


def cmd_probe(ctx: Context, args: argparse.Namespace) -> int:
    cfg = ctx.cfg
    now = ctx.clock()
    if now.minute in cfg.quiet_minutes:
        ctx.out("probe: quiet window (minutes 57-03): no Hyperliquid call; retry later")
        return 0
    env = load_sleeve_env(
        ctx.env_file, include_private_key=False, repo_root=ctx.paths.repo_root
    )
    pacer = HlPacer(cfg, clock=ctx.clock, sleep=ctx.sleep)
    pacer.open_final_reserve()  # no final check to hold budget for
    reader = ctx.reader or HlInfoReader(cfg)
    reader.bind(pacer, ctx.sleep)
    report = verify_identity(reader, env, cfg, now)
    ctx.out(report.line())
    lines: dict[str, Any] = {}
    try:
        values: dict[str, core.AccountValue] = {}
        for role, user, mode in (
            ("master", env.master, report.master_mode),
            ("sub", env.sub, report.sub_mode),
        ):
            if mode not in core.ACCOUNT_MODES:
                continue
            unified = mode == "unifiedAccount"
            # A unified master's equity is its spot USDC; only the sub's
            # perp state is needed (for its positions).
            perp = (
                reader.clearinghouse_state(user)
                if role == "sub" or not unified
                else None
            )
            spot = reader.spot_state(user) if unified else None
            values[role] = core.parse_account_value(str(mode), perp, spot)
            if role == "sub":
                positions = core.parse_positions(perp)
        if "sub" in values and "master" in values:
            book = values["master"].equity_usd + values["sub"].equity_usd
            orders = core.parse_open_orders(reader.frontend_open_orders(env.sub))
            mids = core.parse_mids(reader.all_mids())
            book_state = core.derive_book(core.load_journal(ctx.paths.journal))
            owned_orders = [
                o
                for o in orders
                if core.is_owned_cloid(cfg, o.cloid) or o.oid in book_state.known_oids
            ]
            owned = [c for c in positions if c in book_state.open_trades]
            gross = sum(p.size * mids.get(c, 0.0) for c, p in positions.items())
            lines.update(
                master_equity_usd=values["master"].equity_usd,
                sub_equity_usd=values["sub"].equity_usd,
                sub_free_usd=values["sub"].free_usd,
                book_equity_usd=book,
                risk_per_trade_usd=cfg.risk_fraction * book,
                positions=len(positions),
                positions_owned=len(owned),
                positions_unowned=len(positions) - len(owned),
                orders_owned=len(owned_orders),
                orders_unowned=len(orders) - len(owned_orders),
                slots_used=len(positions),
                slots_max=cfg.max_slots,
                gross_used_usd=gross,
                gross_cap_usd=cfg.gross_cap * book,
                est_full_book_margin_usd=FULL_BOOK_MARGIN_FRACTION * book,
                capacity_guideline=f"{FULL_BOOK_MARGIN_FRACTION:g} x book",
                capacity_hint=_capacity_hint(
                    values["sub"].free_usd, FULL_BOOK_MARGIN_FRACTION * book
                ),
            )
    except (TechnicalError, RefusalError) as exc:
        lines["venue_error"] = core.redact(exc)
    lines.update(_shadow_freshness(ctx))
    lines["webhook_configured"] = env.webhook is not None
    lines["deadman_configured"] = env.deadman is not None
    skew = reader.clock_skew_s
    lines["clock_skew_s"] = "unknown" if skew is None else skew
    lines["clock_skew_ok"] = skew is None or abs(skew) <= CLOCK_SKEW_LIMIT_S
    lines["config_fingerprint"] = cfg.fingerprint()
    lines["runner_sha_ok"] = runner_file_sha256() == cfg.shadow_runner_sha256
    for name, value in lines.items():
        ctx.out(f"{name}={_fmt(value)}")
    sent, refused = reader.traffic()
    ctx.out(
        f"probe traffic: hl_info_weight={pacer.info_weight} hl_info_calls="
        f"{pacer.info_calls} refused={sum(refused.values())} signing_client=none"
    )
    return 0 if report.ok else 3


def _capacity_hint(sub_free: float, guideline: float) -> str:
    """A funding hint, never a failure: what a full book does at this funding."""
    if sub_free >= guideline:
        return "full_book_fits_guideline"
    return (
        "below_guideline_not_a_failure: a crowded day fills slots until sub "
        "collateral runs short, then later entries scale down (to no less "
        "than 25%) or skip as sub_collateral and retry next hour"
    )


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.2f}"
    return core.redact(value)


def _shadow_freshness(ctx: Context) -> dict[str, Any]:
    try:
        events = read_shadow(ctx.paths.shadow_ledger, ctx.cfg, ctx.sleep)
        view = core.build_shadow_view(events, ctx.clock(), ctx.cfg)
    except (core.SleeveError, runner.LedgerError) as exc:
        return {"shadow_state": "invalid", "shadow_error": core.redact(exc, 120)}
    return {
        "shadow_state": view.state,
        "shadow_mark": view.mark_date.isoformat(),
        "shadow_today": view.today.isoformat(),
        "shadow_open_virtual": view.open_virtual,
        "shadow_entries_today": len(view.entries_today),
    }


def cmd_status(ctx: Context, args: argparse.Namespace) -> int:
    cfg, paths = ctx.cfg, ctx.paths
    document: dict[str, Any] = {}
    code = 0
    known_oids: Mapping[int, tuple[str, str]] = {}
    try:
        events = core.load_journal(paths.journal)
        book = core.derive_book(events)
        known_oids = book.known_oids
        document["journal_events"] = len(events)
        document["open_trades"] = [
            {
                "trade_id": t.trade_id,
                "coin": t.coin,
                "direction": t.direction,
                "sz": t.sz,
                "entry_px": t.entry_px,
                "stop_px": t.stop_px,
            }
            for t in book.open_trades.values()
        ]
        document["unresolved_intents"] = len(book.unresolved)
        document["last_run_end"] = (
            {
                "recorded_at": book.last_run_end.get("recorded_at"),
                "status": book.last_run_end.get("status"),
            }
            if book.last_run_end
            else None
        )
    except core.JournalError as exc:
        document["journal_error"] = core.redact(exc)
        code = 2
    status = _read_status(paths.status)
    if status is not None:
        document["status"] = {
            "last_run": status.get("last_run"),
            "problems": status.get("problems"),
            "agent_days_left": status.get("agent_days_left"),
        }
    document["stop_file_present"] = paths.stop_file.exists()
    document["shadow"] = _shadow_freshness(ctx)
    document["runner_sha_ok"] = runner_file_sha256() == cfg.shadow_runner_sha256
    if args.venue:
        now = ctx.clock()
        if now.minute in cfg.quiet_minutes:
            document["venue"] = "skipped: quiet window"
        else:
            env = load_sleeve_env(
                ctx.env_file, include_private_key=False, repo_root=paths.repo_root
            )
            pacer = HlPacer(cfg, clock=ctx.clock, sleep=ctx.sleep)
            pacer.open_final_reserve()  # no final check to hold budget for
            reader = ctx.reader or HlInfoReader(cfg)
            reader.bind(pacer, ctx.sleep)
            perp = reader.clearinghouse_state(env.sub)
            spot = reader.spot_state(env.sub)
            orders = core.parse_open_orders(reader.frontend_open_orders(env.sub))
            mids = core.parse_mids(reader.all_mids())
            positions = core.parse_positions(perp)
            balances = spot.get("balances") if isinstance(spot, Mapping) else None
            document["venue"] = {
                "positions": [
                    {
                        "coin": p.coin,
                        "szi": p.szi,
                        "entry_px": p.entry_px,
                        "mid": mids.get(p.coin),
                        "lev_type": p.leverage_type,
                        "lev_value": p.leverage_value,
                        "liq_px": p.liquidation_px,
                    }
                    for p in positions.values()
                ],
                "orders": [
                    {
                        "coin": o.coin,
                        "oid": o.oid,
                        "is_trigger": o.is_trigger,
                        "trigger_px": o.trigger_px,
                        "reduce_only": o.reduce_only,
                        "sz": o.sz,
                        "owned": core.is_owned_cloid(cfg, o.cloid)
                        or o.oid in known_oids,
                    }
                    for o in orders
                ],
                "usdc_balances": [
                    {"total": b.get("total"), "hold": b.get("hold")}
                    for b in (balances or [])
                    if isinstance(b, Mapping) and b.get("coin") == "USDC"
                ],
                "info_calls": pacer.info_calls,
            }
    if args.json:
        ctx.out(json.dumps(runner._jsonable(document), sort_keys=True, indent=1))
    else:
        for name, value in document.items():
            ctx.out(f"{name}: {runner._canonical(value)}")
    return code


def cmd_approval_template(ctx: Context, args: argparse.Namespace) -> int:
    env = load_sleeve_env(
        ctx.env_file, include_private_key=False, repo_root=ctx.paths.repo_root
    )
    ctx.out(json.dumps(approval_template(ctx.cfg, env), indent=1, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--env-file",
        type=Path,
        default=argparse.SUPPRESS,
        help="sleeve env file (default ~/.config/hypervector/d1_sleeve.env, 0600)",
    )
    arming = argparse.ArgumentParser(add_help=False)
    arming.add_argument("--approval", type=Path, default=None)
    arming.add_argument("--enabled", action="store_true")
    arming.add_argument("--i-accept-live-risk", action="store_true")
    parser = argparse.ArgumentParser(
        prog="d1_sleeve_executor.py",
        description=(
            "D1 sleeve executor: follows the observe-only D1 shadow on a "
            "Hyperliquid sub-account. Every command is a dry run unless armed "
            "with --enabled --i-accept-live-risk --approval PATH."
        ),
        parents=[common],
    )
    commands = parser.add_subparsers(dest="cmd")
    commands.add_parser("probe", parents=[common], help="read-only identity and book")
    commands.add_parser("run", parents=[common, arming], help="hourly run (default)")
    canary = commands.add_parser("canary", parents=[common, arming])
    canary.add_argument("--coin", required=True)
    flatten = commands.add_parser("flatten", parents=[common, arming])
    target = flatten.add_mutually_exclusive_group(required=True)
    target.add_argument("--coin")
    target.add_argument("--all", action="store_true")
    flatten.add_argument("--reason", required=True)
    status = commands.add_parser("status", parents=[common])
    status.add_argument("--venue", action="store_true")
    status.add_argument("--json", action="store_true")
    commands.add_parser("approval-template", parents=[common])
    return parser


def main(
    argv: list[str] | None = None,
    *,
    reader: HlInfoReader | None = None,
    exchange_factory: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
    paths: Paths | None = None,
    env_file: Path | None = None,
) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not any(
        a
        in (
            "probe",
            "run",
            "canary",
            "flatten",
            "status",
            "approval-template",
            "-h",
            "--help",
        )
        for a in arguments
    ):
        arguments = ["run", *arguments]
    args = parser.parse_args(arguments)
    ctx = Context(
        cfg=SleeveConfig(),
        paths=paths or Paths.default(),
        clock=clock or _utc_now,
        sleep=sleep or time.sleep,
        reader=reader,
        exchange_factory=exchange_factory,
        env_file=env_file if env_file is not None else getattr(args, "env_file", None),
    )
    try:
        if args.cmd == "approval-template":
            return cmd_approval_template(ctx, args)
        if args.cmd == "status":
            return cmd_status(ctx, args)
        if args.cmd == "probe":
            return cmd_probe(ctx, args)
        return _session_command(ctx, args)
    except core.SleeveError as exc:
        label = "REFUSED" if exc.exit_code == 3 else "FAIL-CLOSED"
        ctx.err(f"d1_sleeve {label}: {core.redact(exc, 400)}")
        return exc.exit_code
    except Exception as exc:  # any other failure also fails closed (exit 2)
        ctx.err(f"d1_sleeve FAIL-CLOSED: unexpected {_frames(exc)}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
