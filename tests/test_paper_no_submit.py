"""Structural barriers: no testnet URL, order intents never submit-enabled (Phase 4b)."""

from __future__ import annotations

from pathlib import Path


def test_no_testnet_url_in_hl_module():
    from hypervector.data import hl

    assert "hyperliquid.xyz" in hl.HL_INFO_URL
    assert "testnet" not in hl.HL_INFO_URL.lower()


def test_order_intent_never_submit_enabled():
    from hypervector.paper.order_intent import build_order_intent

    d = build_order_intent(symbol="X", side="buy", qty=1.0)
    assert d["submit_enabled"] is False


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
                offenders.append(f"{path.relative_to(paper_root.parent.parent)}: {needle}")
    assert not offenders, "forbidden submit-client imports in paper:\n" + "\n".join(offenders)
