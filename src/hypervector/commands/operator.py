"""Reviewable operator requests for an explicitly selected cohort run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hypervector.commands.common import CommandRefused
from hypervector.live.cohort_operator_requests import build_request, publish_request


def cmd_operator_request(args: argparse.Namespace) -> int:
    """Dry-run by default; publishing live requests requires both authority flags."""
    if (
        args.submit
        and args.request_action != "stage_profile"
        and not (args.enabled and args.i_accept_live_risk)
    ):
        raise CommandRefused(
            "operator request refused: publication requires both --enabled and "
            "--i-accept-live-risk"
        )
    try:
        settings = (
            json.loads(Path(args.settings).read_text()) if args.settings else None
        )
        request = build_request(
            run_id=args.run_id,
            profile_fingerprint=args.profile_fingerprint,
            action=args.request_action,
            symbol=args.symbol,
            provider=args.provider,
            side=args.side,
            settings=settings,
        )
        path = publish_request(Path(args.inbox), request) if args.submit else None
    except (OSError, ValueError) as exc:
        raise CommandRefused(f"operator request refused: {exc}") from exc
    print(
        json.dumps(
            {
                "dry_run": not args.submit,
                "request": request,
                "path": str(path) if path else None,
                "execution_result": "not_observed",
            },
            indent=2,
        )
    )
    return 0
