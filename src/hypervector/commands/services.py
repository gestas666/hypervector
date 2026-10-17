"""Nested public operator-service commands without checkout-relative imports."""

from __future__ import annotations
import argparse


def cmd_supervisor(args: argparse.Namespace) -> int:
    """Forward an explicit supervisor action, preserving its ownership boundaries."""
    from hypervector_supervision.cohort_backend_supervisor import CLI_PROG, main

    return main(args.arguments, prog=CLI_PROG)
