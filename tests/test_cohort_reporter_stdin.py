"""Report-only processes must not inherit the interactive terminal's input."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("boundary", ["checkpoint", "research_worker"])
def test_reporter_input_is_independent_of_launcher(
    tmp_path: Path, boundary: str,
) -> None:
    """Real child interpreters receive EOF instead of consuming launcher input."""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    probe = (
        "import json,sys; print(json.dumps({'ok':True,"
        "'ingest':{'stdin_eof':sys.stdin.read(1)==''}}))"
    )
    controller = """
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
command = [sys.executable, '-c', sys.argv[4]]
if sys.argv[2] == 'checkpoint':
    import multi_asset_bidirectional_canary_tui as module
    module._CHECKPOINT_LOG = Path(sys.argv[3]) / 'reporter.log'
    process = module._start_checkpoint_monitor(tuple(command))
    assert process.wait(timeout=10) == 0
    print(module._CHECKPOINT_LOG.read_text())
else:
    import multi_asset_bidirectional_live_checkpoint as module
    module._research_worker_command = lambda *args: command
    result = module._sync_research_database(Path('unused.db'), Path('unused'))
    print(json.dumps({'ingest': result}))
"""
    result = subprocess.run(
        [sys.executable, "-c", controller, str(scripts), boundary, str(tmp_path), probe],
        input="launcher input",
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert json.loads(result.stdout)["ingest"]["stdin_eof"] is True
