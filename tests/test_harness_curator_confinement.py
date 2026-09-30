"""A confined worker runs as a user who reaches only its own area: its code image holds the worker's code and nothing
of the evaluation, its data points into the image, its area is handed to the user without following links, its
environment carries no secret of this process, and a run is laid out so the user can neither list nor read it."""

import asyncio
import os
import pwd
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.automation.employee import AREA, BOUNDARIES, REPLICAS, seal, unsealed
from experimental.curator.harness import Task
from experimental.curator.raven_adapter.baselines import Baseline
from experimental.curator.raven_adapter.confinement import Confinement, selected
from experimental.curator.raven_adapter.worker import Worker
from raven.config.raven import RavenConfig
from raven.config.schema import Config

WORKER_CODE = [
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "LICENSE",
    "hatch_build.py",
    "raven/__init__.py",
    "agents/raven-ppt/run.py",
    "plugins-dist/ppt-engine/pyproject.toml",
    "experimental/__init__.py",
    "experimental/audience.py",
    "experimental/requirements.py",
    "experimental/curator/raven_adapter/worker.py",
    "experimental/scenario/sealed.py",
    "experimental/iteration/__init__.py",
    "experimental/iteration/compartment.py",
]
EVALUATION = [
    "experimental/iteration/session.py",
    "experimental/analyst/run.py",
    "experimental/simulation/scenarios/shop/checks.md",
    "experimental/simulation/cases/one.md",
    "experimental/notes/draft.md",
    "experimental/docs/design.md",
    "tests/test_something.py",
    ".git/config",
]


