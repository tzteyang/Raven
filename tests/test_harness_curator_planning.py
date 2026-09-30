"""Planning contracts support distinct representations and explicit shared ownership."""

import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def test_public_protocol_does_not_import_raven():
    code = (
        "import sys; from experimental.curator.harness.strategies import PlanningStrategy; "
        "assert not any(name == 'raven' or name.startswith('raven.') for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], cwd=REPOSITORY, check=True, capture_output=True, text=True)
