"""Replay declared native acquisition packets; never construct signing or venue clients."""

import argparse
import json
from pathlib import Path
import sys

from eth_account import Account
from hyperliquid.exchange import Exchange


def deny_network(event: str, args: tuple[object, ...]) -> None:
    """Reject connection, DNS and datagram operations throughout this offline command."""
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
        raise RuntimeError("native replay command forbids network operations")


def deny_execution(*args: object, **kwargs: object) -> None:
    """Reject constructing a real exchange client or account signer."""
    raise RuntimeError("native replay command forbids signing and live SDK construction")


def main(argv: list[str] | None = None) -> int:
    """Run a source-bound scenario into a new native telemetry directory and report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    project = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(project / "src"), str(project)]
    from hypervector.research.native_replay_packets import run_packet_scenario

    sys.addaudithook(deny_network)
    Exchange.__init__ = deny_execution
    Account.from_key = deny_execution
    result = run_packet_scenario(args.scenario, args.output)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "scope",
                    "completed_packets",
                    "filled_orders",
                    "equity_usd",
                    "execution_authority",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
