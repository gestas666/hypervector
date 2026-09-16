"""Run a finite passive watch of explicitly pinned public research collectors."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.prospective_collector_health import load_pins, observe_collector
from hypervector.research.prospective_collector_watch import run_health_watch


def main() -> int:
    """Retain exact input pins, observe health and return a nonzero alert status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    args = parser.parse_args()
    pins = load_pins(args.pins)
    write_immutable_json(args.output / "pins.json", {
        "input": {"path": str(args.pins.resolve()), **file_evidence(args.pins)},
        "collectors": [{**asdict(pin), "root": str(pin.root)} for pin in pins],
        "execution_authority": "none", "outcomes_evaluated": False,
    })
    result = run_health_watch(lambda: [observe_collector(pin) for pin in pins],
                              args.output, duration_seconds=args.duration_seconds)
    print(json.dumps({"status": result["status"], "result": str(args.output / "result.json")}), flush=True)
    return 2 if result["status"] == "alert" else 0


if __name__ == "__main__":
    raise SystemExit(main())
