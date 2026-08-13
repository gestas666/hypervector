"""Independent breadth-artifact integrity helper tests."""

from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research import cross_asset_breadth_provenance
from hypervector.research.cross_asset_breadth_artifact_validation import (
    _data_root,
    _compare_event_rows,
    _validate_contract,
    _validate_event_authority,
    _validate_generators,
)
from hypervector.research.cross_asset_impulse_artifact_validation import (
    ImpulseArtifactValidation,
)
from hypervector.research.cross_asset_breadth_models import (
    CrossAssetBreadthConfig,
    declared_breadth_folds,
)
from hypervector.research.cross_asset_breadth_provenance import (
    build_breadth_generator_identity,
    build_prior_impulse_identity,
)


def _contract_artifact() -> dict[str, object]:
    config = CrossAssetBreadthConfig()
    payload = asdict(config)
    for field in ("warmup_start", "development_start", "development_end"):
        payload[field] = getattr(config, field).isoformat()
    payload["symbols"] = list(config.symbols)
    return {
        "schema_version": "cross_asset_breadth_development_v1",
        "config": payload,
        "folds": [
            {"fold": name, "start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for name, start, end in declared_breadth_folds(config)
        ],
        "contract_identity": {
            "warmup_start_utc": config.warmup_start.isoformat(),
            "development_start_utc": config.development_start.isoformat(),
            "development_end_utc": config.development_end.isoformat(),
            "report_only": True,
            "execution_authority": "none",
        },
    }


def test_contract_validator_rejects_any_frozen_parameter_change() -> None:
    artifact = _contract_artifact()
    _validate_contract(artifact)
    config = artifact["config"]
    assert isinstance(config, dict)
    config["breadth_required"] = 4

    with pytest.raises(ValueError, match="config differs"):
        _validate_contract(artifact)


def test_event_reconciliation_detects_value_or_authority_corruption() -> None:
    expected = pd.DataFrame(
        {"report_only": [True], "execution_authority": ["none"], "value": [1.0]}
    )
    _validate_event_authority(expected)
    _compare_event_rows(expected, expected.copy())
    changed = expected.copy()
    changed.loc[0, "value"] = 2.0

    with pytest.raises(ValueError, match="causal rebuild"):
        _compare_event_rows(changed, expected)
    changed.loc[0, "execution_authority"] = "orders"
    with pytest.raises(ValueError, match="execution authority"):
        _validate_event_authority(changed)


def test_data_root_accepts_canonical_json_symbol_key_order() -> None:
    sources = {
        symbol: {"bars_path": f"data/cache/{symbol}_1m_365d.parquet"}
        for symbol in ("BTC", "ETH", "HYPE", "SOL")
    }

    assert _data_root({"source_identity": sources}) == Path("data")


def test_generator_identity_covers_shared_source_repair_and_validates() -> None:
    identity = build_breadth_generator_identity(
        Path("scripts/cross_asset_breadth_development.py")
    )

    assert _validate_generators({"generator_identity": identity}) == 12
    modules = identity["generator_modules"]
    assert isinstance(modules, dict)
    assert "src/hypervector/data/oxa_trade_bars.py" in modules
    assert (
        "src/hypervector/research/cross_asset_breadth_artifact_validation.py" in modules
    )


def test_prior_impulse_identity_is_independently_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "prior.json"
    artifact.write_text(
        '{"schema_version":"cross_asset_impulse_development_v1",'
        '"search_accounting":{"known_cumulative_selectable_cells":105}}\n',
        encoding="utf-8",
    )
    validation = ImpulseArtifactValidation(
        artifact_path=str(artifact),
        artifact_sha256="a" * 64,
        sidecar_path="events.parquet",
        sidecar_sha256="b" * 64,
        primary_cells_verified=15,
        control_cells_verified=45,
        event_rows_verified=1,
        source_files_verified=1,
        generator_modules_verified=1,
        execution_authority="none",
    )
    monkeypatch.setattr(
        cross_asset_breadth_provenance,
        "validate_cross_asset_impulse_artifact",
        lambda path: validation,
    )

    identity = build_prior_impulse_identity(artifact)

    assert identity["selectable_cells"] == 105
    assert identity["validated_primary_cells"] == 15
    assert identity["validated_control_cells"] == 45