def repository(tmp_path) -> Path:
    root = tmp_path / "repo"
    for name in (*WORKER_CODE, *EVALUATION, "raven/__pycache__/x.pyc"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    return root


def confinement(tmp_path, repo=None) -> Confinement:
    return Confinement("worker", 4242, 4242, tmp_path / "image", repo or tmp_path / "repo")


def test_the_image_holds_the_worker_code_and_nothing_of_the_evaluation(tmp_path):
    repo = repository(tmp_path)
    assert sorted(path.as_posix() for path in selected(repo)) == sorted(WORKER_CODE)
    (repo / "raven" / "__init__.py").unlink()
    (repo / "raven").rename(repo / "elsewhere")
    with pytest.raises(FileNotFoundError, match="needs raven"):
        selected(repo)


def test_the_process_data_points_into_the_image_and_nothing_else_moves(tmp_path):
    repo = tmp_path / "repo"
    confined = confinement(tmp_path, repo)
    command = f"{repo}/.venv/bin/python3 {repo}/agents/raven-ppt/run.py --acp --config {tmp_path}/run/ppt.json"
    data = {"command": command, "cwd": str(repo), "roots": (f"{repo}-other/x", f"{tmp_path}/run/employee")}
    image = tmp_path / "image"
    assert confined.translate(data) == {
        "command": f"{image}/.venv/bin/python3 {image}/agents/raven-ppt/run.py --acp --config {tmp_path}/run/ppt.json",
        "cwd": str(image),
        "roots": (f"{repo}-other/x", f"{tmp_path}/run/employee"),
    }


@pytest.mark.skipif(os.geteuid() != 0, reason="handing files to another user needs root")
def test_the_area_is_handed_to_the_user_without_following_a_link_out_of_it(tmp_path):
    nobody = pwd.getpwnam("nobody")
    confined = Confinement("nobody", nobody.pw_uid, nobody.pw_gid, tmp_path / "image", tmp_path / "repo")
    outside = tmp_path / "records.json"
    outside.write_text("{}")
    area = tmp_path / "area"
    (area / "home" / "skills").mkdir(parents=True)
    (area / "home" / "skills" / "SKILL.md").write_text("sop")
    (area / "records").symlink_to(outside)
    confined.hand_over(area, tmp_path / "missing")
    for path in (area, area / "home", area / "home" / "skills" / "SKILL.md", area / "records"):
        assert os.lstat(path).st_uid == nobody.pw_uid
    assert outside.stat().st_uid == 0


def test_the_process_environment_carries_nothing_of_this_process_but_what_it_needs(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    confined = confinement(tmp_path)
    monkeypatch.setattr(Confinement, "hand_over", lambda self, *paths: None)
    options = confined.options(tmp_path / "area")
    environment = options.pop("env")
    assert options == {"user": 4242, "group": 4242, "extra_groups": [], "cwd": str(tmp_path / "area")}
    assert "OPENROUTER_API_KEY" not in environment and environment["TZ"] == "Asia/Shanghai"
    assert environment["HOME"] == str(tmp_path / "area") and (tmp_path / "area" / "tmp").is_dir()
    assert environment["PATH"].startswith(f"{tmp_path / 'image' / '.venv' / 'bin'}:")


def test_a_confined_worker_refuses_to_start_without_an_area_apart_from_its_records(tmp_path):
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "home")
    worker = Worker(
        Baseline(config, RavenConfig(), tmp_path, task=Task(text="Work")), tmp_path / "run", confinement=object()
    )
    with pytest.raises(ValueError, match="needs an area apart from its root"):
        asyncio.run(worker.start())


def test_a_sealed_run_is_passable_not_listable_and_its_boundary_log_is_append_only_to_others(tmp_path):
    previous = os.umask(0o022)
    try:
        seal(tmp_path / "run")
        (tmp_path / "run" / "references.jsonl").write_text("{}")
    finally:
        os.umask(previous)
    mode = {name: stat.S_IMODE((tmp_path / "run" / name).stat().st_mode) for name in (".", REPLICAS, BOUNDARIES)}
    assert mode == {".": 0o711, REPLICAS: 0o711, BOUNDARIES: 0o602}
    assert stat.S_IMODE((tmp_path / "run" / "references.jsonl").stat().st_mode) == 0o600


class Probe:
    repository = Path("/repository")

    def __init__(self):
        self.asked, self.handed = None, None

    def hand_over(self, *paths):
        self.handed = paths

    def probe(self, **asked):
        self.asked = asked
        return ["can read /somewhere"]


def test_the_probe_is_asked_to_close_the_records_the_runs_beside_and_what_the_owner_keeps_above(tmp_path):
    owner = tmp_path / "owner"
    runs = owner / "runs"
    root = runs / "run-2"
    (root / AREA).mkdir(parents=True)
    (root / REPLICAS).mkdir()
    (root / BOUNDARIES).write_text("")
    (root / "settings.json").write_text("{}")
    (runs / "run-1").mkdir()
    (owner / "projects").mkdir()
    for folder in (owner, runs):
        folder.chmod(0o711)
    tmp_path.chmod(0o755)
    probe = Probe()
    employee = SimpleNamespace(root=root, area=root / AREA, baseline=SimpleNamespace(workdir=tmp_path / "w"))
    employee.confinement = probe
    assert unsealed(employee, closed=[tmp_path / "scenario"]) == ["can read /somewhere"]
    assert probe.handed == (root / AREA, tmp_path / "w")
    assert probe.asked == {
        "writable": [root / AREA],
        "unlisted": [root, root / REPLICAS, runs, Path(tempfile.gettempdir())],
        "closed": [
            tmp_path / "scenario",
            Path("/repository"),
            root / "settings.json",
            runs / "run-1",
            owner / "projects",
        ],
    }


def test_a_worker_whose_process_cannot_start_is_left_unstarted(tmp_path, monkeypatch):
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "home")
    worker = Worker(
        Baseline(config, RavenConfig(), tmp_path, task=Task(text="Work")),
        tmp_path / "run",
        area=tmp_path / "run" / "employee",
        confinement=confinement(tmp_path),
    )
    monkeypatch.setattr(Confinement, "hand_over", lambda self, *paths: None)
    with pytest.raises(OSError):
        asyncio.run(worker.start())
    assert worker._process is None
    assert stat.S_IMODE((tmp_path / "run").stat().st_mode) == 0o711


def test_only_a_delivered_file_inside_the_workdir_or_the_area_is_kept(tmp_path):
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "run" / "employee" / "home")
    work = tmp_path / "work"
    work.mkdir()
    worker = Worker(
        Baseline(config, RavenConfig(), work, task=Task(text="Work")),
        tmp_path / "run",
        area=tmp_path / "run" / "employee",
    )
    records = tmp_path / "run" / "settings.json"
    records.parent.mkdir(parents=True)
    records.write_text("{}")
    (work / "deck.pptx").write_bytes(b"deck")
    (work / "notes.md").symlink_to(records)
    delivered = ["deck.pptx", "notes.md", str(records)]
    row = {
        "kind": "runner.event",
        "event": {"name": "deliver_files", "phase": "start", "arguments": {"files": [{"path": p} for p in delivered]}},
    }
    kept = worker._keep_deliverables("t1", [row])
    assert [Path(path).name for path in kept] == ["deck.pptx"]
