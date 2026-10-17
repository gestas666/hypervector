"""Shadow command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from hypervector.paper.runner import start_paper_daemon
from hypervector.strategies.runtime_profile import load_hypervelocity_runtime_profile
from hypervector.commands.common import _ensure_root


def cmd_hypervelocity_shadow_run(args: argparse.Namespace) -> int:
    """Run the validated one-position, bidirectional Hypervelocity backend."""
    from hypervector.runtime_lock import hypervelocity_runtime_lock

    _ensure_root(args)
    try:
        profile = load_hypervelocity_runtime_profile(Path(args.config))
        with hypervelocity_runtime_lock(Path(args.data_root)):
            result = start_paper_daemon(
                export_dir=profile.export_path,
                data_root=Path(args.data_root),
                fee_tier=profile.fee_tier,
                poll_interval_secs=profile.poll_interval_seconds,
                max_live_bars=args.max_live_bars,
                lookback_days=profile.lookback_days,
                enable_funding_refresh=False,
                metalabel_enabled=profile.metalabel_mode != "off",
                metalabel_filter=False,
                metalabel_mode=profile.metalabel_mode,
                execution_mode=profile.runtime_mode,
                hypervelocity_profile=profile,
            )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"paper shadow failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "run_id": result.run_id,
                "execution_mode": result.execution_mode,
                "decisions_path": str(result.decisions_path),
                "fills_count": result.fills_count,
                "position_policy": profile.position_policy(),
                "regime_policy": profile.regime_policy(),
                "funding_authority": "hyperliquid_ws_activeAssetCtx",
                "rest_funding_refresh_enabled": False,
                "fee_tier": profile.fee_tier,
            },
            indent=2,
        )
    )
    return 0


def cmd_hypervelocity_shadow_reset(args: argparse.Namespace) -> int:
    """Dry-run or perform a backed-up Hypervelocity shadow state reset."""
    from hypervector.shadow_reset import reset_shadow_state

    try:
        report = reset_shadow_state(
            Path(args.data_root),
            confirmed=bool(args.yes),
        )
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(f"paper shadow-reset failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report.as_dict(), indent=2))
    return 0


def cmd_shadow_compare(args: argparse.Namespace) -> int:
    """Reconcile explicit shadow run IDs with a same-window real-strategy log."""
    from hypervector.research.shadow_compare import (
        compare_shadow_to_positions,
        load_real_positions,
        load_shadow_ledger,
    )

    for label, value in (
        ("shadow ledger", args.shadow_ledger),
        ("positions file", args.positions),
    ):
        if not Path(value).is_file():
            raise FileNotFoundError(f"{label} not found: {value}")
    report = compare_shadow_to_positions(
        load_shadow_ledger(args.shadow_ledger),
        load_real_positions(args.positions),
        run_ids=tuple(args.run_id),
        entry_tolerance_seconds=args.entry_tolerance_seconds,
    )
    rendered = json.dumps(report, indent=2, default=str)
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0
