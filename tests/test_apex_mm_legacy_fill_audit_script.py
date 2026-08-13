"""Operator contract for the read-only Apex legacy-fill recovery audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_protocol import SolFill


_SCRIPT = Path("scripts/apex_regime_mm_legacy_fill_audit.py")


class _Reader:
    def fills(self) -> tuple[SolFill, ...]:
        return (_fill(),)


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("apex_legacy_fill_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load audit script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fill() -> SolFill:
    return SolFill(
        oid=101,
        price=63_090.0,
        size=0.00019,
        side="A",
        timestamp_ms=1_785_586_383_357,
        fee_usd=0.001726,
        fee_token="USDC",
        closed_pnl_usd=0.0,
        crossed=False,
        direction="Open Short",
        transaction_hash="0xabc",
        trade_id=7_001,
    )


def _rows() -> list[dict[str, object]]:
    fill = _fill()
    payloads = [
        (
            "configuration_identity",
            {"strategy_name": "apex_regime_mm_v2"},
        ),
        (
            "fill",
            {
                "oid": fill.oid,
                "venue_timestamp_ms": fill.timestamp_ms,
                "price": fill.price,
                "size": fill.size,
                "side": fill.side,
                "direction": fill.direction,
                "closed_pnl_usd": fill.closed_pnl_usd,
                "crossed": fill.crossed,
                "transaction_hash": fill.transaction_hash,
                "fee_usd": fill.fee_usd,
                "fee_token": fill.fee_token,
            },
        ),
        (
            "fee",
            {
                "source": "fill",
                "oid": fill.oid,
                "venue_timestamp_ms": fill.timestamp_ms,
                "fee_usd": fill.fee_usd,
            },
        ),
        (
            "position",
            {"size_signed": -fill.size, "position_value_usd": fill.price * fill.size},
        ),
        (
            "reconciliation",
            {
                "account_value_usd": 150.0,
                "withdrawable_usd": 140.0,
                "open_order_ids": [],
            },
        ),
        ("state_transition", {"state": "STOPPED"}),
    ]
    return [
        {
            "schema_version": 1,
            "sequence": sequence,
            "event_type": event_type,
            "observed_at_utc": f"2026-08-01T12:00:0{sequence}+00:00",
            "execution_mode": "live",
            "live_armed": True,
            "execution_authority": "hyperliquid_mainnet",
            "profile_id": "apex_regime_mm_canary_v1",
            "profile_fingerprint": "profile",
            "run_fingerprint": "run",
            "run_id": "run-a",
            "payload": payload,
        }
        for sequence, (event_type, payload) in enumerate(payloads, start=1)
    ]


def test_script_publishes_immutable_exact_recovery_without_execution_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command binds the ledger and venue TID without changing the ledger."""
    module = _load_script()
    ledger = tmp_path / "decisions.jsonl"
    content = b"".join(json.dumps(row).encode() + b"\n" for row in _rows())
    ledger.write_bytes(content)
    output = tmp_path / "audit.json"
    monkeypatch.setattr(module, "load_wallet_env_if_present", lambda: ())
    monkeypatch.setattr(module, "create_read_only_btc_reader", lambda: _Reader())

    assert (
        module.main(
            [
                "--decisions",
                str(ledger),
                "--run-id",
                "run-a",
                "--out",
                str(output),
            ]
        )
        == 0
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["experiment_contract"]["execution_authority"] == "none"
    assert report["execution"]["fills"] == 1
    assert report["evidence"]["decisions"] == {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }
    recovery = report["evidence"]["venue_fill_recovery"]
    assert recovery["recovered_fill_count"] == 1
    assert recovery["matches"][0]["trade_id"] == 7_001
    assert b"trade_id" not in ledger.read_bytes()
    with pytest.raises(FileExistsError, match="immutable live audit output exists"):
        module.main(
            [
                "--decisions",
                str(ledger),
                "--run-id",
                "run-a",
                "--out",
                str(output),
            ]
        )

    source = _SCRIPT.read_text(encoding="utf-8")
    assert "create_armed" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
