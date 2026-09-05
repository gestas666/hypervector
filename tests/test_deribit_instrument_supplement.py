"""Tests for immutable exact-name Deribit instrument recovery."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.deribit_instrument_supplement import (
    acquire_deribit_instrument_supplement,
    reproduce_deribit_instrument_supplement,
)


def test_supplement_preserves_raw_exact_names_and_reproduces_parquet(
    tmp_path: Path,
) -> None:
    """Every recovered dictionary row must reproduce from its official raw page."""
    names = ("BTC-25DEC26-80000-C", "BTC-25SEP26-60000-P")

    def fetch(name: str) -> bytes:
        option_type = "put" if name.endswith("-P") else "call"
        strike = 60_000.0 if "-60000-" in name else 80_000.0
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "result": {
                    "instrument_name": name,
                    "creation_timestamp": 1,
                    "expiration_timestamp": 2_000_000_000_000,
                    "strike": strike,
                    "option_type": option_type,
                    "contract_size": 1.0,
                },
            }
        ).encode()

    output = tmp_path / "supplement"
    acquire_deribit_instrument_supplement(
        output,
        names,
        fetch,
        max_workers=2,
        context=_context(),
    )
    audit = reproduce_deribit_instrument_supplement(output)

    assert audit.instrument_rows == 2
    assert audit.raw_pages == 2
    assert audit.rows_match is True
    assert audit.all_registered_files_verified is True


def _context() -> dict[str, object]:
    return {
        "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
        "execution_authority": "none",
        "live_change_authorized": False,
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
        "completeness_audit": {"sha256": "a" * 64, "bytes": 1},
        "preregistration": {"sha256": "b" * 64, "bytes": 1},
    }
