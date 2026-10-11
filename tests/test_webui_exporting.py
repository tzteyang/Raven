"""Portable Studio employees preserve trained state and share the live API's access boundary."""

import base64
import io
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from experimental.curator.harness import Artifact, Task
from experimental.curator.raven_adapter.deployment import _digest
from experimental.curator.raven_adapter.inspection import fingerprint
from experimental.webui import exporting
from experimental.webui.employee_runtime import prepare_employee
from experimental.webui.live import Live, LiveConfig
from experimental.webui.serve import Handler
from raven.agent.subagent.vendored_agents import discover_product_rows
from tests.test_webui_live import SESSION, write_config


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def write_saved(path, value):
    value = {key: item for key, item in value.items() if key != "sha256"}
    value["sha256"] = _digest(value)
    path.write_text(json.dumps(value))
    return value


@pytest.fixture
def employee(tmp_path):
    config = LiveConfig.load(write_config(tmp_path))
    live = Live(config)
    directory = live.runs / SESSION
    directory.mkdir()
    (directory / "studio.json").write_text(json.dumps({"id": SESSION, "title": "Travel employee"}))
    artifact = Artifact(values={}, files={"notes.md": "A cultivated employee."})
    task = Task(text="Prepare travel quotations.")
    state = {"task_id": task.id, "data": {"learned": "Check every price"}}
    saved = write_saved(
        directory / "deployment.json",
        {
            "artifact": artifact.model_dump(mode="json"),
            "task": task.model_dump(mode="json"),
            "revision": fingerprint(artifact.model_dump(mode="json")),
            "children": {},
            "content": {
                "TOOLS.md": [b64(b"Use the supplied prices."), 0o640],
                "removed.md": [None, 0],
                "private.txt": [b64(b"Saved without permissions"), 0],
            },
            "state": {
                "memory.json": b64(json.dumps(state).encode()),
                "planning.json": b64(b'{"step":3}'),
                "capability.json": None,
            },
            "attribution": {"private_evaluation": "This must not be shipped"},
        },
    )
    uploads = directory / "employee/home/uploads"
    uploads.mkdir(parents=True)
    (uploads / "prices.csv").write_text("Trip,USD\nRail,50\n")
    (directory / "settings.json").write_text(
        json.dumps(
            {
                "models": {"partner": "deepseek/trained-model"},
                "efforts": {"partner": "high"},
            }
        )
    )
    config.config.write_text(
        json.dumps(
            {
                "providers": {
                    "deepseek": {"apiKey": "fake-provider-credential"},
                    "custom": {
                        "apiKey": "fake-custom-credential",
                        "apiBase": "https://provider.example.test/v1",
                        "models": ["deepseek/trained-model"],
                    },
                },
                "tools": {"web": {"search": {"apiKey": "fake-web-credential"}}, "exec": {"env": {"TOKEN": "fake-env"}}},
                "agents": {
                    "defaults": {
                        "workspace": "/private/training/home",
                        "model": "deepseek/base-model",
                        "provider": "deepseek",
                        "reasoningEffort": "low",
                        "apiKey": "fake-extra-credential",
                    }
                },
                "channels": {"slack": {"token": "fake-slack-credential"}},
            }
        )
    )
    return SimpleNamespace(live=live, directory=directory, config=config.config, saved=saved, uploads=uploads)


def unpack(employee, tmp_path):
    package = exporting.build(employee.directory, employee.config)
    with zipfile.ZipFile(io.BytesIO(package.data)) as archive:
        archive.extractall(tmp_path / "agents")
    return tmp_path / "agents" / f"expert-{SESSION}"


def test_zip_is_discoverable_and_only_carries_the_saved_employee(employee, tmp_path):
    folder = unpack(employee, tmp_path)
    package, files = exporting.load_package(folder)
    assert package["options"] == {"model": "deepseek/trained-model", "reasoningEffort": "high"}
    assert files["uploads/prices.csv"] == b"Trip,USD\nRail,50\n"
    assert set(files) == {"deployment.json", "subagent.json", "README.md", "run.py", "uploads/prices.csv"}
    saved = json.loads(files["deployment.json"])
    assert saved["content"] == employee.saved["content"]
    assert saved["state"] == employee.saved["state"] and saved["task"] == employee.saved["task"]
    assert package["source"]["deployment_sha256"] == employee.saved["sha256"]
    text = b"".join(files.values()) + (folder / "package.json").read_bytes()
    for forbidden in (
        b"fake-provider-credential",
        b"fake-web-credential",
        b"fake-env",
        b"fake-extra-credential",
        b"fake-slack-credential",
        b"/private/training/home",
        b"private_evaluation",
    ):
        assert forbidden not in text
    rows = discover_product_rows(root=folder.parent)
    [row] = [row for row in rows if row.name == f"expert-{SESSION}"]
    assert row.enabled and str(folder / "run.py") in row.command
    assert employee.live.summary(SESSION)["exportable"] is True


