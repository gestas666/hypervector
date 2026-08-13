"""Supplemental report-only observer coverage for cohort checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from hypervector.research.cohort_live_checkpoint import (
    build_live_checkpoint,
    publish_live_checkpoint,
)
from test_multi_asset_live_audit import _asset_rows, _cohort_rows

_RUN_ID = "cohort-live-a"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_GENERATED_AT = datetime(2026, 8, 4, 23, 45, tzinfo=timezone.utc)


def test_checkpoint_preserves_distinct_supplemental_forward_observer() -> None:
    """A second report-only challenger remains separately attributable."""
    primary = _matrix("hype-fixed-v4", "hype-source", "HYPE")
    supplemental = _matrix("btc-structural-v1", "btc-source", "BTC")

    checkpoint = build_live_checkpoint(
        _cohort_rows(),
        {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
        execution_opportunity_matrix=primary,
        supplemental_execution_opportunity_matrices=[supplemental],
    )

    matrix = checkpoint["audit"]["execution_opportunity_matrix"]
    assert (
        matrix["forward_challenger"]["portfolio_journal"]["contract"][
            "candidate_strategy_id"
        ]
        == "hype-fixed-v4"
    )
    assert [
        row["portfolio_journal"]["contract"]["candidate_strategy_id"]
        for row in matrix["supplemental_forward_challengers"]
    ] == ["btc-structural-v1"]


def test_checkpoint_rejects_duplicate_forward_observer_identity() -> None:
    """Two files cannot masquerade as independent candidate evidence."""
    primary = _matrix("same-candidate", "hype-source", "HYPE")
    duplicate = _matrix("same-candidate", "btc-source", "BTC")

    with pytest.raises(ValueError, match="duplicate candidate strategy"):
        build_live_checkpoint(
            _cohort_rows(),
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
            execution_opportunity_matrix=primary,
            supplemental_execution_opportunity_matrices=[duplicate],
        )


def test_checkpoint_rejects_nested_supplemental_execution_authority() -> None:
    """A safe outer envelope cannot conceal an authoritative challenger."""
    primary = _matrix("hype-fixed-v4", "hype-source", "HYPE")
    unsafe = _matrix("btc-structural-v1", "btc-source", "BTC")
    unsafe["forward_challenger"]["contract"]["execution_authority"] = "venue"

    with pytest.raises(ValueError, match="challenger execution authority"):
        build_live_checkpoint(
            _cohort_rows(),
            {symbol: _active_asset_rows(symbol) for symbol in _SYMBOLS},
            run_id=_RUN_ID,
            generated_at=_GENERATED_AT,
            execution_opportunity_matrix=primary,
            supplemental_execution_opportunity_matrices=[unsafe],
        )


def test_publish_fails_closed_when_explicit_supplemental_file_is_missing(
    tmp_path: Path,
) -> None:
    """An explicitly requested observer cannot disappear as a silent default."""
    ledger_root = tmp_path / "ledgers"
    ledger_root.mkdir()
    _write_rows(ledger_root / "decisions.jsonl", _cohort_rows())
    for symbol in _SYMBOLS:
        _write_rows(ledger_root / f"{symbol.lower()}.jsonl", _asset_rows(symbol))

    with pytest.raises(FileNotFoundError, match="supplemental opportunity matrix"):
        publish_live_checkpoint(
            ledger_root,
            tmp_path / "checkpoint.json",
            run_id=_RUN_ID,
            opportunity_matrix_path=None,
            supplemental_opportunity_matrix_paths=[tmp_path / "missing.json"],
        )


def _matrix(candidate_id: str, source_id: str, symbol: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_execution_opportunity_matrix",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "portfolio_pnl_claimed": False,
        },
        "hypotheses": 0,
        "comparisons": 0,
        "results": [],
        "forward_challenger": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "live_strategy_changed": False,
                "automatic_promotion": False,
                "portfolio_pnl_claimed": False,
            },
            "portfolio_journal": {
                "contract": {
                    "candidate_strategy_id": candidate_id,
                    "source_strategy_id": source_id,
                    "symbol": symbol,
                    "report_only": True,
                    "execution_authority": "none",
                    "portfolio_pnl_claimed": False,
                }
            },
        },
    }


def _active_asset_rows(symbol: str) -> list[dict[str, object]]:
    rows = _asset_rows(symbol)
    payload = rows[-1]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = "FLAT"
    payload["stop_reason"] = None
    return rows


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
