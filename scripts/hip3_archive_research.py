#!/usr/bin/env python3
"""Run symbol-exact, report-only HIP-3 archive qualification."""

from __future__ import annotations

from mu_hip3_archive_research import build_parser, main, run_command

__all__ = ["build_parser", "main", "run_command"]


if __name__ == "__main__":
    raise SystemExit(main())
