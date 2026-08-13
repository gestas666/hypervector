"""Evidence contract for reconsidered strategy families."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_REPORT = Path("docs/research-journal/retired-strategy-reexamination-v1.json")
_ETH_COMPARISON = Path(
    "data/logs/research/lean_successor_portfolio_comparison_20260809T161609Z.json"
)
_SOURCE_REPLAY = Path(
    "data/logs/research/source_follow_deployed_shape_btc_1y_20260804.json"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _provider(path: str, strategy_id: str) -> object:
    config = load_multi_asset_live_config(Path(path), mode="observe")
    return next(row for row in config.providers if row.strategy_id == strategy_id)


def test_reexamination_separates_defects_from_negative_economics() -> None:
    """A failed route must not be mislabeled as a software defect."""
    report = _load(_REPORT)
    cases = {row["strategy"]: row for row in report["cases"]}

    assert cases["HYPE native breakout/onset"]["classification"] == (
        "experiment_identity_contamination"
    )
    assert cases["HIP-3 pressure v1/v2"]["classification"] == "confirmed_defect"
    assert cases["SOL Range Onset"]["classification"] == (
        "confirmed_stop_defect_and_valid_sparse_signal"
    )
    assert cases["ETH precompression pullback"]["classification"] == (
        "valid_but_inferior_same_clock_alternative"
    )
    assert cases["BTC Source Follow"]["classification"] == "negative_economics"
    assert cases["HIP-3 Swing/HA"]["classification"] == "negative_economics"
    assert report["execution_authority"] == "none"


def test_hype_identity_was_reused_across_incompatible_route_scopes() -> None:
    """HYPE-only and four-asset experiments must not share one scorecard."""
    strategy_id = "hype_breakout_onset_bidirectional_v1"
    native = _provider("configs/multi_asset_bidirectional_canary.toml", strategy_id)
    transfer = _provider(
        "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml",
        strategy_id,
    )

    assert native.symbols == ("HYPE",)
    assert transfer.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert native.execution.maximum_hold_policy == "extend_while_regime_supported"
    assert transfer.execution.maximum_hold_policy == "extend_while_regime_supported"


def test_eth_range_wins_same_clock_head_to_head_and_source_remains_negative() -> None:
    """Reconsideration must preserve exact comparative and deployed-shape evidence."""
    report = _load(_REPORT)
    comparison = _load(_ETH_COMPARISON)["head_to_head"]
    source = _load(_SOURCE_REPLAY)["replay"]

    for window in comparison.values():
        for friction in window.values():
            assert friction["dual_mtf_minus_pullback_net_pnl_usd"] > 0.0
    assert source["completed_trades"] == 782
    assert source["net_pnl_usd"] == pytest.approx(-17.82370190128165)
    assert source["profit_factor"] == pytest.approx(0.6193340501086962)
    assert str(_ETH_COMPARISON) in report["evidence_paths"]
    assert str(_SOURCE_REPLAY) in report["evidence_paths"]
