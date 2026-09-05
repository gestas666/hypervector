"""Tests for the source- and generator-bound BTC DVOL-VRP publisher."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from btc_dvol_vrp_fixtures import dvol_vrp_dvol, dvol_vrp_market
from hypervector.data.oxa_storage import file_evidence


def test_dvol_vrp_experiment_script_exists() -> None:
    """The exact replay requires one immutable publisher entry point."""
    assert Path("scripts/v58_btc_dvol_vrp_experiment.py").is_file()


def test_command_publishes_source_bound_complete_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exact inputs and generators must remain bound through publication."""
    module = _load_module()
    registration, _ = _write_registration(tmp_path, module)
    bars = dvol_vrp_market(150)
    dvol = dvol_vrp_dvol(bars)
    monkeypatch.setattr(
        module, "frozen_btc_dvol_vrp_partitions", _short_partitions(module)
    )
    monkeypatch.setattr(module, "_load_inputs", lambda *_: (bars, dvol))
    output = tmp_path / "result"
    args = module.build_parser().parse_args(
        ["--input-registration", str(registration), "--output", str(output)]
    )

    published = module.run_command(args)

    report = json.loads((published / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
    assert published == output
    assert report["hypothesis_id"] == "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1"
    assert report["authority"]["execution_authority"] == "none"
    assert report["live_promotion_authorized"] is False
    assert len(report["summary_rows"]) == 54
    assert set(manifest["files"]) == {"report.json", "trades.parquet"}
    assert report["generator_identity"]["aggregate_sha256"]
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


@pytest.mark.parametrize(
    ("authority", "inspected", "message"),
    [("live", False, "acquired authority"), ("none", True, "not outcome-blind")],
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
    """Changed source bytes or registered generator hashes fail closed."""
    module = _load_module()
    registration, bars = _write_registration(tmp_path / "source", module)
    bars.write_bytes(bars.read_bytes() + b"drift")
    args = module.build_parser().parse_args(
        ["--input-registration", str(registration), "--output", str(tmp_path / "out")]
    )
    with pytest.raises(ValueError, match="bytes changed"):
        module.run_command(args)

    registration, _ = _write_registration(
        tmp_path / "generator", module, generator_drift=True
    )
    args = module.build_parser().parse_args(
        ["--input-registration", str(registration), "--output", str(tmp_path / "out2")]
    )
    with pytest.raises(ValueError, match="generator identity drifted"):
        module.run_command(args)


def test_deribit_manifest_binds_raw_pages_and_normalized_parquet(
    tmp_path: Path,
) -> None:
    """A changed raw official page must invalidate the registered source bundle."""
    module = _load_module()
    bundle = tmp_path / "deribit"
    raw = bundle / "raw"
    raw.mkdir(parents=True)
    page = raw / "page_0001.json"
    page.write_bytes(b'{"jsonrpc":"2.0"}')
    dvol = bundle / "dvol.parquet"
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=2, freq="h", tz="UTC"),
            "open": [60.0, 60.0],
            "high": [61.0, 61.0],
            "low": [59.0, 59.0],
            "close": [60.0, 60.0],
        }
    ).to_parquet(dvol, index=False)
    manifest = bundle / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "deribit_btc_dvol_hourly_bundle_v1",
                "execution_authority": "none",
                "candidate_outcomes_computed": False,
                "files": {
                    "raw/page_0001.json": file_evidence(page),
                    "dvol.parquet": file_evidence(dvol),
                },
            }
        ),
        encoding="utf-8",
    )
    sources = {
        "deribit_dvol_manifest": _evidence(manifest),
        "deribit_dvol_parquet": _evidence(dvol),
    }

    loaded = module._load_deribit_dvol(sources)

    assert len(loaded) == 2
    page.write_bytes(page.read_bytes() + b"drift")
    with pytest.raises(ValueError, match="evidence"):
        module._load_deribit_dvol(sources)


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
    preregistration.write_text(json.dumps(_preregistration()), encoding="utf-8")
    manifest = root / "dvol-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    dvol = root / "dvol.parquet"
    dvol.write_bytes(b"dvol")
    bars = root / "bars.parquet"
    bars.write_bytes(b"bars")
    funding = root / "funding.parquet"
    funding.write_bytes(b"funding")
    generators = module._generator_identity(Path.cwd())
    if generator_drift:
        generators = {**generators, "aggregate_sha256": "0" * 64}
    registration = root / "registration.json"
    registration.write_text(
        json.dumps(
            {
                "schema_version": "v58_btc_dvol_vrp_continuation_long_input_registration_v1",
                "hypothesis_id": "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1",
                "status": "inputs_hash_bound_before_candidate_signal_or_return_results",
                "authority": {"report_only": True, "execution_authority": authority},
                "change_scope": {
                    "candidate_signal_count_inspected": inspected,
                    "candidate_returns_inspected": False,
                    "candidate_pnl_inspected": False,
                },
                "preregistration": _evidence(preregistration),
                "source_evidence": {
                    "deribit_dvol_manifest": _evidence(manifest),
                    "deribit_dvol_parquet": _evidence(dvol),
                    "hyperliquid_btc_1m_bars": _evidence(bars),
                    "hyperliquid_btc_hourly_funding": _evidence(funding),
                },
                "generator_identity": generators,
            }
        ),
        encoding="utf-8",
    )
    return registration, bars


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v58_btc_dvol_vrp_continuation_long_preregistration_v1",
        "hypothesis_id": "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1",
        "status": "preregistered_before_source_acquisition_or_outcomes",
        "execution_authority": "none",
        "outcomes_inspected_before_preregistration": False,
        "candidate_signal_counts_inspected": False,
        "candidate_forward_returns_inspected": False,
        "candidate_trade_outcomes_inspected": False,
    }


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
        module.BtcDvolVrpPartition(name, boundaries[index], boundaries[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    return lambda: partitions


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_dvol_vrp_experiment.py")
    spec = importlib.util.spec_from_file_location(
        "btc_dvol_vrp_experiment_script", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
