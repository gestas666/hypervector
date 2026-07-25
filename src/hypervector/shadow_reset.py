"""Recoverable reset for Hypervelocity shadow portfolio telemetry."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hypervector.runtime_lock import hypervelocity_runtime_lock

SHADOW_TARGETS = (
    Path("paper/decisions/decisions.jsonl"),
    Path("paper/hypervelocity-shadow.log"),
)


@dataclass(frozen=True)
class ShadowResetReport:
    """Auditable result of a dry-run or confirmed shadow reset."""

    dry_run: bool
    data_root: Path
    target_files: tuple[Path, ...]
    backup_dir: Path | None
    backed_up_files: tuple[Path, ...]

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe reset telemetry."""
        return {
            "ok": True,
            "dry_run": self.dry_run,
            "data_root": str(self.data_root),
            "target_files": [str(path) for path in self.target_files],
            "backup_dir": str(self.backup_dir) if self.backup_dir else None,
            "backed_up_files": [str(path) for path in self.backed_up_files],
        }


def reset_shadow_state(
    data_root: Path,
    *,
    confirmed: bool,
    now: datetime | None = None,
) -> ShadowResetReport:
    """Back up and clear shadow decisions/logs, or report a dry run."""
    root = Path(data_root)
    targets = tuple(root / relative for relative in SHADOW_TARGETS)
    existing = tuple(path for path in targets if path.is_file())
    if not confirmed:
        return ShadowResetReport(True, root, targets, None, ())
    timestamp = now or datetime.now(timezone.utc)
    backup_dir = root / "backups" / _backup_name(timestamp)
    with hypervelocity_runtime_lock(root):
        backed_up = _backup_targets(root, existing, backup_dir)
        for target in existing:
            target.write_text("", encoding="utf-8")
    return ShadowResetReport(False, root, targets, backup_dir, backed_up)


def _backup_targets(
    root: Path,
    targets: tuple[Path, ...],
    backup_dir: Path,
) -> tuple[Path, ...]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    destinations: list[Path] = []
    for target in targets:
        destination = backup_dir / target.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        destinations.append(destination)
    return tuple(destinations)


def _backup_name(timestamp: datetime) -> str:
    utc = timestamp.astimezone(timezone.utc)
    return f"shadow_reset_{utc.strftime('%Y%m%dT%H%M%SZ')}"
