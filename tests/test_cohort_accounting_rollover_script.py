"""CLI tests for atomic, recoverable cohort accounting rollover evidence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

from hypervector.runtime_lock import RuntimeLockError

SCRIPT = Path(__file__).parents[1] / "scripts/cohort_accounting_rollover.py"
PRIOR = Path(
    "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
)
SUCCESSOR = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")


def _load() -> ModuleType:
    spec = spec_from_file_location("cohort_accounting_rollover", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    checkpoint = tmp_path / "latest_checkpoint.json"
    preflight = tmp_path / "final_preflight.json"
    bundle = tmp_path / "prestart_bundle"
    bundle.mkdir()
    checkpoint.write_text('{"checkpoint":true}\n', encoding="utf-8")
    preflight.write_text('{"preflight":true}\n', encoding="utf-8")
    (bundle / "manifest.json").write_text(
        '{"bundle_type":"cohort_prestart_backup"}\n', encoding="utf-8"
    )
    return checkpoint, preflight, bundle


def _args(module: ModuleType, tmp_path: Path, *, yes: bool) -> object:
    checkpoint, preflight, bundle = _inputs(tmp_path)
    values = [
        "--prior-config",
        str(PRIOR),
        "--successor-config",
        str(SUCCESSOR),
        "--checkpoint",
        str(checkpoint),
        "--preflight",
        str(preflight),
        "--prestart-bundle",
        str(bundle),
        "--epoch-id",
        "growth_5000_v49",
        "--out",
        str(tmp_path / "accounting_epoch"),
    ]
    if yes:
        values.append("--yes")
    return module.build_parser().parse_args(values)


def _locks() -> tuple[object, object, list[Path]]:
    held: list[Path] = []

    @contextmanager
    def live_lock(path: Path) -> Iterator[Path]:
        held.append(path)
        yield path.parent / "process.lock"

    @contextmanager
    def checkpoint_lock(path: Path) -> Iterator[Path]:
        held.append(path)
        yield path.parent / "checkpoint.writer.lock"

    return live_lock, checkpoint_lock, held


def _build_report(*args: object, **kwargs: object) -> dict[str, object]:
    assert kwargs["epoch_id"] == "growth_5000_v49"
    assert kwargs["checkpoint_evidence"]["path"] == "final_checkpoint.json"
    assert kwargs["preflight_evidence"]["path"] == "final_preflight.json"
    assert args[2] == {"checkpoint": True}
    assert args[3] == {"preflight": True}
    return {"schema_version": 1, "accounting_epoch": {"epoch_id": "growth_5000_v49"}}


def test_confirmed_rollover_publishes_one_immutable_evidence_bundle(
    tmp_path: Path,
) -> None:
    module = _load()
    args = _args(module, tmp_path, yes=True)
    live_lock, checkpoint_lock, held = _locks()

    report = module.run_rollover(
        args,
        live_lock_fn=live_lock,
        checkpoint_lock_fn=checkpoint_lock,
        verify_backup_fn=lambda _: {"bundle_type": "cohort_prestart_backup"},
        build_report_fn=_build_report,
        now_fn=lambda: datetime(2026, 8, 12, 23, tzinfo=UTC),
    )

    output = Path(args.out)
    assert report["accounting_epoch"]["epoch_id"] == "growth_5000_v49"
    assert json.loads((output / "manifest.json").read_text()) == report
    assert (output / "final_checkpoint.json").read_bytes() == b'{"checkpoint":true}\n'
    assert (output / "final_preflight.json").read_bytes() == b'{"preflight":true}\n'
    assert held[0].name == "decisions.jsonl"
    assert held[1] == Path(args.checkpoint)


def test_rollover_is_dry_run_by_default(tmp_path: Path) -> None:
    module = _load()
    args = _args(module, tmp_path, yes=False)
    live_lock, checkpoint_lock, _ = _locks()

    module.run_rollover(
        args,
        live_lock_fn=live_lock,
        checkpoint_lock_fn=checkpoint_lock,
        verify_backup_fn=lambda _: {"bundle_type": "cohort_prestart_backup"},
        build_report_fn=_build_report,
        now_fn=lambda: datetime(2026, 8, 12, 23, tzinfo=UTC),
    )

    assert not Path(args.out).exists()


def test_rollover_refuses_an_active_checkpoint_writer(tmp_path: Path) -> None:
    module = _load()
    args = _args(module, tmp_path, yes=True)
    live_lock, _, _ = _locks()

    @contextmanager
    def active_writer(_: Path) -> Iterator[Path]:
        raise RuntimeLockError("checkpoint writer already running")
        yield Path("unreachable")

    try:
        module.run_rollover(
            args,
            live_lock_fn=live_lock,
            checkpoint_lock_fn=active_writer,
            verify_backup_fn=lambda _: {"bundle_type": "cohort_prestart_backup"},
            build_report_fn=_build_report,
            now_fn=lambda: datetime(2026, 8, 12, 23, tzinfo=UTC),
        )
    except RuntimeLockError as exc:
        assert "checkpoint writer already running" in str(exc)
    else:
        raise AssertionError("active checkpoint writer was accepted")
    assert not Path(args.out).exists()
