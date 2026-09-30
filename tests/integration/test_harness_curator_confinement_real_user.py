"""The confinement on a real user of this machine: the probe runs as that user from the code image, writes the area
it is handed, and reports what it can read.

Runs as root on a machine with the user `CONFINEMENT_TEST_USER` (default `raven-worker`); the image is built in the
default image folder, or reused when it is already there.
"""

import os
import pwd
import shutil
import tempfile
from pathlib import Path

import pytest

from experimental.curator.raven_adapter.confinement import Confinement

USER = os.environ.get("CONFINEMENT_TEST_USER", "raven-worker")
REPOSITORY = Path(__file__).resolve().parents[2]


def _user_exists() -> bool:
    try:
        pwd.getpwnam(USER)
    except KeyError:
        return False
    return True


pytestmark = pytest.mark.skipif(os.geteuid() != 0 or not _user_exists(), reason=f"needs root and the user {USER}")


def test_the_probe_runs_as_the_user_from_the_image_and_reports_what_it_reaches():
    confinement = Confinement.of(USER, REPOSITORY)
    place = Path(tempfile.mkdtemp(prefix="raven-confinement-test-"))
    try:
        place.chmod(0o755)
        area, shown, private = place / "area", place / "shown.md", place / "private.md"
        area.mkdir()
        shown.write_text("anyone may read this")
        shown.chmod(0o644)
        private.write_text("root only")
        private.chmod(0o600)
        confinement.hand_over(area)
        assert confinement.probe(writable=[area], closed=[private]) == []
        assert confinement.probe(writable=[place], unlisted=[place], closed=[shown]) == [
            f"cannot write {place}: Permission denied",
            f"can list {place}",
            f"can read {shown}",
        ]
        assert os.stat(area).st_uid == confinement.uid
    finally:
        shutil.rmtree(place)
