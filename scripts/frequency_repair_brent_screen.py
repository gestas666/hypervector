"""Capture and screen the declared Brent alternative using unchanged mechanisms."""

from __future__ import annotations

import argparse
from pathlib import Path

import frequency_repair_inputs as inputs
import frequency_repair_reversion_screen as reversion
import frequency_repair_screen as channel
from hypervector.data.oxa_storage import file_evidence, write_immutable_json

SYMBOL = "xyz:BRENTOIL"


def main() -> None:
    """Run the fixed alternate-asset experiment without loading credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.input_dir.exists():
        raise FileExistsError("Brent experiment requires unused input and output paths")
    args.input_dir.mkdir(parents=True)
    captured = inputs.capture_symbol(SYMBOL, args.input_dir)
    write_immutable_json(
        args.input_dir / "manifest.json",
        {
            "symbol": captured,
            "execution_authority": "none",
            "start_utc": inputs.START.isoformat(),
            "end_exclusive_utc": inputs.END.isoformat(),
        },
    )
    channel.VENUE_MAX[SYMBOL] = 20
    cases = channel.evaluate_symbol(args.input_dir, SYMBOL)
    cases.extend(reversion.evaluate(args.input_dir, SYMBOL))
    sources = [
        Path(__file__),
        Path(inputs.__file__),
        Path(channel.__file__),
        Path(reversion.__file__),
        Path("docs/research/frequency-brent-extension-protocol-20260907.md"),
    ]
    sources.extend(sorted(args.input_dir.rglob("*.parquet")))
    write_immutable_json(
        args.out,
        {
            "cases": cases,
            "execution_authority": "none",
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "evidence": {str(path.resolve()): file_evidence(path) for path in sources},
            "limitations": [
                "Exploratory alternate-asset selection, not untouched OOS.",
                "Conditional OHLC fills; source, mark, latency and depth limitations remain.",
            ],
        },
    )


if __name__ == "__main__":
    main()
