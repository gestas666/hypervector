"""Measure synthetic recovery memory and fresh-process CLI startup without a venue."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

from hypervector.live.cohort_candidate_entry_clock import AcceptedEntryClock

_ROW = b'{"event_type":"telemetry","payload":{}}\n'


def measure_recovery(directory: Path, sizes: list[int]) -> list[dict[str, object]]:
    """Measure fixed synthetic prefixes; tracing includes Python allocations only."""
    results = []
    ledger = directory / "synthetic.jsonl"
    for size in sizes:
        count = size // len(_ROW)
        with ledger.open("wb") as stream:
            for _ in range(count):
                stream.write(_ROW)
        tracemalloc.start()
        try:
            started = time.perf_counter()
            clock = AcceptedEntryClock(ledger, strategy_id="benchmark", symbol="BTC")
            elapsed = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        results.append(
            {
                "source_bytes": ledger.stat().st_size,
                "rows": count,
                "python_traced_peak_bytes": peak,
                "elapsed_seconds": elapsed,
                "latest_entry_ms": clock.latest_ms,
            }
        )
    return results


def measure_startup(
    samples: int, baseline_root: Path | None = None
) -> dict[str, object]:
    """Record subprocess wall time using the same interpreter and dependency set."""
    environment = dict(os.environ)
    programs = {
        "import": "import hypervector.cli",
        "help": "from hypervector.cli import build_parser; build_parser().format_help()",
    }
    if baseline_root is not None:
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(baseline_root / "src"), str(baseline_root))
        )
    else:
        programs["status"] = "from hypervector.cli import main; main(['status'])"
    result = {}
    with tempfile.TemporaryDirectory(prefix="hv-startup-") as directory:
        for name, program in programs.items():
            durations = []
            for _ in range(samples):
                started = time.perf_counter()
                subprocess.run(
                    [sys.executable, "-c", program],
                    cwd=directory,
                    env=environment,
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                durations.append(time.perf_counter() - started)
            result[name] = {
                "median_seconds": statistics.median(durations),
                "samples_seconds": durations,
            }
    return result


def main() -> int:
    """Print reproducible local observations, without claiming production latency."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    if (
        args.baseline_root
        and not (args.baseline_root / "src/hypervector/cli.py").is_file()
    ):
        parser.error("--baseline-root must contain src/hypervector/cli.py")
    with tempfile.TemporaryDirectory(prefix="hv-recovery-") as directory:
        report = {
            "scope": "synthetic Python allocation tracing and warm-cache subprocess wall times; no production latency guarantee",
            "recovery": measure_recovery(Path(directory), [2 * 1024**2, 8 * 1024**2]),
            "startup": measure_startup(args.samples),
        }
    if args.baseline_root:
        report["baseline_startup"] = measure_startup(
            args.samples, args.baseline_root.resolve()
        )
    document = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(document, encoding="utf-8")
    print(document, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
