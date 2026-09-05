"""Resolved-deadline regressions for the V58 ETH path report."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.v58_eth_open_path_context import (
    eth_open_path_context_payload,
    load_v58_eth_open_path_context,
)
from test_v58_eth_open_path_context import _resolved_status


def test_resolved_path_derives_missing_deadline_from_frozen_hold(
    tmp_path: Path,
) -> None:
    """A compact resolved row must retain the predeclared 720-minute deadline."""
    status, _ = _resolved_status(tmp_path)
    raw = json.loads(status.read_text(encoding="utf-8"))
    execution = raw["latest_executions"][0]
    del execution["deadline_time_ms"]
    status.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")

    context = load_v58_eth_open_path_context(status)
    payload = eth_open_path_context_payload(context)

    assert payload["state"] == "resolved"
    assert payload["deadline_time_ms"] == 43_201_000
    assert payload["holding_remaining_seconds"] == 43_197.0