@pytest.mark.parametrize(
    "field,name",
    [
        ("content", "../outside"),
        ("content", "/outside"),
        ("content", "a/../../outside"),
        ("state", "../outside"),
        ("state", "/outside"),
        ("state", "observations.jsonl"),
    ],
)
def test_saved_paths_cannot_escape_or_add_unowned_state(employee, field, name):
    employee.saved[field][name] = [b64(b"bad"), 0o600] if field == "content" else b64(b"bad")
    write_saved(employee.directory / "deployment.json", employee.saved)
    assert not employee.live.summary(SESSION)["exportable"]
    assert employee.live.export(SESSION)[0] == 409


def test_checksum_children_and_corrupt_state_are_refused(employee):
    original = employee.saved
    for patch in (
        {"sha256": "bad"},
        {"children": {"child": {}}},
        {"state": {"memory.json": "!"}},
        {"content": []},
        {"state": None},
        {"revision": "another-revision"},
    ):
        value = {**original, **patch}
        if "sha256" not in patch:
            value = {key: item for key, item in value.items() if key != "sha256"}
            value["sha256"] = _digest(value)
        (employee.directory / "deployment.json").write_text(json.dumps(value))
        assert employee.live.export(SESSION)[0] == 409


def test_symlinked_material_and_modified_packages_are_refused(employee, tmp_path):
    (employee.uploads / "linked.csv").symlink_to(employee.config)
    assert employee.live.export(SESSION)[0] == 409
    (employee.uploads / "linked.csv").unlink()
    folder = unpack(employee, tmp_path)
    (folder / "uploads/prices.csv").write_text("changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        exporting.load_package(folder)
    (folder / "uploads/prices.csv").unlink()
    (folder / "uploads/prices.csv").symlink_to(employee.uploads / "prices.csv")
    with pytest.raises(ValueError, match="symbolic"):
        exporting.load_package(folder)


def test_runtime_restores_materials_and_checkpoints_only_on_first_start(employee, tmp_path):
    folder = unpack(employee, tmp_path)
    root, home = tmp_path / "runtime", tmp_path / "home"
    home.mkdir()
    (root / "state").mkdir(parents=True)
    (home / "removed.md").write_text("Old content")
    (root / "state/capability.json").write_text('{"old":true}')
    baseline, artifact, state = prepare_employee(folder, host_path=employee.config, root=root, home=home)
    assert baseline.task.id == employee.saved["task"]["id"]
    assert baseline.config.agents.defaults.model == "deepseek/trained-model"
    assert baseline.config.agents.defaults.reasoning_effort == "high"
    assert baseline.config.providers.deepseek.api_key == "fake-provider-credential"
    assert baseline.config.agents.defaults.provider == "deepseek"
    assert baseline.config.get_provider_name() == "deepseek"
    automatic = baseline.config.model_copy(deep=True)
    automatic.agents.defaults.provider = "auto"
    assert automatic.get_provider_name() == "custom"
    assert baseline.hosting == "acp" and not baseline.allow_delegation
    assert artifact.model_dump(mode="json") == employee.saved["artifact"]
    assert (home / "TOOLS.md").read_bytes() == b"Use the supplied prices."
    assert (home / "TOOLS.md").stat().st_mode & 0o777 == 0o640
    assert (home / "private.txt").stat().st_mode & 0o777 == 0
    assert (home / "uploads/prices.csv").read_bytes() == (employee.uploads / "prices.csv").read_bytes()
    assert (root / "work/uploads/prices.csv").is_file()
    assert json.loads((state / "memory.json").read_text())["data"]["learned"] == "Check every price"
    assert json.loads((state / "planning.json").read_text()) == {"step": 3}
    assert not (home / "removed.md").exists() and not (state / "capability.json").exists()
    (state / "memory.json").write_text('{"progress":4}')
    (home / "TOOLS.md").write_text("A later edit")
    (home / "uploads/prices.csv").unlink()
    prepare_employee(folder, host_path=employee.config, root=root, home=home)
    assert json.loads((state / "memory.json").read_text()) == {"progress": 4}
    assert (home / "TOOLS.md").read_text() == "A later edit"
    assert not (home / "uploads/prices.csv").exists()
    assert not list(root.glob("*config*")) and not list(root.glob("*deployment*"))
    (root / ".seeded").write_text("another-package")
    with pytest.raises(ValueError, match="another employee package"):
        prepare_employee(folder, host_path=employee.config, root=root, home=home)


def test_export_refuses_busy_or_stale_live_revisions(employee):
    state = {"step": "curate", "saved": True, "revision": employee.saved["revision"]}
    employee.live.handles[SESSION] = SimpleNamespace(
        lock=threading.RLock(),
        alive=True,
        ask=lambda *args: {"state": state},
        last=state,
    )
    assert employee.live.export(SESSION)[0] == 409
    state["step"] = None
    state["trial"] = {"name": "trial-1"}
    assert employee.live.export(SESSION)[0] == 409
    state["trial"] = None
    state["revision"] = "unsaved-revision"
    assert employee.live.export(SESSION)[0] == 409
    state["revision"] = employee.saved["revision"]
    assert employee.live.export(SESSION)[0] == 200


@pytest.mark.parametrize("operation", ["step", "delete", "resume"])
def test_export_finishes_its_snapshot_before_a_competing_operation(employee, monkeypatch, operation):
    reading, release, attempting, mutated = (threading.Event() for _ in range(4))
    build = exporting.build

    def paused_build(*args, **kwargs):
        reading.set()
        assert release.wait(5)
        return build(*args, **kwargs)

    monkeypatch.setattr(exporting, "build", paused_build)
    if operation == "step":
        lock = threading.RLock()
        state = {"step": None, "saved": True, "revision": employee.saved["revision"]}

        def ask(command, wait):
            with lock:
                if command["op"] != "state":
                    mutated.set()
                return {"ok": True, "state": state}

        employee.live.handles[SESSION] = SimpleNamespace(lock=lock, alive=True, ask=ask, last=state)
        mutate = partial(employee.live.step, SESSION, "trial", {})
    elif operation == "resume":
        (employee.directory / "iteration").mkdir()
        (employee.directory / "iteration/r.json").write_text(json.dumps({"status": "running", "rounds": []}))

        def start(spec):
            mutated.set()
            return SimpleNamespace(is_alive=lambda: False), None

        employee.live.start = start
        mutate = partial(employee.live.resume, SESSION)
    else:
        mutate = partial(employee.live.delete, SESSION)

    def attempted():
        attempting.set()
        result = mutate()
        mutated.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        download = pool.submit(employee.live.export, SESSION)
        assert reading.wait(5)
        mutation = pool.submit(attempted)
        assert attempting.wait(5)
        assert not mutated.wait(0.05)
        release.set()
        assert download.result(timeout=5)[0] == 200
        assert mutation.result(timeout=5)[0] in (200, 202)


def test_package_manifest_paths_are_checked_even_with_a_new_checksum(employee, tmp_path):
    folder = unpack(employee, tmp_path)
    package = json.loads((folder / "package.json").read_text())
    package["files"]["../outside"] = "irrelevant"
    write_saved(folder / "package.json", package)
    with pytest.raises(ValueError, match="relative POSIX"):
        exporting.load_package(folder)


def test_http_download_is_authenticated_and_handles_missing_or_unsaved_sessions(employee):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(
            Handler,
            root=employee.live.runs,
            live=employee.live,
            token="test-access-token",
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/api/studio/live"
    try:
        with pytest.raises(HTTPError) as denied:
            urlopen(f"{base}/{SESSION}/export")
        assert denied.value.code == 401
        headers = {"Cookie": "studio_access=test-access-token"}
        with urlopen(Request(f"{base}/{SESSION}/export", headers=headers)) as response:
            assert response.status == 200 and response.headers["Content-Type"] == "application/zip"
            assert response.headers["Content-Disposition"] == f'attachment; filename="expert-{SESSION}.zip"'
            assert response.headers["Cache-Control"] == "no-store"
            assert zipfile.is_zipfile(io.BytesIO(response.read()))
        for target, expected in (("../outside", 404), ("live-20000101000000-000000", 404)):
            with pytest.raises(HTTPError) as missing:
                urlopen(Request(f"{base}/{target}/export", headers=headers))
            assert missing.value.code == expected
        (employee.directory / "deployment.json").unlink()
        with pytest.raises(HTTPError) as unsaved:
            urlopen(Request(f"{base}/{SESSION}/export", headers=headers))
        assert unsaved.value.code == 409
        assert "error" in json.loads(unsaved.value.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
