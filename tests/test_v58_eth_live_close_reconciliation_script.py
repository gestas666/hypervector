"""CLI coverage for immutable V58 ETH live-close reconciliation."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence


def test_publisher_is_immutable_and_report_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI must publish once and preserve authority-none semantics."""
    script = Path("scripts/v58_eth_live_close_reconciliation.py")
    spec = importlib.util.spec_from_file_location("v58_eth_close_script", script)
    assert spec is not None and spec.loader is not None, "V58 ETH close CLI is missing"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "close.json"
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    report = {
        "mode": "v58_eth_first_live_close_reconciliation_v1",
        "contract": {"execution_authority": "none"},
    }
    monkeypatch.setattr(module, "_generator_paths", lambda: (source,))
    monkeypatch.setattr(
        module,
        "load_v58_eth_live_close_reconciliation",
        lambda *args, **kwargs: dict(report),
    )
    args = _args(output)

    published = module.publish_report(args)

    assert published["contract"]["execution_authority"] == "none"
    assert published["generator_identity"][0]["path"] == str(source.resolve())
    assert output.exists()
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(args)


def test_static_source_accepts_hash_only_immutable_manifest(tmp_path: Path) -> None:
    """A frozen manifest digest remains sufficient when bytes were not declared."""
    module = importlib.import_module(
        "hypervector.research.v58_eth_live_close_reconciliation_io"
    )
    config = tmp_path / "config.toml"
    manifest = tmp_path / "manifest.json"
    config.write_text("profile = 'v58'\n", encoding="utf-8")
    manifest.write_text('{"status":"verified"}\n', encoding="utf-8")
    config_evidence = file_evidence(config)
    manifest_evidence = file_evidence(manifest)
    sources = {
        "config": {"path": str(config), **config_evidence},
        "prestart_manifest": {
            "path": str(manifest),
            "sha256": manifest_evidence["sha256"],
        },
    }

    observed = module._verify_static_sources(sources)

    assert observed["prestart_manifest"]["bytes"] == manifest_evidence["bytes"]


def test_generator_identity_includes_transitive_ledger_accounting_modules() -> None:
    """Every module capable of changing raw close accounting must be frozen."""
    script = Path("scripts/v58_eth_live_close_reconciliation.py")
    spec = importlib.util.spec_from_file_location("v58_eth_close_generators", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    names = {path.name for path in module._generator_paths()}

    assert "cohort_lifecycle_evidence.py" in names
    assert "cohort_live_audit_values.py" in names


def _args(output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        preregistration=Path("preregistration.json"),
        preregistration_sha256="d" * 64,
        continuous=Path("continuous.json"),
        venue=Path("venue.json"),
        observer_status=Path("observer.json"),
        observer_provenance=Path("observer_provenance.json"),
        observer_provenance_sha256="e" * 64,
        out=output,
    )
