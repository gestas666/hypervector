from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-trend-pullback-reacceleration-preregistration-20260821-v1.json"
)


def test_preregistration_is_report_only_and_source_bound() -> None:
    """Require exact authority and source identities before result generation."""
    payload = json.loads(_PREREGISTRATION.read_text(encoding="utf-8"))
    assert payload["hypothesis_id"] == (
        "V58_BTC_15M_TREND_PULLBACK_REACCELERATION_LONG_V1"
    )
    authority = payload["authority"]
    assert authority["execution_authority"] == "none"
    assert authority["automatic_live_change"] is False
    assert authority["runtime_strategy_changed"] is False
    for evidence in payload["source_evidence"].values():
        source = Path(evidence["path"])
        content = source.read_bytes()
        assert len(content) == evidence["bytes"]
        assert sha256(content).hexdigest() == evidence["sha256"]
