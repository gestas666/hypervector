"""Tests for immutable Market Cipher source evidence."""

from __future__ import annotations

from pathlib import Path
import subprocess

from hypervector.research.market_cipher_source_contract import (
    audit_market_cipher_sources,
)


def _write_fixture_sources(root: Path) -> tuple[Path, Path]:
    """Create minimal prompt and executable source trees."""
    scalper = root / "mc-scalper"
    scalper.mkdir()
    (scalper / "HAND.toml").write_text(
        'id = "mc-scalper"\nmodule = "builtin:chat"\n', encoding="utf-8"
    )
    (scalper / "SKILL.md").write_text(
        "---\nruntime: prompt_only\n---\n# MC 15m Scalper\n", encoding="utf-8"
    )
    executable = root / "market-cipher-cli"
    (executable / "src" / "mcc").mkdir(parents=True)
    (executable / "config").mkdir()
    (executable / "tools" / "autotune").mkdir(parents=True)
    pine = executable / "ai_docs" / "pine-scripts"
    pine.mkdir(parents=True)
    (executable / "src" / "mcc" / "engine.py").write_text(
        "ENGINE = 'hulk_smash'\n", encoding="utf-8"
    )
    (executable / "config" / "default.toml").write_text(
        'intervals = ["30m"]\n', encoding="utf-8"
    )
    (executable / "tools" / "autotune" / "evaluate.py").write_text(
        "REPORT_ONLY = True\n", encoding="utf-8"
    )
    for name in ("cipher_a.pine", "cipher_b.pine"):
        (pine / name).write_text(f"// {name}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=executable, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=executable,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Hypervector Test"],
        cwd=executable,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=executable, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=executable, check=True)
    return scalper, executable


def test_contract_distinguishes_prompt_spec_from_executable_engine(
    tmp_path: Path,
) -> None:
    """The two source trees must retain separate identities and roles."""
    scalper, executable = _write_fixture_sources(tmp_path)

    report = audit_market_cipher_sources(scalper, executable)

    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["place_attempted"] is False
    assert report["mc_scalper"]["runtime"] == "prompt_only"
    assert report["mc_scalper"]["executable_strategy"] is False
    assert report["market_cipher_cli"]["executable_strategy"] is True
    assert len(str(report["market_cipher_cli"]["git_commit"])) == 40


def test_contract_detects_source_changes_without_reading_secrets(
    tmp_path: Path,
) -> None:
    """Relevant edits change identity while excluded secret files stay excluded."""
    scalper, executable = _write_fixture_sources(tmp_path)
    first = audit_market_cipher_sources(scalper, executable)
    (executable / ".env").write_text("PRIVATE_KEY=do-not-read\n", encoding="utf-8")
    second = audit_market_cipher_sources(scalper, executable)
    assert (
        first["market_cipher_cli"]["source_tree_sha256"]
        == second["market_cipher_cli"]["source_tree_sha256"]
    )

    (executable / "src" / "mcc" / "engine.py").write_text(
        "ENGINE = 'changed'\n", encoding="utf-8"
    )
    third = audit_market_cipher_sources(scalper, executable)
    assert (
        second["market_cipher_cli"]["source_tree_sha256"]
        != third["market_cipher_cli"]["source_tree_sha256"]
    )
    assert third["market_cipher_cli"]["worktree_dirty"] is True
    assert "PRIVATE_KEY" not in repr(third)
