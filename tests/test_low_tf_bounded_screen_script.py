"""CLI contract tests for bounded challenger development evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd


def _script() -> object:
    """Load the standalone script without executing its main entry point."""
    path = Path("scripts/low_tf_bounded_development.py")
    spec = spec_from_file_location("low_tf_bounded_development_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("bounded development script cannot be loaded")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bounded_cli_defaults_to_immutable_report_only_bundle() -> None:
    module = _script()

    args = module._parser().parse_args([])

    assert args.database == Path("data/research/market.duckdb")
    assert args.output == Path(
        "data/logs/research/low_tf_bounded_development_20260812_v3"
    )
    assert module._FRICTION_SCENARIOS == {
        "nominal_13bps": 13.0,
        "stress_20bps": 20.0,
    }


def test_bounded_l2_source_hash_changes_when_one_causal_row_changes() -> None:
    module = _script()
    frame = pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=2, freq="5min", tz="UTC"
            ),
            "value": [1.0, 2.0],
        }
    )

    before = module._frame_sha256(frame)
    frame.loc[1, "value"] = 3.0

    assert module._frame_sha256(frame) != before


def test_bounded_funding_path_uses_verified_bundle_identity() -> None:
    module = _script()

    path = module._funding_path(Path("data"), "ETH")

    assert path == Path(
        "data/cache/vendor/hyperliquid/ETH/"
        "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
    )


def test_bounded_generator_identity_hashes_exact_loaded_dependencies() -> None:
    module = _script()

    identity = module._generator_identity()

    assert identity["method"] == "exact_loaded_dependency_files_sha256_v1"
    files = identity["files"]
    assert "scripts/low_tf_bounded_development.py" in files
    assert "src/hypervector/research/low_tf_multi_asset_replay.py" in files
    assert "src/hypervector/research/low_tf_rsi_divergence.py" in files
    assert "pyproject.toml" in files
    assert "uv.lock" in files
    assert all(entry["bytes"] > 0 for entry in files.values())
    assert all(len(entry["sha256"]) == 64 for entry in files.values())


def test_bounded_generator_recheck_rejects_source_drift() -> None:
    module = _script()
    expected = module._generator_identity()
    observed = {
        **expected,
        "files": {
            **expected["files"],
            "uv.lock": {"bytes": 1, "sha256": "0" * 64},
        },
    }

    try:
        module._require_unchanged_generator(expected, observed)
    except RuntimeError as exc:
        assert "generator changed during evaluation" in str(exc)
    else:
        raise AssertionError("generator drift must fail closed")
