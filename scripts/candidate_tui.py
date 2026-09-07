"""Open the seven-asset V89 candidate with public data and no order authority."""

import argparse
from pathlib import Path
import tempfile

from multi_asset_bidirectional_canary_tui import run_supervisor

from hypervector.live.cohort_candidate_preview import build_candidate_preview

_CONFIG = Path("configs/multi_asset_growth_first_5000_noncrypto_research_v89.toml")
_OUTPUT_PARENT = Path("data/observe/candidate_tui")


def main() -> int:
    """Start an isolated observer cockpit; quitting stops only its owned observer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument(
        "--backtest-lab-root", type=Path, default=Path("../backtest-lab/backtest_lab")
    )
    args = parser.parse_args()
    _OUTPUT_PARENT.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="preview-", dir=_OUTPUT_PARENT)).resolve()
    launch = build_candidate_preview(args.config, root, args.backtest_lab_root)
    print(
        f"Candidate cockpit: {launch.config.profile_id}; EXECUTION DISARMED", flush=True
    )
    print(f"Observation and audit directory: {root}", flush=True)
    return run_supervisor(launch)


if __name__ == "__main__":
    raise SystemExit(main())
