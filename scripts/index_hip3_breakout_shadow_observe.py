"""Run an exact report-only SP500 or SPCX pre-close pressure observer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from hypervector.live.hip3_breakout_shadow_observer import (
    ObserverDefaults,
    main_for,
)
from hypervector.live.hip3_breakout_shadow_specs import (
    SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC,
    Hip3BreakoutShadowSpec,
)

_SPECS = {
    SP500_SHADOW_SPEC.symbol: SP500_SHADOW_SPEC,
    SPCX_SHADOW_SPEC.symbol: SPCX_SHADOW_SPEC,
}


def build_selector() -> argparse.ArgumentParser:
    """Build the exact index-route selector without execution flags."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--symbol", choices=tuple(_SPECS), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Select one isolated index route and run its unsigned observer."""
    selected, remaining = build_selector().parse_known_args(argv)
    spec = _SPECS[selected.symbol]
    return main_for(spec, _defaults(spec), argv=remaining)


def _defaults(spec: Hip3BreakoutShadowSpec) -> ObserverDefaults:
    token = spec.symbol.lower()
    slug = token.replace(":", "_")
    return ObserverDefaults(
        asset=Path(f"data/live/research/{token}_fresh15_v3.jsonl"),
        cohort=Path(f"data/live/research/{slug}_unused_cohort.jsonl"),
        cursor=Path(f"data/runtime/research/{slug}_fresh15_v3_cursor.json"),
        journal=Path(f"data/live/research/{slug}_fresh15_v3_decisions.jsonl"),
        status=Path(f"data/runtime/research/{slug}_fresh15_v3_latest.json"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
