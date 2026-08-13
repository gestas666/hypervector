"""CLI contract tests for the lean successor comparison."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path("scripts/lean_successor_portfolio.py")


def _load() -> ModuleType:
    """Load the command without invoking its entry point."""
    spec = spec_from_file_location("lean_successor_portfolio_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load lean successor command")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_binds_local_sources_and_requires_output() -> None:
    """The command must default to immutable local evidence and explicit output."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "result.json"])

    assert args.range_context.name.endswith("_v2.json")
    assert args.eth_bars.name == "ETH_1m_365d.parquet"
    assert args.hip3_sidecar.name.endswith(".trades.parquet")
    assert len(args.sol_artifact) == 12
    assert args.out == Path("result.json")


def test_fixed_contract_has_four_variants_and_two_common_windows() -> None:
    """Route composition and evidence windows may not drift during execution."""
    module = _load()

    variants = module.fixed_variants()
    windows = module.fixed_windows()

    assert [row.variant_id for row in variants] == [
        "sol_range_control",
        "sol_range_spcx",
        "sol_range_spcx_eth_pullback",
        "sol_range_spcx_eth_dual_mtf",
    ]
    assert [row.window_id for row in windows] == [
        "development_common",
        "opened_final_common",
        "full_opened_descriptive",
    ]
    assert module.NOMINAL_CRYPTO_ROUND_TRIP_BPS == 13.0
    assert module.STRESS_CRYPTO_ROUND_TRIP_BPS == 20.0


def test_publish_refuses_to_overwrite_immutable_artifact(tmp_path: Path) -> None:
    """Research output must be append-only."""
    module = _load()
    path = tmp_path / "existing.json"
    path.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_artifact(path, {"execution_authority": "none"})
