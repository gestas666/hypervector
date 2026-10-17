"""LivePolicy fail-closed gates (no network)."""

from __future__ import annotations

import json

import pytest

from hypervector.cli import main
from hypervector.live.policy import LivePolicy, LivePolicyError, live_policy_from_env


def test_require_start_fails_when_disabled():
    p = LivePolicy(enabled=False, armed=True, secrets_present=True)
    with pytest.raises(LivePolicyError, match="enabled"):
        p.require_start()


def test_require_start_fails_when_unarmed():
    p = LivePolicy(enabled=True, armed=False, secrets_present=True)
    with pytest.raises(LivePolicyError, match="armed"):
        p.require_start()


def test_require_start_fails_without_secrets():
    p = LivePolicy(enabled=True, armed=True, secrets_present=False)
    with pytest.raises(LivePolicyError, match="secrets"):
        p.require_start()


def test_require_start_ok_when_all_gates_pass():
    p = LivePolicy(enabled=True, armed=True, secrets_present=True)
    p.require_start()  # no raise


def test_require_notional_cap():
    p = LivePolicy(max_notional_usd=100.0)
    assert p.require_notional(qty=0.001, mark_px=50_000.0) == pytest.approx(50.0)
    with pytest.raises(LivePolicyError, match="exceeds"):
        p.require_notional(qty=0.01, mark_px=50_000.0)


def test_live_policy_from_env_reads_secrets(monkeypatch):
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    p = live_policy_from_env(enabled=True, armed=True)
    assert p.secrets_present is False
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    p2 = live_policy_from_env(enabled=True, armed=True)
    assert p2.secrets_present is True
    r = p2.readiness()
    assert r["can_start"] is True
    assert r["submit_wired"] is True  # F2: exec client module present
    assert "sekrit" not in json.dumps(r)


def test_cli_live_check_refuses_start_by_default(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("HYPERVECTOR_HL_WALLET_ADDRESS", raising=False)
    monkeypatch.delenv("HYPERVECTOR_HL_API_PRIVATE_KEY", raising=False)
    rc = main(["live", "check"])
    assert rc == 0
    out = capsys.readouterr().out
    rep = json.loads(out)
    assert rep["ok"] is True
    assert rep["venue_submit"] is False
    assert rep["live"]["enabled"] is False
    assert rep["live"]["submit_wired"] is True  # F2 wired; still refuse start
    assert rep["live"]["can_start"] is False
    assert rep["start_gate"] == "refused"
    assert "sekrit" not in out


def test_cli_live_check_can_start_when_simulated(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("HYPERVECTOR_HL_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("HYPERVECTOR_HL_API_PRIVATE_KEY", "sekrit")
    rc = main(
        [
            "live",
            "check",
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    rep = json.loads(out)
    assert rep["live"]["can_start"] is True
    assert rep["start_gate"] == "ok"
    assert "sekrit" not in out
