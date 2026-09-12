"""Small immutable JSON writer shared by offline report-audit commands."""

import json
from pathlib import Path


def write(path: Path, value: object) -> None:
    """Write new inspectable evidence without replacing earlier files."""
    with path.open("x") as stream:
        stream.write(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
