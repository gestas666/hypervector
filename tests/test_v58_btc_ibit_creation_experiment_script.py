"""Tests for the source- and generator-bound IBIT experiment publisher."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from btc_ibit_creation_fixtures import ibit_market
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.blackrock_ibit_acquisition import (
    acquire_blackrock_ibit_history_bundle,
)


def test_ibit_experiment_script_exists() -> None:
    """The exact replay requires one immutable publisher entry point."""
    assert Path("scripts/v58_btc_ibit_creation_experiment.py").is_file()


def test_command_publishes_source_bound_complete_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All exact inputs and generators must remain bound through publication."""
    module = _load_module()
    registration, _ = _write_registration(tmp_path, module)
    monkeypatch.setattr(
        module,
        "frozen_btc_ibit_creation_partitions",
        _short_partitions(module),
    )
    output = tmp_path / "result"
    args = module.build_parser().parse_args(
        ["--input-registration", str(registration), "--output", str(output)]
    )

    published = module.run_command(args)

    assert published == output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report["hypothesis_id"] == "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1"
    assert report["authority"]["execution_authority"] == "none"
    assert report["live_promotion_authorized"] is False
    assert len(report["summary_rows"]) == 45
    assert set(manifest["files"]) == {"report.json", "trades.parquet"}
    assert report["generator_identity"]["aggregate_sha256"]
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


@pytest.mark.parametrize(
    "authority, inspected, message",
    [
        ("live", False, "acquired authority"),
        ("none", True, "not outcome-blind"),
    ],
)
def test_command_rejects_authority_or_outcome_inspection(
    tmp_path: Path,
    authority: str,
    inspected: bool,
    message: str,
) -> None:
    """Registration drift must fail before calculating a candidate signal."""
    module = _load_module()
    registration, _ = _write_registration(
        tmp_path,
        module,
        authority=authority,
        inspected=inspected,
    )
    args = module.build_parser().parse_args(
        ["--input-registration", str(registration), "--output", str(tmp_path / "out")]
    )

    with pytest.raises(ValueError, match=message):
        module.run_command(args)


def test_command_rejects_source_or_generator_drift(tmp_path: Path) -> None:
    """Changed bytes and changed registered generator hashes both fail closed."""
    module = _load_module()
    source_registration, bars_path = _write_registration(tmp_path / "source", module)
    bars_path.write_bytes(bars_path.read_bytes() + b"drift")
    source_args = module.build_parser().parse_args(
        [
            "--input-registration",
            str(source_registration),
            "--output",
            str(tmp_path / "source-result"),
        ]
    )
    with pytest.raises(ValueError, match="bytes changed"):
        module.run_command(source_args)

    generator_registration, _ = _write_registration(
        tmp_path / "generator",
        module,
        generator_drift=True,
    )
    generator_args = module.build_parser().parse_args(
        [
            "--input-registration",
            str(generator_registration),
            "--output",
            str(tmp_path / "generator-result"),
        ]
    )
    with pytest.raises(ValueError, match="generator identity drifted"):
        module.run_command(generator_args)


def _write_registration(
    root: Path,
    module: ModuleType,
    *,
    authority: str = "none",
    inspected: bool = False,
    generator_drift: bool = False,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    preregistration = root / "preregistration.json"
    preregistration.write_text(
        json.dumps(
            {
                "schema_version": (
                    "v58_btc_ibit_creation_persistence_long_preregistration_v1"
                ),
                "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
                "status": (
                    "preregistered_before_blackrock_source_acquisition_or_"
                    "candidate_results"
                ),
                "authority": {"report_only": True, "execution_authority": "none"},
            }
        ),
        encoding="utf-8",
    )
    addendum = root / "source-addendum.json"
    addendum.write_text(
        json.dumps(
            {
                "schema_version": (
                    "v58_btc_ibit_creation_persistence_long_source_integrity_"
                    "addendum_v1"
                ),
                "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
            }
        ),
        encoding="utf-8",
    )
    vendor = acquire_blackrock_ibit_history_bundle(
        root / "blackrock",
        lambda _: _workbook(),
        context={
            "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
            "execution_authority": "none",
            "candidate_results_inspected_before_acquisition": False,
            "preregistration": file_evidence(preregistration),
            "source_integrity_addendum": _evidence(addendum),
        },
    )
    bars, funding = _market_sources(root)
    generators = module._generator_identity(Path.cwd())
    if generator_drift:
        generators = {**generators, "aggregate_sha256": "0" * 64}
    registration = root / "registration.json"
    payload = {
        "schema_version": "v58_btc_ibit_creation_persistence_long_input_registration_v1",
        "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
        "status": "inputs_hash_bound_before_candidate_signal_or_return_results",
        "authority": {"report_only": True, "execution_authority": authority},
        "change_scope": {
            "candidate_signal_count_inspected": inspected,
            "candidate_returns_inspected": False,
            "candidate_pnl_inspected": False,
        },
        "preregistration": _evidence(preregistration),
        "source_evidence": {
            "blackrock_ibit_manifest": _evidence(vendor / "manifest.json"),
            "blackrock_ibit_raw": _evidence(vendor / "fund_data.xml"),
            "blackrock_ibit_history": _evidence(vendor / "history.parquet"),
            "source_integrity_addendum": _evidence(addendum),
            "hyperliquid_btc_1m_bars": _evidence(bars),
            "hyperliquid_btc_hourly_funding": _evidence(funding),
        },
        "generator_identity": generators,
    }
    registration.write_text(json.dumps(payload), encoding="utf-8")
    return registration, bars


def _market_sources(root: Path) -> tuple[Path, Path]:
    market = ibit_market(100)
    bars = root / "bars.parquet"
    market.drop(columns="funding_rate").reset_index(names="timestamp").to_parquet(
        bars, index=False
    )
    funding = root / "funding.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.date_range(market.index[0], market.index[-1], freq="1h"),
            "funding_rate": 0.0,
            "source": "hl_funding_history",
        }
    ).to_parquet(funding, index=False)
    return bars, funding


def _short_partitions(module: ModuleType) -> object:
    boundaries = pd.to_datetime(
        [
            "2026-08-03T12:00:00Z",
            "2026-08-04T00:00:00Z",
            "2026-08-04T12:00:00Z",
            "2026-08-05T00:00:00Z",
        ],
        utc=True,
    )
    partitions = tuple(
        module.BtcIbitCreationPartition(name, boundaries[index], boundaries[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    return lambda: partitions


def _workbook() -> bytes:
    headers = ("As Of", "NAV per Share", "Ex-Dividends", "Shares Outstanding")
    rows = (
        ("Aug 02, 2026", "30", "-", "120"),
        ("Aug 01, 2026", "30", "-", "110"),
        ("Jul 31, 2026", "30", "-", "100"),
    )
    rendered = "".join(_row(row) for row in (headers, *rows))
    return (
        '<Workbook xmlns:ss="urn:test"><Worksheet ss:Name="Historical"><Table>'
        f"{rendered}</Table></Worksheet></Workbook>"
    ).encode()


def _row(values: tuple[str, str, str, str]) -> str:
    cells = "".join(f"<Cell><Data>{value}</Data></Cell>" for value in values)
    return f"<Row>{cells}</Row>"


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_ibit_creation_experiment.py")
    spec = importlib.util.spec_from_file_location("btc_ibit_experiment_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
