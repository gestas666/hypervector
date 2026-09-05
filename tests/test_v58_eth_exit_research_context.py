"""Immutable ETH exit research context for the V58 continuous ledger."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.v58_eth_exit_research_context import (
    eth_exit_research_payload,
    load_v58_eth_exit_research_context,
)


def test_exit_context_preserves_rejections_and_legacy_control_identity(
    tmp_path: Path,
) -> None:
    """Only 12h survives both partitions; every tested lock remains rejected."""
    journal, duration = _sources(tmp_path)

    context = load_v58_eth_exit_research_context(journal, duration)
    payload = eth_exit_research_payload(context)

    assert payload["retained_maximum_hold_minutes"] == 720
    assert payload["duration_dispositions"] == {
        "240": "rejected_development_negative",
        "480": "rejected_opened_final_negative",
        "720": "retained_least_contradicted",
    }
    assert set(payload["rejected_profit_locks"]) == {
        "profit_a25_floor15_trail10",
        "profit_a40_floor15_trail20",
        "profit_a60_floor15_trail30",
    }
    assert payload["legacy_control_policy_id"] == "generic_8h_control"
    assert payload["legacy_control_enforced_hold_minutes"] == 720
    assert payload["opened_final_720m_ex_largest_positive"] is False
    assert payload["automatic_strategy_change"] is False
    assert payload["execution_authority"] == "none"


def test_exit_context_rejects_control_that_differs_from_12h(tmp_path: Path) -> None:
    """A stale label becomes unsafe if its replay economics stop matching 12h."""
    journal, duration = _sources(tmp_path)
    artifact = json.loads(duration.read_text(encoding="utf-8"))
    artifact["profit_lock_comparison"]["development"]["generic_8h_control"][
        "net_return_bps"
    ] = 999.0
    duration.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")
    _rewrite_journal_hash(journal, duration)

    with pytest.raises(ValueError, match="legacy profit-lock control differs"):
        load_v58_eth_exit_research_context(journal, duration)


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    duration = tmp_path / "duration.json"
    duration.write_text(json.dumps(_artifact(), sort_keys=True), encoding="utf-8")
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps(_journal(duration), sort_keys=True), encoding="utf-8")
    return journal, duration


def _rewrite_journal_hash(journal: Path, duration: Path) -> None:
    payload = json.loads(journal.read_text(encoding="utf-8"))
    evidence = payload["evidence"][0]
    raw = duration.read_bytes()
    evidence.update({"sha256": sha256(raw).hexdigest(), "bytes": len(raw)})
    journal.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _journal(duration: Path) -> dict[str, object]:
    raw = duration.read_bytes()
    return {
        "schema_version": 1,
        "hypothesis_id": "eth-breakout-precompression-pullback",
        "revision_number": 5,
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "status": "candidate",
        "decision": "Retain the exact 12-hour ETH exit contract and reject tested locks.",
        "falsifier": "A preregistered state-aware exit must win both partitions and forward.",
        "evidence": [
            {
                "path": str(duration),
                "role": "exact_fixed_entry_profit_lock_and_duration_comparison",
                "sha256": sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        ],
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _artifact() -> dict[str, object]:
    durations = {
        "development": {
            "fixed_240m": _row(282, -2_322.0, 0.80, -2_793.0),
            "fixed_480m": _row(282, 235.0, 1.01, -520.0),
            "fixed_720m": _row(282, 1_657.0, 1.11, 487.0),
        },
        "opened_final_60d": {
            "fixed_240m": _row(56, 395.0, 1.21, 88.0),
            "fixed_480m": _row(56, -37.0, 0.98, -330.0),
            "fixed_720m": _row(56, 322.0, 1.12, -346.0),
        },
    }
    locks = {
        partition: {
            "generic_8h_control": dict(rows["fixed_720m"]),
            "profit_a25_floor15_trail10": _row(
                rows["fixed_720m"]["trades"], -50.0, 0.5
            ),
            "profit_a40_floor15_trail20": _row(
                rows["fixed_720m"]["trades"], -40.0, 0.6
            ),
            "profit_a60_floor15_trail30": _row(
                rows["fixed_720m"]["trades"],
                -30.0 if partition == "development" else 20.0,
                0.8,
            ),
        }
        for partition, rows in durations.items()
    }
    return {
        "schema_version": 1,
        "mode": "eth_pullback_side_breakout_relation_attribution_v1",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "contract": {
            "automatic_promotion": False,
            "entry_gate": False,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
            "report_only": True,
            "runtime_strategy_changed": False,
        },
        "coverage": {"development_trades": 282, "opened_final_trades": 56},
        "duration_comparison": durations,
        "profit_lock_comparison": locks,
    }


def _row(
    trades: int, net: float, profit_factor: float, ex_largest: float = -1.0
) -> dict[str, object]:
    return {
        "trades": trades,
        "wins": 1,
        "losses": trades - 1,
        "net_return_bps": net,
        "net_excluding_largest_winner_bps": ex_largest,
        "profit_factor": profit_factor,
        "maximum_drawdown_bps": 10.0,
        "exit_reasons": {"maximum_hold": trades},
    }
