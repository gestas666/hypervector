from __future__ import annotations

import json
from pathlib import Path

from hypervector.research import range_onset_forward_observer


def test_btc_capital_reader_contract_is_available() -> None:
    assert hasattr(range_onset_forward_observer, "BtcShadowCapitalReader")


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    payload = "".join(json.dumps(row) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")


def test_pending_btc_entry_reserves_configured_shared_margin(tmp_path: Path) -> None:
    path = tmp_path / "decisions.jsonl"
    _write_rows(
        path,
        [
            {
                "action": "session_start",
                "run_id": "btc-run",
                "execution_mode": "shadow",
                "risk": {"margin_fraction": 0.35},
                "strategy_params": {"leverage": 30.0},
            },
            {
                "action": "regime_observation",
                "run_id": "btc-run",
                "execution_mode": "shadow",
                "feed_ts": "2026-07-31T06:00:00+00:00",
                "equity": 15_000.0,
                "position_qty": 0.0,
                "position_avg_px": 0.0,
            },
            {
                "action": "entry_execution_observation",
                "run_id": "btc-run",
                "execution_mode": "shadow",
                "maker_entry_state": "pending",
            },
        ],
    )

    snapshot = range_onset_forward_observer.BtcShadowCapitalReader(path).read_latest()

    assert snapshot is not None
    assert snapshot.source_run_id == "btc-run"
    assert snapshot.equity_usd == 15_000.0
    assert snapshot.reserved_margin_usd == 5_250.0
    assert snapshot.observed_time_ms == 1_785_477_600_000
