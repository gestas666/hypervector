"""Cohort supervisor alerts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Protocol
import urllib.error
import urllib.request

from cohort_supervisor_models import (
    SupervisorPaths,
    HealthReport,
    WEBHOOK_ENV,
)


class AlertSink(Protocol):
    """Destination for one already-formatted, secret-free alert."""

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        """Deliver one alert; durable storage errors propagate at the boundary."""
        ...


class JsonlSink:
    """Append-only durable alert journal. Always enabled."""

    def __init__(self, path: Path) -> None:
        """Bind the append-only local alert journal."""
        self._path = path

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        """Persist a complete local alert record."""
        append_jsonl(self._path, {"title": title, "body": body, **record})


class MacNotificationSink:
    """Best-effort Notification Centre banner."""

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        """Present an optional local notification without process authority."""
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


class WebhookSink:
    """POST a small JSON document to an operator-configured endpoint."""

    def __init__(self, url: str) -> None:
        """Bind an explicitly configured notification endpoint."""
        self._url = url

    def send(self, title: str, body: str, record: dict[str, object]) -> None:
        """Deliver an optional webhook without recording its URL."""
        data = json.dumps({"text": f"{title}: {body}", **record}).encode("utf-8")
        try:
            request = urllib.request.Request(
                self._url,
                data=data,
                headers={"Content-Type": "application/json", "Title": title},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10):  # noqa: S310
                return
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _delivery_failure("webhook", type(exc).__name__)


class Alerter:
    """Alert on every change of the problem set, then remind while unhealthy."""

    def __init__(
        self,
        sinks: Sequence[AlertSink],
        *,
        reminder_seconds: float = 1_800.0,
        minimum_interval_seconds: float = 0.0,
    ) -> None:
        """Bind notification sinks, the reminder interval, and the churn floor.

        ``minimum_interval_seconds`` bounds how often a *transition* alone can
        alert. It defaults to 0.0 so the class imposes no policy of its own; the
        supervisor CLI sets the operational value. A problem label that has not
        been alerted since the last recovery always bypasses the floor, so new
        information is never delayed.
        """
        self._sinks = tuple(sinks)
        self._reminder_seconds = reminder_seconds
        self._minimum_interval = minimum_interval_seconds
        self._last_problems: tuple[str, ...] | None = None
        self._alerted_labels: set[str] = set()
        self._suppressed = 0
        self._last_sent = 0.0

    def observe(self, report: HealthReport, now: float) -> bool:
        """Send at most one alert for this report. Return whether one was sent."""
        problems = report.problems
        previous = self._last_problems
        changed = problems != previous
        reminder_due = (
            bool(problems) and now - self._last_sent >= self._reminder_seconds
        )
        first_healthy = previous is None and not problems
        self._last_problems = problems
        if first_healthy or not (changed or reminder_due):
            return False
        within_floor = now - self._last_sent < self._minimum_interval
        if not problems:
            if within_floor:
                # Hold the recovery notice rather than let a flapping probe
                # alternate alert and recovery banners without bound.
                self._last_problems = previous
                self._suppressed += 1
                return False
            self._alerted_labels.clear()
            self.emit(
                "Hypervector recovered", "all probes healthy", asdict(report), now
            )
            return True
        unreported = [problem for problem in problems if problem not in self._alerted_labels]
        if not unreported and not reminder_due and within_floor:
            self._suppressed += 1
            return False
        self._alerted_labels.update(problems)
        self.emit("HYPERVECTOR ALERT", self._body(problems), asdict(report), now)
        return True

    def _body(self, problems: tuple[str, ...]) -> str:
        body = ", ".join(problems)
        if not self._suppressed:
            return body
        suppressed, self._suppressed = self._suppressed, 0
        return f"{body} (+{suppressed} suppressed transitions)"

    def emit(
        self, title: str, body: str, record: dict[str, object], now: float
    ) -> None:
        """Deliver one explicit alert to every sink."""
        self._last_sent = now
        stamped = {
            "alerted_at_utc": datetime.fromtimestamp(now, UTC).isoformat(),
            **record,
        }
        for sink in self._sinks:
            try:
                sink.send(title, body, stamped)
            except OSError as exc:
                _delivery_failure(type(sink).__name__, type(exc).__name__)


def build_sinks(paths: SupervisorPaths, *, notifications: bool) -> list[AlertSink]:
    """Assemble the durable journal plus any operator-enabled channels."""
    sinks: list[AlertSink] = [JsonlSink(paths.alerts)]
    if notifications and Path("/usr/bin/osascript").exists():
        sinks.append(MacNotificationSink())
    webhook = os.environ.get(WEBHOOK_ENV, "").strip()
    if webhook:
        sinks.append(WebhookSink(webhook))
    return sinks


def ping_deadman(url: str | None) -> None:
    """Tell an external monitor this host is alive.

    A process supervisor cannot report a dead or sleeping host. An external
    dead-man check that alerts when these pings STOP is the only detector for the
    2026-09-12 to 09-15 class of outage.
    """
    if not url:
        return
    try:
        with urllib.request.urlopen(url, timeout=10):  # noqa: S310
            return
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _delivery_failure("deadman", type(exc).__name__)


def _delivery_failure(channel: str, failure: str) -> None:
    print(
        json.dumps(
            {"event": "alert_delivery_failed", "channel": channel, "failure": failure}
        ),
        file=sys.stderr,
        flush=True,
    )


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    """Append one JSON line, creating the parent directory when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
