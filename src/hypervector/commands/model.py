"""Model command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from hypervector.commands.exports import resolve_export
from hypervector.infra import ensure_data_layout

INSTALLED_FILES: tuple[str, ...] = (
    "metalabel_lgbm.txt",
    "metalabel_calibrator.joblib",
    "metalabel_metadata.json",
    "walk_forward_report.json",
)


def train_metalabel_bundle(
    *,
    export_dir: Path | str,
    data_root: Path | str,
    out_dir: Path | str | None = None,
    lookback_days: int | None = None,
    train_days: int = 45,
    test_days: int = 15,
    step_days: int | None = None,
    embargo_minutes: int = 60,
    max_hold_bars: int = 120,
    ohlcv: Any = None,
    ohlcv_provenance: dict[str, Any] | None = None,
    allow_network: bool = True,
    strict_hl_only: bool | None = None,
) -> dict[str, Any]:
    """Walk-forward LightGBM metalabel training on one strategy bundle's entries.

    Writes the model bundle (default ``<root>/models/metalabel/wf_<strategy>_<ts>``)
    and returns its report with ``bundle_dir``. Never installs. ``ohlcv`` trains
    on an already loaded window (``pipeline run`` passes its pinned frame) and
    skips the history load; ``ohlcv_provenance`` is recorded with it.
    on an already pinned window without loading history; otherwise history is
    loaded cache-first (``allow_network=False``: cache only), strict HL-only
    when ``strict_hl_only`` says so or, when ``None``, when the bundle was.
    """
    from hypervector.ml.walk_forward import run_walk_forward_metalabel

    result = run_walk_forward_metalabel(
        export_dir=Path(export_dir),
        data_root=Path(data_root),
        out_dir=Path(out_dir) if out_dir is not None else None,
        lookback_days=int(lookback_days) if lookback_days is not None else None,
        train_days=int(train_days),
        test_days=int(test_days),
        step_days=int(step_days) if step_days is not None else None,
        embargo_minutes=int(embargo_minutes),
        max_hold_bars=int(max_hold_bars),
        ohlcv=ohlcv,
        ohlcv_provenance=ohlcv_provenance,
        allow_network=bool(allow_network),
        strict_hl_only=strict_hl_only,
    )
    return {**result.report, "bundle_dir": str(Path(result.bundle_dir).resolve())}


def cmd_model_train(args: argparse.Namespace) -> int:
    """Walk-forward LightGBM retrain; labels match the bundle's strategy exits.

    Failures inside training (including library errors such as LightGBM's)
    print ``{"ok": false, ...}`` JSON and exit 1.
    """
    export_path = resolve_export(args.export, args.data_root)
    root = ensure_data_layout(Path(args.data_root)).root
    try:
        report = train_metalabel_bundle(
            export_dir=export_path,
            data_root=root,
            out_dir=args.out_dir,
            lookback_days=args.lookback,
            train_days=args.train_days,
            test_days=args.test_days,
            step_days=args.step_days,
            embargo_minutes=args.embargo_minutes,
            max_hold_bars=args.max_hold_bars,
        )
    except Exception as exc:  # noqa: BLE001 - training failures are technical (exit 1)
        if os.environ.get("HYPERVECTOR_DEBUG") == "1":
            raise
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": args.command,
                    "error_type": type(exc).__name__,
                    "error": f"{type(exc).__name__}: {exc}",
                    "export_dir": str(export_path),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    bundle_dir = Path(report["bundle_dir"])
    install_path = _install_model(bundle_dir, root) if args.install else None
    # A candidate id only resolves under <root>/exports of the same data root.
    export_ref = (
        export_path.name
        if export_path.parent == (root / "exports").resolve()
        else str(export_path)
    )
    root_flag = (
        "" if Path(args.data_root) == Path("data") else f"--data-root {args.data_root} "
    )
    out = {
        **report,
        "export_dir": str(export_path),
        "installed_to": install_path,
        "env_hint": f"export HYPERVECTOR_METALABEL_ROOT={install_path or bundle_dir}",
        "paper_hint": (
            f"hypervector {root_flag}paper run --export {export_ref} "
            f"--metalabel-bundle {bundle_dir} --metalabel-mode observe"
        ),
        "artifacts": {"export": str(export_path), "model": str(bundle_dir)},
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _install_model(bundle: Path, root: Path) -> str:
    """Install the declared trained bundle files into the selected data root."""
    dest = root / "models" / "metalabel"
    dest.mkdir(parents=True, exist_ok=True)
    for name in INSTALLED_FILES:
        src = bundle / name
        if src.is_file():
            shutil.copy2(src, dest / name)
    return str(dest.resolve())
