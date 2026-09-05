"""Tests for verified vectorized BTC option-flow source materialization."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence, write_json
from hypervector.research.btc_option_flow_source_materialization import (
    materialize_registered_hourly_flow,
)
from hypervector.research.btc_option_directional_flow import weighted_directional_trade
from hypervector.research.deribit_option_trade_acquisition import (
    OptionInstrument,
    OptionTrade,
)


_START = pd.Timestamp("2025-08-01T00:00:00Z")
_END = pd.Timestamp("2025-08-02T00:00:00Z")
_PREREGISTRATION_SHA256 = "a" * 64


def test_materialization_verifies_source_and_matches_frozen_weighting(
    tmp_path: Path,
) -> None:
    """Vectorized source rows must reproduce exact eligible directional weights."""
    instrument = _instrument()
    trades = [_trade(index, instrument.instrument_name) for index in range(20)]
    trades.extend(
        [
            _trade(20, instrument.instrument_name, iv=0.0),
            _trade(21, instrument.instrument_name, block_trade_id="block"),
        ]
    )
    bundle = _bundle(tmp_path, trades, [instrument])

    hourly, audit = materialize_registered_hourly_flow(
        bundle,
        start=_START,
        end=_END,
        expected_preregistration_sha256=_PREREGISTRATION_SHA256,
    )

    first = hourly.iloc[0]
    expected = weighted_directional_trade(trades[0], instrument)
    assert expected is not None
    assert len(hourly) == 24
    assert first["eligible_trade_count"] == 20
    assert first["weight_usd"] == pytest.approx(20.0 * expected.weight_usd)
    assert first["directional_imbalance"] == pytest.approx(1.0)
    assert hourly.iloc[1:]["eligible_trade_count"].eq(0).all()
    assert audit.trade_rows == 22
    assert audit.eligible_trade_rows == 20
    assert audit.excluded_nonordinary_rows == 1
    assert audit.excluded_invalid_feature_rows == 1
    assert audit.unmatched_instrument_rows == 0
    assert audit.raw_trade_pages_verified == 1
    assert audit.all_registered_files_verified is True


def test_materialization_rejects_duplicate_trade_ids(tmp_path: Path) -> None:
    """A normalized source cannot contain duplicate economic events."""
    instrument = _instrument()
    trade = _trade(0, instrument.instrument_name)
    bundle = _bundle(tmp_path, [trade, trade], [instrument])

    with pytest.raises(ValueError, match="duplicate trade IDs"):
        materialize_registered_hourly_flow(
            bundle,
            start=_START,
            end=_END,
            expected_preregistration_sha256=_PREREGISTRATION_SHA256,
        )


def test_materialization_rejects_unmatched_instrument(tmp_path: Path) -> None:
    """Every event must join exact static contract metadata."""
    trade = _trade(0, "BTC-8AUG25-110-C")
    bundle = _bundle(tmp_path, [trade], [_instrument(name="BTC-8AUG25-120-C")])

    with pytest.raises(ValueError, match="missing instrument metadata"):
        materialize_registered_hourly_flow(
            bundle,
            start=_START,
            end=_END,
            expected_preregistration_sha256=_PREREGISTRATION_SHA256,
        )


def test_materialization_accepts_exact_supplemental_instrument(tmp_path: Path) -> None:
    """A separately verified metadata supplement may close an exact anti-join."""
    trade = _trade(0, "BTC-8AUG25-110-C")
    bundle = _bundle(tmp_path, [trade], [_instrument(name="BTC-8AUG25-120-C")])
    supplement = tmp_path / "supplement.parquet"
    pd.DataFrame([asdict(_instrument(name="BTC-8AUG25-110-C"))]).to_parquet(
        supplement, index=False
    )

    hourly, audit = materialize_registered_hourly_flow(
        bundle,
        start=_START,
        end=_END,
        expected_preregistration_sha256=_PREREGISTRATION_SHA256,
        supplemental_instruments_path=supplement,
    )

    assert hourly.iloc[0]["eligible_trade_count"] == 1
    assert audit.unmatched_instrument_rows == 0
    assert audit.supplemental_instruments == file_evidence(supplement)


def test_materialization_rejects_manifest_authority_or_file_drift(
    tmp_path: Path,
) -> None:
    """Source materialization must fail closed on authority or byte drift."""
    instrument = _instrument()
    bundle = _bundle(tmp_path, [_trade(0, instrument.instrument_name)], [instrument])
    manifest = bundle / "manifest.json"
    payload = pd.read_json(manifest, typ="series").to_dict()
    payload["execution_authority"] = "live"
    write_json(manifest, payload)

    with pytest.raises(ValueError, match="execution authority"):
        materialize_registered_hourly_flow(
            bundle,
            start=_START,
            end=_END,
            expected_preregistration_sha256=_PREREGISTRATION_SHA256,
        )


def test_materialization_accepts_resolved_parent_page_truncation(
    tmp_path: Path,
) -> None:
    """A split parent is not an unresolved terminal truncation."""
    instrument = _instrument()
    trades = [_trade(index, instrument.instrument_name) for index in range(20)]
    bundle = _bundle(tmp_path, trades, [instrument])
    manifest = bundle / "manifest.json"
    payload = pd.read_json(manifest, typ="series").to_dict()
    payload["coverage"]["raw_trade_pages"] = 3
    payload["coverage"]["truncated_pages"] = 1
    write_json(manifest, payload)

    hourly, audit = materialize_registered_hourly_flow(
        bundle,
        start=_START,
        end=_END,
        expected_preregistration_sha256=_PREREGISTRATION_SHA256,
    )

    assert hourly.iloc[0]["eligible_trade_count"] == 20
    assert audit.raw_trade_pages_verified == 3


def _instrument(name: str = "BTC-8AUG25-110-C") -> OptionInstrument:
    return OptionInstrument(
        instrument_name=name,
        creation_timestamp_ms=int((_START - pd.Timedelta(days=30)).timestamp() * 1000),
        expiration_timestamp_ms=int((_START + pd.Timedelta(days=7)).timestamp() * 1000),
        strike=110.0 if "-110-" in name else 120.0,
        option_type="call",
        contract_size=1.0,
    )


def _trade(
    index: int,
    instrument_name: str,
    *,
    iv: float = 80.0,
    block_trade_id: str | None = None,
) -> OptionTrade:
    return OptionTrade(
        trade_id=f"trade-{index}",
        trade_seq=index,
        instrument_name=instrument_name,
        timestamp_ms=int((_START + pd.Timedelta(minutes=10)).timestamp() * 1000)
        + index,
        direction="buy",
        amount=1.0,
        price=0.01,
        index_price=100.0,
        mark_price=0.01,
        iv=iv,
        tick_direction=1,
        block_trade_id=block_trade_id,
        block_rfq_id=None,
        combo_id=None,
        combo_trade_id=None,
    )


def _bundle(
    tmp_path: Path,
    trades: list[OptionTrade],
    instruments: list[OptionInstrument],
) -> Path:
    bundle = tmp_path / "bundle"
    raw = bundle / "raw" / "trades"
    raw.mkdir(parents=True)
    pd.DataFrame([asdict(value) for value in trades]).to_parquet(
        bundle / "trades.parquet", index=False
    )
    pd.DataFrame([asdict(value) for value in instruments]).to_parquet(
        bundle / "instruments.parquet", index=False
    )
    (bundle / "raw" / "instruments.json.gz").write_bytes(b"instrument-source")
    (raw / "page_000001.json.gz").write_bytes(b"trade-source")
    files = {
        str(path.relative_to(bundle)): file_evidence(path)
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }
    write_json(bundle / "manifest.json", _manifest(trades, instruments, files))
    return bundle


def _manifest(
    trades: list[OptionTrade],
    instruments: list[OptionInstrument],
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "deribit_btc_option_flow_source_bundle_v1",
        "source": "deribit_official_btc_option_trades",
        "symbol": "BTC",
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
        "context": {
            "execution_authority": "none",
            "candidate_outcomes_inspected_before_acquisition": False,
            "live_change_authorized": False,
            "preregistration": {"sha256": _PREREGISTRATION_SHA256},
        },
        "coverage": {
            "start_timestamp_ms": int(_START.timestamp() * 1000),
            "end_timestamp_ms_exclusive": int(_END.timestamp() * 1000),
            "trade_rows": len(trades),
            "instrument_rows": len(instruments),
            "raw_trade_pages": 1,
            "truncated_pages": 0,
        },
        "requests": [{"page": 1, "normalized": True}],
        "files": files,
    }
