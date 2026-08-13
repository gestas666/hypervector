"""Generator-code provenance for cross-asset residual artifacts."""

from __future__ import annotations

from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

_MODULE_PATHS = (
    "src/hypervector/research/cross_asset_residual_data.py",
    "src/hypervector/research/cross_asset_residual_gap_audit.py",
    "src/hypervector/research/cross_asset_residual_models.py",
    "src/hypervector/research/cross_asset_residual_signal.py",
    "src/hypervector/research/cross_asset_residual_replay.py",
    "src/hypervector/research/cross_asset_residual_replay_validation.py",
    "src/hypervector/research/cross_asset_residual_report.py",
    "src/hypervector/research/cross_asset_residual_screen.py",
)


def build_residual_generator_identity(runner_path: Path) -> dict[str, object]:
    """Hash every residual runtime module plus the invoked command runner."""
    root = Path(__file__).resolve().parents[3]
    runner = runner_path if runner_path.is_absolute() else root / runner_path
    resolved_runner = runner.resolve()
    try:
        relative_runner = resolved_runner.relative_to(root)
    except ValueError as error:
        raise ValueError("residual runner must be inside the repository") from error
    relative_paths = (*_MODULE_PATHS, str(relative_runner))
    modules: dict[str, dict[str, object]] = {}
    for relative in relative_paths:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"residual generator module does not exist: {path}")
        modules[relative] = file_evidence(path)
    return {"generator_modules": modules}
