from __future__ import annotations

import hashlib
from pathlib import Path

from hypervector.research.cross_asset_residual_provenance import (
    build_residual_generator_identity,
)


def test_generator_identity_binds_every_runtime_module_and_runner() -> None:
    runner = Path("scripts/cross_asset_residual_exit_surface.py")

    identity = build_residual_generator_identity(runner)

    modules = identity["generator_modules"]
    assert str(runner) in modules
    assert "src/hypervector/research/cross_asset_residual_replay.py" in modules
    assert "src/hypervector/research/cross_asset_residual_screen.py" in modules
    assert "src/hypervector/research/cross_asset_residual_gap_audit.py" in modules
    assert "src/hypervector/research/cross_asset_residual_report.py" in modules
    assert len(modules) == 9
    for relative_path, evidence in modules.items():
        payload = Path(relative_path).read_bytes()
        assert evidence["bytes"] == len(payload)
        assert evidence["sha256"] == hashlib.sha256(payload).hexdigest()
