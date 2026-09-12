"""Real checkpoint publication across inherited live-trade lifecycles."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from cohort_live_audit_trade_fixture import traded_asset_rows
from hypervector.research.cohort_live_checkpoint import publish_live_checkpoint
from test_multi_asset_live_audit import _RUN_ID, _SYMBOLS, _asset_rows
from test_multi_asset_live_audit_restart import (
    _open_cohort_rows,
    _restart_spanning_trade_rows,
    _with_prior_cohort_identity,
)
from test_multi_asset_live_audit import _cohort_rows_with_trade


def test_current_run_checkpoint_recovers_inherited_open_costs(tmp_path: Path) -> None:
    """Prior entry costs and funding survive without becoming new-run fills."""
    cohort, assets = _open_restart_fixture()
    root = _write_ledgers(tmp_path, cohort, assets)
    before = _hashes(root)

    checkpoint = _publish(root, tmp_path)

    execution = checkpoint["audit"]["execution"]
    assert execution["current_run_fills"] == 0
    assert execution["fills"] == 1
    assert execution["closed_trades"] == 0
    assert execution["open_lifecycles"] == 1
    position = execution["open_positions"][0]
    assert position["fees_usd"] == pytest.approx(0.01)
    assert position["funding_usd"] == pytest.approx(-0.007)
    assert position["cost_scope"] == "active_lifecycle"
    context = checkpoint["audit"]["open_trade_reflections"]["trades"][0][
        "entry_context"
    ]["signal_provider"]
    assert context["source"] == "asset_entry_journal"
    assert context["primary_regime"] == "TREND_UP"
    assert context["readiness"] is None
    assert context["readiness_status"] == "unavailable_cohort_entry_evaluation"
    assert checkpoint["audit"]["health"]["assets"]["BTC"]["final_state"] == "OPEN"
    assert checkpoint["evidence"]["cohort"]["telemetry_scope"] == "current_run"
    assert _hashes(root) == before


def test_current_run_checkpoint_recovers_exit_before_first_snapshot(
    tmp_path: Path,
) -> None:
    """An inherited trade closed at startup retains entry, exit, and total costs."""
    cohort = _with_prior_cohort_identity(_cohort_rows_with_trade())
    for row in cohort:
        if row["event_type"] == "cohort_snapshot":
            row["payload"]["recent_fills"] = []
    assets = {symbol: _asset_rows(symbol) for symbol in _SYMBOLS}
    assets["BTC"] = _restart_spanning_trade_rows()
    root = _write_ledgers(tmp_path, cohort, assets)

    checkpoint = _publish(root, tmp_path)

    execution = checkpoint["audit"]["execution"]
    assert execution["current_run_fills"] == 1
    assert execution["fills"] == 2
    assert execution["closed_trades"] == 1
    assert execution["open_lifecycles"] == 0
    assert execution["net_pnl_usd"] == pytest.approx(0.97)
    assert execution["fees_usd"] == pytest.approx(0.02)
    assert execution["funding_usd"] == pytest.approx(-0.01)
    assert [fill["trade_id"] for fill in execution["fill_details"]] == [101, 202]


def test_incompatible_entry_history_cannot_repair_inherited_position(
    tmp_path: Path,
) -> None:
    """History from a different execution profile cannot establish ownership."""
    cohort, assets = _open_restart_fixture()
    for row in assets["BTC"]:
        if row["run_id"] != _RUN_ID:
            row["run_fingerprint"] = "incompatible-run-fingerprint"
    root = _write_ledgers(tmp_path, cohort, assets)

    with pytest.raises(
        ValueError, match="inherited entry missing from compatible execution history"
    ):
        _publish(root, tmp_path)
    assert not (tmp_path / "checkpoint.json").exists()


def _open_restart_fixture() -> tuple[
    list[dict[str, object]], dict[str, list[dict[str, object]]]
]:
    """Build a prior entry plus restarted telemetry and one new funding credit."""
    cohort = _with_prior_cohort_identity(_open_cohort_rows())
    assets = {symbol: _asset_rows(symbol) for symbol in _SYMBOLS}
    for rows in (cohort, *assets.values()):
        for row in rows:
            if row.get("run_id") != _RUN_ID:
                continue
            observed = datetime.fromisoformat(row["observed_at_utc"])
            row["observed_at_utc"] = (observed + timedelta(minutes=1)).isoformat()
    for row in cohort:
        if row["event_type"] == "cohort_snapshot":
            row["payload"]["recent_fills"] = []
            row["payload"]["assets"][0].update(
                entry_price=100.01,
                mark_price=100.21,
                position_value_usd=25.0525,
                unrealized_pnl_usd=0.05,
                margin_used_usd=5.0,
                liquidation_price=80.0,
                state="OPEN",
            )
    current = assets["BTC"]
    current[2]["payload"].update(size_signed=0.25, margin_used_usd=5.0, leverage=5)
    current[3]["payload"]["value"] = 80.0
    current[4]["payload"].update(
        state="OPEN",
        position_size_signed=0.25,
        entry_oid=11,
        opened_at_ms=1_785_600_000_000,
        stop_oid=12,
        stop_reason=None,
    )
    credit = deepcopy(current[-1])
    credit.update(
        event_type="funding",
        payload={"venue_timestamp_ms": 1_785_600_050_000, "usdc_delta": 0.003},
    )
    prior = traded_asset_rows("prior-run")[:9]
    assets["BTC"] = [
        {**row, "sequence": index}
        for index, row in enumerate([*prior, *current, credit], 1)
    ]
    return cohort, assets


def _write_ledgers(
    tmp_path: Path,
    cohort: list[dict[str, object]],
    assets: dict[str, list[dict[str, object]]],
) -> Path:
    """Write independent fixture ledgers with exact physical sequences."""
    root = tmp_path / "ledgers"
    root.mkdir()
    records = {
        "decisions": cohort,
        **{symbol.lower(): rows for symbol, rows in assets.items()},
    }
    for name, rows in records.items():
        (root / f"{name}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )
    return root


def _publish(root: Path, tmp_path: Path) -> dict[str, object]:
    """Exercise the actual bounded publisher with no network or cache substitute."""
    return publish_live_checkpoint(
        root,
        tmp_path / "checkpoint.json",
        run_id=_RUN_ID,
        generated_at=datetime(2026, 8, 2, 4, 0, tzinfo=timezone.utc),
        current_run_only=True,
    )


def _hashes(root: Path) -> dict[str, str]:
    """Authenticate every fixture ledger before and after publication."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir()
    }
