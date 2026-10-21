"""Options for the read-only rolling cohort checkpoint service."""

from __future__ import annotations

import argparse
from pathlib import Path

_DEFAULT_LEDGER_ROOT = Path("data/live/bidirectional_cohort")
_DEFAULT_OUTPUT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_RESEARCH_SYNC_MIN_PENDING_BYTES = 4 * 1024 * 1024
_RESEARCH_SYNC_MAX_AGE_SECONDS = 600.0


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable rolling checkpoint CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", type=Path, default=_DEFAULT_LEDGER_ROOT)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="exact cohort profile the observed run uses",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--follow-latest-run", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    _add_research_options(parser)
    parser.add_argument("--venue-portfolio", action="store_true")
    parser.add_argument(
        "--current-run-only",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="bound publication to the explicitly selected live run",
    )
    parser.add_argument("--once", action="store_true")
    return parser


def _add_research_options(parser: argparse.ArgumentParser) -> None:
    """Declare bounded analytical synchronization and accounting inputs."""
    parser.add_argument("--research-database", type=Path)
    parser.add_argument("--accounting-epoch-bundle", type=Path)
    parser.add_argument("--research-sync-interval-seconds", type=float, default=600.0)
    parser.add_argument(
        "--research-sync-min-pending-bytes",
        type=int,
        default=_RESEARCH_SYNC_MIN_PENDING_BYTES,
        help="defer a continuous research import until this many ledger bytes "
        "are pending, unless a fill is pending or the maximum age passed; "
        "0 imports at every interval",
    )
    parser.add_argument(
        "--research-sync-max-age-seconds",
        type=float,
        default=_RESEARCH_SYNC_MAX_AGE_SECONDS,
        help="import pending ledger evidence at least this often",
    )
