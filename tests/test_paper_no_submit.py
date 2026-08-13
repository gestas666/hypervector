"""Structural barriers: no testnet URL, order intents never submit-enabled (Phase 4b)."""

from __future__ import annotations

from pathlib import Path


def test_no_testnet_url_in_hl_module():
    from hypervector.data import hl

    assert "hyperliquid.xyz" in hl.HL_INFO_URL
    assert "testnet" not in hl.HL_INFO_URL.lower()
    # Mainnet info host only (no api.hyperliquid-testnet.xyz).
    assert "testnet" not in hl.HL_INFO_URL


def test_order_intent_never_submit_enabled():
    from hypervector.paper.order_intent import build_order_intent

    d = build_order_intent(symbol="X", side="buy", qty=1.0)
    assert d["submit_enabled"] is False
    assert d["schema"] == "hv_order_intent_v1"
    assert d["network"] == "mainnet"
    # Builder has no submit_enabled parameter — field is structural hard-false.
    import inspect

    assert "submit_enabled" not in inspect.signature(build_order_intent).parameters


def test_daemon_banner_matches_execution_mode():
    """Ops clarity: stderr banner must reflect shadow vs paper (HANDOFF / SRS_HV4B_MODE)."""
    from hypervector.paper.runner import PAPER_BANNER, SHADOW_BANNER, banner_for_mode

    assert banner_for_mode("shadow") == SHADOW_BANNER
    assert banner_for_mode("SHADOW") == SHADOW_BANNER
    assert banner_for_mode("paper") == PAPER_BANNER
    assert "no venue orders" in banner_for_mode("shadow").lower()
    assert "no venue orders" in banner_for_mode("paper").lower()
    assert "SHADOW" in banner_for_mode("shadow")
    assert "PAPER" in banner_for_mode("paper")


def test_paper_package_has_no_exchange_submit_imports():
    """Paper path must not import HL Exchange / order-submit clients."""
    paper_root = Path(__file__).resolve().parents[1] / "src" / "hypervector" / "paper"
    forbidden = (
        "hyperliquid.exchange",
        "from hyperliquid import Exchange",
        "import hyperliquid.exchange",
        "HyperliquidExecClient",
        "HyperliquidLiveExecClient",
    )
    offenders: list[str] = []
    for path in sorted(paper_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(
                    f"{path.relative_to(paper_root.parent.parent)}: {needle}"
                )
    assert not offenders, "forbidden submit-client imports in paper:\n" + "\n".join(
        offenders
    )
