"""Model command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from hypervector.commands.common import _ensure_root


def cmd_metalabel_train(args: argparse.Namespace) -> int:
    """Walk-forward LightGBM retrain; labels match export strategy exits."""
    from hypervector.ml.walk_forward import run_walk_forward_metalabel

    paths = _ensure_root(args)
    export_path = Path(args.export)
    if not export_path.is_dir():
        print(json.dumps({"ok": False, "error": f"export not found: {export_path}"}))
        return 1
    try:
        result = run_walk_forward_metalabel(
            export_dir=export_path,
            data_root=paths.root,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            lookback_days=int(args.lookback) if args.lookback is not None else None,
            train_days=int(args.train_days),
            test_days=int(args.test_days),
            step_days=int(args.step_days) if args.step_days is not None else None,
            embargo_minutes=int(args.embargo_minutes),
            max_hold_bars=int(args.max_hold_bars),
        )
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    install_path = (
        _install_model(result.bundle_dir, paths.root) if args.install else None
    )
    out = {
        **result.report,
        "installed_to": install_path,
        "env_hint": (
            f"export HYPERVECTOR_METALABEL_ROOT={install_path or result.bundle_dir}"
        ),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _install_model(bundle: Path, root: Path) -> str:
    """Install the declared trained bundle files into the selected data root."""
    import shutil

    dest = root / "models" / "metalabel"
    dest.mkdir(parents=True, exist_ok=True)
    for name in (
        "metalabel_lgbm.txt",
        "metalabel_calibrator.joblib",
        "metalabel_metadata.json",
    ):
        src = bundle / name
        if src.is_file():
            shutil.copy2(src, dest / name)
    report_src = bundle / "walk_forward_report.json"
    if report_src.is_file():
        shutil.copy2(report_src, dest / "walk_forward_report.json")
    return str(dest.resolve())
