from __future__ import annotations

from pathlib import Path

from hypervector.runtime_env import (
    credential_presence_from_env,
    load_dotenv_if_present,
    load_wallet_env_if_present,
)


def test_dotenv_loads_without_overwriting_process_values(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "HYPERVECTOR_HL_WALLET_ADDRESS=0xfromfile\n"
        "HYPERVECTOR_HL_API_PRIVATE_KEY='fake-test-key'\n",
        encoding="utf-8",
    )
    environment = {"HYPERVECTOR_HL_WALLET_ADDRESS": "0xexisting"}

    loaded = load_dotenv_if_present(candidates=(dotenv,), environ=environment)

    assert loaded == (dotenv.resolve(),)
    assert environment["HYPERVECTOR_HL_WALLET_ADDRESS"] == "0xexisting"
    assert environment["HYPERVECTOR_HL_API_PRIVATE_KEY"] == "fake-test-key"


def test_credential_presence_exposes_booleans_only() -> None:
    status = credential_presence_from_env(
        environ={
            "HYPERVECTOR_HL_WALLET_ADDRESS": "0xabc",
            "HYPERVECTOR_HL_API_PRIVATE_KEY": "fake-test-key",
        }
    )

    assert status.wallet_configured is True
    assert status.signing_key_configured is True
    assert "0xabc" not in repr(status)
    assert "fake-test-key" not in repr(status)


def test_wallet_only_loader_does_not_import_signing_key(tmp_path: Path) -> None:
    """Read-only preflight can consume dotenv identity without signing material."""
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "HYPERVECTOR_HL_WALLET_ADDRESS=0xfromfile\n"
        "HYPERVECTOR_HL_API_PRIVATE_KEY='must-not-load'\n",
        encoding="utf-8",
    )
    environment: dict[str, str] = {}

    loaded = load_wallet_env_if_present(candidates=(dotenv,), environ=environment)

    assert loaded == (dotenv.resolve(),)
    assert environment == {"HYPERVECTOR_HL_WALLET_ADDRESS": "0xfromfile"}


def test_selected_loader_preserves_archive_credentials_without_signing_keys(tmp_path: Path) -> None:
    """An archive request needs its own token, without loading trading authority."""
    from hypervector.runtime_env import load_selected_env_if_present

    dotenv = tmp_path / ".env"
    dotenv.write_text("OXA_API_KEY=fixture-token\nHYPERVECTOR_HL_API_PRIVATE_KEY=fixture-key\n")
    environ: dict[str, str] = {}
    load_selected_env_if_present(frozenset({"OXA_API_KEY"}), candidates=[dotenv], environ=environ)
    assert environ == {"OXA_API_KEY": "fixture-token"}
