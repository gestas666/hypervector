"""All-time lifecycle coverage for assets retired from the active roster."""

from __future__ import annotations

from copy import deepcopy

from cohort_trade_reflection_fixtures import (
    reflection_asset_rows,
    reflection_cohort_rows,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from test_multi_asset_live_audit import _RUN_ID, _SYMBOLS, _asset_rows


def test_all_time_reflections_retain_a_retired_asset_ledger() -> None:
    """Removing route authority must not delete that asset's closed history."""
    current = reflection_asset_rows()
    retired = _retired_ddd_rows(current)

    report = audit_multi_asset_live_run(
        reflection_cohort_rows(),
        {
            "BTC": current,
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        all_time_asset_records={
            "BTC": current,
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
            "xyz:DDD": retired,
        },
        run_id=_RUN_ID,
    )

    all_time = report["trade_reflections"]["all_time_live"]
    assert all_time["closed_trades"] == 2
    assert {trade["symbol"] for trade in all_time["trades"]} == {
        "BTC",
        "xyz:DDD",
    }
    assert report["trade_reflections"]["closed_trades"] == 1


def _retired_ddd_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return a distinct retired-asset ledger with the same causal lifecycle."""
    output = deepcopy(rows)
    for row in output:
        _replace_symbol(row)
    return output


def _replace_symbol(value: object) -> None:
    """Replace exact fixture symbol values without changing unrelated text."""
    if isinstance(value, dict):
        for key, item in value.items():
            if item == "BTC" and key == "symbol":
                value[key] = "xyz:DDD"
            else:
                _replace_symbol(item)
    elif isinstance(value, list):
        for item in value:
            _replace_symbol(item)
